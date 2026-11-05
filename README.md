# srt-whiteboard-workflow

**把 SRT 字幕 / 解说稿做成「手握笔边画边讲」的白板手绘动画成片** —— 一个从真实项目实测中沉淀下来的完整 Skill（工作流 + 全套脚本 + 踩坑记录）。

基于开源项目 [srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation)（MIT）深度扩展：

| 能力 | 上游 | 本仓库 |
|---|---|---|
| 绘制方式 | 整片擦除 + 笔尖独立扫动（笔与内容脱钩） | **蛇形笔刷**：笔扫到哪、颜色出现在哪 |
| 镜头 | 固定全景 | **镜头运动渲染**：2560×1440 画布逐幕取景 → 平滑摇镜 → 结尾拉远全图 |
| 文字 | — | **`textwrite` 手写标签**：地名/年份楷体烘进底图，笔尖逐列写出 |
| 配音 | 无 | 即梦 SeedAudio 整篇生成 + **静音压缩** + **ASR 时间轴对齐** |
| 字幕 | SRT 直烧（易错位） | 单行大字幕：断句拆条 + ASS 显式 PlayRes + 句起点吸附真实发声帧 |
| 交付 | MP4 | MP4 + 关键截图 + 操作录屏（含可复用的渲染控制台） |

## 效果示例

见 [`examples/`](examples/)：

- `长征路线-手绘白板动画-v5.mp4` —— 地理路线型（83s / 317 字 / 25 条单行字幕）
- `Agent智能体发展史-手绘白板动画-v3.mp4` —— 横向时间轴型（43s）
- `抽帧-*.png` 九宫格速览；`长征示例/` 里有成片使用的底图、标注 JSON、SRT/ASS 与文案原文

## 两种底图范式（实测总结）

| 范式 | 布局 | `--zoom-fill` | 适用 |
|---|---|---|---|
| **地理路线型** | 元素沿真实地理走向排开（瑞金→西→北上→陕北） | 0.86 | 历史、旅程、流程演进 |
| **横向时间轴型** | 节点等距、图标上下交替 | 0.70 | 发展史、迭代、谱系 |

## 快速开始

> 依赖：Windows 10/11、Python 3.10+、FFmpeg（在 PATH）、上游仓库 [srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation)

```bash
# 1) 克隆两个仓库到同一父目录（渲染器会自动发现同级上游）
git clone https://github.com/geeklee/srt-whiteboard-animation.git
git clone https://github.com/TaurenRen/srt-whiteboard-workflow.git
cd srt-whiteboard-workflow

# 2) 装依赖
pip install -r requirements.txt

# 3) 生成配音（需能调用即梦 TTS 或任意 TTS CLI，整篇一次喂入，禁止分段拼接！）
#    详见 SKILL.md 阶段 4

# 4) 配音 → 时间轴 → 字幕（faster-whisper 词级时间戳，句起点自动吸附发声帧）
python scripts/asr_align.py 配音.mp3 文案.txt \
  --out-timing timing.json --out-srt output.srt --max-chars 18

# 5) 配音静音体检 + 压缩（TTS 内部切块会插入 -120dB 绝对静音，必须压掉）
ffmpeg -hide_banner -i voice.mp3 -af "silencedetect=noise=-38dB:d=0.35" -f null - 2>&1 | grep silence_start
python scripts/tighten_audio.py voice.mp3 voice-tight.mp3 --report report.json

# 6) 底图 + 手写标签 → 标注 JSON（环境变量 SRTWB_PROJECT 指向项目目录）
python scripts/make_annotation_v3.py changzheng v5

# 7) 渲染（2560 画布取景 + 蛇形笔刷 + textwrite + 结尾拉远）
python scripts/render_camera_whiteboard.py 主图.png 标注.json out.mp4 assets/drawing-hand.png \
  --total-ms 83150 --fps 24 --grid-edge 20 --zoom-fill 0.86

# 8) 合音轨 + 烧单行字幕
ffmpeg -y -i out.mp4 -i voice-tight.mp3 -c:v copy -c:a aac -b:a 192k -shortest out-voice.mp4
ffmpeg -y -i out-voice.mp4 -vf "ass=subtitle.ass" -c:v libx264 -crf 19 -preset medium -pix_fmt yuv420p -c:a copy 成片.mp4
```

