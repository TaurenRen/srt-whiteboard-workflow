# -*- coding: utf-8 -*-
"""压缩 TTS 配音里的超长静音，让节奏紧凑。

即梦 SeedAudio 对长文本会「内部切块合成再拼接」，块间插入 -120dB 的绝对静音
（长征 v4 实测 4.00s / 2.60s 两处），加上标点停顿，整段静音占比可达 27%。
本脚本按 RMS 找静音段，分级保留自然停顿后按样本重新拼接，**不改动任何发声内容**，
只裁掉空白。输出可选 JSON 报告，记录每处裁了多少。

用法：
  python tighten_audio.py in.mp3 out.mp3 --report tighten.json
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

RATE = 24000          # 即梦导出 mp3 的采样率
CH = 2
WIN = 0.05            # RMS 窗口 50ms
TH_DB = -40.0         # 低于此视为静音
MIN_DUR = 0.35        # 只处理 >=0.35s 的停顿
KEEP_LONG = 0.55      # >=1.0s 的停顿（句号 / 平台块间）保留 0.55s
KEEP_SHORT = 0.32     # 0.35–1.0s 的停顿（逗号）保留 0.32s
KEEP_HEAD = 0.12      # 片头静音


def decode(path: Path) -> np.ndarray:
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path),
        "-ac", str(CH), "-ar", str(RATE), "-f", "s16le", "-",
    ])
    return np.frombuffer(raw, dtype="<i2").reshape(-1, CH)


def find_silence(a: np.ndarray) -> list[tuple[float, float, float]]:
    w = int(WIN * RATE)
    n = len(a) // w
    x = a[:n * w].astype(np.float32) / 32768.0
    rms = np.sqrt(np.mean(x.reshape(n, w, CH) ** 2, axis=(1, 2)) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    quiet = db < TH_DB
    segs, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            dur = (j - i) * WIN
            if dur >= MIN_DUR:
                segs.append((i * WIN, j * WIN, dur))
            i = j
        else:
            i += 1
    return segs


def encode(a: np.ndarray, dst: Path) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "s16le",
           "-ar", str(RATE), "-ac", str(CH), "-i", "pipe:0",
           "-c:a", "libmp3lame", "-b:a", "128k", str(dst)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    p.communicate(a.astype("<i2").tobytes())
    if p.returncode:
        raise RuntimeError(f"ffmpeg 编码失败 rc={p.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report", default=None)
    ap.add_argument("--keep-long", type=float, default=KEEP_LONG)
    ap.add_argument("--keep-short", type=float, default=KEEP_SHORT)
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    a = decode(src)
    segs = find_silence(a)
    src_dur = len(a) / RATE

    pieces, cuts, cursor = [], [], 0
    for idx, (s, e, dur) in enumerate(segs):
        if idx == 0 and s < 0.05:
            keep = KEEP_HEAD
        elif dur >= 1.0:
            keep = args.keep_long
        else:
            keep = args.keep_short
        keep = min(keep, dur)
        b = int(round((s + keep) * RATE))
        pieces.append(a[cursor:b])
        cuts.append({"at_s": round(s, 3), "was_s": round(dur, 3),
                     "keep_s": round(keep, 3), "cut_s": round(dur - keep, 3)})
        cursor = int(round(e * RATE))
    pieces.append(a[cursor:])
    out = np.concatenate(pieces, axis=0)

    encode(out, dst)
    out_dur = len(out) / RATE
    before = sum(c["was_s"] for c in cuts)
    after = sum(c["keep_s"] for c in cuts)

    print(f"源 {src_dur:.2f}s → 输出 {out_dur:.2f}s（省 {src_dur - out_dur:.2f}s）")
    print(f"静音段 {len(segs)} 处：{before:.2f}s → {after:.2f}s "
          f"（静音占比 {before / src_dur * 100:.1f}% → {after / out_dur * 100:.1f}%）")
    print("被裁最多的 5 处：")
    for c in sorted(cuts, key=lambda x: -x["cut_s"])[:5]:
        print(f"  @{c['at_s']:6.2f}s  {c['was_s']:.2f}s → {c['keep_s']:.2f}s "
              f"(裁 {c['cut_s']:.2f}s)")

    if args.report:
        Path(args.report).write_text(json.dumps({
            "src": str(src), "dst": str(dst),
            "src_dur_s": round(src_dur, 3), "out_dur_s": round(out_dur, 3),
            "silence_before_s": round(before, 3), "silence_after_s": round(after, 3),
            "cuts": cuts,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"报告 -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
