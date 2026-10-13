#!/usr/bin/env python3
"""仿真验证：菜单键（轻点/双击）与主页键（双击直达）的行为。不产生真实按键。

做法：用 MappingEngine 灌入合成按键事件，把 run_action / on_layer 换成记录器。
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
        if action.type == "command":
            detail = "命令 " + action.argv[0].split("/")[-1] + " " + " ".join(action.argv[1:])
        else:
            detail = f"{action.type} {getattr(action, 'key', getattr(action, 'value', ''))}"
        fired.append(f"{ms}ms {detail}")

    engine = MappingEngine(config, run_action, on_layer=layers.append)

    def event(key: str, down: bool) -> ButtonEvent:
        return ButtonEvent(
            key=key, is_down=down, time_ns=time.monotonic_ns(), code=0, value=int(down)
        )

    async def tap(key: str, gap: float) -> None:
        engine.handle(event(key, True))
        await asyncio.sleep(0.05)
        engine.handle(event(key, False))
        await asyncio.sleep(gap)

    async def scenario(title: str, keys: list[tuple[str, float]]) -> None:
        nonlocal base
        fired.clear()
        layers.clear()
        base = time.perf_counter()
        for key, gap in keys:
            await tap(key, gap)
        await asyncio.sleep(0.5)
        print(f"{title}")
        print(f"  动作: {fired if fired else '(无)'}")
        print(f"  层变化: {layers if layers else '(无)'}")

    print(f"double_ms={config.settings.double_ms}  hold_ms={config.settings.hold_ms}\n")
    await scenario("① 菜单 轻点一次 → 应发 Ctrl+P（延迟 250ms）", [("menu", 0.4)])
    await scenario("② 菜单 双击 → 应进入启动层 5", [("menu", 0.12), ("menu", 0.4)])
    await scenario("③ 主页 双击 → 应直接启动 OpenCode", [("home", 0.12), ("home", 0.4)])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
