#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_camera_whiteboard.py —— 带镜头运动的 SRT 白板动画渲染器（v3）

与上游 render_stream_whiteboard.py 的差别（都是为「别把一张画布塞满」服务的）：

1. **画布放大 + 镜头取景**
   内部画布按 --canvas-long-edge（默认 2560）渲染，输出帧只有 --frame 尺寸（默认 1280x720）。
   每帧从大画布上按 camera viewport 裁剪缩放，所以镜头可以推近到单个元素，
   元素可以「满屏画」，画完再摇到下一个，最后拉远到全图。

2. **元素级镜头目标**
   每个元素的镜头 = 让它占满 --zoom-fill 的画面比例（同时受 --zoom-max 限制）。
   镜头用指数平滑跟随，天然产生「摇镜」；元素切换时不需要额外的转场帧。

3. **上色改成蛇形笔刷**
   上游的 contour-wipe 是「底向上整片擦除」，笔尖却在区域里横着来回扫，
   两者完全脱钩 —— 这就是「手在动但没东西画出来」的主因。
   这里改成沿蛇形路径逐点刷：笔尖到哪儿，颜色就在哪儿出现，永远同步。

4. **支持元素级 inkPath**
   标注里可写 "inkPath": "skeleton" 让它单独走骨架描线（写字用这个，笔会顺着笔画走）。

用法：
  <ENV_PY> render_camera_whiteboard.py <图> <标注json> <输出mp4> [手部png] \
      --canvas-long-edge 2560 --frame 1280x720 --fps 30 --total-ms 56064
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np

def _find_upstream() -> Path:
    """定位上游仓库 srt-whiteboard-animation（需要导入其 scripts/stream_render 等）。
    优先级：环境变量 SRTWB_UPSTREAM → 本仓库同级目录 → 当前目录，找不到则报错。"""
    env = os.environ.get("SRTWB_UPSTREAM")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env)
    here = Path(__file__).resolve().parent
    for cand in (here.parent.parent / "srt-whiteboard-animation",
                 here.parent / "srt-whiteboard-animation",
                 Path.cwd() / "srt-whiteboard-animation"):
        if (cand / "scripts").is_dir():
            return cand
    raise SystemExit(
        "找不到上游仓库 srt-whiteboard-animation：请先 git clone 到本仓库同级目录，"
        "或设置环境变量 SRTWB_UPSTREAM 指向它。")

REPO = _find_upstream()
sys.path.insert(0, str(REPO / "scripts"))
import stream_render as sr                      # noqa: E402
import render_stream_whiteboard as rsw          # noqa: E402


# ──────────────────────────────────────────────────────────────
# 折线等距重采样：把蛇形路径压到恰好 frames 个点（≈ 一帧一个点）
# ──────────────────────────────────────────────────────────────
def _resample_polyline(pts: list[tuple[float, float]], n: int) -> list[tuple[float, float]]:
    if not pts:
        return []
    if len(pts) == 1:
        return pts * n
    seg = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
           for i in range(len(pts) - 1)]
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total <= 1e-6:
        return [pts[0]] * n
    targets = np.linspace(0.0, total, n)
    out = []
    j = 0
    for t in targets:
        while j < len(seg) - 1 and cum[j + 1] < t:
            j += 1
        span = seg[j] if seg[j] > 1e-6 else 1.0
        r = (t - cum[j]) / span
        out.append((pts[j][0] + (pts[j + 1][0] - pts[j][0]) * r,
                    pts[j][1] + (pts[j + 1][1] - pts[j][1]) * r))
    return out


class CamWriter:
    """把「整张画布的帧」经镜头裁剪后写进视频。每一次 write = 推进一帧镜头。"""

    def __init__(self, path: Path, renderer: "CameraRenderer", fps: int):
        self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                                      fps, (renderer.fw, renderer.fh))
        if not self.writer.isOpened():
            raise RuntimeError("无法打开视频写入器")
        self.r = renderer
        self.n = 0

    def write(self, frame: np.ndarray) -> None:
        out = self.r.view(frame)
        self.r.stamp_tip(out)          # 手部贴到输出帧上（固定屏幕尺寸，不随镜头放大）
        self.writer.write(out)
        self.n += 1

    def release(self) -> None:
        self.writer.release()


