#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asr_align.py —— 用配音本身的转写时间戳，反推解说稿每句的起止时间，并派生单行字幕。

为什么不用 silencedetect：
  静音检测只能给出"哪里有停顿"，停顿未必等于句子边界（换气、强调都会停），
  一旦句子数和停顿数对不上，就只能靠"平均分配"猜，字幕必然错位。
  转写的时间戳是**这条音频自己**的，天然对齐。

用法：
  python asr_align.py 配音.mp3 文案.md --out-timing timing.json --out-srt x.srt --max-chars 14
  （文案.md 用空行/换行分句，一行一句；`#` 开头与表格行会被忽略）

输出：
  timing.json : [{"text": 句, "startMs": 0, "endMs": 12345}, ...]
  x.srt       : 单行字幕，每句按标点/字数再拆，时长按字数比例分摊
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PUNCT = "。，、；：！？,;:!?"
KEEP = "。，、；：！？"


def load_lines(path: Path) -> list[str]:
    """从 markdown/文本里取出句子：忽略标题、表格、引用、空行。"""
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith(("#", ">", "|", "-", "*", "`")):
            continue
        out.append(s)
    return out


def load_pcm16k(path: Path) -> np.ndarray:
    """自己解码成 16k 单声道 float32，绕开 faster-whisper 对 PyAV 版本的强依赖。

    实测：av>=15 去掉了 `metadata_errors` 参数，faster-whisper 1.2.1 的
    `decode_audio` 会直接 TypeError。ffmpeg + wave 是最稳的路径。
    """
    import subprocess
    import tempfile
    import wave

    import numpy as np

    tmp = Path(tempfile.mkdtemp(prefix="asr_")) / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path),
                    "-ac", "1", "-ar", "16000", "-f", "wav", str(tmp)],
                   check=True)
    with wave.open(str(tmp), "rb") as w:
        raw = w.readframes(w.getnframes())
    tmp.unlink(missing_ok=True)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(audio: Path, model_size: str, language: str = "zh"):
    import numpy as np  # noqa: F401
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    pcm = load_pcm16k(audio)
    segments, info = model.transcribe(
        pcm, language=language, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
        beam_size=5, word_timestamps=True,
    )
    segs = []
    for s in segments:
        words = [(w.start, w.end, w.word) for w in (s.words or [])]
        segs.append({"start": s.start, "end": s.end, "text": s.text.strip(), "words": words})
    return segs, info


def norm(s: str) -> str:
    """只保留中英文数字，用于跨文本比对（TTS 会吃掉标点、可能读错个别字）。"""
    return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", s)


def build_char_clock(segs: list[dict]) -> tuple[str, list[float], list[float]]:
    """把转写结果铺成"逐字符时间轴"。

    优先用 word_timestamps（最准）；没有词级时间就按段内字符数线性插值。
    返回 (归一化全文, 每个字符的 start, 每个字符的 end)
    """
    chars: list[str] = []
    c_start: list[float] = []
    c_end: list[float] = []
    for seg in segs:
        words = seg.get("words") or []
        if words:
            for ws, we, wt in words:
                w = norm(wt)
                if not w:
                    continue
                step = (we - ws) / len(w)
                for i, ch in enumerate(w):
                    chars.append(ch)
                    c_start.append(ws + step * i)
                    c_end.append(ws + step * (i + 1))
        else:
            t = norm(seg["text"])
            if not t:
                continue
            step = (seg["end"] - seg["start"]) / len(t)
            for i, ch in enumerate(t):
                chars.append(ch)
                c_start.append(seg["start"] + step * i)
                c_end.append(seg["start"] + step * (i + 1))
    return "".join(chars), c_start, c_end


def locate(sentence: str, full: str, cursor: int, window: int = 40) -> tuple[int, int]:
    """在全文里找这句话的位置。

    先精确找；找不到就取首 8 字做锚点向后搜；再不行按游标 + 字数比例兜底。
    """
    t = norm(sentence)
    if not t:
        return cursor, cursor
    pos = full.find(t, max(0, cursor - window))
    if pos >= 0:
        return pos, pos + len(t)
    anchor = t[:8]
    if len(anchor) >= 4:
        apos = full.find(anchor, max(0, cursor - window))
        if apos >= 0:
            return apos, min(len(full), apos + len(t))
    return cursor, min(len(full), cursor + len(t))


