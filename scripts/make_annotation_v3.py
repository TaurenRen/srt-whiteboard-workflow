#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_annotation_v3.py —— 生成 v3 标注（对象幕 + 写字幕 + 镜头取景框）

v3 相对 v2 的结构变化：
  1. 每一站拆成两幕：先画「物」，紧接着写「地名 + 年份」。
     同一站的两幕共用一个镜头取景框（cameraRegion），镜头不跳，只是笔移到旁边写字。
  2. 时长不再平均分：按 sync_timing 反推的旁白分段，段内按 ratio 切给「画物 / 写字」。
  3. 写字幕 inkPath="textwrite"，渲染器逐列推进，保证文字一定写完。
  4. 最后一段旁白（总结句）不配元素 —— 交给渲染器的结尾拉远定格。
"""
import json
import os
from pathlib import Path

BASE = Path(os.environ.get("SRTWB_PROJECT", Path.cwd()))  # 项目根目录，用环境变量 SRTWB_PROJECT 指定


def _rect(box):
    return {"x": box[0], "y": box[1], "width": box[2] - box[0], "height": box[3] - box[1]}


def build(spec, timing_path, out_json, out_labels):
    timing = json.loads(Path(timing_path).read_text(encoding="utf-8"))
    segs = timing["segments"]
    total = timing["duration_s"] * 1000.0

    elements, labels = [], []
    seq = 0
    for st in spec["stations"]:
        s0 = segs[st["seg"] - 1]["start"] * 1000.0
        s1 = segs[st["seg"] - 1]["end"] * 1000.0
        span = s1 - s0
        # tail：本段末尾留出「不画任何东西」的比例，交给渲染器做结尾拉远定格。
        # 铁律 18 要求收尾留 3-7 秒，整段音频结束时如果没有这一段空隙，就没有拉远的余地。
        eff = span * (1.0 - float(st.get("tail", 0.0)))
        acc = 0.0
        # 逐幕用自身 region 取景：镜头跟着笔走，不为「同一站」硬撑一个大取景框。
        # 共用取景框会把画面拉松（元素只占 30%），实测画物时显得空。
        cam = None
        for part in st["parts"]:
            dur = max(600.0, eff * part["ratio"])
            start = s0 + acc
            acc += eff * part["ratio"]
            seq += 1
            if part["kind"] == "label":
                lb = part["label"]
                el = {
                    "id": f"{st['id']}_label",
                    "label": f"写字·{lb['name']}",
                    "sequence": seq,
                    "narrativeRole": f"写出「{lb['name']} {lb.get('time','')}」",
                    "subtitle": lb.get("name", ""),
                    "type": "text",
                    "inkPath": "textwrite",
                    "region": _rect(lb["box"]),
                    "reveal": {"direction": "left_to_right",
                               "startMs": int(round(start)),
                               "durationMs": int(round(dur)),
                               "maskPaddingPx": 10, "protectedRegions": []},
                    "handPath": {"start": [lb["box"][0], lb["box"][1]],
                                 "end": [lb["box"][2], lb["box"][3]], "easing": "easeInOut"},
                }
                labels.append({"name": lb["name"], "time": lb.get("time", ""),
                               "box": lb["box"], "size": lb.get("size", 40)})
            else:
                ob = part["obj"]
                el = {
                    "id": ob["id"],
                    "label": ob["name"],
                    "sequence": seq,
                    "narrativeRole": ob.get("role", ""),
                    "subtitle": ob.get("subtitle", ""),
                    "type": ob.get("type", "draw"),
                    "inkPath": ob.get("inkPath", "grid"),
                    "region": _rect(ob["box"]),
                    "reveal": {"direction": ob.get("direction", "left_to_right"),
                               "startMs": int(round(start)),
                               "durationMs": int(round(dur)),
                               "maskPaddingPx": 12, "protectedRegions": []},
                    "handPath": {"start": [ob["box"][0], ob["box"][1]],
                                 "end": [ob["box"][2], ob["box"][3]], "easing": "easeInOut"},
                }
            if cam:
                el["cameraRegion"] = _rect(cam)
            elements.append(el)

    ann = {
        "sceneId": spec["sceneId"],
        "canvas": {"width": 1280, "height": 720},
        "storyBasis": spec["storyBasis"],
        "sceneDurationMs": int(round(total)),
        "elements": elements,
    }
    Path(out_json).write_text(json.dumps(ann, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(out_labels).write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK  {Path(out_json).name}  元素 {len(elements)} 个  总时长 {total/1000:.2f}s")
    for e in elements:
        r = e["reveal"]
        print(f"  {e['sequence']:2d} {e['id']:<16} {r['startMs']/1000:6.2f} → "
              f"{(r['startMs']+r['durationMs'])/1000:6.2f}  {e['label']}")


# ────────────────────────── 长征 v3 ──────────────────────────
CHANGZHENG = {
    "sceneId": "changzheng-v3",
    "storyBasis": "按真实地理走向：江西瑞金出发向西，经湘江、遵义、赤水与金沙江，"
                  "再北上过大渡河泸定桥、雪山草地，最终抵达陕北吴起镇。",
    "stations": [
        {"id": "ruijin", "seg": 1, "camera": (1006, 458, 1278, 620),
         "parts": [
             {"kind": "obj", "ratio": 0.62, "obj": {"id": "ruijin", "name": "红旗（瑞金）",
              "type": "start", "box": (1018, 526, 1114, 612), "role": "东南起点出发"}},
             {"kind": "label", "ratio": 0.38, "label": {"name": "瑞金", "time": "1934.10",
              "box": (1092, 468, 1272, 546), "size": 40}}]},

        {"id": "xiangjiang", "seg": 2, "camera": (956, 318, 1160, 480),
         "parts": [
             {"kind": "obj", "ratio": 0.62, "obj": {"id": "xiangjiang", "name": "湘江（水波）",
              "type": "river", "box": (966, 396, 1110, 474), "role": "向西突围"}},
             {"kind": "label", "ratio": 0.38, "label": {"name": "湘江", "time": "1934.11",
              "box": (972, 326, 1150, 396), "size": 40}}]},

        {"id": "zunyi", "seg": 3, "camera": (780, 284, 974, 488),
         "parts": [
             {"kind": "obj", "ratio": 0.62, "obj": {"id": "zunyi", "name": "会址（遵义）",
              "type": "meeting", "box": (854, 376, 950, 482), "role": "历史转折点"}},
             {"kind": "label", "ratio": 0.38, "label": {"name": "遵义", "time": "1935.01",
              "box": (790, 292, 968, 366), "size": 40}}]},

        {"id": "chishui", "seg": 4, "camera": (534, 276, 862, 568),
         "parts": [
             {"kind": "obj", "ratio": 0.62, "obj": {"id": "chishui", "name": "赤水金沙（西段）",
              "type": "route", "box": (546, 376, 854, 558), "role": "四渡赤水、巧渡金沙"}},
             {"kind": "label", "ratio": 0.38, "label": {"name": "赤水·金沙", "time": "1935.01-05",
              "box": (558, 284, 786, 366), "size": 34}}]},

        {"id": "luding", "seg": 5, "camera": (96, 306, 572, 606),
         "parts": [
             {"kind": "obj", "ratio": 0.62, "obj": {"id": "luding", "name": "铁索桥（泸定）",
              "type": "bridge", "box": (146, 316, 562, 596), "role": "折向北方"}},
             {"kind": "label", "ratio": 0.38, "label": {"name": "泸定桥", "time": "1935.05",
              "box": (106, 414, 296, 496), "size": 40}}]},

        {"id": "xueshan", "seg": 6, "camera": (136, 26, 410, 314),
         "parts": [
             {"kind": "obj", "ratio": 0.62, "obj": {"id": "xueshan", "name": "雪山草地",
              "type": "environment", "box": (146, 90, 400, 304), "role": "极端自然环境"}},
             {"kind": "label", "ratio": 0.38, "label": {"name": "雪山草地", "time": "1935.06-08",
              "box": (148, 34, 380, 114), "size": 34}}]},

        # 第 7 段旁白最长，拆成 路线 → 宝塔 → 写字；末尾 30% 留给结尾拉远（约 4s）
        {"id": "beishang", "seg": 7, "tail": 0.30, "camera": (368, 6, 920, 216),
         "parts": [
             {"kind": "obj", "ratio": 0.35, "obj": {"id": "beishang", "name": "路线（奔向陕北）",
              "type": "route", "box": (376, 86, 772, 210), "role": "沿顶部向东"}},
             {"kind": "obj", "ratio": 0.37, "obj": {"id": "wuqi", "name": "宝塔（吴起镇）",
              "type": "end", "box": (756, 12, 910, 154), "role": "落脚点"}},
             {"kind": "label", "ratio": 0.28, "label": {"name": "吴起镇", "time": "1935.10",
              "box": (546, 14, 760, 96), "size": 40}}]},
    ],
}


# ────────────────────────── Agent 发展史 v3 ──────────────────────────
AGENT = {
    "sceneId": "agent-v3",
    "storyBasis": "横向时间轴：从 1956 年人工智能提出，到 2024 年多模态智能体，"
                  "节点沿一条主轴等距排开，图标上下交替，每个节点旁写出年份与名字。",
    "stations": [
        {"id": "ai_birth", "seg": 1, "parts": [
            {"kind": "obj", "ratio": 0.60, "obj": {"id": "ai_birth", "name": "大脑（人工智能诞生）",
             "box": (135, 170, 310, 370), "role": "学科起点"}},
            {"kind": "label", "ratio": 0.40, "label": {"name": "人工智能", "time": "1956",
             "box": (132, 52, 312, 134), "size": 36}}]},

        {"id": "eliza", "seg": 2, "parts": [
            {"kind": "obj", "ratio": 0.60, "obj": {"id": "eliza", "name": "终端（伊莉莎）",
             "box": (265, 325, 475, 555), "role": "第一个对话程序"}},
            {"kind": "label", "ratio": 0.40, "label": {"name": "伊莉莎", "time": "1966",
             "box": (266, 562, 442, 648), "size": 36}}]},

        {"id": "deepblue", "seg": 3, "parts": [
            {"kind": "obj", "ratio": 0.60, "obj": {"id": "deepblue", "name": "棋盘（深蓝）",
             "box": (395, 150, 550, 370), "role": "机器推理惊艳世界"}},
            {"kind": "label", "ratio": 0.40, "label": {"name": "深蓝", "time": "1997",
             "box": (396, 52, 558, 134), "size": 36}}]},

        {"id": "siri", "seg": 4, "parts": [
            {"kind": "obj", "ratio": 0.60, "obj": {"id": "siri", "name": "手机（语音助手）",
             "box": (548, 325, 673, 555), "role": "走进日常生活"}},
            {"kind": "label", "ratio": 0.40, "label": {"name": "语音助手", "time": "2011",
             "box": (544, 562, 702, 648), "size": 32}}]},

        {"id": "alphago", "seg": 5, "parts": [
            {"kind": "obj", "ratio": 0.60, "obj": {"id": "alphago", "name": "围棋盘（阿尔法围棋）",
             "box": (648, 140, 803, 370), "role": "深度学习高光"}},
            {"kind": "label", "ratio": 0.40, "label": {"name": "阿尔法围棋", "time": "2016",
             "box": (640, 44, 814, 130), "size": 30}}]},

        {"id": "gpt2", "seg": 6, "parts": [
            {"kind": "obj", "ratio": 0.60, "obj": {"id": "gpt2", "name": "节点网络（大模型）",
             "box": (755, 325, 895, 530), "role": "文本生成能力"}},
            {"kind": "label", "ratio": 0.40, "label": {"name": "大语言模型", "time": "2018",
             "box": (746, 562, 914, 648), "size": 30}}]},

        {"id": "chatgpt", "seg": 7, "parts": [
            {"kind": "obj", "ratio": 0.60, "obj": {"id": "chatgpt", "name": "对话气泡（对话式AI）",
             "box": (880, 183, 1030, 370), "role": "引爆全球"}},
            {"kind": "label", "ratio": 0.40, "label": {"name": "对话式 AI", "time": "2022",
             "box": (874, 44, 1042, 130), "size": 30}}]},

        # 最后一段留 0.9s 给结尾拉远定格
        {"id": "multimodal", "seg": 8, "parts": [
            {"kind": "obj", "ratio": 0.52, "obj": {"id": "multimodal", "name": "眼与手（多模态）",
             "box": (985, 325, 1145, 540), "role": "开始理解世界"}},
            {"kind": "label", "ratio": 0.30, "label": {"name": "多模态", "time": "2024",
             "box": (976, 562, 1154, 648), "size": 36}}]},
    ],
}


if __name__ == "__main__":
    import sys
    scene = sys.argv[1] if len(sys.argv) > 1 else "changzheng"
    ver = sys.argv[2] if len(sys.argv) > 2 else "v4"
    if scene == "changzheng":
        build(CHANGZHENG,
              BASE / f"03-标注/changzheng-{ver}.annotation.timing.json",
              BASE / f"03-标注/changzheng-{ver}.annotation.json",
              BASE / "02-字幕与配音/长征标签.json")
    else:
        build(AGENT,
              BASE / "03-标注/agent-history-handdrawn.annotation.timing.json",
              BASE / "03-标注/agent-v3.annotation.json",
              BASE / "02-字幕与配音/Agent标签.json")
