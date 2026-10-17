# video-fast

一份给 AI 编码智能体用的**中文配音视频**技能：从一份 `story.json` 走完整支 30s–3min 的解说 / 介绍 / 宣传片——
**配音 + 逐词字幕 + 自作曲配乐 + MP4**，不需要剪映、不需要联网服务、不需要为影视素材付费。

做这支技能的原因是实测：HyperFrames 官方流水线的质量很高，但它的规则散在十几个技能文档里，
一次视频的前期阅读量常常超过成片本身。`video-fast` 把**必须知道的契约压缩成一份**、
把**每次都要重写的代码固化成脚本**、把**踩过的坑写成报错索引**。

## 实测（不是估计）

| | 传统全量流程 | 用 video-fast |
| --- | --- | --- |
| 开工前读的文档 | 约 279 KB（十几个技能文档 + 脚本源码） | 21 KB（合成契约一份） |
| 总 token | 基准 | 约 −50%～−65% |
| 一支 65s 片（7 帧） | 约 2.5 小时（含返工与重渲） | 约 35 分钟；同构帧改走数据驱动后约 15–20 分钟 |
| 返工 | id 非法、字体缺失、字幕碎句、句间静音…反复出现 | 同类问题一个未重现 |

样例成片由本技能产出：7 帧 / 65.4s / 1080p30 / 4.5 MB（配音 edge-tts、配乐程序合成、字幕逐词高亮）；
另有抖音竖版快节奏版：14 镜头 / 45.3s / 1080×1920 / −14.9 LUFS（撞色大字报 + 自作曲 trap-pop + BGM 硬停）。

## 它包含什么

```
SKILL.md                        流程 + 省 token 的六条
references/composition-contract.md   HyperFrames 合成契约压缩版（写帧前读这一份）
references/script-craft.md       中文稿写法、多音字规避、逐句表情参数
references/pitfalls.md           已知坑 → 症状 → 解法（报错时再读）
examples/pi-skills-story.json    可直接改用的 story.json（7 帧 / 65s）
scripts/
  preflight.py              环境一次体检（ffmpeg/代理/edge-tts/whisper/hyperframes/字体/numpy）
  story_build.py            story.json → SCRIPT.md + STORYBOARD.md + 全部帧（主入口）
  frame_kit.py              帧原型库 + 词级 cue 自动解析 + 多样性检查
  tts_lines.py              逐句配音 + 词级时间戳 + 裁尾静音 + atempo 对齐 + audio_meta
  verify_pronunciation.py   whisper 回译校验，抓 TTS 读错的字
  captions_clauses.py       按脚本标点断句的字幕（不是按词）
  bgm_synth.py              无版权配乐合成（chords + arp + bass + drums + sidechain）
  new_frame.py              lint-clean 的帧骨架（手写单帧时用）
  fix_ids.py                元素 id 前缀安全修复（含 getElementById 同步）
  sync_frame_durations.py   帧时长同步（改过配音必跑）
  look.mjs                  项目的"眼睛"：时间轴体检 + 双遍确定性 + 文字裁切 + 音频处方 + 接触表
evals/evals.json            三个真实测试提示词
```

## 三个帧原型

| 原型 | 形状 | 用在哪 |
| --- | --- | --- |
| `kinetic-hook` | 两行动能大字 + 可选徽标 | 开场钩子、结论句 |
| `card-row` | 卡片按台词逐张拼入（1 张居中放大 / 3 张带左题名 / 4 张居中）+ 标签 + 收尾句 | 清单、对比、场景墙 |
| `panel-demo` | 暖海军蓝面板（终端/浏览器/代码）+ 动作芯片逐个点亮 + 光标 + 迷你字幕气泡 + 命令条 | 演示、安装命令 CTA |

每个原型都接受内容与 `cue`：cue 会去配音的词级时间戳里找“这个词被念到的时刻”，揭示就落在那一刻，
所以结构上不可能把画面一次铺满（那正是“幻灯片感”的来源）。

## 竖版（抖音 1080×1920）

支持出竖版：手写帧（frame_kit 目前是 16:9 写死）、字幕 `--band-top 1560`、硬切转场、
终版响度 -16~-18 LUFS（手机外放直接听清）。实战样例：66s 抖音招生片，从剧本到成片一次过。
竖版与 re-voice 的坑见 `references/pitfalls.md`「竖版与重配音」一节。

## 检查：`look.mjs`

