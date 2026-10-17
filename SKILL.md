---
name: video-fast
description: >
  Token-lean pipeline for making Chinese narrated videos (讲解/介绍/宣传/科普, 30s–3min)
  with HyperFrames: voiceover + karaoke captions + self-made BGM + MP4, in one pass.
  Use this skill whenever the user asks for a 视频/短片/介绍片/宣传片/解说视频/带字幕的视频/
  「做个视频讲讲 X」, or when a HyperFrames project needs narration, captions, music, or a
  re-render — including "配音不好听/字幕断句不对/重做一版/加个字幕/换个音色" follow-ups.
  It replaces a full read of the hyperframes*, media-use and faceless-explainer docs with a
  condensed contract plus tested scripts; reach for those heavy skills only for advanced work
  (registry blocks, 3D/shader, media treatments, decks, PR/site capture).
---

# video-fast — 中文配音视频快速通道

这条通道的存在理由：HyperFrames 官方流水线质量高，但它的规则散在十几个技能文档 + 脚本源码里，
一次视频的前期阅读成本常常超过成片本身。这里把**必须知道的契约**压缩到
`references/composition-contract.md`，把**每次都要重写的东西**变成 `scripts/` 下的固定工具，
把**这次踩过的坑**记在 `references/pitfalls.md`（只在报错时读）。

目标：同样质量，阅读量降一个数量级，返工趋近于零。

## 何时用哪档

| 情况 | 做法 |
| --- | --- |
| 30s–3min 中文讲解/介绍视频，有配音、字幕、配乐 | 本文档全流程，不读 hyperframes* 重型技能 |
| 只改一个已建好的项目（换音色/改字幕/改某帧/重渲） | 直接跳到对应步骤，只读 `references/composition-contract.md` 里相关小节 |
| 需要 registry 积木/组件、3D、着色器、媒体调色、幻灯片、按网站或 PR 出片 | 先本技能跑不通再进 `hyperframes-registry` / `hyperframes-animation` / `media-use` / 对应 workflow 技能 |

一次视频的 token 预算参考（中文，含脚本、分镜、10 帧合成、配音、字幕、渲染）：
**顺利时约 4–6 万 token 输出、8–12 万输入**。如果明显超出，多半是在读不该读的文档或返工，见文末《省 token 的六条》。

## 0 · 一次体检代替十次试探

```bash
python <SKILL_DIR>/scripts/preflight.py --proxy http://127.0.0.1:7897
```

输出 PASS/FAIL 一张表：ffmpeg/ffprobe + atempo、代理、edge-tts 连通性、whisper-cli 与模型、
hyperframes CLI 与 Chrome、中文字体（Noto Sans/Serif SC）。**先跑这个再动手**——
本机曾经因为在会话中途才发现「edge-tts 必须走代理」「whisper 模型不在默认路径」「控制台是 GBK」
而反复试错，这些一次体检全能提前暴露。

报错的项按提示修，或换成可用替代（例如无 whisper 就跳过读音校验，改人工抽查）。

## 1 · 精简版需求确认（取代 8 步 intent interview）

问**一屏之内能问完**的 5 件事，一次发问，不要逐条来回：

1. 主题与一句话主张（`message`）——必须是一句能说服人的话，不是一串特性
2. 时长目标与画幅（默认 16:9，横版 B 站/YouTube）
3. 语言与音色（默认中文；先给 2–3 个音色样本让他挑，见 scripts/tts_lines.py --samples）
4. 素材：他有没有现成图/视频/文案；没有就全用"发明的图形"（faceless 路线）
5. 交付位置与文件名

写 `BRIEF.md`（可选但推荐）+ `SCRIPT.md`。**先脚本、后画面**：脚本定稿前不要建任何帧。

`SCRIPT.md` 是本通道的单一真相源：`scripts/tts_lines.py`、`scripts/captions_clauses.py`
都从它取文本，所以**改台词只改这一个文件**即可重新生成配音与字幕。

脚本写法（直接决定成片观感，见 `references/script-craft.md`）：

- 每帧 1–3 句、每句 8–20 字，用逗号分小句——TTS 的停顿和字幕断句都跟着标点走
- 规避多音字与易错读：分叉→另开、长成→变成、干活→做、调→定、行(háng/xíng)谨慎
- 每句写一行 `**Delivery:**` 标注 `rate ±N% · pitch ±NHz`，脚本工具会读取并逐句微调表情
- 屏幕上只放**短标签/关键词/公式**，不要把旁白整句印上去（字幕轨已经在显示）

## 2 · 音频先行（这一步定全片时间轴）

