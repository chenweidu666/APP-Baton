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
layers = []


async def run_action(a):
    pass


engine = MappingEngine(cfg, run_action, on_layer=layers.append)


def ev(k, d):
    return ButtonEvent(key=k, is_down=d, time_ns=time.monotonic_ns(), code=0, value=int(d))


async def tap(k, gap):
    engine.handle(ev(k, True))
    await asyncio.sleep(0.05)
    engine.handle(ev(k, False))
    await asyncio.sleep(gap)


async def main():
    # 双击菜单进入层5
    await tap("menu", 0.12)
    await tap("menu", 1.2)
    print("进入后层:", layers)
    # 隔开足够久，再单独短按菜单
    await tap("menu", 0.8)
    print("单独短按菜单后:", layers)
    # 重新进入，用 TV 退出
    await tap("menu", 0.12)
    await tap("menu", 0.22)
    await tap("menu", 1.2)
    print("再次双击后:", layers)
    await tap("tv", 0.8)
    print("短按 TV 后:", layers)


asyncio.run(main())
