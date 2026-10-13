#!/usr/bin/env python3
"""依据 system/mapping.json 生成键位图（SVG + PNG）。

- 遥控器示意 + 键位说明表，全部矢量绘制
- 键位改了重新跑一次即可；标签文案与托盘菜单「键位速查」保持一致

用法:
    python3 tools/gen-keymap-image.py [映射文件] [输出目录]
默认: system/mapping.json → docs/images/
依赖: cairosvg（pip install cairosvg），中文字体（如 文泉驿微米黑 / Noto Sans CJK）
"""

from __future__ import annotations

import json
import pathlib
import sys

FONT = "'Noto Sans CJK SC','WenQuanYi Micro Hei','Source Han Sans SC',sans-serif"

KEY_LABELS = [
    ("power", "电源"),
    ("voice", "语音"),
    ("up", "上"),
    ("down", "下"),
    ("left", "左"),
    ("right", "右"),
    ("ok", "OK"),
    ("back", "返回"),
    ("home", "主页"),
    ("menu", "菜单"),
    ("tv", "TV"),
    ("vol_up", "音量＋"),
    ("vol_down", "音量－"),
]

# 动作 → 中文短标签
KEY_NAMES = {
    "backspace": "删除一个",
    "escape": "Esc",
    "return": "Enter",
    "page_up": "PageUp",
    "page_down": "PageDown",
    "up_arrow": "↑",
    "down_arrow": "↓",
    "left_arrow": "←",
    "right_arrow": "→",
    "tab": "Tab",
    "F4": "F4",
}
MOD_NAMES = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Super"}
CMD_NAMES = {
    "window-switcher": "窗口切换器",
    "open-workspace-opencode": "打开 OpenCode",
    "open-workspace-cursor": "打开 Cursor",
    "open-workspace-terminal": "打开终端",
    "open-workspace-files": "文件管理器",
    "backspace-burst": "连续删除",
}
SYS_NAMES = {
    "volume_up": "系统音量＋",
    "volume_down": "系统音量－",
    "mute": "静音",
    "display_sleep": "关显示器",
    "play_pause": "播放/暂停",
    "show_desktop": "显示桌面",
}


