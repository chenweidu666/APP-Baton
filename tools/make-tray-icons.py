#!/usr/bin/env python3
"""生成托盘三态图标 —— 与项目 logo 同一套视觉语言（维护工具，不进安装范围）。

设计
-----
    logo  = 深海军蓝圆徽章 + 白色遥控器剪影 + 青色信号弧
    托盘  = 同一枚徽章（白色遥控器剪影不变），**状态直接由徽章底色表达**：

        正常   绿色徽章 +#2ECC71
        警告   琥珀徽章 #F1C40F   （按键在，语音没连）
        异常   红色徽章 #E74C3C

    裸的彩色圆点看不出"这是什么"，纯 logo 又看不出状态；所以把 logo 的徽章
    形状留着、底色换成状态色 —— 既能一眼扫出三态，也还认得出是同一个东西。

为什么不用 AI 出图
------------------
    托盘图标要的是几何精确 + 22px 下可辨认，出图模型给不了；而且这套必须是
    可复现的（改个色值重跑即可），所以纯 Pillow 画。

依赖
----
    pillow  →  pip install pillow

示例
----
    python3 tools/make-tray-icons.py                 # 写 app/assets/tray_{ok,warn,off}.png
    python3 tools/make-tray-icons.py --preview       # 顺带刷新 docs/images/tray-icons.png
"""

from __future__ import annotations

import argparse
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "app" / "assets"

SIZE = 64  # 输出边长；托盘栏一般缩到 22–24px 显示
SS = 8  # 超采样倍率（画完再降采样，换抗锯齿）

# ------------------------------------------------------------------ 主题色
# 白 = logo 里的遥控器剪影；三色 = 老托盘的绿/黄/红（延续语义，不引入新色相）
REMOTE = (254, 254, 254)  # 遥控器剪影
BADGE = {
    "ok": (46, 204, 113),  # 绿：全部正常
    "warn": (241, 196, 15),  # 黄：按键可用，语音未连
    "off": (231, 76, 60),  # 红：服务 / 按键节点异常
}

# ------------------------------------------------------------------ 版式（0–1 归一化，相对徽章正方形）
# 只剩一个主体，所以居中摆，四周留出和 logo 差不多的呼吸
REMOTE_BOX = (0.388, 0.236, 0.612, 0.764)  # 遥控器剪影（宽 0.224 × 高 0.528）
REMOTE_RADIUS = 0.060
DOT_CENTER = (0.5, 0.5)  # 遥控器上的圆形按键，和 logo 一样开在中间
DOT_RADIUS = 0.062

STATES = ("ok", "warn", "off")


def _px(v: float, scale: int) -> float:
    return v * scale


def _circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


def render(state: str, size: int = SIZE, ss: int = SS) -> Image.Image:
    n = size * ss
    badge = BADGE[state]
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 1) 徽章底：整块状态色（留一点点内缩，避免降采样时边缘糊掉）
    _circle(d, n / 2, n / 2, n / 2 - 0.6 * ss, badge)

    # 2) 遥控器剪影 + 圆形按键（按键镂空成底色，和 logo 一致）
    x0, y0, x1, y1 = (_px(v, n) for v in REMOTE_BOX)
    d.rounded_rectangle((x0, y0, x1, y1), radius=_px(REMOTE_RADIUS, n), fill=REMOTE)
    _circle(d, _px(DOT_CENTER[0], n), _px(DOT_CENTER[1], n), _px(DOT_RADIUS, n), badge)

    return img.resize((size, size), Image.LANCZOS)


def cmd_write(args) -> int:
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for state in STATES:
        path = out / f"tray_{state}.png"
        render(state, args.size).save(path, "PNG", optimize=True)
        print(f"  ✅ {path}  {args.size}px · {path.stat().st_size} B")
    return 0


def cmd_preview(args) -> int:
    """拼一张预览：深/浅两种底 × 四种尺寸，方便肉眼验收。"""
    panel_sizes = (64, 32, 24, 16)
    pad, gap = 24, 18
    row_h = 64 + pad
    width = pad * 2 + len(panel_sizes) * 64 + (len(panel_sizes) - 1) * gap
    height = pad + len(STATES) * row_h + (len(STATES) - 1) * gap + pad
    sheet = Image.new("RGBA", (width, height), (32, 33, 36, 255))
    d = ImageDraw.Draw(sheet)
    # 上半深底 / 下半浅底，模拟深色与浅色任务栏
    d.rectangle((0, 0, width, height // 2), fill=(45, 46, 52, 255))
    d.rectangle((0, height // 2, width, height), fill=(238, 239, 241, 255))
    for row, state in enumerate(STATES):
        y = pad + row * (row_h + gap)
        for col, s in enumerate(panel_sizes):
            x = pad + col * (64 + gap)
            icon = render(state, s)
            sheet.alpha_composite(icon, (x + (64 - s) // 2, y + (64 - s) // 2))
    out = pathlib.Path(args.preview)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "PNG")
    print(f"  ✅ {out}  （上=深色任务栏，下=浅色任务栏；每行一种状态，列依次 64/32/24/16px）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 Baton Mi 托盘三态图标")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    ap.add_argument("--size", type=int, default=SIZE, help=f"输出边长，默认 {SIZE}")
    ap.add_argument(
        "--preview",
        nargs="?",
        const=str(ROOT / "docs" / "images" / "tray-icons.png"),
        help="另存预览图（默认 docs/images/tray-icons.png）",
    )
    args = ap.parse_args()
    rc = cmd_write(args)
    if args.preview:
        rc |= cmd_preview(args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
