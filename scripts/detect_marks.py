#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按颜色分离手绘图里的「点缀色」元素，输出连通域包围盒，供标注精确取坐标。
红色=旗帜/高光；橙色=星标/节点；蓝色=河流/声波/眼睛。
深灰线条另外做整体墨迹 bbox。
"""
import sys
import cv2
import numpy as np

def report(img_path, tag):
    b = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    hsv = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    print(f"=== {tag} {b.shape[1]}x{b.shape[0]} ===")

    ranges = {
        "RED":    [((0, 60, 80), (12, 255, 255)), ((168, 60, 80), (180, 255, 255))],
        "ORANGE": [((13, 60, 90), (32, 255, 255))],
        "BLUE":   [((90, 45, 80), (135, 255, 255))],
    }
    for name, rs in ranges.items():
        m = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in rs:
            m |= cv2.inRange(hsv, np.array(lo), np.array(hi))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, labels, stats, cents = cv2.connectedComponentsWithStats(m, 8)
        items = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area < 60:
                continue
            items.append((y, x, w, h, area))
        items.sort()
        print(f"-- {name}: {len(items)} blobs")
        for y, x, w, h, area in items:
            print(f"   bbox x={x:4d} y={y:4d} w={w:4d} h={h:4d} area={area}")


if __name__ == "__main__":
    report(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
