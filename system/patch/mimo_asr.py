"""云端 ASR：地址、模型和 Key 都在同一份 JSON（system/cloud-asr.json，不进 git）。

换厂商只改这一文件。模板见 cloud-asr.json.example。
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

CONFIG_ENV = "MIMO_ASR_CONFIG"
_REPO_DEFAULT = Path(__file__).resolve().parents[1] / "cloud-asr.json"
_last_down_notify = 0.0
NOTIFY_COOLDOWN_SECONDS = 60.0

# --- 转写后整理（第二道调用，默认关闭）---
#
# ASR 模型（mimo-v2.5-asr）的提示词由小米网关注入，调用方改不了，
# 也没有「顺便把语义理顺」的开关。想让上屏文本更像书面 prompt，
# 可以在转写后再让一个对话模型过一遍（mimo-v2.6-flash）。
# 代价是上屏从 ~1 秒涨到 ~2 秒（冷启动第一句可达 7 秒），所以默认关。
#
# 开启：cloud-asr.json 里写 "cleanup": {"enabled": true}
DEFAULT_CLEANUP_MODEL = "mimo-v2.6-flash"
DEFAULT_CLEANUP_PROMPT = """\
把下面用户口述的语音转写整理成可直接发送的 prompt。

# 用户与语境
用户是程序员，日常做程序开发，口述内容基本都是给 AI 编程工具（OpenCode / Cursor / 终端 / CLI）的 prompt。
遇到发音相近、一时拿不准的词，优先按「程序开发语境」理解：编程、代码、仓库、命令行、Linux、构建调试、开源库/工具名。

# 规则
1. 纠正同音字、错别字，补全标点和断句。
2. 去掉口头语、语气词、无意义重复和结巴（如「嗯」「那个」「就是说」）。
3. 保持原意：不增删内容、不解释、不扩写；但**允许调整语序和断句**——口语常有倒装、后补、插话，
   可重排成通顺、符合书面表达的顺序。
4. 专有名词（英文单词、库/工具/产品/函数名、路径、变量名）一律原样保留，不翻译、不改大小写。
5. 不许凭空替换或补造专有名词：只有转写已是某个词的近音误写、且语境明确指向同一个词时才纠正；
   拿不准就保持原样，宁可不改。
