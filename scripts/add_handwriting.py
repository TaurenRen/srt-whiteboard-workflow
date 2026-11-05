#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_handwriting.py —— 把手写体文字「写进」底图

为什么写到图里而不是后期叠加字幕：
  画面里的地名/年份要跟笔迹一起被「画」出来 —— 笔顺着笔画走、字一个个出现。
  所以文字必须是图里的墨迹，由渲染器当作 ink 逐笔揭示，而不是视频上叠一层。

用法：
  python add_handwriting.py 底图.png 输出.png labels.json
labels.json:
  [{"name": "瑞金", "time": "1934.10", "box": [1090, 468, 1268, 545], "size": 42}]

box 是该标签的可用区域（左上右下，底图像素坐标）；文字在框内左对齐、垂直居中，
主名用 --font-size 指定的楷体，年份用 0.6 倍字号写在主名右下。
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = r"C:/Windows/Fonts/simkai.ttf"       # 楷体，最接近手写
INK = (58, 56, 52)                          # 与线稿同色系的深墨灰


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def _text_size(txt: str, size: int) -> tuple[int, int]:
    f = _font(size)
    b = f.getbbox(txt)
    return b[2] - b[0], b[3] - b[1], b


def draw_label(draw: ImageDraw.ImageDraw, lb: dict) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = lb["box"]
    box_w, box_h = x1 - x0, y1 - y0
    name = lb["name"]
    tm = lb.get("time") or ""
    size = int(lb.get("size", 42))

    # 自动缩字号，保证主名不超框
    while size > 16:
        w, h, _ = _text_size(name, size)
        if w <= box_w - 6:
            break
        size -= 2
    sub = max(16, int(round(size * 0.60)))

    nw, nh, nb = _text_size(name, size)
    if tm:
        tw, th, tb = _text_size(tm, sub)
        total_h = nh + int(sub * 0.55) + th
    else:
        total_h = nh

    ty = y0 + max(0, (box_h - total_h) // 2)
    draw.text((x0 + 2 - nb[0], ty - nb[1]), name, font=_font(size), fill=INK)
    if tm:
        draw.text((x0 + 8 - tb[0], ty + nh + int(sub * 0.55) - tb[1]),
                  tm, font=_font(sub), fill=(96, 92, 86))
    return (x0, y0, x1, y1)


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    src, dst, spec = sys.argv[1], sys.argv[2], sys.argv[3]

    raw = np.fromfile(src, dtype=np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if img is None:
        print(f"[err] 读不到 {src}")
        return 1
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)

    labels = json.loads(Path(spec).read_text(encoding="utf-8"))
    for lb in labels:
        draw_label(d, lb)
        print(f"  写: {lb['name']:<8} {lb.get('time',''):<10} box={lb['box']}")

    out = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    ext = Path(dst).suffix.lower()
    ok, buf = cv2.imencode(ext, out)
    if not ok:
        print("[err] 编码失败")
        return 1
    buf.tofile(dst)
    print(f"OK -> {dst}  ({len(labels)} 个标签)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
