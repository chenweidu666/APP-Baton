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
    d = " ".join(a.argv) if a.type == "command" else str(getattr(a, "key", getattr(a, "value", "")))
    fired.append(f"{a.type}:{d}")


engine = MappingEngine(cfg, run_action, on_layer=layers.append)


def ev(k, d):
    return ButtonEvent(key=k, is_down=d, time_ns=time.monotonic_ns(), code=0, value=int(d))


async def press(k, hold_ms, gap):
    engine.handle(ev(k, True))
    await asyncio.sleep(hold_ms / 1000)
    engine.handle(ev(k, False))
    await asyncio.sleep(gap)


async def main():
    print(f"hold_ms={cfg.settings.hold_ms} double_ms={cfg.settings.double_ms}")
    for title, seq in [
        ("① 短按 TV", [("tv", 60, 0.5)]),
        ("② 双击 TV", [("tv", 60, 0.12), ("tv", 60, 0.6)]),
        ("③ 长按 TV", [("tv", 500, 0.6)]),
    ]:
        fired.clear()
        for k, h, g in seq:
            await press(k, h, g)
        print(f"{title}\n  动作: {fired or '(无)'}  层: {layers[-1] if layers else '-'}")


asyncio.run(main())
