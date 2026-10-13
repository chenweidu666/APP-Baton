#!/usr/bin/env python3
"""行为仿真：验证返回键 单击/双击/长按 三种行为（不产生任何真实按键）。"""

import asyncio
import json
import pathlib
import time

from mi_remote_linux.config import parse_config
from mi_remote_linux.hid_engine import ButtonEvent
from mi_remote_linux.mapping_engine import MappingEngine

CONFIG = pathlib.Path.home() / ".config/mi-remote-linux/mapping.json"


async def main() -> int:
    config = parse_config(json.loads(CONFIG.read_text(encoding="utf-8")))
    fired: list[tuple[float, str, str]] = []
    start = time.perf_counter()

    async def run_action(action) -> None:
        fired.append(
            (
                round((time.perf_counter() - start) * 1000),
                action.type,
                str(getattr(action, "key", getattr(action, "value", ""))),
            )
        )

    engine = MappingEngine(config, run_action)
    print(f"double_ms = {config.settings.double_ms}  hold_ms = {config.settings.hold_ms}")

    def ev(down: bool) -> ButtonEvent:
        return ButtonEvent(
            key="back", is_down=down, time_ns=time.monotonic_ns(), code=158, value=int(down)
        )

    async def press(hold_ms: int) -> None:
        engine.handle(ev(True))
        await asyncio.sleep(hold_ms / 1000)
        engine.handle(ev(False))

    # 场景 1：单击 → 应发 Backspace（因配了 double，会延后 double_ms）
    fired.clear()
    start = time.perf_counter()
    await press(50)
    await asyncio.sleep(0.5)
    print(f"单击   → {fired}")

    # 场景 2：双击（间隔 120ms）→ 应发 Esc，且不发 Backspace
    fired.clear()
    start = time.perf_counter()
    await press(50)
    await asyncio.sleep(0.12)
    await press(50)
    await asyncio.sleep(0.5)
    print(f"双击   → {fired}")

    # 场景 3：长按 500ms → 走项目保护逻辑（只发一次 Backspace，不发 Esc）
    fired.clear()
    start = time.perf_counter()
    await press(500)
    await asyncio.sleep(0.5)
    print(f"长按   → {fired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
