#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检测深灰线条簇的包围盒，用于定位云/山/桥/草等无彩色元素。"""
import sys
import cv2
import numpy as np


def main(img_path, tag, min_area=250):
    b = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    g = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    # 背景是米黄（亮），线条是深灰
    _, m = cv2.threshold(g, 150, 255, cv2.THRESH_BINARY_INV)
    k = np.ones((7, 7), np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=2)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    items = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < min_area:
            continue
        items.append((a, x, y, w, h))
    items.sort(reverse=True)
    print(f"=== {tag} 暗线条簇 {len(items)} 个（按面积降序）===")
    for a, x, y, w, h in items[:24]:
        print(f"  x={x:4d} y={y:4d} w={w:4d} h={h:4d}  area={a}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
