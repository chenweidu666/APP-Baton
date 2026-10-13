#!/usr/bin/env python3
"""把 mimo-asr 引擎补进已安装的 mi-remote voice.py / main.py。幂等。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOICE_ENGINE_OLD = """        if engine not in {
            "auto",
            "faster-whisper",
            "sherpa-paraformer",
            "voxtype-paraformer",
        }:"""
VOICE_ENGINE_NEW = """        if engine not in {
            "auto",
            "faster-whisper",
            "sherpa-paraformer",
            "voxtype-paraformer",
            "mimo-asr",
        }:"""

LOAD_OLD = '''    def load_model(self) -> bool:
        """检查/加载所选模型；可在线程中预热 Whisper。"""
        if self.active_engine == "sherpa-paraformer":'''
LOAD_NEW = '''    def load_model(self) -> bool:
        """检查/加载所选模型；可在线程中预热 Whisper。"""
        if self.active_engine == "mimo-asr":
            return True
        if self.active_engine == "sherpa-paraformer":'''

TRANSCRIBE_OLD = """        prepared = self._prepare_for_recognition(samples)
        if prepared is None:
            return None

        if not self.load_model():
            return None
"""
TRANSCRIBE_NEW = """        prepared = self._prepare_for_recognition(samples)
        if prepared is None:
            return None

        if self.active_engine == "mimo-asr":
            return self._transcribe_mimo_or_fallback(prepared)

        if not self.load_model():
            return None
"""

METHODS = '''
    def _transcribe_mimo_or_fallback(self, prepared):
        """只走小米云端，避免加载 Paraformer/Whisper 占内存。

        恢复本地回退时：取消下面 sherpa 段注释，并把服务改回带
        --paraformer-model-dir。
        """
        try:
            from . import mimo_asr

            text = mimo_asr.transcribe_pcm(prepared, self.sample_rate, self.language)
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            logger.error("MiMo ASR 失败（未加载本地模型）: %s", exc)
            return None
        logger.error("MiMo ASR 空结果（未加载本地模型）")
        return None
        # --- 本地回退（默认关闭，减少内存）---
        # logger.warning("MiMo ASR 失败，回退本地 Paraformer")
        # if self._paraformer_files_ready() and find_spec("sherpa_onnx") is not None:
        #     previous = self.active_engine
        #     self.active_engine = "sherpa-paraformer"
        #     try:
        #         if self.load_model():
        #             return self._transcribe_sherpa(prepared)
        #     finally:
        #         self.active_engine = previous
        # logger.error("MiMo ASR 失败且本地 Paraformer 不可用")
        # return None

'''

METHODS_OLD_FALLBACK = """    def _transcribe_mimo_or_fallback(self, prepared):
        try:
            from . import mimo_asr

            text = mimo_asr.transcribe_pcm(prepared, self.sample_rate, self.language)
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("MiMo ASR 失败，回退本地 Paraformer: %s", exc)
        if self._paraformer_files_ready() and find_spec("sherpa_onnx") is not None:
            previous = self.active_engine
            self.active_engine = "sherpa-paraformer"
            try:
                if self.load_model():
                    return self._transcribe_sherpa(prepared)
            finally:
                self.active_engine = previous
        logger.error("MiMo ASR 失败且本地 Paraformer 不可用")
        return None
"""

MAIN_OLD = """        choices=["auto", "faster-whisper", "sherpa-paraformer", "voxtype-paraformer"],
        default="auto",
        help="转写引擎；auto 优先常驻 Sherpa-ONNX Paraformer（默认: auto）","""
MAIN_NEW = """        choices=["auto", "faster-whisper", "sherpa-paraformer", "voxtype-paraformer", "mimo-asr"],
        default="auto",
        help="转写引擎；auto 优先常驻 Sherpa-ONNX Paraformer；mimo-asr 为小米云端（默认: auto）","""


def patch_text(path: Path, replacements: list[tuple[str, str]]) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in replacements:
        if new.strip() in text and old not in text:
            continue
        if old not in text:
            if new[:80] in text:
                continue
            raise SystemExit(f"{path.name}: 找不到补丁锚点，上游可能已变")
        text = text.replace(old, new, 1)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else "0.4.1"
    pkg = (
        Path.home()
        / f".local/share/mi-remote-linux/versions/{version}/lib/python3.12/site-packages/mi_remote_linux"
    )
    if not pkg.is_dir():
        raise SystemExit(f"找不到 {pkg}")

    shutil.copy2(ROOT / "mimo_asr.py", pkg / "mimo_asr.py")
    voice = pkg / "voice.py"
    main_py = pkg / "main.py"

    changed = False
    voice_text = voice.read_text(encoding="utf-8")
    if METHODS_OLD_FALLBACK in voice_text:
        voice.write_text(
            voice_text.replace(METHODS_OLD_FALLBACK, METHODS.strip("\n") + "\n", 1),
            encoding="utf-8",
        )
        changed = True
        print(f"已关闭本地回退 {voice}")
    elif METHODS.strip() not in voice_text:
        if "def save_wav(" not in voice_text:
            raise SystemExit("voice.py 无 save_wav")
        voice_text = voice_text.replace(VOICE_ENGINE_OLD, VOICE_ENGINE_NEW, 1)
        voice_text = voice_text.replace(LOAD_OLD, LOAD_NEW, 1)
        voice_text = voice_text.replace(TRANSCRIBE_OLD, TRANSCRIBE_NEW, 1)
        marker = "    def save_wav("
        voice_text = voice_text.replace(marker, METHODS + marker, 1)
        voice.write_text(voice_text, encoding="utf-8")
        changed = True
        print(f"已补丁 {voice}")
    else:
        print("voice.py 已是云端-only mimo-asr，跳过逻辑补丁")

    if patch_text(main_py, [(MAIN_OLD, MAIN_NEW)]):
        changed = True
        print(f"已补丁 {main_py}")
    else:
        print("main.py 已含 mimo-asr，跳过")

    print("mimo_asr.py 已安装" if not changed else "补丁完成")


if __name__ == "__main__":
    main()