```bash
# 2.1 试音：给用户 2–3 个音色样本，让他挑（可选但强烈建议，省一次全片重渲）
python <SKILL_DIR>/scripts/tts_lines.py --script SCRIPT.md --samples

# 2.2 生成配音：逐句 TTS + 词级时间戳 + 裁尾静音 + 固定抬头静音 + 帧长
python <SKILL_DIR>/scripts/tts_lines.py --project <PROJ> --script SCRIPT.md \
    --voice zh-CN-YunxiNeural --head 0.5 --tails "0.9,1.8,0.9,0.9,1.8,0.9,1.8,0.9,2.5,5.5"

# 2.3 读音校验（抓到 TTS 读错的字，改脚本重跑 2.2）
python <SKILL_DIR>/scripts/verify_pronunciation.py --project <PROJ> --script SCRIPT.md

# 2.4 配乐（自己合成，离线、秒级、无版权风险）
python <SKILL_DIR>/scripts/bgm_synth.py --out <PROJ>/assets/bgm/track.wav \
    --duration <总长+4> --style uplifting
```

关键约定（都写进 `audio_meta.json`，后续步骤统一从这里取时间）：

- 每条配音 = `head(0.5s) + 语音 + tail`，`duration_s` 就是该帧的画面时长
- **句间停顿靠 tail 控制**：常规帧 tail 0.9（≈1.4s 换气），段落转场 1.8，结尾 CTA 5.5。
  TTS 每段自带约 0.9s 尾部静音，工具会裁掉——不裁就会出现"一句话说完冷场两秒"的断裂感
- **换音色/改台词后要回到原时间轴**：`--target-durations` 传入上一版逐帧语音时长，
  工具会用 ffmpeg `atempo` 拉伸对齐，画面分镜的卡点无需改动即保持同步
- 词级时间戳来自 edge-tts 的 WordBoundary，比事后转写对齐更准

## 3 · 字幕（按句子断，不按词断）

```bash
python <SKILL_DIR>/scripts/captions_clauses.py --project <PROJ>
```

它把 `SCRIPT.md` 的标点当断句依据，把词级时间戳归到**从句**上，直接产出：

- `caption_groups.json`（时间/文本/词表）
- 补丁后的 `compositions/captions.html`（保留预设皮肤与 GSAP 时间轴，只换 GROUPS）

为什么不用 workflow 自带的 captions.mjs：它按"每秒词密度"切组，中文常见词速下每个气泡只装 2 个词，
实测 219 个词切成 108 组，读起来一蹦一跳。按标点切是 47 组、平均 7 字、整句成行。
**字幕要能一口气读完，这是断句问题的唯一标准。**

皮肤调整集中在 `.hyperframes/caption-skin.html`：字幕带位置 `--cap-band-top`（默认 900 → 中下方用 836）、
中文字体（思源宋体/黑体）、词间距 `gap: 0.06em 0.16em`。

## 4 · 画面：三种路子，选最省的那条

先看 `references/composition-contract.md`（约 150 行，替代 HyperFrames 全部核心文档）。

| 情况 | 做法 |
| --- | --- |
| 各帧形状重复（清单、演示、钩子、CTA 这类） | **数据驱动**：写一份 `story.json`，`story_build.py` 生成 SCRIPT/STORYBOARD + 全部帧 |
| 只有一两帧要改，或形状很特别 | **手写**：`new_frame.py` 起骨架，自己填内容 |
| 成套模板都不合适 | 读 `references/composition-contract.md` 手写，或补一个新的原型进 frame_kit |

### 数据驱动（推荐默认）

```bash
python <SKILL_DIR>/scripts/story_build.py --project <PROJ> \
    --story <SKILL_DIR>/examples/pi-skills-story.json     # 生成 SCRIPT.md + STORYBOARD.md + 帧
python <SKILL_DIR>/scripts/tts_lines.py --project <PROJ> --script <PROJ>/SCRIPT.md --voice zh-CN-YunxiNeural
python <SKILL_DIR>/scripts/captions_clauses.py --project <PROJ>
python <SKILL_DIR>/scripts/sync_frame_durations.py --project <PROJ>
```

现有原型（`frame_kit.py --list`）：

| 原型 | 形状 | 用在哪 |
| --- | --- | --- |
| `kinetic-hook` | 两行动能大字 + 可选徽标 | 开场钩子、结论句、口号 |
| `card-row` | 一排卡片逐张拼入（卡片数决定布局：1 张居中放大 / 3 张带左题名 / 4 张居中）+ 标签行 + 收尾句 | 清单、对比、场景墙、图集 |
| `panel-demo` | 暖海军蓝面板（终端/浏览器/代码）+ 动作芯片逐个点亮 + 可选光标 + 可选迷你字幕气泡 + `panel_size: pill` 的路径/命令条 | 演示、安装命令 CTA |