def split_subs(sentence: str, limit: int) -> list[str]:
    """句子 → 若干单行字幕。

    规则（踩过的坑都在这三条里）：
      1. 先按标点切成小句，**只在短块时才尝试合并**（< limit*0.55），
         否则会出现"踏上了举世闻名的长征之路那一年"这种跨小句粘连。
      2. 合并后不得超过 limit —— 之前留 +3 容差，结果 20 字被均分成
         "…要走多远只 / 知道必须一直往前走"，单字甩到行尾很难看。
      3. 单块仍超长才均分。
    """
    parts = re.split(f"[{PUNCT}]", sentence)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []
    chunks: list[str] = []
    cur = ""
    soft = limit * 0.55
    for p in parts:
        if not cur:
            cur = p
        elif len(cur) < soft and len(cur) + len(p) <= limit:
            cur += p
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)

    out: list[str] = []
    for c in chunks:
        if len(c) <= limit:
            out.append(c)
        else:
            n = -(-len(c) // limit)
            size = -(-len(c) // n)
            out.extend(c[i:i + size] for i in range(0, len(c), size))
    # 尾巴太短就并进前一条（同样不能超 limit）
    if len(out) >= 2 and len(out[-1]) <= 4 and len(out[-2]) + len(out[-1]) <= limit:
        out[-1] = out.pop() + out[-1]
    return out


def ts(sec: float, sep: str = ",") -> str:
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", sep)


def snap_to_voice(audio: Path, timing: list[dict], lookahead: float = 1.0) -> int:
    """把每句起点吸附到「真实发声」的第一帧。

    faster-whisper 在长静音处习惯把下一句的 start 标在静音刚开始的位置，
    结果字幕提前亮出、观众盯着字等声音（长征 v4 里提前了整整 4 秒）。
    逐帧找发声点即可修正；本来就在发声中的句子不动。
    """
    import subprocess

    import numpy as np

    win = 0.02
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(audio),
        "-ac", "1", "-ar", "16000", "-f", "s16le", "-",
    ])
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    w = int(16000 * win)
    n = len(a) // w
    rms = np.sqrt(np.mean(a[:n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
    voiced = 20 * np.log10(rms + 1e-9) > -40.0

    moved, limit = 0, int(lookahead / win)
    for t in timing:
        s = t["startMs"] / 1000.0
        i0 = max(0, int(s / win))
        if i0 < len(voiced) and voiced[i0]:
            continue                       # 起点已在发声中，不动
        for k in range(i0, min(len(voiced), i0 + limit)):
            if voiced[k]:
                ns = k * win
                if ns * 1000 < t["endMs"]:
                    t["startMs"] = int(round(ns * 1000))
                    moved += 1
                break
    return moved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("script")
    ap.add_argument("--model", default="small")
    ap.add_argument("--out-timing", default=None)
    ap.add_argument("--out-srt", default=None)
    ap.add_argument("--max-chars", type=int, default=14)
    ap.add_argument("--dump-asr", default=None, help="把转写结果存成 json，便于人工核对")
    ap.add_argument("--reuse-asr", default=None,
                    help="复用已有的 dump json（跳过转写，调字幕断行时用）")
    ap.add_argument("--no-snap", action="store_true",
                    help="不做句边界吸附（默认吸附到真实发声起点）")
    args = ap.parse_args()

    audio = Path(args.audio)
    lines = [l for l in load_lines(Path(args.script)) if len(norm(l)) >= 4]
    if not lines:
        print("文案里没找到句子", file=sys.stderr)
        return 2
    print(f"文案 {len(lines)} 句，共 {sum(len(norm(l)) for l in lines)} 字")

    if args.reuse_asr and Path(args.reuse_asr).exists():
        dump = json.loads(Path(args.reuse_asr).read_text(encoding="utf-8"))
        segs = dump["segs"]
        duration = float(dump.get("duration") or (segs[-1]["end"] if segs else 0.0))

        class _I:  # 轻量替代 whisper 的 info 对象
            pass

        info = _I()
        info.duration = duration
        print(f"复用转写 {args.reuse_asr}（{len(segs)} 段 / {duration:.2f}s）")
    else:
        segs, info = transcribe(audio, args.model)
    full, c_start, c_end = build_char_clock(segs)
    print(f"转写 {len(segs)} 段 / {len(full)} 字，音频 {info.duration:.2f}s")
    if args.dump_asr:
        Path(args.dump_asr).write_text(
            json.dumps({"segs": segs, "full": full, "duration": info.duration},
                       ensure_ascii=False, indent=1), encoding="utf-8")

    timing = []
    cursor = 0
    for i, line in enumerate(lines, 1):
        a, b = locate(line, full, cursor)
        b = max(a + 1, min(b, len(full)))
        s = c_start[min(a, len(c_start) - 1)]
        e = c_end[min(b - 1, len(c_end) - 1)]
        timing.append({"text": line, "startMs": int(round(s * 1000)), "endMs": int(round(e * 1000))})
        print(f"  {i}  {s:6.2f}→{e:6.2f}  ({e-s:4.1f}s)  {line[:24]}…")
        cursor = b

    if not args.no_snap:
        moved = snap_to_voice(audio, timing)
        print(f"句边界吸附到真实发声起点：修正 {moved} 处")

    # 收尾对齐：最后一句以音频实际时长收边，避免尾巴被切
    timing[-1]["endMs"] = int(round(max(timing[-1]["endMs"], info.duration * 1000)))
    if args.out_timing:
        # 同时兼容 make_annotation_v3.py 的 segments 格式（i / start / end / text）
        payload = {
            "audio": str(audio).replace("\\", "/"),
            "duration_s": round(info.duration, 3),
            "source": f"asr_align.py (faster-whisper {args.model})",
            "segments": [
                {"i": i, "start": t["startMs"] / 1000.0, "end": t["endMs"] / 1000.0, "text": t["text"]}
                for i, t in enumerate(timing, 1)
            ],
        }
        Path(args.out_timing).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"timing -> {args.out_timing}")

    if args.out_srt:
        subs = []
        for t in timing:
            chunks = split_subs(t["text"], args.max_chars)
            if not chunks:
                continue
            span = (t["endMs"] - t["startMs"]) / 1000.0
            total = sum(len(c) for c in chunks)
            cur = t["startMs"] / 1000.0
            for c in chunks:
                d = span * len(c) / total
                subs.append((cur, cur + d, c))
                cur += d
        blocks = []
        for i, (a, b, c) in enumerate(subs, 1):
            blocks.append(f"{i}\n{ts(a)} --> {ts(b)}\n{c}\n")
        Path(args.out_srt).write_text("\n".join(blocks), encoding="utf-8")
        print(f"srt   -> {args.out_srt}  ({len(subs)} 条字幕)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