`hyperframes lint/check` 查的是静态约定；`look.mjs` 查的是**画出来的东西对不对**——
把"图对不对"从肉眼判断变成可断言的检查，渲染前 15 秒跑完。

```bash
node scripts/look.mjs .            # 全量：静态体检 + 音频处方 + 浏览器双遍 + 接触表
node scripts/look.mjs . --fast     # 0.5 秒：只跑静态体检 + 音频处方
node scripts/look.mjs . --at 12.5  # 只盯某一帧
```

零 npm 依赖（复用 hyperframes 自带的 `puppeteer-core` 与 `chrome-headless-shell`）。退出码 `0/1/2`。

| 检查 | 拦的是什么 |
| --- | --- |
| 双遍乱序确定性 | 同一 `t` 两次求值画出两幅不同的画（`onUpdate` 里用 `Math.random`/`Date.now`、状态残留、媒体未 seek） |
| 文字被裁 | 出画框、或被 `overflow:hidden` 父盒切掉（`DOM Range` 量真实渲染盒，给出选择器） |
| 纯色帧 | 场景中点整幅画是空的（历史头号事故：某帧整帧空白） |
| 语音 vs 帧时长 | 语音比所属场景长 → 话没说完画面就切了 |
| 音频处方 | 逐轨峰值、人声与 BGM 落差（10–24 dB）、整片 EBU R128 LUFS + true peak |

前三项的方法来自 [OpenFilm](https://github.com/openfilm/openfilm) 的 `openfilm look`（MIT）：
固定种子洗牌两遍、8×8 降采样后最大通道差 > 32/255 判为两幅不同的画、亮度极差 < 6 判为纯色帧。
后两项与接触表是针对中文配音视频补的。

## 快速开始

```bash
# 0. 环境体检（代理、edge-tts、whisper、hyperframes、中文字体一次查完）
python scripts/preflight.py --proxy http://127.0.0.1:7897

# 1. 建工程
npx hyperframes init my-video --non-interactive --example=blank

# 2. 写一份 story.json（照抄 examples/pi-skills-story.json 改内容即可）
python scripts/story_build.py --project my-video --story my-story.json

# 3. 配音 → 读音校验 → 字幕 → 配乐
python scripts/tts_lines.py --project my-video --script my-video/SCRIPT.md --voice zh-CN-YunxiNeural
python scripts/verify_pronunciation.py --project my-video
python scripts/captions_clauses.py --project my-video
python scripts/bgm_synth.py --out my-video/assets/bgm/track.wav --duration 70 --style uplifting

# 4. 时长同步 → 组装 → 检查 → 出片
python scripts/sync_frame_durations.py --project my-video
cd my-video && npx hyperframes lint && npx hyperframes check
node ../scripts/look.mjs .        # 双遍确定性 / 文字裁切 / 纯色帧 / 音频处方
npx hyperframes render --quality high --output renders/video.mp4
```

改音色 / 改台词后想保住画面卡点：把上一版的逐帧语音时长传给 `tts_lines.py --target-durations`，
脚本用 `atempo` 把新配音拉伸回原时间轴，分镜的 cue 一个都不用改。

## 依赖

- Node 22+ 与 `hyperframes`（HTML/GSAP 合成 → MP4）
- `ffmpeg` / `ffprobe`（含 `atempo`、`adelay`、`apad`、`atrim`）
- Python 3.10+，`edge-tts`（中文配音，需代理）、`numpy`（配乐）
- 可选：`whisper.cpp` + `ggml-large-v3-turbo`（读音校验）
- 字体：`assets/fonts/` 里的中文思源宋体/黑体 + 拉丁 EB Garamond / Inter / JetBrains Mono；
  渲染机是干净 headless Chrome，**系统字体一律不可用**（详见 `references/composition-contract.md` §5）

## 设计取向

- **声音先行**：先把配音、词级时间戳、停顿定死，再画画面——分镜的每个动作都对准一个词。
- **字幕按句子断**：按脚本文标点切从句（同例 219 词 → 47 组，均 7 字）；按词切会变成 2 词一闪。
- **连贯性优先**：句间停顿 1.4s、段落 2.3s、结尾留 5s；宁可成片短 15 秒，也不要一句一冷场。
- **模板只负责同构帧**：形状重复的节拍走数据驱动，选形状与写文案仍然是人的工作；
  相邻两帧同原型会被提示（十帧一个样就是幻灯片）。
- **先快照后渲染**：快照 20 秒能拦下大半返工，渲染一支 65s 片约 2 分钟。

## License

MIT