常用可选字段：`note`（收尾句）、`note_size: display`（大字落板）、`note_coral`（下划线）、
`sub` + `sub_place: note`、`type_cmd`（打字机命令/路径）、`mock_caption`（迷你字幕气泡）、
`final: true`（只给最后一帧：允许淡出）。

**cue 解析**：每个项目给 `cue`（或 `label`），frame_kit 去 `audio_meta.json` 里找它被念到的时刻，
把揭示落在那一刻；找不到就按 60% 窗口均分。所以 t=0 不会把画面铺满——这是防“幻灯片感”的硬机制。

**多样性是规则，不是自觉**：`story_build.py` 会检查相邻两帧是否同原型、强构图原型是否过半，
并给出提示。同一原型也要换布局（张数/尺寸/pill）——十帧一个样就是幻灯片。

### 手写一帧（少帧修改、特殊形状）

```bash
python <SKILL_DIR>/scripts/new_frame.py --project <PROJ> --id 03-hands-on --duration 11.47
```

骨架自带：`<template>` 包裹、`#root` + 本地 GSAP、内联 `@font-face`、全幅背景 `class="clip"`、
单条 paused timeline 并注册、`reveal/typeOn/jitter` 三个 seek-safe 助手。

写帧的三条硬规矩（违反必出问题，细节见 pitfalls）：

- **元素 id 用 `f` 前缀**（`f03-hands-on-panel`）。以数字开头会让 `querySelector('#03-…')`
  直接抛错、整帧空白；CSS 选择器静默失效，lint 也只给个提示
- **只显示短文案**，不印旁白；每帧视觉元素少而重，主视觉占 40–60% 画面
- **动作等台词**：t=0 只上旁白正在说的内容，其余元素各等自己的 cue；禁 front-load、禁无限循环、
  禁 CSS transition/animation、禁 `Math.random`
- 内容下缘 ≤ `0.83 × 高`（1080p 用 816），底部留给字幕

生成方式二选一：

- **自己写**（推荐单帧修改、少帧数）：按上面的契约直接写，快且可控
- **派子代理**（8 帧以上、追求并行）：每帧一个 worker，任务里给 packet 路径 + 本技能的
  `references/composition-contract.md`，禁止它去读 hyperframes 技能文档。
  注意：**pi-web 宿主不支持后台/并行子代理**（报 `Background children require a supported
  standalone Pi host`），阻塞式子代理又会被用户的新消息打断——长任务优先自己内联做，
  或拆成小串行块

帧做好后同步时长（改过配音就必跑）：

```bash
python <SKILL_DIR>/scripts/sync_frame_durations.py --project <PROJ>
```

## 5 · 组装、检查、渲染

```bash
cd <PROJ>
npx hyperframes lint         # 0 error 才能继续；warning 里 id_override_reduced_specificity 可忽略
npx hyperframes check        # 硬门槛：runtime / layout / contrast
node <SKILL_DIR>/scripts/look.mjs .        # 我自己的"眼睛"：双遍确定性 + 文字被裁 + 纯色帧 + 音频处方 + 接触表
npx hyperframes snapshot --at <各帧中点>   # 出 contact-sheet，自己先看一眼再渲染
npx hyperframes render --quality high --output renders/video-v2.mp4
```

**`look.mjs` 与 `snapshot` 的分工**：snapshot 给你一张能看的图；`look.mjs` 把"图画得对不对"变成可断言的检查，
渲染前 15 秒跑完，能拦住 lint/check 拦不到的一整类错：

| 检查 | 拦的是什么 | 分不清就要返工的典型症状 |
| --- | --- | --- |
| 双遍乱序确定性 | 同一 `t` 画出两幅不同的画 | `onUpdate` 里用了 `Math.random`/`Date.now`、两次渲染结果不一样、抽帧对不上 |
| 文字被裁 | 出画框 / 被 `overflow:hidden` 父盒切掉 | 字幕长了一行就被切、标题撞边、`snapshot` 缩略图看不清的细裁 |
| 纯色帧 | 场景中点整幅画是空的 | "第 2 帧整帧空白"（历史头号事故） |
| 语音 vs 帧时长 | 语音比所属场景长 | 话没说完画面就切了 |
| 音频处方 | 音轨峰值 / 人声与 BGM 落差 / 整片 LUFS 与真峰 | 配音被 BGM 盖、手机外放听不清、转 AAC 削波 |

三种用法，按时间预算挑：

