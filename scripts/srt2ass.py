# -*- coding: utf-8 -*-
"""
srt2ass.py —— 把 SRT 转成精确定位/精确定字号的 ASS

为什么不用 ffmpeg 的 force_style:
  纯 SRT 没有 PlayRes, libass 会用一个内部默认分辨率去换算字号和边距,
  结果是 FontSize / MarginV 都不落在真实像素上, 调起来全靠试错。
  这里显式写 PlayResX/PlayResY = 视频尺寸, 字号和边距就是真像素。

用法:
  python srt2ass.py <in.srt> <out.ass> [--width 1280] [--height 720]
                    [--font "Microsoft YaHei"] [--size 34] [--margin-v 22]
                    [--primary "&H00F8FBFF"] [--outline "&H00201812"]
"""
import argparse
import re
from pathlib import Path

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{primary},{outline},&H64000000,0,0,0,0,100,100,0.6,0,1,{outline_w},1.2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(s: str) -> str:
    """00:00:08,123 -> 0:00:08.12 (ASS 用 centisecond)"""
    h, m, rest = s.split(":")
    sec, ms = rest.split(",")
    cs = int(round(int(ms) / 10))
    if cs == 100:
        cs = 99
    return f"{int(h)}:{int(m):02d}:{int(sec):02d}.{cs:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--size", type=int, default=34)
    ap.add_argument("--margin-v", type=int, default=22)
    ap.add_argument("--primary", default="&H00F8FBFF")   # ABGR, 米白
    ap.add_argument("--outline", default="&H00201812")   # ABGR, 深墨褐
    ap.add_argument("--outline-w", type=float, default=2.2)
    ap.add_argument("--anchor-y", type=int, default=0,
                    help="非 0 时改用 {\\an2\\pos(x,y)} 显式锚定字幕块底边到该 y 像素,"
                         "绕开 libass 对 MarginV 的内部偏移")
    a = ap.parse_args()

    raw = Path(a.src).read_text(encoding="utf-8").strip()
    blocks = re.split(r"\n\s*\n", raw)
    events = []
    for b in blocks:
        lines = [x for x in b.splitlines() if x.strip()]
        if len(lines) < 2:
            continue
        m = re.match(r"(.+?)\s*-->\s*(.+)", lines[1])
        if not m:
            continue
        start, end = ts(m.group(1).strip()), ts(m.group(2).strip())
        text = "\\N".join(lines[2:])
        if a.anchor_y:
            # \an2 = 底部居中对齐, \pos 的 y 即字幕块底边
            text = "{\\an2\\pos(%d,%d)}%s" % (a.width // 2, a.anchor_y, text)
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    header = HEADER.format(
        w=a.width, h=a.height, font=a.font, size=a.size,
        primary=a.primary, outline=a.outline,
        outline_w=a.outline_w, margin_v=a.margin_v,
    )
    Path(a.dst).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    print(f"OK -> {a.dst}  ({len(events)} 条, PlayRes {a.width}x{a.height}, FontSize {a.size}px)")


if __name__ == "__main__":
    main()
