import asyncio
import json
import pathlib
import time

from mi_remote_linux.config import parse_config
from mi_remote_linux.hid_engine import ButtonEvent
from mi_remote_linux.mapping_engine import MappingEngine

cfg = parse_config(
    json.loads((pathlib.Path.home() / ".config/mi-remote-linux/mapping.json").read_text())
)
fired, layers = [], []


async def run_action(a):
    fired.append(a.type + " " + str(getattr(a, "key", getattr(a, "value", ""))))


engine = MappingEngine(cfg, run_action, on_layer=layers.append)


def ev(k, d):
    return ButtonEvent(key=k, is_down=d, time_ns=time.monotonic_ns(), code=0, value=int(d))


async def tap(k, gap=0.4):
    engine.handle(ev(k, True))
    await asyncio.sleep(0.05)
    engine.handle(ev(k, False))
    await asyncio.sleep(gap)


async def step(desc, keys, gap=0.4):
    fired.clear()
    for k in keys:
        await tap(k, gap)
    print(f"{desc}\n  动作: {fired or '(无)'}  层: {layers[-1] if layers else '-'}  记录: {layers}")


async def main():
    await step("① TV 短按 → 应进入启动层 5", ["tv"])
    await step("② 启动层内 OK → 应启动 OpenCode", ["ok"])
    await step("③ 启动层内 TV → 应退出", ["tv"])
    await step("④ 基础层 OK/方向/返回双击", ["ok", "up", "back", "back"], gap=0.12)


asyncio.run(main())
