#!/usr/bin/env python3
"""修 mi-remote 的 BLE 断开收尾：链路已经掉了也要走 bleak 的 disconnect()。

背景（2026-10-16 排查）：
    ble_client.disconnect() 里写的是

        if client and client.is_connected:
            await asyncio.wait_for(client.disconnect(), timeout=timeout)

    当链路是「掉」的（而不是我们自己主动断的）时候，is_connected 已经是 False，
    于是 bleak 的 disconnect() 根本不会被调用：_cleanup_all() 不跑、D-Bus watcher
    不摘、bus 不关。而 baton-asr-guard 的存在恰恰说明「每次重连会多叠一层音频
    notify 订阅」—— 订阅之所以能跨重连累积，就是因为上一次连接没被真正拆干净。

    改成 `if client is not None:`。对一个已经断掉的 client 再调一次 bleak 的
    disconnect() 是安全的（内部 `if self._bus is None: return`），真出异常也已经
    被下面的 try/except 收住，不会影响后续重连。

幂等：锚点已是新写法就跳过。改前会备份一份 ble_client.py。
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

OLD = """        if client and client.is_connected:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=timeout)"""
NEW = """        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=timeout)"""


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else "0.4.1"
    path = (
        Path.home()
        / f".local/share/mi-remote-linux/versions/{version}"
        / "lib/python3.12/site-packages/mi_remote_linux/ble_client.py"
    )
    if not path.is_file():
        raise SystemExit(f"找不到 {path}")

    text = path.read_text(encoding="utf-8")
    if NEW in text:
        print("ble_client.py 断开收尾已是修复版，跳过")
        return
    if OLD not in text:
        raise SystemExit(f"{path.name}: 找不到补丁锚点，上游可能已变")

    backup = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(path, backup)
    path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"已补丁 {path}")
    print(f"   备份 → {backup.name}")


if __name__ == "__main__":
    main()
