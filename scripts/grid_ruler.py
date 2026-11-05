#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在原图上叠加 100px 坐标网格 + 数字标尺，便于目视读出真实像素坐标。"""
import sys
from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/msyhbd.ttc"


def main(src, dst, step=100):
    im = Image.open(src).convert("RGB")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    font = ImageFont.truetype(FONT, 18)
    W, H = im.size
    for x in range(0, W + 1, step):
        d.line((x, 0, x, H), fill=(255, 0, 128, 70), width=1)
        d.text((x + 2, 2), str(x), font=font, fill=(200, 0, 90, 230))
        d.text((x + 2, H - 24), str(x), font=font, fill=(200, 0, 90, 230))
    for y in range(0, H + 1, step):
        d.line((0, y, W, y), fill=(255, 0, 128, 70), width=1)
        d.text((2, y + 1), str(y), font=font, fill=(0, 110, 200, 230))
        d.text((W - 52, y + 1), str(y), font=font, fill=(0, 110, 200, 230))
    Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB").save(dst, quality=95)
    print("GRID", dst, im.size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
