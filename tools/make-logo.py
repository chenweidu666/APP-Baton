#!/usr/bin/env python3
"""生成 / 精修项目 logo —— 火山引擎方舟（Doubao-Seedream）出图 + 几何精修。

这是**维护工具**（不在 `install.sh` 的安装范围内，也不会进 `~/.local/bin`）。

子命令
------
  gen       出图。默认 4 个候选，原图（2048²）存到 --out 目录
  refine    把某张原图精修成 512px 透明 PNG（默认覆盖 docs/images/logo.png）
  all       gen 1 张并直接 refine 成最终 logo
  install   把 docs/images/logo.png 装到用户图标主题并刷新缓存（桌面 / 应用图标用）

精修思路（不靠手工量圆角）
--------------------------
  1. 取"离白色足够远"的像素为主体（可吃掉很淡的灰晕），取最大连通块 → 外接框
  2. 外接框接近正方形 且 四角几乎没有主体像素 → 判定为圆形，用**解析圆遮罩**裁切
     （锐利、四角对称、不留白边）；否则退回泛洪遮罩
  3. 裁切居中 → 512px PNG（形状之外透明、边缘抗锯齿）

依赖
----
  pillow numpy scipy  →  pip install pillow numpy scipy

密钥
----
  环境变量 ARK_API_KEY（方舟 API Key），或用 --key 传入；**不要写进仓库**

示例
----
  ARK_API_KEY=xxx python3 tools/make-logo.py gen --variants 4
  python3 tools/make-logo.py refine /tmp/logo-candidates/1.png --mode circle
  ARK_API_KEY=xxx python3 tools/make-logo.py all            # 出图并直接定稿
  python3 tools/make-logo.py install                        # 刷新桌面 / 应用图标
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.request
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs" / "images" / "logo.png"
ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-5-0-260128"
WHITE = np.array([255.0, 255.0, 255.0])

# 现用 logo = 圆形徽章（遥控器 + 信号弧）；换设计时改这里或 --prompt / --preset
PRESETS = {
    "circle-remote": (
        "Professional app logo, flat vector style, circular badge: a deep navy blue circle containing "
        "a simplified white TV remote control silhouette standing upright with a round direction pad, "
        "three cyan sound wave arcs radiating to the right of the remote. Perfectly centered and symmetrical, "
        "thick clean geometric shapes, flat colors only, no gradients, no shadows, no text, "
        "generous padding inside the circle, crisp vector edges, minimal modern design"
    ),
    "square-dpad": (
        "Professional app logo, flat vector, rounded square icon with dark charcoal background: centered white "
        "circular direction pad glyph made of four rounded triangles, one small cyan microphone dot above it and "
        "one cyan rounded horizontal bar below it. Perfectly symmetrical, bold geometric shapes, flat colors only, "
        "no gradients, no text, generous padding, crisp vector edges, minimal modern design"
    ),
    "bar-dock": (
        "Professional app logo, flat vector, dark charcoal background: a clean white horizontal tray bar with a "
        "small white remote control silhouette docked on top of it and a single cyan sound wave rising from the "
        "remote, wide composition, minimal geometric style, flat colors only, no gradients, no text, centered, "
        "generous padding, crisp vector edges"
    ),
}


# --------------------------------------------------------------- 出图
def api_key(args) -> str:
    key = args.key or os.environ.get("ARK_API_KEY", "")
    if not key:
        sys.exit(
            "  ⚠️ 缺少 API Key：请设置环境变量 ARK_API_KEY=xxx（或用 --key），不要把密钥写进仓库"
        )
    return key


def generate(prompt: str, key: str, out: pathlib.Path, model: str = MODEL) -> None:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "sequential_image_generation": "disabled",
            "response_format": "url",
            "size": "2K",
            "stream": False,
            "watermark": False,
        }
    ).encode()
    req = urllib.request.Request(
        ARK_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.load(resp)
    url = data["data"][0]["url"]
    out.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out)
    print(f"  ✅ {out}  ({out.stat().st_size // 1024} KB)")


def cmd_gen(args) -> int:
    prompt = args.prompt or PRESETS[args.preset]
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    key = api_key(args)
    for i in range(1, args.variants + 1):
        generate(prompt, key, out_dir / f"{i}.png", args.model)
    print("\n  下一步：挑一张，然后 python3 tools/make-logo.py refine <图> [--mode circle]")
    return 0


# --------------------------------------------------------------- 精修
def circle_mask(side: int, ss: int = 4) -> Image.Image:
    """解析圆遮罩（超采样抗锯齿）。"""
    n = side * ss
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    r = n / 2.0
    d = np.sqrt((xx - (r - 0.5)) ** 2 + (yy - (r - 0.5)) ** 2)
    return Image.fromarray(np.where(d <= r * 0.99, 255, 0).astype(np.uint8), "L").resize(
        (side, side), Image.LANCZOS
    )


def flood_alpha(rgb: np.ndarray, tol: int = 70) -> np.ndarray:
    """从四边泛洪吃掉接近背景色的像素，返回 alpha(0/255)。"""
    h, w, _ = rgb.shape
    bg = np.median(np.stack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]]), axis=0)
    near = np.sqrt(((rgb.astype(float) - bg) ** 2).sum(2)) < tol
    out = np.zeros((h, w), bool)
    dq: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near[y, x] and not out[y, x]:
                out[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x] and not out[y, x]:
                out[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                dq.append((ny, nx))
    return np.where(out, 0, 255).astype(np.uint8)


def refine(
    src_path: pathlib.Path, out_path: pathlib.Path, mode: str = "auto", size: int = 512
) -> None:
    from scipy import ndimage

    src = Image.open(src_path).convert("RGB")
    rgb = np.asarray(src).astype(float)
    h, w, _ = rgb.shape

    body = np.sqrt(((rgb - WHITE) ** 2).sum(2)) > 80  # 离白色足够远 = 主体
    lab, _ = ndimage.label(body)
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    big = int(sizes.argmax())
    ys, xs = np.where(lab == big)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    bw, bh = x1 - x0, y1 - y0
    cw, ch = max(1, min(20, bw // 4)), max(1, min(20, bh // 4))
    corner_frac = float(
        np.mean(
            [
                (lab[y0 : y0 + ch, x0 : x0 + cw] == big).mean(),
                (lab[y0 : y0 + ch, x1 - cw : x1] == big).mean(),
                (lab[y1 - ch : y1, x0 : x0 + cw] == big).mean(),
                (lab[y1 - ch : y1, x1 - cw : x1] == big).mean(),
            ]
        )
    )
    is_circle = mode == "circle" or (
        mode == "auto" and abs(bw / bh - 1) < 0.04 and corner_frac < 0.05
    )
    print(
        f"  外接框 {bw}x{bh}（宽高比 {bw / bh:.3f}）· 四角主体占比 {corner_frac:.3f} → "
        f"{'圆形 → 解析圆遮罩' if is_circle else '非圆 → 泛洪遮罩'}"
    )

    side = max(bw, bh)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bx0, by0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    bgc = tuple(
        int(v)
        for v in np.median(np.stack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]]), axis=0)
    )
    work = Image.new("RGB", (side, side), bgc)
    work.paste(
        src.crop((max(bx0, 0), max(by0, 0), min(bx0 + side, w), min(by0 + side, h))),
        (max(0, -bx0), max(0, -by0)),
    )

    img = work.convert("RGBA")
    if is_circle:
        img.putalpha(circle_mask(side))
    else:
        img.putalpha(
            Image.fromarray(flood_alpha(np.asarray(work)), "L").filter(ImageFilter.MinFilter(3))
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((size, size), Image.LANCZOS).save(out_path, "PNG")
    chk = np.asarray(Image.open(out_path))
    al = chk[:, :, 3]
    print(
        f"  ✅ {out_path}  {size}px · 透明 {100 * (al == 0).mean():.1f}%（圆≈21.5%）· "
        f"四角 {al[0, 0]}/{al[0, -1]}/{al[-1, 0]}/{al[-1, -1]}"
    )


def cmd_refine(args) -> int:
    refine(pathlib.Path(args.src), pathlib.Path(args.out), args.mode)
    return 0


def cmd_all(args) -> int:
    prompt = args.prompt or PRESETS[args.preset]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="baton-logo-"))
    raw = tmp / "raw.png"
    generate(prompt, api_key(args), raw, args.model)
    refine(raw, pathlib.Path(args.out), args.mode)
    print(f"  （原图留在 {raw}，可再 refine 别的尺寸/模式）")
    return 0


def cmd_install(args) -> int:
    src = pathlib.Path(args.out)
    if not src.exists():
        sys.exit(f"  ⚠️ 找不到 {src}")
    dst_dir = pathlib.Path.home() / ".local/share/icons/hicolor/512x512/apps"
    dst_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["install", "-m", "644", str(src), str(dst_dir / "baton.png")], check=True)
    if subprocess.run(["which", "gtk-update-icon-cache"], capture_output=True).returncode == 0:
        subprocess.run(
            [
                "gtk-update-icon-cache",
                "-f",
                "-t",
                str(pathlib.Path.home() / ".local/share/icons/hicolor"),
            ],
            capture_output=True,
        )
    print(f"  ✅ 已安装到 {dst_dir / 'baton.png'}（桌面条目用 Icon=baton 引用）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="生成 / 精修项目 logo（火山引擎 Doubao-Seedream + 几何精修）"
    )
    ap.add_argument("--key", help="方舟 API Key（也可用环境变量 ARK_API_KEY）")
    ap.add_argument("--model", default=MODEL, help=f"出图模型，默认 {MODEL}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="出候选图（原图）")
    g.add_argument("--variants", type=int, default=4)
    g.add_argument("--out", default=str(pathlib.Path(tempfile.gettempdir()) / "logo-candidates"))
    g.add_argument("--prompt", default="")
    g.add_argument("--preset", default="circle-remote", choices=sorted(PRESETS))
    g.set_defaults(func=cmd_gen)

    r = sub.add_parser("refine", help="把原图精修成 512px 透明 PNG")
    r.add_argument("src")
    r.add_argument("--out", default=str(DEFAULT_OUT))
    r.add_argument("--mode", default="auto", choices=["auto", "circle", "square"])
    r.set_defaults(func=cmd_refine)

    a = sub.add_parser("all", help="出 1 张并直接定稿")
    a.add_argument("--out", default=str(DEFAULT_OUT))
    a.add_argument("--prompt", default="")
    a.add_argument("--preset", default="circle-remote", choices=sorted(PRESETS))
    a.add_argument("--mode", default="auto", choices=["auto", "circle", "square"])
    a.set_defaults(func=cmd_all)

    i = sub.add_parser("install", help="刷新桌面 / 应用图标")
    i.add_argument("--out", default=str(DEFAULT_OUT))
    i.set_defaults(func=cmd_install)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
