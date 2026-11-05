#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成结构化关键截图：对比图 / 特写 / 帧条，统一带中文标题。"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

FONT_B = "C:/Windows/Fonts/msyhbd.ttc"
FONT_R = "C:/Windows/Fonts/msyh.ttc"
BASE = os.environ.get("SRTWB_PROJECT", ".")
OUT = f"{BASE}/05-录屏截图"


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    x = (im.width - w) // 2
    y = (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def compare(src_a, src_b, title_a, title_b, title, dst, cw=560, ch=315):
    pad, head = 16, 62
    W = pad * 3 + cw * 2
    H = head + ch + 46 + pad
    sheet = Image.new("RGB", (W, H), (250, 248, 244))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 16), title, font=ImageFont.truetype(FONT_B, 26), fill=(30, 30, 34))
    for i, (p, t) in enumerate(((src_a, title_a), (src_b, title_b))):
        im = cover(Image.open(p).convert("RGB"), cw, ch)
        x = pad + i * (cw + pad)
        sheet.paste(im, (x, head))
        d.rectangle((x, head, x + cw, head + ch), outline=(205, 200, 192))
        d.text((x + 6, head + ch + 10), t, font=ImageFont.truetype(FONT_R, 18), fill=(70, 70, 78))
    sheet.save(dst, quality=95)
    print("SHOT", dst)


def zoom(src, box, title, dst, scale=2.0):
    im = Image.open(src).convert("RGB").crop(box)
    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    head = 54
    sheet = Image.new("RGB", (im.width, im.height + head), (250, 248, 244))
    d = ImageDraw.Draw(sheet)
    d.text((14, 12), title, font=ImageFont.truetype(FONT_B, 24), fill=(30, 30, 34))
    sheet.paste(im, (0, head))
    sheet.save(dst, quality=95)
    print("SHOT", dst)


def framestrip(frames, labels, title, dst, cw=430, ch=242):
    pad, head, cap = 14, 56, 34
    W = pad + (cw + pad) * len(frames)
    H = head + ch + cap
    sheet = Image.new("RGB", (W, H), (250, 248, 244))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 14), title, font=ImageFont.truetype(FONT_B, 24), fill=(30, 30, 34))
    for i, (p, lb) in enumerate(zip(frames, labels)):
        im = cover(Image.open(p).convert("RGB"), cw, ch)
        x = pad + i * (cw + pad)
        sheet.paste(im, (x, head))
        d.rectangle((x, head, x + cw, head + ch), outline=(205, 200, 192))
        d.text((x + 4, head + ch + 8), lb, font=ImageFont.truetype(FONT_R, 17), fill=(70, 70, 78))
    sheet.save(dst, quality=95)
    print("SHOT", dst)


if __name__ == "__main__":
    # 1) 源图净化前后
    compare(f"{BASE}/01-素材/changzheng-handdrawn.png", f"{BASE}/03-标注/changzheng-handdrawn.png",
            "AI 生成原图（纸纹颗粒）", "净化后（线条+彩色保留）",
            "长征源图：净化前后对比", f"{OUT}/截图-03-源图净化对比-长征.png")
    compare(f"{BASE}/01-素材/agent-history-handdrawn.png", f"{BASE}/03-标注/agent-history-handdrawn.png",
            "AI 生成原图（纸纹颗粒）", "净化后（线条+彩色保留）",
            "Agent 发展史源图：净化前后对比", f"{OUT}/截图-04-源图净化对比-Agent.png")

    # 2) 笔杆标识特写
    zoom(f"{BASE}/01-素材/drawing-hand-feifeiAI.png", (330, 250, 860, 680),
         "手部素材笔杆标识重绘为「狒狒AI」（源图 1069x1472）",
         f"{OUT}/截图-05-笔杆标识-狒狒AI.png", 1.4)
