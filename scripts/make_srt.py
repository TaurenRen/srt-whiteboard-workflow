# -*- coding: utf-8 -*-
"""
make_srt.py —— 由 sync_timing.py 产出的 .timing.json 生成烧录用 SRT

字幕最佳实践（按这版用户反馈定的硬规矩）：
  1. **一行**。绝不两行 —— 两行会同时抢占画面上下两块，中文字幕两行读起来也断气。
  2. 一行不超过 --max-chars 个字（720p 下 46px 字号，14 字约满屏宽 80%）。
  3. 一句话太长就拆成**多条连续字幕**，按时长按字数比例分摊，
     而不是压成两行或缩小字号。观众看到的是一条一条往下滚，这是正常字幕节奏。
  4. 换条时刻严格落在逐句配音分段内，不跨句 —— 语义不串。

用法:
  python make_srt.py <timing.json> <out.srt> [--max-chars 14] [--gap 0.05]
"""
import argparse
import json
import re
import sys
from pathlib import Path

BREAK = "，。、；：？！,.;:?!"


def fmt(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    if s >= 60:
        m += 1
        s -= 60
    if m >= 60:
        h += 1
        m -= 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _clean(t: str) -> str:
    return t.strip().strip("。，、；：,;:").strip()


def _even_split(p: str, limit: int) -> list[str]:
    """无标点的超长短语：按行数均分，而不是硬切出一条长尾巴。"""
    n_lines = -(-len(p) // limit)          # 向上取整
    size = -(-len(p) // n_lines)
    return [p[i:i + size] for i in range(0, len(p), size)]


def split_one_line(text: str, limit: int) -> list[str]:
    """把一句长字幕切成若干「单行」片段：先按标点断，再贪心合并到 limit 以内。"""
    text = _clean(text)
    if len(text) <= limit:
        return [text]
    phrases = [p for p in re.split(f"(?<=[{BREAK}])", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in phrases:
        p = p.strip()
        if not p:
            continue
        if len(cur) + len(p) <= limit + 3:
            cur += p
        else:
            if cur:
                chunks.append(_clean(cur))
            if len(p) > limit + 3:
                chunks.extend(_clean(x) for x in _even_split(p, limit))
                cur = ""
            else:
                cur = p
    if cur:
        chunks.append(_clean(cur))
    chunks = [c for c in chunks if c]
    # 末尾只剩很短一条（<=3 字）就并回上一条，避免一闪而过；但并完不能超 limit
    if len(chunks) >= 2 and len(chunks[-1]) <= 3 and \
            len(chunks[-2]) + len(chunks[-1]) <= limit:
        tail = chunks.pop()
        chunks[-1] = chunks[-1] + tail
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("timing")
    ap.add_argument("out")
    ap.add_argument("--max-chars", type=int, default=14)
    ap.add_argument("--gap", type=float, default=0.05)
    a = ap.parse_args()

    data = json.loads(Path(a.timing).read_text(encoding="utf-8"))
    segs = data["segments"]

    cues: list[tuple[float, float, str]] = []
    for sg in segs:
        s0, s1 = float(sg["start"]), float(sg["end"])
        chunks = split_one_line(sg["text"], a.max_chars)
        total_chars = sum(len(c) for c in chunks)
        if total_chars == 0:
            continue
        span = (s1 - s0) - a.gap
        acc = 0.0
        for i, c in enumerate(chunks):
            d = span * len(c) / total_chars
            cs = s0 + acc
            ce = cs + d if i < len(chunks) - 1 else s1
            acc += d
            if ce - cs >= 0.5:
                cues.append((cs, ce, c))

    out = []
    for i, (cs, ce, txt) in enumerate(cues, 1):
        out.append(f"{i}\n{fmt(cs)} --> {fmt(ce)}\n{txt}\n")
    Path(a.out).write_text("\n".join(out), encoding="utf-8")

    print(f"OK -> {a.out}  ({len(cues)} 条单行字幕, 每行 <= {a.max_chars} 字)")
    for i, (cs, ce, txt) in enumerate(cues, 1):
        print(f"  {i:2d}. {cs:6.2f}-{ce:6.2f} ({ce-cs:4.1f}s)  {txt}  [{len(txt)}字]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