完整工作流（AI 出图 → 源图净化 → 像素级标注 → 分镜时长 → 配音对齐 → 渲染 → 验收清单）见 [`SKILL.md`](SKILL.md)。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SRTWB_UPSTREAM` | 同级目录自动发现 | 上游 srt-whiteboard-animation 仓库路径 |
| `SRTWB_PROJECT` | 当前目录 | 项目素材目录（01-素材/02-字幕与配音/03-标注/…） |
| `SRTWB_PY` / `SRTWB_RENDERER` / `SRTWB_HAND` | 见脚本头 | 渲染控制台（render_console*.py）用 |

## scripts 一览

| 脚本 | 作用 |
|---|---|
| `render_camera_whiteboard.py` | ★ 核心：镜头运动白板渲染器（蛇形笔刷 / textwrite / 结尾拉远） |
| `asr_align.py` | ★ 配音 → 逐字符时间轴 → 标注 timing + 单行 SRT（含句起点吸附） |
| `tighten_audio.py` | ★ TTS 静音压缩（分级保留自然停顿，不动发声内容） |
| `make_annotation_v3.py` | 由站点 spec + timing 生成标注 JSON（一站两幕：画物 + 写字） |
| `add_handwriting.py` | 把地名/年份楷体烘进底图 |
| `srt2ass.py` / `make_srt.py` | SRT 拆条（单行 ≤14~18 字）→ ASS（显式 PlayRes + 底边锚定） |
| `sync_timing.py` | （上游方式）silencedetect 静音检测反推时长 —— 仅适合短篇 |
| `clean_source.py` | AI 源图去纸纹（否则 adaptiveThreshold 把纸纹判成墨迹） |
| `render_console.py` / `render_console_v3.py` | 录屏用的置顶渲染控制台（实时进度 + 收尾链） |
| `retag_hand.py` / `make_shots.py` / 其余 | 手部素材加工 / 截图工具 / 调试辅助 |

## 28 条铁律（节选）

全部来自真实返工，完整版见 [`SKILL.md`](SKILL.md)：

1. **禁止拿示例图当交付** —— 用户要什么主题就生成什么主题
2. **源图必须净化** —— 纸纹会被判成墨迹，线条碎成点阵
8. **一张画布只讲一件事，而且必须连续推进** —— 笔在"走路"，不是到处补细节
13. **字幕只允许一行** —— 装不下就拆成多条连续字幕，不压行不缩字号
14. **画布要能移动** —— 2 倍画布逐幕取景 + 平滑摇镜 + 结尾拉远，别用固定全景
15. **笔尖必须跟着内容走** —— 蛇形笔刷，否则"手在动但没内容"
16. **讲关键节点要写字** —— 地名/年份烘进底图，`textwrite` 逐列写出
19. **取景用真实墨迹包围盒，不用标注 region** —— region 普遍大一圈还会横跨邻居
23. **配音整篇一次生成，禁止分段拼接** —— 分段 = 语速不一致 + 时间轴错位
24. **时间轴来自配音转写的时间戳，不来自静音检测** —— 停顿 ≠ 句界
27. **配音生成后必须做静音体检** —— "整篇送 TTS"不等于平台内部不切块（实测 4s 纯静音）

## 已知短板

- 16:9 里竖长元素纵向最多到画面 60–70%（几何约束），想更满请画宽元素或出竖屏
- 宽高比 >2.2 的细长元素取景会带进邻域标签，计划做「镜头跟随笔尖」模式
- `tighten_audio` 只压纯静音，TTS 块间若插入非零噪声底则需手动处理

## 致谢

- 上游渲染管线：[geeklee/srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation)（MIT）
- 配音：即梦 SeedAudio 1.0（全能配音）

## License

[MIT](LICENSE) © 2026 TaurenRen