def describe(action: dict | None) -> str:
    if not action or action.get("type") == "none":
        return "—"
    kind = action.get("type")
    if kind == "voice":
        return "按住口述"
    if kind == "key_stroke":
        key = KEY_NAMES.get(action.get("key", ""), action.get("key", "?").upper())
        mods = "+".join(MOD_NAMES.get(m, m) for m in action.get("mods", []))
        return f"{mods}+{key}" if mods else key
    if kind == "command":
        argv = action.get("argv", [])
        name = pathlib.Path(argv[0]).name if argv else ""
        if name == "ydotool" and argv and "125" in argv[-1]:
            return "Super 活动概览"
        return CMD_NAMES.get(name, name or "命令")
    if kind == "system":
        return SYS_NAMES.get(action.get("value", ""), action.get("value", ""))
    if kind == "layer_toggle":
        return f"切换层{action.get('value')}"
    if kind == "macro":
        return "宏"
    return kind


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(bindings: dict) -> str:
    W, H = 1560, 900
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="#f7f8f7"/>',
        f'<text x="46" y="66" font-family="{FONT}" font-size="34" font-weight="600" fill="#1b1f23">'
        f"Baton Mi · 键位映射</text>",
        f'<text x="46" y="98" font-family="{FONT}" font-size="17" fill="#5c6672">'
        f"小米蓝牙遥控器 2 Pro（RC003 · BLE VID:PID 2717:32b8）→ Linux 桌面 · 由 mapping.json 自动生成</text>",
    ]

    # ---------- 左：遥控器示意 ----------
    out.append(
        '<rect x="96" y="140" width="230" height="660" rx="30" fill="#e9ebee" stroke="#c9ced6" stroke-width="2"/>'
    )
    key_fill, key_text = "#272b31", "#f2f4f6"

    def circle(cx, cy, r, label, sub="", fill=key_fill):  # noqa: ARG001
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>')
        out.append(
            f'<text x="{cx}" y="{cy + (5 if not sub else -2)}" font-family="{FONT}" font-size="{16 if len(label) <= 2 else 13}" '
            f'fill="{key_text}" text-anchor="middle">{esc(label)}</text>'
        )
        if sub:
            out.append(
                f'<text x="{cx}" y="{cy + 16}" font-family="{FONT}" font-size="11" fill="#aab2bd" '
                f'text-anchor="middle">{esc(sub)}</text>'
            )

    def keymap_labels(name: str) -> str:
        b = bindings.get(name, {})
        parts = []
        if describe(b.get("tap")) != "—":
            parts.append(describe(b["tap"]))
        if describe(b.get("hold")) != "—":
            parts.append("长按 " + describe(b["hold"]))
        if describe(b.get("double")) != "—":
            parts.append("双击 " + describe(b["double"]))
        return " · ".join(parts) if parts else "—"

    circle(176, 210, 30, "电源")
    circle(246, 210, 30, "语音")
    # D-pad
    out.append('<circle cx="211" cy="392" r="98" fill="#272b31"/>')
    out.append(
        '<circle cx="211" cy="392" r="34" fill="#3a4048" stroke="#4b525b" stroke-width="2"/>'
    )
    out.append(
        f'<text x="211" y="398" font-family="{FONT}" font-size="17" fill="{key_text}" text-anchor="middle">OK</text>'
    )
    for cx, cy, t in ((211, 308, "↑"), (211, 476, "↓"), (127, 392, "←"), (295, 392, "→")):
        out.append(
            f'<text x="{cx}" y="{cy + 7}" font-family="{FONT}" font-size="21" fill="{key_text}" text-anchor="middle">{t}</text>'
        )
    circle(160, 560, 30, "返回")
    circle(160, 640, 30, "主页")
    circle(160, 720, 30, "菜单")
    out.append(
        f'<text x="211" y="836" font-family="{FONT}" font-size="13" fill="#8a939e" text-anchor="middle">遥控器按键位置示意</text>'
    )
    # 音量摇杆
    out.append(f'<rect x="232" y="528" width="58" height="128" rx="29" fill="{key_fill}"/>')
    out.append(
        f'<text x="261" y="572" font-family="{FONT}" font-size="19" fill="{key_text}" text-anchor="middle">＋</text>'
    )
    out.append(
        f'<text x="261" y="632" font-family="{FONT}" font-size="19" fill="{key_text}" text-anchor="middle">－</text>'
    )
    circle(261, 720, 30, "TV")

    # 左侧图例
    out.append(
        f'<text x="452" y="860" font-family="{FONT}" font-size="13" fill="#8a939e">'
        f"本图由 tools/gen-keymap-image.py 读取 system/mapping.json 自动生成 —— 键位改了重跑一次即可</text>"
    )

    # ---------- 右：说明表 ----------
    x0, y0, row_h = 452, 186, 46
    col = {"key": x0, "tap": x0 + 132, "hold": x0 + 470, "dbl": x0 + 742}
    rule_x2 = x0 + 900
    out.append(
        f'<rect x="{x0 - 30}" y="{y0 - 52}" width="{rule_x2 - x0 + 62}" height="{row_h * (len(KEY_LABELS) + 1) + 40}" rx="16" '
        f'fill="#ffffff" stroke="#e2e6ea"/>'
    )
    for text, x in (
        ("按键", col["key"]),
        ("短按", col["tap"]),
        ("长按（≥350ms）", col["hold"]),
        ("双击", col["dbl"]),
    ):
        out.append(
            f'<text x="{x}" y="{y0 - 14}" font-family="{FONT}" font-size="16" font-weight="600" fill="#5c6672">{text}</text>'
        )
    out.append(
        f'<line x1="{col["key"]}" y1="{y0}" x2="{rule_x2}" y2="{y0}" stroke="#e2e6ea" stroke-width="2"/>'
    )
    for i, (name, label) in enumerate(KEY_LABELS):
        b = bindings.get(name, {})
        y = y0 + row_h * (i + 1)
        out.append(
            f'<text x="{col["key"]}" y="{y}" font-family="{FONT}" font-size="18" font-weight="600" fill="#1b1f23">{esc(label)}</text>'
        )
        out.append(
            f'<text x="{col["tap"]}" y="{y}" font-family="{FONT}" font-size="17" fill="#2f6f4f">{esc(describe(b.get("tap")))}</text>'
        )
        out.append(
            f'<text x="{col["hold"]}" y="{y}" font-family="{FONT}" font-size="17" fill="#8a6d1f">{esc(describe(b.get("hold")))}</text>'
        )
        out.append(
            f'<text x="{col["dbl"]}" y="{y}" font-family="{FONT}" font-size="17" fill="#8c4a4a">{esc(describe(b.get("double")))}</text>'
        )
        if i < len(KEY_LABELS) - 1:
            out.append(
                f'<line x1="{col["key"]}" y1="{y + 15}" x2="{rule_x2}" y2="{y + 15}" stroke="#f0f2f4"/>'
            )
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    mapping = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "system/mapping.json")
    outdir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "docs/images")
    data = json.loads(mapping.read_text(encoding="utf-8"))
    svg = build_svg(data.get("bindings", {}))
    outdir.mkdir(parents=True, exist_ok=True)
    svg_path = outdir / "keymap.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(f"✅ SVG: {svg_path}")
    try:
        import cairosvg  # type: ignore

        png_path = outdir / "keymap.png"
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), scale=1.5)
        print(f"✅ PNG: {png_path} ({png_path.stat().st_size // 1024} KB)")
    except ImportError:
        print("⚠️ 未安装 cairosvg，只生成了 SVG（pip install cairosvg 可转 PNG）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
