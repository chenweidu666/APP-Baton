#!/usr/bin/env python3
"""用 mi-remote 自己的 action_runner 做端到端注入测试。

验证链路：mi-remote 动作引擎 → ydotool(垫片) → uinput → GNOME
用音量键作为可观测结果（XF86AudioRaiseVolume / LowerVolume）。
"""

import asyncio
import sys

from mi_remote_linux.action_runner import LinuxActionRunner


async def main() -> int:
    runner = LinuxActionRunner(session="wayland")
    print(f"session        = {runner.session}")
    print(f"wtype          = {runner.wtype}")
    print(f"ydotool        = {runner.ydotool}")
    print(f"缺失依赖       = {runner.missing_dependencies()}")
    print(f"支持鼠标       = {runner.supports_mouse}")

    checks = [
        ("音量＋（音媒体键注入）", lambda: runner.key_stroke("XF86AudioRaiseVolume")),
        ("音量－（回收）", lambda: runner.key_stroke("XF86AudioLowerVolume")),
        ("Ctrl+X（leader 宏第一步）", lambda: runner.key_stroke("x", ("ctrl",))),
        ("字母 n（leader 宏第二步）", lambda: runner.key_stroke("n")),
        ("Esc（中断）", lambda: runner.key_stroke("escape")),
        ("PageUp（对话翻页）", lambda: runner.key_stroke("page_up")),
        ("EntER（提交）", lambda: runner.key_stroke("return")),
    ]
    failures = 0
    for label, action in checks:
        try:
            await action()
            print(f"  ✓ {label}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ✗ {label}: {exc}")
    print(f"\n结果：{len(checks) - failures}/{len(checks)} 通过")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
