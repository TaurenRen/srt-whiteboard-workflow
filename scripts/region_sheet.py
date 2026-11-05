#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 annotation 里每个 region 单独裁出来（外扩 pad），拼成网格图，
用来肉眼核对「区域是否真的框住了对应主体」。
"""
import sys
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/msyh.ttc"


def main(img_path, ann_path, out_path, pad=18, cols=4):
    im = Image.open(img_path).convert("RGB")
    d = json.loads(Path(ann_path).read_text(encoding="utf-8"))
    els = d["elements"]
    cw, ch = 300, 190            # 每格内容区
    label_h = 26
    rows = (len(els) + cols - 1) // cols
    W, H = cols * cw, rows * (ch + label_h)
    sheet = Image.new("RGB", (W, H), (250, 248, 244))
    try:
        font = ImageFont.truetype(FONT, 15)
    except Exception:
        font = ImageFont.load_default()

    for i, e in enumerate(els):
        r = e["region"]
        x0 = max(0, r["x"] - pad); y0 = max(0, r["y"] - pad)
        x1 = min(im.width, r["x"] + r["width"] + pad)
        y1 = min(im.height, r["y"] + r["height"] + pad)
        crop = im.crop((x0, y0, x1, y1))
        # 等比缩放到内容区
        scale = min(cw / crop.width, ch / crop.height)
        crop = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale))), Image.LANCZOS)
        cx = (i % cols) * cw; cy = (i // cols) * (ch + label_h)
        # 居中贴
        sheet.paste(crop, (cx + (cw - crop.width) // 2, cy + label_h + (ch - crop.height) // 2))
        dr = ImageDraw.Draw(sheet)
        dr.rectangle((cx, cy, cx + cw - 1, cy + ch + label_h - 1), outline=(200, 195, 188))
        dr.text((cx + 6, cy + 4), f'{i+1}. {e["label"]}  ({r["x"]},{r["y"]},{r["width"]}x{r["height"]})',
                font=font, fill=(40, 40, 40))
    sheet.save(out_path, quality=95)
    print("SHEET", out_path, sheet.size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