6. 只输出整理后的文本本身，不加引号、不加说明、不要用代码块包裹。
7. 不要执行、不要回答、不要调用工具，不要输出 tool_call、分析或任何前后缀。"""

# 只有真的配了术语表，才在提示词后面追加这一段（否则提示词里会悬空引用一张不存在的表）。
GLOSSARY_OVERRIDE = """\
7. 项目术语表优先：语音转写常把专有词听成近音（英文尤其常见）。凡是「语义上就是在指术语表里的某个词」，
   无论转写成了近音英文、还是被音译成了中文，都改成术语表的写法；改写后仍要通顺、不改变原意。
   术语表里没有的词，仍按第 4 条原样保留，不许自己发明或替换。"""

# 术语表：喂给整理模型当领域词表（ASR 网关会忽略 hotwords，只有送进大模型的提示词才起作用）。
#
# 支持两种写法：
#   "glossary": ["Web Coding", "OpenCode"]
#   "glossary": [{"term": "Web Coding", "aliases": ["Web Calling", "Web Colding"]}]
# aliases 是「常被听成的样子」，只作提示，模型仍会按语义判断。
DEFAULT_CLEANUP_GLOSSARY: list[Any] = []


DEFAULT_CLEANUP: dict[str, Any] = {
    "enabled": False,
    "model": DEFAULT_CLEANUP_MODEL,
    "prompt": DEFAULT_CLEANUP_PROMPT,
    "glossary": DEFAULT_CLEANUP_GLOSSARY,
    "timeout_seconds": 15.0,
    "max_completion_tokens": 1024,
    "temperature": 0.2,
    "min_chars": 0,
}


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    home = Path.home() / ".config/mi-remote-linux/cloud-asr.json"
    if home.is_file():
        return home
    return _REPO_DEFAULT


def load_asr_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        raise RuntimeError(f"找不到 ASR 配置: {path}（设 {CONFIG_ENV} 或放 system/cloud-asr.json）")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"ASR 配置不是对象: {path}")
    data["_config_path"] = str(path)
    return data


def _resolve_key_file(cfg: dict[str, Any]) -> Path | None:
    raw = str(cfg.get("key_file") or "").strip()
    env_file = os.environ.get("MIMO_ENV_FILE", "").strip()
    if env_file:
        return Path(env_file).expanduser()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path(cfg["_config_path"]).parent / path).resolve()
    return path


def load_api_key(cfg: dict[str, Any] | None = None) -> str | None:
    for name in ("MIMO_API_KEY", "MIMO_ASR_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if cfg is None:
        try:
            cfg = load_asr_config()
        except RuntimeError:
            cfg = {}
    embedded = str(cfg.get("api_key") or cfg.get("apiKey") or "").strip()
    if embedded:
        return embedded
    key_path = _resolve_key_file(cfg) if cfg else None
    if key_path and key_path.is_file():
        return _read_env_file(key_path)
    return None


def _read_env_file(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    first = text.splitlines()[0].strip()
    if first.startswith("sk-") or first.startswith("tp-") or first.startswith("ttp-"):
        return first
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() in {"MIMO_API_KEY", "MIMO_ASR_API_KEY", "API_KEY"}:
            return value.strip().strip('"').strip("'")
    return None


def pcm_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    audio = np.ascontiguousarray(samples.astype("<i2", copy=False))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    return buf.getvalue()


# --- 语种 ---
#
# mimo-v2.5-asr 是中英双语、支持代码混说（code-switching）的模型；它的
# asr_options.language 只接受单一值 auto / zh / en，官方默认 auto。
# 早前本服务把语种写死 zh，中英混说时英文会被按中文去猜 —— 改成以
# cloud-asr.json 的 language 为准，缺省 auto（自动检测）。
_ASR_LANGUAGES = ("auto", "zh", "en")


def resolve_asr_language(cfg: dict[str, Any], fallback: str | None = None) -> str:
    """决定送给云端的语种；配置优先，缺省 auto。"""
    raw = str(cfg.get("language") or fallback or "auto").strip().lower()
    if raw not in _ASR_LANGUAGES:
        logger.warning("language=%r 不受支持（仅 auto/zh/en），改用 auto", raw)
        return "auto"
    return raw


# --- 送云端前的 RMS 归一化（AGC）---
#
# 遥控麦电平很不稳（实测 RMS 1.1e4–2.2e4，即 -9～-3 dBFS），同一句话的
# 绝对电平随远近/音量变化，模型体感时好时坏。这里把每句话归一到统一
# 的 RMS 目标，并用峰值上限保证不会再顶到 0 dBFS。
#
# 注意：ADPCM 解码器里的预测器钳位（遥控器端偏热）在主机侧无法复原，
# 归一化能保证「送出去的信号电平一致、不削顶」，但不能还原已经削掉的波形。
_DEFAULT_NORMALIZE: dict[str, Any] = {
    "enabled": True,
    "target_rms_dbfs": -16.0,   # 目标 RMS（0 dBFS = 32768）
    "peak_ceiling_dbfs": -2.0,  # 峰值上限
    "max_gain_db": 15.0,
    "min_gain_db": -12.0,
    "min_input_rms": 60.0,      # 低于此 RMS（≈-55 dBFS）视为静音，不放大
}
_FULL_SCALE = 32768.0


def _amp_from_dbfs(db: float) -> float:
    return 10.0 ** (db / 20.0)


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    settings = dict(_DEFAULT_NORMALIZE)
    raw = cfg.get("normalize")
    if raw is False:
        settings["enabled"] = False
        return settings
    if not isinstance(raw, dict):
        return settings
    if "enabled" in raw:
        settings["enabled"] = bool(raw["enabled"])
    for name in (
        "target_rms_dbfs",
        "peak_ceiling_dbfs",
        "max_gain_db",
        "min_gain_db",
        "min_input_rms",
    ):
        value = raw.get(name)
        if value is None:
            continue
        try:
            settings[name] = float(value)
        except (TypeError, ValueError):
            logger.warning("normalize.%s 取值无效，用默认值 %r", name, _DEFAULT_NORMALIZE[name])
    return settings


def normalize_pcm(
    samples: np.ndarray,
    cfg: dict[str, Any],
    sample_rate: int = 16000,
) -> np.ndarray:
    """把整句话的 RMS 归一到目标电平，并保证峰值不超上限。"""
    settings = normalize_config(cfg)
    if not settings["enabled"] or samples is None or len(samples) == 0:
        return samples

    x = samples.astype(np.float64, copy=False)
    rms = float(np.sqrt(np.mean(x * x)))
    peak = float(np.max(np.abs(x)))
    if peak <= 0:
        return samples
    if rms < settings["min_input_rms"]:
        logger.info("归一化跳过：RMS %.0f 低于底噪门限 %.0f", rms, settings["min_input_rms"])
        return samples

    gain = _amp_from_dbfs(settings["target_rms_dbfs"]) * _FULL_SCALE / rms
    gain = min(
        max(gain, _amp_from_dbfs(settings["min_gain_db"])),
        _amp_from_dbfs(settings["max_gain_db"]),
    )

    # 峰值上限只用于压住个别尖峰（点击/瞬态），不因此把整句拉低 ——
    # 早期实现用"整句缩放"满足峰值上限，一个尖峰就能把整句压低十几 dB。
    ceiling = _amp_from_dbfs(settings["peak_ceiling_dbfs"]) * _FULL_SCALE
    y = np.clip(x * gain, -ceiling, ceiling).astype("<i2")
    limited = int(np.count_nonzero(np.abs(x * gain) > ceiling))
    yf = y.astype(np.float64)
    logger.info(
        "音频归一化：%.1f dB（RMS %.0f→%.0f，峰值 %.0f→%.0f，压峰 %d 样本）",
        20.0 * np.log10(gain),
        rms,
        float(np.sqrt(np.mean(yf * yf))),
        peak,
        float(np.max(np.abs(yf))),
        limited,
    )
    return y


def parse_glossary(raw: Any) -> list[tuple[str, list[str]]]:
    """把 cleanup.glossary 归一成 [(term, aliases), ...]，非法项跳过。"""
    entries: list[tuple[str, list[str]]] = []
    if not isinstance(raw, list):
        return entries
    for item in raw:
        term: Any = None
        aliases: Any = None
        if isinstance(item, str):
            term = item
        elif isinstance(item, dict):
            term = item.get("term")
            aliases = item.get("aliases")
        else:
            continue
        if not isinstance(term, str) or not term.strip():
            logger.warning("cleanup.glossary 项缺少 term，跳过: %r", item)
            continue
        alias_list: list[str] = []
        if isinstance(aliases, list):
            alias_list = [a.strip() for a in aliases if isinstance(a, str) and a.strip()]
        elif isinstance(aliases, str) and aliases.strip():
            alias_list = [aliases.strip()]
        entries.append((term.strip(), alias_list))
    return entries


def glossary_block(entries: list[tuple[str, list[str]]]) -> str:
    """把术语表渲染成提示词里的一段；空表返回空串。"""
    if not entries:
        return ""
    lines = ["# 项目术语表（专有词按此写法输出）"]
    for term, aliases in entries:
        if aliases:
            lines.append(f"- {term}（语音常听成：{'、'.join(aliases)}）")
        else:
            lines.append(f"- {term}")
    return "\n".join(lines)


def cleanup_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """读 cloud-asr.json 的 cleanup 段；缺省即默认关闭。"""
    settings = dict(DEFAULT_CLEANUP)
    raw = cfg.get("cleanup")
    if raw is False:
        settings["enabled"] = False
        return settings
    if not isinstance(raw, dict):
        return settings
    if "enabled" in raw:
        settings["enabled"] = bool(raw["enabled"])
    for name in ("model", "prompt"):
        value = raw.get(name)
        if isinstance(value, str) and value.strip():
            settings[name] = value.strip()
    if "glossary" in raw:
        settings["glossary"] = parse_glossary(raw["glossary"])
    else:
        settings["glossary"] = parse_glossary(DEFAULT_CLEANUP["glossary"])
    for name in ("timeout_seconds", "max_completion_tokens", "temperature", "min_chars"):
        value = raw.get(name)
        if value is None:
            continue
        try:
            settings[name] = type(DEFAULT_CLEANUP[name])(value)
        except (TypeError, ValueError):
            logger.warning("cleanup.%s 取值无效，用默认值 %r", name, DEFAULT_CLEANUP[name])
    return settings


_LEADING_LABELS = ("整理后的文本：", "整理后：", "整理：", "结果：", "输出：", "转写：")
_QUOTE_PAIRS = (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"))
_REFUSAL_STARTS = ("抱歉", "对不起", "无法", "我不能", "i cannot", "i'm sorry", "i am sorry")
# 模型有时会把转写内容当成任务去执行，吐工具调用——这种绝对不能上屏。
_AGENT_MARKERS = ("<tool_call", "</tool_call", "<function=", "<parameter=", "<|tool", "<|endoftext")
# 长度守卫：只挡「整段被吞」和「凭空扩写」，不挡正常的去口水词。
# 短句本身字少，去完口头语就能砍掉一大半，所以下限放宽。
_SHORT_INPUT_CHARS = 24
_MIN_KEEP_LONG = 0.4
_MIN_KEEP_SHORT = 0.2
_MAX_GROWTH = 2.2


def _sanitize_cleanup(raw: Any, original: str) -> str | None:
    """把模型输出收拾成可上屏的纯文本；不可信就返回 None（调用方保留原文）。"""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.startswith("```"):
        head = text.find("\n")
        text = text[head + 1 :] if head != -1 else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    for label in _LEADING_LABELS:
        if text.startswith(label):
            text = text[len(label) :].strip()
            break
    for left, right in _QUOTE_PAIRS:
        if len(text) >= 2 and text.startswith(left) and text.endswith(right):
            text = text[1:-1].strip()
            break
    if not text:
        return None
    lowered = text.lower()
    if any(marker in lowered for marker in _AGENT_MARKERS):
        logger.warning("整理结果像工具调用，保留原文")
        return None
    if len(text) < 120 and text.lower().startswith(_REFUSAL_STARTS):
        logger.warning("整理结果像拒答，保留原文")
        return None
    ratio = len(text) / max(len(original), 1)
    floor = _MIN_KEEP_LONG if len(original) >= _SHORT_INPUT_CHARS else _MIN_KEEP_SHORT
    if ratio < floor or ratio > _MAX_GROWTH:
        logger.warning("整理长度异常（%d → %d 字），保留原文", len(original), len(text))
        return None
    return text


def cleanup_transcript(
    text: str,
    cfg: dict[str, Any],
    key: str | None = None,
    timeout: float | None = None,
) -> str | None:
    """转写后整理。任何失败都返回 None——绝不因为整理失败而丢字。"""
    settings = cleanup_config(cfg)
    if not settings["enabled"]:
        return None
    if len(text) < settings["min_chars"]:
        return None
    base = str(cfg.get("base_url") or "").rstrip("/")
    if not base:
        return None
    if key is None:
        key = load_api_key(cfg)
    if not key:
        return None

    glossary = glossary_block(settings.get("glossary") or [])
    system_prompt = settings["prompt"]
    if glossary:
        system_prompt = f"{system_prompt}\n{GLOSSARY_OVERRIDE}\n\n{glossary}"

    payload = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": settings["temperature"],
        "max_completion_tokens": settings["max_completion_tokens"],
        "thinking": {"type": "disabled"},
    }
    wait = float(timeout if timeout is not None else settings["timeout_seconds"])
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=wait) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("整理失败（%s），直接用转写原文", exc)
        return None
    choices = data.get("choices") or []
    if not choices:
        logger.warning("整理无结果，直接用转写原文")
        return None
    cleaned = _sanitize_cleanup((choices[0].get("message") or {}).get("content"), text)
    if cleaned is None:
        return None
    logger.info(
        "整理 %s 用时 %.2fs（%d → %d 字）",
        settings["model"],
        time.monotonic() - started,
        len(text),
        len(cleaned),
    )
    return cleaned


def transcribe_pcm(
    samples: np.ndarray,
    sample_rate: int = 16000,
    language: str | None = None,
    timeout: float | None = None,
) -> str:
    cfg = load_asr_config()
    key = load_api_key(cfg)
    if not key:
        notify_asr_down("缺少 api_key")
        raise RuntimeError("未配置 api_key（写在 cloud-asr.json 里，该文件不进 git）")

    import base64

    samples = normalize_pcm(samples, cfg, sample_rate)
    wav = pcm_to_wav_bytes(samples, sample_rate)
    asr_language = resolve_asr_language(cfg, language)
    model = str(cfg.get("model") or "").strip()
    base = str(cfg.get("base_url") or "").rstrip("/")
    if not model or not base:
        raise RuntimeError("cloud-asr.json 需要 base_url 和 model")
    wait = float(timeout if timeout is not None else cfg.get("timeout_seconds") or 20)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": "data:audio/wav;base64," + base64.b64encode(wav).decode("ascii")
                        },
                    }
                ],
            }
        ],
        "asr_options": {"language": asr_language},
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    logger.info(
        "云端 ASR %s / %s（%d 字节 wav）",
        cfg.get("provider") or base,
        model,
        len(wav),
    )
    try:
        with urllib.request.urlopen(request, timeout=wait) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        reason = f"HTTP {exc.code}"
        notify_asr_down(reason)
        raise RuntimeError(f"云端 ASR {reason}: {detail}") from exc
    except urllib.error.URLError as exc:
        reason = "网络超时或连不上"
        notify_asr_down(reason)
        raise RuntimeError(f"云端 ASR {reason}: {exc}") from exc

    data = json.loads(raw)
    if data.get("error"):
        reason = "接口返回错误"
        notify_asr_down(reason)
        raise RuntimeError(str(data["error"]))
    choices = data.get("choices") or []
    if not choices:
        notify_asr_down("无识别结果")
        raise RuntimeError("云端 ASR 无 choices")
    text = str((choices[0].get("message") or {}).get("content") or "").strip()
    if not text:
        notify_asr_down("空文本")
        raise RuntimeError("云端 ASR 空文本")
    logger.info("云端 ASR 转写结果: %s", text)
    cleaned = cleanup_transcript(text, cfg, key)
    if cleaned:
        logger.info("整理后: %s", cleaned)
        return cleaned
    return text


def notify_asr_down(reason: str) -> None:
    """桌面通知：云端挂了。60 秒内最多一条，避免刷屏。"""
    global _last_down_notify
    now = time.monotonic()
    if now - _last_down_notify < NOTIFY_COOLDOWN_SECONDS:
        return
    _last_down_notify = now
    logger.error("云端 ASR 不可用: %s", reason)
    try:
        subprocess.run(
            [
                "notify-send",
                "-a",
                "Baton Mi",
                "-u",
                "critical",
                "-t",
                "8000",
                "小米语音识别挂了",
                reason[:160],
            ],
            check=False,
            timeout=3,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def probe_health(*, notify: bool = False) -> bool:
    """探测 GET {base_url}/models，确认配置的 model 在列表里。不打印 Key。"""
    try:
        cfg = load_asr_config()
        key = load_api_key(cfg)
        base = str(cfg.get("base_url") or "").rstrip("/")
        model = str(cfg.get("model") or "").strip()
        if not key or not base:
            if notify:
                notify_asr_down("缺少 api_key 或 base_url")
            print("FAIL: 配置不完整", flush=True)
            return False
        request = urllib.request.Request(
            f"{base}/models",
            headers={
                "Authorization": f"Bearer {key}",
                "api-key": key,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            status = response.status
        data = json.loads(body)
        ids = [item.get("id") for item in data.get("data") or []]
        ok = status == 200 and (not model or model in ids)
        print(
            f"{'OK' if ok else 'FAIL'} HTTP {status} provider={cfg.get('provider')} "
            f"model={model} listed={model in ids}",
            flush=True,
        )
        if not ok and notify:
            notify_asr_down(f"探测失败 HTTP {status}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", flush=True)
        if notify:
            notify_asr_down("探测失败（连不上）")
        return False