class CameraRenderer(rsw.RegionStreamRenderer):
    def __init__(self, image_bgr, annotation, cfg, hand_png, bare_tip,
                 frame_w=1280, frame_h=720, zoom_fill=0.72, zoom_max=6.0,
                 pan_tau=0.20, zoom_tau=0.30, hand_height=470):
        # 手部不要画进画布（画布会被镜头放大），改成贴到输出帧上
        super().__init__(image_bgr, annotation, cfg, hand_png, True)
        self.fw, self.fh = frame_w, frame_h
        self.zoom_fill, self.zoom_max = zoom_fill, zoom_max
        self.pan_k = 1.0 - math.exp(-1.0 / (cfg.fps * pan_tau))
        self.zoom_k = 1.0 - math.exp(-1.0 / (cfg.fps * zoom_tau))
        self.cz, self.cx, self.cy = 1.0, self.out_w / 2.0, self.out_h / 2.0
        self.tz, self.tx, self.ty = 1.0, self.out_w / 2.0, self.out_h / 2.0

        self._pen = (self.out_w // 2, self.out_h // 2)
        self._win = (0, 0, self.out_w, self.out_h)     # x0,y0,vw,vh（画布坐标）
        self.tip_out = None
        if not bare_tip and hand_png:
            hd = sr._load_hand(Path(hand_png), hand_height)
            if hd is not None:
                self.tip_out = sr.TipOverlay(hd[0], hd[1],
                                             tip_anchor_x=cfg.tip_anchor_x,
                                             tip_anchor_y=cfg.tip_anchor_y)
        self._show_tip = True

        # ── 墨迹口径 ──
        # 用上游的 adaptiveThreshold 判墨（二值，边缘干净）；
        # 但落墨色固定成深墨灰而不是纯黑，贴近原图 #333 的线稿调子。
        # 源图在 main() 里已用 INTER_CUBIC 放大过，所以这里的二值边缘是平滑轮廓，
        # 不会出现 INTER_AREA 放大导致的方块台阶。
        ink = np.array([45, 45, 45], dtype=np.float32)
        self.ink_paint = np.empty_like(self.color_img, dtype=np.float32)
        self.ink_paint[...] = ink

    def _ink_stamp_cell(self, cell, allowed):
        r, c = cell
        e = self.cfg.grid_edge
        sl = (slice(r * e, r * e + e), slice(c * e, c * e + e))
        block = self.ink_pixels[sl] & allowed[sl]
        if not block.any():
            return
        self.drawn[sl][block] = self.ink_paint[sl][block]

    def _reveal_ink_segment(self, a, b, allowed):
        """按落墨点的包围盒局部处理。
        上游每段都 new 一张整画布掩码（2560x1440 → 3.7MB×3 次布尔运算），
        镜头版画布放大 4 倍后这是最大瓶颈；只算笔画附近那一小块即可。"""
        rad = self.cfg.ink_reveal_radius + 2
        x0 = max(0, min(a[0], b[0]) - rad)
        x1 = min(self.out_w, max(a[0], b[0]) + rad + 1)
        y0 = max(0, min(a[1], b[1]) - rad)
        y1 = min(self.out_h, max(a[1], b[1]) + rad + 1)
        if x1 <= x0 or y1 <= y0:
            return
        seg = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
        thick = max(1, self.cfg.ink_reveal_radius * 2 + 1)
        cv2.line(seg, (a[0] - x0, a[1] - y0), (b[0] - x0, b[1] - y0),
                 255, thickness=thick, lineType=cv2.LINE_AA)
        m = (seg > 0) & self.ink_pixels[y0:y1, x0:x1] & allowed[y0:y1, x0:x1]
        if not m.any():
            return
        self.drawn[y0:y1, x0:x1][m] = self.ink_paint[y0:y1, x0:x1][m]

    # 画布快照不带手，手在输出帧上贴
    def _snapshot_with_tip(self, px: int, py: int) -> np.ndarray:
        self._pen = (int(px), int(py))
        return self.drawn.astype(np.uint8)

    def stamp_tip(self, out: np.ndarray) -> None:
        if self.tip_out is None or not self._show_tip:
            return
        x0, y0, vw, vh = self._win
        k = self.fw / float(max(1, vw))
        px = int(round((self._pen[0] - x0) * k))
        py = int(round((self._pen[1] - y0) * k))
        self.tip_out.stamp(out, px, py)

    # ── 镜头目标 ──
    def set_target(self, element: dict, snap: bool = False,
                   allowed: np.ndarray | None = None) -> None:
        # cameraRegion：同一站的「画物」和「写字」共用取景框，镜头不来回跳
        reg = element.get("cameraRegion") or element["region"]
        x0, y0, x1, y1 = rsw._scaled_rect(reg, self.sx, self.sy,
                                         self.out_w, self.out_h)
        # 按「真实墨迹包围盒」收紧取景框（2026-11-05）。
        # 手写标注的 region 往往比实际图形大一圈，甚至横跨相邻元素，
        # 直接用 region 取景会导致画面正中是空白、真正的图形被顶到边角。
        # 注意：**只对画物生效**。文字幕的墨迹（标签字）经常比 region 还宽，
        # 套 bbox 会把字裁到框外（实测「对话式 AI」整句出画）。
        if allowed is not None and self.ink_pixels is not None \
                and element.get("type") != "text":
            rx0, ry0 = max(0, int(x0)), max(0, int(y0))
            rx1 = min(self.out_w, int(math.ceil(x1)))
            ry1 = min(self.out_h, int(math.ceil(y1)))
            if rx1 - rx0 > 4 and ry1 - ry0 > 4:
                sub = self.ink_pixels[ry0:ry1, rx0:rx1] & allowed[ry0:ry1, rx0:rx1]
                ys, xs = np.where(sub)
                if ys.size >= 40:
                    tx0, tx1 = rx0 + int(xs.min()), rx0 + int(xs.max()) + 1
                    ty0, ty1 = ry0 + int(ys.min()), ry0 + int(ys.max()) + 1
                    # 墨迹框不要比原 region 更大（防越界），也不要窄到贴脸
                    if (tx1 - tx0) >= 24 and (ty1 - ty0) >= 24:
                        x0, y0, x1, y1 = tx0, ty0, tx1, ty1
        # 留一点呼吸空间，别把元素顶到画面边缘。
        # 写字幕要给得松一些：贴太近手会把正在写的字整片挡住。
        # 2026-11-05 二次调参：留白收窄，让内容更满屏；手整体缩小后写字幕可以贴得更近
        pad_ratio = 0.34 if element.get("type") == "text" else 0.05
        pad_x = (x1 - x0) * pad_ratio
        pad_y = (y1 - y0) * pad_ratio
        x0 -= pad_x
        x1 += pad_x
        y0 -= pad_y
        y1 += pad_y
        w = max(1, x1 - x0)
        h = max(1, y1 - y0)
        z = min(self.out_w / (w / self.zoom_fill), self.out_h / (h / self.zoom_fill))
        z = max(1.0, min(self.zoom_max, z))
        vw, vh = self.out_w / z, self.out_h / z
        cx = min(max((x0 + x1) / 2.0, vw / 2.0), self.out_w - vw / 2.0)
        cy = min(max((y0 + y1) / 2.0, vh / 2.0), self.out_h - vh / 2.0)
        self.tz, self.tx, self.ty = z, cx, cy
        if snap:
            self.cz, self.cx, self.cy = z, cx, cy

    def set_target_full(self) -> None:
        self.tz, self.tx, self.ty = 1.0, self.out_w / 2.0, self.out_h / 2.0

    def _advance(self) -> None:
        self.cx += (self.tx - self.cx) * self.pan_k
        self.cy += (self.ty - self.cy) * self.pan_k
        self.cz += (self.tz - self.cz) * self.zoom_k

    def view(self, canvas: np.ndarray) -> np.ndarray:
        self._advance()
        vw = int(round(self.out_w / self.cz))
        vh = int(round(self.out_h / self.cz))
        vw = max(2, min(self.out_w, vw))
        vh = max(2, min(self.out_h, vh))
        cx = int(round(min(max(self.cx, vw / 2.0), self.out_w - vw / 2.0)))
        cy = int(round(min(max(self.cy, vh / 2.0), self.out_h - vh / 2.0)))
        x0 = max(0, min(self.out_w - vw, cx - vw // 2))
        y0 = max(0, min(self.out_h - vh, cy - vh // 2))
        self._win = (x0, y0, vw, vh)
        crop = canvas[y0:y0 + vh, x0:x0 + vw]
        if crop.shape[0] != vh or crop.shape[1] != vw:      # 兜底，防越界
            crop = cv2.resize(crop, (vw, vh), interpolation=cv2.INTER_LINEAR)
        return cv2.resize(crop, (self.fw, self.fh), interpolation=cv2.INTER_LINEAR)

    # ── 上色：蛇形笔刷，笔到即有颜色 ──
    def _serpentine(self, allowed: np.ndarray, frames: int) -> list[tuple[int, int]]:
        ys, xs = np.where(allowed)
        if ys.size == 0:
            return []
        y0, y1 = int(ys.min()), int(ys.max())
        x0, x1 = int(xs.min()), int(xs.max())
        area = max(1, (x1 - x0 + 1) * (y1 - y0 + 1))
        r = max(6, self.cfg.brush_radius)
        sp = math.sqrt(area / max(1, frames))
        sp = max(6.0, min(sp, r * 1.3))
        step = max(3, int(round(sp * 0.8)))
        pts: list[tuple[float, float]] = []
        y = y0 + sp * 0.5
        flip = False
        guard = 0
        while y <= y1 and guard < 4000:
            row = int(min(max(y, y0), y1))
            xi = np.where(allowed[row])[0]
            if xi.size >= 2:
                a, b = int(xi.min()), int(xi.max())
                seq = list(range(a, b + 1, step))
                if flip:
                    seq.reverse()
                pts.extend((float(x), float(y)) for x in seq)
            y += sp
            flip = not flip
            guard += 1
        if not pts:
            return []
        dense = _resample_polyline(pts, max(8, frames))
        return [(int(round(x)), int(round(y))) for x, y in dense]

    def _color_pass(self, cw: CamWriter, frames: int, allowed: np.ndarray) -> None:
        pts = self._serpentine(allowed, frames)
        if not pts:
            snap = self.drawn.astype(np.uint8)
            for _ in range(frames):
                cw.write(snap)
            return
        self._wash_brush(cw, frames, pts, allowed)

    # ── 写字：按列从右推进，笔到字出，且保证整段文字必然写完 ──
    def _lay_text(self, cw: CamWriter, frames: int, allowed: np.ndarray,
                  hold_frac: float = 0.18) -> None:
        ys, xs = np.where(self.ink_pixels & allowed)
        if ys.size == 0:
            snap = self.drawn.astype(np.uint8)
            for _ in range(frames):
                cw.write(snap)
            return
        x0 = int(xs.min())
        x1 = int(xs.max())
        # 前 hold_frac 帧不动笔：这一幕刚切过来时镜头还在从上一幕摇过来，
        # 立刻开写会把字写到画面外（实测：遵义幕前 0.4s 笔在画框左上角外）。
        hold = int(frames * hold_frac)
        write_frames = max(1, frames - hold)
        order = np.argsort(xs, kind="stable")
        ys_o, xs_o = ys[order], xs[order]
        pen_y = int(np.median(ys_o))
        for _ in range(hold):
            cw.write(self._snapshot_with_tip(x0, pen_y))
        for fi in range(write_frames):
            p = 1.0 if write_frames == 1 else (fi + 1) / write_frames
            xe = x0 + (x1 - x0 + 1) * p
            k = int(np.searchsorted(xs_o, xe, side="right"))
            if k > 0:
                ny = ys_o[:k]
                nx = xs_o[:k]
                self.drawn[ny, nx] = self.ink_paint[ny, nx]
                tail = ys_o[max(0, k - 220):k]
                if tail.size:
                    pen_y = int(np.median(tail))
            cw.write(self._snapshot_with_tip(int(min(xe, x1)), pen_y))

    # ── 起笔：按元素级 inkPath 分发 ──
    def _ink_pass(self, cw: CamWriter, frames: int, allowed: np.ndarray, mode: str):
        if mode == "textwrite":
            self._lay_text(cw, frames, allowed)
            return []
        if mode == "skeleton":
            strokes = self._region_skeleton_strokes(allowed)
            if strokes:
                samples: list[tuple[int, int]] = []
                lifts: set[int] = set()
                for si, st in enumerate(strokes):
                    if si > 0:
                        lifts.add(len(samples))
                    samples.extend(st)
                self._lay_ink(cw, frames, samples, lifts, allowed)
                return samples
        path = self._region_grid_path(allowed)
        if path:
            samples, lifts, scell = self._grid_plan(path)
            self._lay_ink_grid(cw, frames, samples, lifts, scell, path, allowed)
            return [self._cell_center(c) for c in path]
        self._lay_ink(cw, frames, [], set(), allowed)
        return []

    # ── 主循环 ──
    def render_camera(self, raw_path: Path, total_ms: int) -> Path:
        cfg = self.cfg
        elements = sorted(self.ann["elements"], key=lambda e: e["reveal"]["startMs"])
        cw = CamWriter(raw_path, self, cfg.fps)
        weight_sum = cfg.ink_weight + cfg.color_weight
        ms_per_frame = 1000.0 / cfg.fps
        cur_ms = 0.0

        def fill_static(until_ms: float) -> None:
            nonlocal cur_ms
            n = int(round((until_ms - cur_ms) / ms_per_frame))
            if n <= 0:
                return
            snap = self.drawn.astype(np.uint8)
            for _ in range(n):
                cw.write(snap)
            cur_ms += n * ms_per_frame

        try:
            self.set_target(elements[0], snap=True,
                            allowed=self._allowed_mask(elements[0], elements[1:]))
            for idx, element in enumerate(elements):
                rv = element["reveal"]
                fill_static(rv["startMs"])
                allowed = self._allowed_mask(element, elements[idx + 1:])
                self.set_target(element, allowed=allowed)
                ink_f = max(1, round(rv["durationMs"] * cfg.ink_weight / weight_sum * cfg.fps / 1000))
                col_f = max(1, round(rv["durationMs"] * cfg.color_weight / weight_sum * cfg.fps / 1000))

                # 换场缓冲：镜头从上一幕摇过来要 0.3~0.6s，这期间先别落笔，
                # 否则笔会在画面外/边缘开画（实测「手在动却没画出东西」的主因之一）。
                hold = min(int(round(0.22 * cfg.fps)), max(0, ink_f - 4))
                if hold > 0:
                    snap = self.drawn.astype(np.uint8)
                    for _ in range(hold):
                        cw.write(snap)

                mode = element.get("inkPath", cfg.ink_path_mode)
                self._ink_pass(cw, ink_f - hold, allowed, mode)
                cur_ms += ink_f * ms_per_frame

                self._color_pass(cw, col_f, allowed)
                cur_ms += col_f * ms_per_frame

            # 结尾：拉远到全图 + 定帧（收起手部，把画面让给全图）
            self.set_target_full()
            self._show_tip = False
            self.drawn[...] = self.color_img.astype(np.float32)
            fill_static(max(total_ms, cur_ms + 500))
        finally:
            cw.release()
        return raw_path


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="带镜头运动的白板动画渲染器（v3）")
    p.add_argument("image")
    p.add_argument("annotation")
    p.add_argument("output")
    p.add_argument("hand", nargs="?", default=None)
    p.add_argument("--total-ms", type=int, default=None)
    p.add_argument("--canvas-long-edge", type=int, default=2560)
    p.add_argument("--frame", default="1280x720")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--grid-edge", type=int, default=16)
    p.add_argument("--brush-radius", type=int, default=70)
    p.add_argument("--zoom-fill", type=float, default=0.86)
    p.add_argument("--zoom-max", type=float, default=7.0)
    p.add_argument("--ink-path", default="grid", choices=["grid", "skeleton"])
    p.add_argument("--ink-weight", type=int, default=3)
    p.add_argument("--color-weight", type=int, default=1)
    p.add_argument("--hand-height", type=int, default=350,
                   help="手部在输出帧上的高度（屏幕空间，不随镜头缩放）")
    p.add_argument("--bare-tip", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    fw, fh = (int(v) for v in args.frame.lower().split("x"))

    kw = dict(fps=args.fps, grid_edge=args.grid_edge, brush_radius=args.brush_radius,
              cap_long_edge=args.canvas_long_edge, ink_weight=args.ink_weight,
              color_weight=args.color_weight, ink_path_mode=args.ink_path,
              color_fill="brush",
              # 画布放大后采样点会成倍膨胀：格内插值步长跟着网格放大，
              # 否则 2560 画布上每条边要插 12 个采样点，逐帧开销爆炸。
              sample_step=max(2, args.grid_edge // 3))
    cfg = sr.Config(**kw)

    image_bgr = sr._imread_any(args.image)
    if image_bgr is None:
        print(f"[err] 无法读取图片: {args.image}")
        return 1
    # 先把源图三次插值放大到画布尺寸：上游 resize 用的是 INTER_AREA，
    # 放大时等价于最近邻，会直接把线条变成方块。这里预放大后渲染器不再缩放。
    h0, w0 = image_bgr.shape[:2]
    cw_, ch_ = (args.canvas_long_edge,
                int(round(h0 * args.canvas_long_edge / w0)))
    ch_ -= ch_ % 2
    if (cw_, ch_) != (w0, h0):
        image_bgr = cv2.resize(image_bgr, (cw_, ch_), interpolation=cv2.INTER_CUBIC)
    ann = json.loads(Path(args.annotation).read_text(encoding="utf-8"))
    total_ms = args.total_ms or ann.get("sceneDurationMs")
    if not total_ms:
        total_ms = max(e["reveal"]["startMs"] + e["reveal"]["durationMs"]
                       for e in ann["elements"]) + 1000

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = out_path.with_name(out_path.stem + "_raw.mp4")

    hand_png = Path(args.hand) if args.hand else None
    r = CameraRenderer(image_bgr, ann, cfg, hand_png, args.bare_tip,
                       frame_w=fw, frame_h=fh, zoom_fill=args.zoom_fill,
                       zoom_max=args.zoom_max, hand_height=args.hand_height)
    print("=" * 58)
    print("带镜头运动的白板动画渲染器 v3")
    print(f"  画布: {r.out_w}x{r.out_h}  输出帧: {fw}x{fh}  fps={cfg.fps}")
    print(f"  区域: {len(ann['elements'])}  总时长: {total_ms}ms  "
          f"zoom_fill={args.zoom_fill} zoom_max={args.zoom_max}")
    print("=" * 58)

    r.render_camera(raw_path, total_ms)
    final = sr.transcode_h264(raw_path, out_path)
    print(f"\n最终视频: {final}  ({final.stat().st_size / 1048576:.2f} MB)")
    print(f"OUTPUT={final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
