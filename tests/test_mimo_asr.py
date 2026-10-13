"""MiMo ASR 辅助：WAV 封装与 Key 读取（不打真实网络、不打印 Key）。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "system/patch"))

from mimo_asr import (  # noqa: E402
    DEFAULT_CLEANUP_MODEL,
    _read_env_file,
    _sanitize_cleanup,
    cleanup_config,
    glossary_block,
    load_api_key,
    load_asr_config,
    parse_glossary,
    pcm_to_wav_bytes,
)


class MimoAsrGlossaryTest(unittest.TestCase):
    def test_plain_string_list(self) -> None:
        self.assertEqual(parse_glossary(["Web Coding"]), [("Web Coding", [])])

    def test_dict_with_aliases(self) -> None:
        raw = [{"term": "Vibe Coding", "aliases": ["Web God", "Web Calling"]}]
        self.assertEqual(
            parse_glossary(raw), [("Vibe Coding", ["Web God", "Web Calling"])]
        )

    def test_alias_may_be_single_string(self) -> None:
        self.assertEqual(parse_glossary([{"term": "A", "aliases": "B"}]), [("A", ["B"])])

    def test_skips_invalid_entries(self) -> None:
        raw = [123, {"aliases": ["x"]}, {"term": "  "}, None, "OK"]
        self.assertEqual(parse_glossary(raw), [("OK", [])])

    def test_non_list_is_empty(self) -> None:
        self.assertEqual(parse_glossary(None), [])
        self.assertEqual(parse_glossary({"term": "A"}), [])

    def test_block_empty(self) -> None:
        self.assertEqual(glossary_block([]), "")

    def test_block_renders_term_and_aliases(self) -> None:
        block = glossary_block([("Vibe Coding", ["Web God"]), ("OpenCode", [])])
        self.assertIn("Vibe Coding", block)
        self.assertIn("Web God", block)
        self.assertIn("OpenCode", block)

    def test_config_reads_glossary(self) -> None:
        cfg = cleanup_config({"cleanup": {"enabled": True, "glossary": ["Vibe Coding"]}})
        self.assertEqual(cfg["glossary"], [("Vibe Coding", [])])

    def test_config_without_glossary_is_empty(self) -> None:
        self.assertEqual(cleanup_config({"cleanup": {"enabled": True}})["glossary"], [])

    def test_base_prompt_has_no_dangling_glossary_reference(self) -> None:
        # 没配术语表时，提示词里不该出现「术语表」，否则是悬空引用。
        cfg = cleanup_config({"cleanup": {"enabled": True}})
        self.assertNotIn("术语表", cfg["prompt"])


class MimoAsrCleanupConfigTest(unittest.TestCase):
    def test_defaults_to_disabled(self) -> None:
        cfg = cleanup_config({})
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["model"], DEFAULT_CLEANUP_MODEL)

    def test_enabled_by_flag(self) -> None:
        self.assertTrue(cleanup_config({"cleanup": {"enabled": True}})["enabled"])

    def test_false_disables(self) -> None:
        self.assertFalse(cleanup_config({"cleanup": False})["enabled"])

    def test_dict_overrides(self) -> None:
        cfg = cleanup_config({"cleanup": {"enabled": False, "model": "mimo-v2.5", "min_chars": 10}})
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["model"], "mimo-v2.5")
        self.assertEqual(cfg["min_chars"], 10)

    def test_blank_strings_are_ignored(self) -> None:
        cfg = cleanup_config({"cleanup": {"model": "   ", "prompt": ""}})
        self.assertEqual(cfg["model"], DEFAULT_CLEANUP_MODEL)
        self.assertTrue(cfg["prompt"])

    def test_bad_numbers_fall_back(self) -> None:
        cfg = cleanup_config({"cleanup": {"temperature": "hot", "timeout_seconds": None}})
        self.assertEqual(cfg["temperature"], 0.2)
        self.assertEqual(cfg["timeout_seconds"], 15.0)


class MimoAsrCleanupSanitizeTest(unittest.TestCase):
    ORIGINAL = "嗯那个 帮我看一下 这个 web socket 的 连接 为什么 老是 断啊 你帮 我 改 一下"

    def test_strips_code_fence(self) -> None:
        raw = "```\n帮我看一下这个 WebSocket 的连接为什么老是断，你帮我改一下。\n```"
        self.assertEqual(
            _sanitize_cleanup(raw, self.ORIGINAL),
            "帮我看一下这个 WebSocket 的连接为什么老是断，你帮我改一下。",
        )

    def test_strips_label_and_quotes(self) -> None:
        raw = "整理后：“帮我看一下这个 WebSocket 的连接为什么老是断，你帮我改一下。”"
        self.assertEqual(
            _sanitize_cleanup(raw, self.ORIGINAL),
            "帮我看一下这个 WebSocket 的连接为什么老是断，你帮我改一下。",
        )

    def test_rejects_empty_and_non_string(self) -> None:
        self.assertIsNone(_sanitize_cleanup("   ", self.ORIGINAL))
        self.assertIsNone(_sanitize_cleanup(None, self.ORIGINAL))
        self.assertIsNone(_sanitize_cleanup(["x"], self.ORIGINAL))

    def test_rejects_refusal(self) -> None:
        self.assertIsNone(_sanitize_cleanup("抱歉，我无法整理这段内容。", self.ORIGINAL))

    def test_rejects_too_short(self) -> None:
        original = "帮我把 app 下面的 web socket 连接重连逻辑全部检查一遍然后修好谢谢" * 2
        self.assertIsNone(_sanitize_cleanup("改好了", original))

    def test_rejects_runaway_length(self) -> None:
        self.assertIsNone(_sanitize_cleanup("解释" * 200, self.ORIGINAL))

    def test_short_input_may_compress_a_lot(self) -> None:
        # 短句里全是口头语时，去完剩下几个字是正常的，不能拦。
        original = "嗯，那个，就是，测试一下，测试一下。"
        self.assertEqual(_sanitize_cleanup("测试一下。", original), "测试一下。")

    def test_short_input_still_rejects_catastrophic_shrink(self) -> None:
        original = "嗯，那个，就是，测试一下，测试一下。"
        self.assertIsNone(_sanitize_cleanup("嗯", original))

    def test_rejects_tool_call_output(self) -> None:
        raw = "我来帮你排查 WebSocket 断连的问题。<tool_call><function=search_files>"
        self.assertIsNone(_sanitize_cleanup(raw, self.ORIGINAL))

    def test_accepts_normal_text(self) -> None:
        raw = "帮我看一下这个 WebSocket 的连接为什么老是断，你帮我改一下。"
        self.assertEqual(_sanitize_cleanup(raw, self.ORIGINAL), raw)


class MimoAsrHelpersTest(unittest.TestCase):
    def test_pcm_to_wav_header(self) -> None:
        samples = np.array([0, 1000, -1000, 0], dtype=np.int16)
        blob = pcm_to_wav_bytes(samples, 16000)
        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            handle.write(blob)
            handle.flush()
            with wave.open(handle.name, "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getnframes(), 4)

    def test_read_bare_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("sk-unittest-not-real\n", encoding="utf-8")
            self.assertEqual(_read_env_file(path), "sk-unittest-not-real")

    def test_read_named_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mimo.env"
            path.write_text("MIMO_API_KEY=sk-named\n", encoding="utf-8")
            self.assertEqual(_read_env_file(path), "sk-named")

    def test_accept_token_plan(self) -> None:
        os.environ["MIMO_API_KEY"] = "tp-unittest-not-real"
        try:
            self.assertEqual(load_api_key(), "tp-unittest-not-real")
        finally:
            os.environ.pop("MIMO_API_KEY", None)

    def test_load_asr_config_and_key_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg_path = tmp_path / "cloud-asr.json"
            cfg_path.write_text(
                '{"provider":"test","base_url":"https://example.invalid/v1",'
                '"model":"demo-asr","api_key":"tp-from-json"}',
                encoding="utf-8",
            )
            os.environ.pop("MIMO_API_KEY", None)
            os.environ.pop("MIMO_ASR_API_KEY", None)
            os.environ.pop("MIMO_ENV_FILE", None)
            os.environ["MIMO_ASR_CONFIG"] = str(cfg_path)
            try:
                cfg = load_asr_config()
                self.assertEqual(cfg["model"], "demo-asr")
                self.assertEqual(load_api_key(cfg), "tp-from-json")
            finally:
                os.environ.pop("MIMO_ASR_CONFIG", None)


if __name__ == "__main__":
    unittest.main()
