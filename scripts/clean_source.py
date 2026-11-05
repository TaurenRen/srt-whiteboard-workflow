#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手绘源图「净化」：抹掉纸张纹理颗粒，只保留线条与彩色点缀。
原理：
  paper = 大核中值滤波（去掉线条，得到纯纸底）
  line  = gray < paper - 18          （明显暗于纸底的像素 = 线条）
  color = HSV 饱和度 > 55             （彩色点缀，如橙星/红旗/蓝波）
  result = 原像素*(line|color) + 纸底*(其余)
这样渲染器的 adaptiveThreshold 不会把纸纹误判成墨迹，线条也不会被打碎。
"""
import sys
import cv2
import numpy as np
from PIL import Image


def clean(src, dst, line_delta=18, sat_min=70, med_k=31):
    b = cv2.imdecode(np.fromfile(src, dtype=np.uint8), cv2.IMREAD_COLOR)
    if b is None:
        raise SystemExit(f"读取失败: {src}")
    gray = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    paper = cv2.medianBlur(gray, med_k)
    line = (gray.astype(np.int16) < (paper.astype(np.int16) - line_delta))

    hsv = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    # 彩色点缀：饱和度高且不太亮（排除浅色纸纹）
    color = (hsv[:, :, 1] > sat_min) & (gray < 190)
    keep = (line | color)

    # 轻微膨胀 keep，避免线条被削薄
    keep_u8 = cv2.dilate(keep.astype(np.uint8), np.ones((3, 3), np.uint8), 1)
    keep3 = np.repeat(keep_u8[:, :, None], 3, axis=2).astype(bool)

    # 纸底取画面中心的米黄色（BGR 顺序），保证底色统一
    h, w = gray.shape
    cx, cy = w // 2, h // 2
    patch = b[cy - 20:cy + 20, cx - 20:cx + 20].reshape(-1, 3)
    paper_bgr = np.median(patch, axis=0).astype(np.uint8)

    out = np.where(keep3, b, paper_bgr)
    # 四周 8px 强制纸底（去掉原图边缘残留）
    m = 8
    out[:m, :] = paper_bgr
    out[-m:, :] = paper_bgr
    out[:, :m] = paper_bgr
    out[:, -m:] = paper_bgr
    # 再轻微锐化线条
    blur = cv2.GaussianBlur(out, (0, 0), 1.0)
    out = cv2.addWeighted(out, 1.35, blur, -0.35, 0)

    cv2.imencode(".png", out)[1].tofile(dst)
    print(f"OUT {dst}  paper_bgr={paper_bgr.tolist()}")
    print(f"  line%={line.mean()*100:.2f} color%={color.mean()*100:.2f} keep%={keep.mean()*100:.2f}")


if __name__ == "__main__":
    clean(sys.argv[1], sys.argv[2])
