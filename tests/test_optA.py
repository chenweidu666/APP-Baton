#!/usr/bin/env python3
"""仿真验证方案 A：层内"返回"发 Esc 且不退出层；只有 TV / 菜单 才退出层。

用 MappingEngine 灌合成事件，不产生真实按键。
"""

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
    fired: list[str] = []
    layers: list[int] = []
    base = time.perf_counter()

    async def run_action(action) -> None:
        ms = round((time.perf_counter() - base) * 1000)
        detail = (
            "命令 " + action.argv[0].split("/")[-1]
            if action.type == "command"
            else f"{action.type} {getattr(action, 'key', getattr(action, 'value', ''))}"
        )
        fired.append(f"{ms}ms {detail}")

    engine = MappingEngine(config, run_action, on_layer=layers.append)

    def ev(key: str, down: bool) -> ButtonEvent:
        return ButtonEvent(
            key=key, is_down=down, time_ns=time.monotonic_ns(), code=0, value=int(down)
        )

    async def tap(key: str, gap: float = 0.4) -> None:
        engine.handle(ev(key, True))
        await asyncio.sleep(0.05)
        engine.handle(ev(key, False))
        await asyncio.sleep(gap)

    async def step(desc: str, keys: list[str], gap: float = 0.4) -> None:
        fired.clear()
        before = layers[-1] if layers else -1
        for key in keys:
            await tap(key, gap)
        after = layers[-1] if layers else -1
        print(
            f"{desc}\n  动作: {fired if fired else '(无)'}\n  层: {before} → {after} (变化记录 {layers})"
        )

    print(f"double_ms={config.settings.double_ms} hold_ms={config.settings.hold_ms}\n")

    await step("① 双击菜单 → 进入启动层", ["menu", "menu"], gap=0.12)
    await step("② 层内按一次返回 → 应发 Esc，且仍在层 5", ["back"])
    await step("③ 层内再按一次返回 → 同上，层不变", ["back"])
    await step("④ 层内按 TV → 退出层", ["tv"])
    await step("⑤ 再双击菜单进入，然后按菜单短按 → 退出层", ["menu", "menu", "menu"], gap=0.12)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
