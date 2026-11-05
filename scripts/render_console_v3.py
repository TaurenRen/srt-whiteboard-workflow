#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可见的渲染控制台 v3：
- 真实执行 render_stream_whiteboard.py（python -u 无缓冲）
- 顶部实时计时 + 进度条（按标注总时长估算），保证录屏画面始终在动
- 日志区实时滚动显示子进程输出
- 完成后显示产物大小并停留
"""
import sys
import os
import json
import time
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk

PY = os.environ.get("SRTWB_PY", "python")
RENDER = os.environ.get("SRTWB_RENDERER", "scripts/render_camera_whiteboard.py")
HAND = os.environ.get("SRTWB_HAND", "assets/drawing-hand.png")
BASE = os.environ.get("SRTWB_PROJECT", ".")

JOBS = {
    "changzheng-v3": ("changzheng-v3", f"{BASE}/04-渲染输出/changzheng-v3-silent.mp4"),
    "changzheng-v4": ("changzheng-v3", f"{BASE}/04-渲染输出/changzheng-v4-silent.mp4"),
    "changzheng-v5": ("changzheng-v3", f"{BASE}/04-渲染输出/changzheng-v5-silent.mp4"),
    "agent-v3": ("agent-v3", f"{BASE}/04-渲染输出/agent-v3-silent.mp4"),
}

# 渲染完成后的收尾链：合音轨 → 烧字幕 → ffprobe 校验
# 注意：ass 滤镜里**不能出现盘符冒号**（会被当成 original_size 参数），一律用相对路径 + cwd=BASE
POST = {
    "changzheng-v3": [
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/changzheng-v3-silent.mp4",
         "-i", "02-字幕与配音/changzheng-voice.mp3",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
         "04-渲染输出/changzheng-v3-voice.mp4"],
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/changzheng-v3-voice.mp4",
         "-vf", "ass=02-字幕与配音/长征路线-v3.ass",
         "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart",
         "04-渲染输出/长征路线-手绘白板动画-v3.mp4"],
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=nw=1", "04-渲染输出/长征路线-手绘白板动画-v3.mp4"],
    ],
    "changzheng-v4": [
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/changzheng-v4-silent.mp4",
         "-i", "02-字幕与配音/changzheng-v4-voice.mp3",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
         "04-渲染输出/changzheng-v4-voice.mp4"],
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/changzheng-v4-voice.mp4",
         "-vf", "ass=02-字幕与配音/长征路线-v4.ass",
         "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart",
         "04-渲染输出/长征路线-手绘白板动画-v4.mp4"],
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=nw=1", "04-渲染输出/长征路线-手绘白板动画-v4.mp4"],
    ],
    "changzheng-v5": [
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/changzheng-v5-silent.mp4",
         "-i", "02-字幕与配音/changzheng-v5-voice.mp3",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
         "04-渲染输出/changzheng-v5-voice.mp4"],
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/changzheng-v5-voice.mp4",
         "-vf", "ass=02-字幕与配音/长征路线-v5.ass",
         "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart",
         "04-渲染输出/长征路线-手绘白板动画-v5.mp4"],
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=nw=1", "04-渲染输出/长征路线-手绘白板动画-v5.mp4"],
    ],
    "agent-v3": [
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/agent-v3-silent.mp4",
         "-i", "02-字幕与配音/agent-voice.mp3",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
         "04-渲染输出/agent-v3-voice.mp4"],
        ["ffmpeg", "-y", "-v", "error",
         "-i", "04-渲染输出/agent-v3-voice.mp4",
         "-vf", "ass=02-字幕与配音/Agent发展史-v3.ass",
         "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart",
         "04-渲染输出/Agent智能体发展史-手绘白板动画-v3.mp4"],
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=nw=1", "04-渲染输出/Agent智能体发展史-手绘白板动画-v3.mp4"],
    ],
}

q = queue.Queue()
state = {"exit": None, "t0": None}


def worker(cmd):
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1, env=env)
    for line in p.stdout:
        q.put(line.rstrip())
    p.wait()
    q.put(f"__EXIT__{p.returncode}")


def post_worker(steps):
    for i, step in enumerate(steps, 1):
        q.put(f"[收尾 {i}/{len(steps)}] $ {os.path.basename(step[0])} {' '.join(step[1:5])} ...")
        p = subprocess.Popen(step, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1,
                             cwd=BASE)
        for line in p.stdout:
            q.put("  " + line.rstrip())
        p.wait()
        if p.returncode != 0:
            q.put(f"__EXIT__{p.returncode}")
            return
    q.put(f"__POST_OK__")


def main():
    job = sys.argv[1] if len(sys.argv) > 1 else "changzheng"
    stem, out = JOBS[job]
    img = f"{BASE}/03-标注/{stem}.png"
    ann = (f"{BASE}/03-标注/{job}.annotation.json" if job.endswith(("-v4", "-v5"))
           else f"{BASE}/03-标注/{stem}.annotation.json")
    meta = json.loads(open(ann, encoding="utf-8").read())
    total_ms = meta["sceneDurationMs"]

    cmd = [PY, "-u", RENDER, img, ann, out, HAND,
           "--fps", "24", "--total-ms", str(total_ms), "--grid-edge", "20"]
    if job.startswith("agent"):
        cmd += ["--zoom-fill", "0.70"]

    root = tk.Tk()
    root.title("srt-whiteboard-animation 实测 · 渲染")
    root.geometry("1180x740+30+30")
    root.configure(bg="#0f1419")
    root.attributes("-topmost", True)

    tk.Label(root, text=f"渲染任务  {os.path.basename(out)}", bg="#0f1419", fg="#58a6ff",
             font=("Microsoft YaHei UI", 20, "bold"), anchor="w").pack(fill="x", padx=20, pady=(14, 0))
    tk.Label(root, text=f"元素 {len(meta['elements'])} 个 · 目标时长 {total_ms/1000:.1f}s · 2560 画布取景 → 1280x720 · 24fps",
             bg="#0f1419", fg="#8b949e", font=("Microsoft YaHei UI", 11), anchor="w").pack(fill="x", padx=20)

    bar = ttk.Progressbar(root, length=1140, mode="determinate", maximum=100)
    bar.pack(fill="x", padx=20, pady=(10, 4))

    clock = tk.Label(root, text="耗时 0.0s", bg="#0f1419", fg="#3fb950",
                     font=("Consolas", 14, "bold"), anchor="w")
    clock.pack(fill="x", padx=20)

    txt = tk.Text(root, bg="#010409", fg="#c9d1d9", font=("Consolas", 11), bd=0, padx=12, pady=10)
    txt.pack(fill="both", expand=True, padx=20, pady=(8, 14))
    txt.insert("end", "$ " + " ".join(cmd[1:]) + "\n\n")
    txt.see("end")

    state["t0"] = time.time()
    threading.Thread(target=worker, args=(cmd,), daemon=True).start()

    def tick():
        if state["exit"] is None:
            el = time.time() - state["t0"]
            clock.config(text=f"耗时 {el:5.1f}s   状态：渲染中…")
            # 估算进度：以典型 60s 素材约 3.5 倍实时为基准，走满前停在 97%
            est = min(97.0, el / (total_ms / 1000 * 0.78) * 100)
            bar["value"] = est
        root.after(200, tick)

    def pump():
        while True:
            try:
                line = q.get_nowait()
            except queue.Empty:
                break
            if line.startswith("__EXIT__"):
                code = line.split("__EXIT__")[1]
                if code == "0" and job in POST:
                    txt.insert("end", "\n[渲染完成] 进入收尾链：合音轨 → 烧字幕 → ffprobe 校验\n")
                    txt.see("end")
                    bar["value"] = 97
                    clock.config(text="渲染完成 · 收尾处理中…", fg="#d29922")
                    threading.Thread(target=post_worker, args=(POST[job],), daemon=True).start()
                    root.after(150, pump)
                    return
                state["exit"] = code
                bar["value"] = 100
                el = time.time() - state["t0"]
                txt.insert("end", f"\n[完成] 退出码 {code}   总耗时 {el:.1f}s\n")
                if os.path.exists(out):
                    txt.insert("end", f"[产物] {out}\n[大小] {os.path.getsize(out)/1048576:.2f} MB\n")
                    clock.config(text=f"完成 · 用时 {el:.1f}s", fg="#3fb950")
                else:
                    clock.config(text="渲染失败", fg="#f85149")
                txt.see("end")
                root.after(6000, root.destroy)
                return
            if line.startswith("__POST_OK__"):
                state["exit"] = "0"
                bar["value"] = 100
                el = time.time() - state["t0"]
                clock.config(text=f"全流程完成 · 用时 {el:.1f}s", fg="#3fb950")
                txt.insert("end", f"\n[全流程完成] 用时 {el:.1f}s\n")
                txt.see("end")
                root.after(6000, root.destroy)
                return
            txt.insert("end", line + "\n")
            txt.see("end")
        root.after(150, pump)

    tick()
    root.after(300, pump)
    root.mainloop()


if __name__ == "__main__":
    main()