```bash
node scripts/look.mjs . --fast      # 0.5 秒：只跑时间轴体检 + 音频处方（改完配音先跑这个）
node scripts/look.mjs .             # 15 秒：加上浏览器双遍 + 文字裁切 + 接触表
node scripts/look.mjs . --at 12.5   # 只盯某一帧
```

零 npm 依赖：复用 hyperframes 自带的 `puppeteer-core` 与 `chrome-headless-shell`，并自己注入
`hyperframe.runtime.iife.js`（index.html 本身不带 runtime，`window.__player.seek(t)` 是真正的定位入口）。
退出码：`0` 无错误 / `1` 有错误 / `2` 脚本崩了。

- 组装：用 workflow 的 `assemble-index.mjs`（需要 STORYBOARD.md 的每帧 duration/src），
  转场用 `transitions.mjs inject|verify`；或沿用上一次项目的这两步命令
- **渲染前必看快照**：第 2 帧整帧空白、CTA 淡出落在时长之外、字幕错位这些错，
  快照一眼就能看到，渲染之后才发现就要多花 2 分钟
- 覆盖式重渲**不要覆盖**已交付的文件名：先渲 `video-vN.mp4`，确认后再拷成最终文件名，
  旧版本留在 `renders/` 方便 A/B

## 6 · 交付与回访

- 交付物：成片 MP4 + 预览快照 jpg（+ 音色样本、工程目录）。微信渠道用 `send_file_to_wechat` 发文件
- 报告里给：时长、画幅、帧清单、**哪里做了取舍**（例如"为了连贯把总长从 1:57 收到 1:43"）
- 用户说"配音不好听/字幕断句不对"时的定点修法：
  - 换音色 → 只重跑 2.2（带 `--target-durations`）+ 2.4 + 组装 + 渲染，画面零改动
  - 改断句 → 只重跑 3
  - 改台词 → 2.2 + 3，并回看该帧卡点是否需要微调
  - 改一帧画面 → 只改该帧 + 组装 + 渲染（`--frames` 分帧渲染更快，若 CLI 支持）

## 省 token 的六条

1. **别读重型技能**：hyperframes/faceless-explainer/product-launch 那套只在需要 registry、3D、
   调色、幻灯片时进；常规讲解片读 `references/composition-contract.md` 足够
2. **同构帧走数据驱动**：`story.json` → `story_build.py` 一次出全片（实测 7 帧同类短片省下
   大段逐帧手写；同构帧的样板代码、cue 查找、多样性检查全由脚本承担）
2. **别读脚本源码**：`audio_meta.json` 的结构、`captions.html` 的可替换点在契约文档里写好了；
   真要读源码，用 grep 定位而不是整篇读
3. **脚本文件是唯一真相源**：台词/时长/断句都从这里推导，避免在多个文件间同步同一信息
4. **先音频后画面**：时间轴定死再画，省掉"帧时长变了要改所有卡点"的连锁返工
5. **固定参数不要现场试**：head/tail、字幕分组、BGM 参数、音色都已给默认值
6. **快照先于渲染**：一次渲染 ≈ 2 分钟，一次快照 ≈ 20 秒，能拦下大半返工
7. **`look.mjs --fast` 比渲染便宜两个数量级**：改完配音、改完帧时长，先跑它，红了就别渲

## 目录

- `references/composition-contract.md` — HyperFrames 合成契约压缩版（写帧前读这一份）
- `references/script-craft.md` — 中文解说稿写法、多音字规避、表情标注
- `references/pitfalls.md` — 已踩过的坑与解法（报错时再读）
- `examples/pi-skills-story.json` — 一份可直接改用的 story.json 示例（7 帧 / 65s）
- `scripts/preflight.py` — 环境一次体检
- `scripts/look.mjs` — 项目的"眼睛"：时间轴体检 + 音频处方 + 双遍确定性 + 文字裁切 + 接触表（`--fast` 只跑前两项）
- `scripts/story_build.py` — story.json → SCRIPT.md + STORYBOARD.md + 全部帧（数据驱动主入口）
- `scripts/frame_kit.py` — 帧原型库（kinetic-hook / card-row / panel-demo），含 cue 自动解析与多样性检查
- `scripts/tts_lines.py` — 逐句配音 + 时间戳 + 拉伸对齐 + audio_meta
- `scripts/verify_pronunciation.py` — whisper 读音校验
- `scripts/captions_clauses.py` — 按句断句的字幕
- `scripts/bgm_synth.py` — 无版权配乐合成
- `scripts/new_frame.py` — lint-clean 的帧骨架（手写单帧时用）
- `scripts/fix_ids.py` — id 前缀安全修复（含 getElementById 同步）
- `scripts/sync_frame_durations.py` — 帧时长同步
