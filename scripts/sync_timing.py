#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把配音时长对齐到 8 幕画面：
1) ffprobe 取音频总时长
2) silencedetect 找句间停顿，按「字数比例预期位置 ± 容差内取最近停顿」定 8 段边界
3) 回写 annotation.json 的 startMs / durationMs / sceneDurationMs（原文件备份 .bak）
4) 输出时间表 JSON 供核对
"""
import sys
import os
import json
import re
import subprocess
import shutil

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def dur(audio):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", audio],
                         capture_output=True, text=True).stdout.strip()
    return float(out)


def silences(audio, noise="-35dB", d="0.20"):
    p = subprocess.run([FFMPEG, "-i", audio, "-af", f"silencedetect=noise={noise}:d={d}",
                        "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    txt = p.stderr
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", txt)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", txt)]
    segs = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else s
        segs.append((s, e, (s + e) / 2))
    return segs


def char_weights(texts):
    # 中文按字数，数字/字母按 1 个权重
    w = []
    for t in texts:
        n = len(re.sub(r"[，。、；：！？\s]", "", t))
        w.append(max(1, n))
    tot = sum(w)
    return [x / tot for x in w]


def main(ann_path, audio_path, texts):
    total = dur(audio_path)
    segs = silences(audio_path)
    mids = [m for _, _, m in segs if 0.3 < m < total - 0.3]
    print(f"[audio] {total:.2f}s, 检出停顿中点 {len(mids)} 个")

    weights = char_weights(texts)
    n = len(weights)
    cum = []
    acc = 0.0
    for w in weights[:-1]:
        acc += w
        cum.append(acc)

    # 为每个预期边界找最近停顿中点
    bounds = []
    used = set()
    for c in cum:
        expect = c * total
        cand = sorted(((abs(m - expect), i, m) for i, m in enumerate(mids) if i not in used))
        tol = max(1.6, total * 0.06)
        pick = None
        for diff, i, m in cand:
            if diff <= tol:
                pick = (i, m)
                break
        if pick:
            used.add(pick[0])
            bounds.append(pick[1])
        else:
            bounds.append(expect)
            print(f"[warn] 边界 {expect:.2f}s 无匹配停顿，用字数预估")

    bounds = sorted(bounds)
    edges = [0.0] + bounds + [total]
    print("[bounds]", " ".join(f"{b:.2f}" for b in edges))

    # 回写 annotation
    shutil.copy2(ann_path, ann_path + ".bak")
    data = json.loads(open(ann_path, encoding="utf-8").read())
    els = data["elements"]
    if len(els) != n:
        print(f"[err] 元素数 {len(els)} != 文本段数 {n}")
        return 1
    for i, e in enumerate(els):
        s = round(edges[i] * 1000)
        en = round(edges[i + 1] * 1000)
        e["reveal"]["startMs"] = s
        e["reveal"]["durationMs"] = max(600, en - s)
    data["sceneDurationMs"] = round(total * 1000)
    open(ann_path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))

    table = {"audio": audio_path, "duration_s": round(total, 3),
             "segments": [{"i": i + 1, "start": round(edges[i], 3), "end": round(edges[i + 1], 3),
                           "text": texts[i]} for i in range(n)]}
    open(os.path.splitext(ann_path)[0] + ".timing.json", "w", encoding="utf-8").write(
        json.dumps(table, ensure_ascii=False, indent=2))
    print("[ok] annotation 已按配音时长重排:", ann_path)
    return 0


if __name__ == "__main__":
    ann, audio, *txts = sys.argv[1:]
    sys.exit(main(ann, audio, txts))
