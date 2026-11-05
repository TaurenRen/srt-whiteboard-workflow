#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 drawing-hand.png 笔杆上的标识重绘为「狒狒AI」。

几何由 PCA 实测得到（源图 1069x1472）：
  笔杆中心 (602, 476)，轴向 ≈ 顺时针 39.6°
  文字带：|v| < 28；笔杆描边在 |v| ≈ 55

关键：填充区域 = 旋转矩形 ∩ 笔杆本体掩码（闭运算填掉原文字笔画），
因此绝不会溢出到笔杆黑色描边或手部。
"""
import os
import sys
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

UP = Path(os.environ.get("SRTWB_UPSTREAM", "../srt-whiteboard-animation"))
SRC = str(UP / "assets/drawing-hand.png")
DST = str(Path(os.environ.get("SRTWB_PROJECT", ".")) / "01-素材/drawing-hand-feifeiAI.png")

CX, CY = 602.0, 476.0
ANGLE = 39.6
PEN_FILL = (252, 251, 251)
TEXT = "狒狒AI"
FONT = r"C:/Windows/Fonts/msyhbd.ttc"
FONT_SIZE = 62


def rot_rect(cx, cy, half_len, half_wid, deg):
    t = math.radians(deg)
    ax, ay = math.cos(t), math.sin(t)
    px, py = -ay, ax
    return [(cx + ax * half_len * su + px * half_wid * sv,
             cy + ay * half_len * su + py * half_wid * sv)
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def main():
    im = Image.open(SRC).convert("RGBA")
    W, H = im.size
    arr = np.array(im.convert("RGBA"))

    # --- 笔杆本体掩码：近白 且 不透明（透明背景转 RGB 会变白，必须用 alpha 排除）---
    white = ((arr[:, :, 0] > 170) & (arr[:, :, 1] > 170) & (arr[:, :, 2] > 170)
             & (arr[:, :, 3] > 200))
    wm = Image.fromarray((white * 255).astype(np.uint8), "L")

    # 闭运算：先膨胀后腐蚀，把黑色文字笔画所在处填成笔杆
    dil = wm
    for _ in range(6):
        dil = dil.filter(ImageFilter.MaxFilter(9))
    ero = dil
    for _ in range(6):
        ero = ero.filter(ImageFilter.MinFilter(9))
    pen_mask = np.array(ero) > 128

    # --- 旋转矩形掩码（界定要清理的文字带） ---
    rm = Image.new("L", (W, H), 0)
    ImageDraw.Draw(rm).polygon(rot_rect(CX, CY, 252, 34, ANGLE), fill=255)
    rot_mask = np.array(rm) > 128

    # --- 最终填充区 = 矩形 ∩ 笔杆本体 ---
    fill_mask = rot_mask & pen_mask
    fill_area = Image.fromarray((fill_mask * 255).astype(np.uint8), "L")
    # 边缘羽化 1px，避免硬边
    fill_area = fill_area.filter(ImageFilter.GaussianBlur(0.6))

    fill_layer = Image.new("RGBA", (W, H), PEN_FILL + (255,))
    im = Image.composite(fill_layer, im, fill_area)

    # --- 写新文字（沿笔杆方向） ---
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = ImageFont.truetype(FONT, FONT_SIZE)
    bbox = d.textbbox((0, 0), TEXT, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((CX - tw / 2 - bbox[0], CY - th / 2 - bbox[1]), TEXT,
           font=font, fill=(28, 28, 30, 255))
    layer = layer.rotate(-ANGLE, resample=Image.BICUBIC, center=(CX, CY))

    im = Image.alpha_composite(im, layer)
    im.save(DST)
    print("SAVED", DST, im.size, "textbox", tw, th, "fillpix", int(fill_mask.sum()))


if __name__ == "__main__":
    sys.exit(main())
