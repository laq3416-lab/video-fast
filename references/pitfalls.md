# 已知坑与解法（报错时再读）

按"症状 → 原因 → 解法"记。带 lint/check 代码的可以直接搜代码。

## 合成与渲染

**整帧空白，只有字幕在动**
元素 id 以数字开头（`id="03-hands-on-panel"`）+ JS 用 `document.querySelector("#03-hands-on-panel")`
→ 选择器非法抛异常 → 时间轴构建中断 → 先建好的 `fromTo` 已经把元素留在 `opacity:0`。
解法：id 一律字母开头（约定 `f` 前缀），跑 `scripts/fix_ids.py` 一次修全项目。

**批量改 id 后某几帧仍然空白**
`document.getElementById("03-meet-pi-text")` 这类**字符串**没跟着改（属性改了、字符串没改 → 取到 null）。
`fix_ids.py` 会同步处理 `id="…"`、`#…` 选择器、`getElementById("…")`，并且**不动** `data-composition-id`。

**`timeline_id_mismatch`**
`window.__timelines["x"]` 的键与根的 `data-composition-id` 不一致（常见于改 id 时误伤
`data-composition-id` 的尾部）。运行时不会嵌套该时间轴 → 画面停在初始态。

**`root_missing_composition_id` / 整帧无样式**
前者是根没写 `data-composition-id`；后者多半是给根加了 class 再写样式——渲染时类被作用域化后匹配不到，
**预览正常但成片无样式**。根样式写 `#root`。

**`css_transition_used` / 动效抖动跳帧**
用 CSS transition/@keyframes 驱动动效。帧是被 seek 的暂停时间轴，浏览器时钟与它不同步。
改用 GSAP 补间；抖动用有限的往返两段，不要 `repeat`/`yoyo`。

**`gsap_relative_value_second_writer`**
`y: "-=3"` 后面又 `y: "+=3"`。改绝对值（`y: -3` → `y: 0`）；需要基于原位的用变量算出目标值。

**`gsap_css_transform_conflict` / 元素位置突然跳**
元素用 CSS `transform` 居中（`translateY(-50%)`），又被 GSAP 动 `x/y/scale`：GSAP 覆盖整个
`transform`，居中丢失。用 `margin`/`inset` 定位，或折进 `xPercent`/`yPercent`。

**`font_family_without_font_face`**
用了系统字体名（`Microsoft YaHei` 等）。渲染机是干净 headless Chrome，系统字体一律不可用。
把 TTF 拷进 `assets/fonts/` 并在**每个帧文件内**内联 `@font-face`；路径 root-relative，写 `../` 会 404。

**深色内容在成片里消失**
全幅底色画在 `#root` 上。根在组装时被裁到自己的时间窗，底色不可靠 → 用独立 `class="clip"` 背景层。

**`content_overlap`（check error）**
字块重叠被判定不可读。若是**刻意**（旧词残影 + 新词替换、叠字效果），在元素或场景内层容器上
加 `data-layout-allow-overlap`——加在场景根上无效。若非刻意，给两块各自的位置。

**`text_box_overflow`（check info/warning）**
字溢出容器。字幕高亮词的 1–4px 溢出是已知误报（不要为了提高 line-height 把字幕气泡撑大）；
帧内元素溢出才需要调容器或字号。

**对比度不足**
浅色小字（`alpha 0.42~0.5`）在奶油底上不够。加深到 0.64 左右即可，别动背景色。

**帧时长缩短后结尾的淡出没发生**
淡出（或任何末段动作）的时间点写死在旧时长里，超过了新的 `data-duration`。改过配音后，
末帧的动作时间要用“时长 − 0.85”这类表达式给。

## 音频

**一句话说完冷场两秒**
edge-tts 每段尾部自带约 0.9s 静音，再叠加你设的 tail 和下一帧的抬头静音。
解法：`tts_lines.py` 会按最后一个词的结束时间裁尾（`atrim`），再用 `adelay`+`apad` 精确铺满帧长。

**换了音色/改了台词，画面卡点全错位**
分镜的 cue 时间是基于上一版词级时间戳写的。解法：传 `--target-durations`（上一版逐帧语音时长），
工具用 ffmpeg `atempo` 把新配音拉伸回原时长，卡点无需改动。声画同步的根因是"帧内相对时间"，
拉伸保持了这个映射。

**配音听起来平、没感情**
默认音色偏播报。换音色（中文推荐 `zh-CN-YunxiNeural` 阳光男声 / `zh-CN-XiaoxiaoNeural` 温暖女声 /
`zh-CN-YunyangNeural` 沉稳男声），并逐句加 `rate ±4% · pitch ±4Hz`。给出 2–3 个样本让用户挑，
比全片渲完再换便宜得多。

**"调"被读成 diào、"只"读成 zhī 之类**
换词（调 → 定/设定）。校验用 whisper 转写回文字；注意 whisper 自己也有同音误判，只改真有歧义的。

## 字幕

**字幕一蹦一跳、断句碎**
workflow 自带 captions.mjs 按"每秒词密度"切组，中文常见语速下每组只装 2 个词（实测 219 词 → 108 组）。
改用 `captions_clauses.py`：按脚本标点切从句（同例 47 组、平均 7 字）。判断标准是"能不能一口气读完"。

**字幕位置太高/太低**
默认字幕带 = 底部 16.67%（1080p 下 top=900）。要"画面中下方"用 836。
组装/重建字幕会重置该值，改完 captions.html 后要复检。

**字幕词间空得太开**
皮肤里 `.caption-line` 的 `gap` 默认 `0.12em 0.3em` 是按拉丁词距设的；中文用 `0.06em 0.16em`。

## 流程与环境

**`Background children require a supported standalone Pi host`**
pi-web 宿主不支持后台/并行子代理。改为内联自己写，或串行派发小块任务。

**子代理跑到一半 `Request was aborted`**
阻塞式子代理会被用户的新消息打断。长任务优先内联，或拆成能在一次消息间隔内完成的块。

**帧包超过 48KB 上限**
打包脚本会把该帧引用的蓝图正文 + 每条动作配方全文内联。分镜里出现过多规则 id 就会爆。
解法：分镜正文只写动作名不写规则 id，规则改用显式 `- rules:` 字段点名 2–3 条。

**Python 控制台 `UnicodeEncodeError: 'gbk' codec`**
Windows 控制台默认 GBK。运行脚本加 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`，脚本内避免 `✓` 之类字符。

**edge-tts 连接失败**
必须走代理：`edge_tts.Communicate(..., proxy="http://127.0.0.1:7897")`（环境变量对它无效）。

**whisper 模型找不到**
模型在 `C:\Users\zz\.cache\hyperframes\whisper\models\ggml-large-v3-turbo.bin`，
`C:\Users\zz\whisper.cpp\models\` 可能是空的。另外 whisper-cli 读不了 mp4，先用 ffmpeg 抽成 16k 单声道 wav。

**渲染耗时**
1080p/30fps 约为成片时长的 1.0–1.2 倍（本机硬件 GPU）。一次 1:43 的片子约 105 秒。
所以"先快照后渲染"很划算：快照 20 秒能拦住大半返工。

## 模板化（frame_kit / story_build）专属坑

**某元素永远不出现，其他元素正常**
入场助手只写了起始态、没写目标态（`.fromTo(el, {scale:0}, {opacity:1})` → scale 永远停在 0）。
`frame_kit` 的 `at()` 现在会从 props 推断目标值（scale→1、x/y→0）；自己写帧时也要显式写目标态。

**整帧空白、根元素都不见了**
生成器漏了 `#root` / `data-composition-id` / 背景 `class="clip"`。模板必须把这三样作为固定骨架输出，
不能只输出内容片段。（这就是"修一次、所有帧受益"的意义。）

**JS 里残留 `{{scale: 0}}` 这种双花括号**
Python 里 f-string 需要 `{{}}` 转义，普通字符串不需要。混用时模板会写出非法 JS（lint 报
`invalid_inline_script_syntax`）。占位符替换也要在**最终整篇文档**上做一次，别用 `str.format`——
内联 JS/CSS 全是花括号。

**卡片行跑到画外**
一排卡片要按总宽居中/限右边距（3 张 330 + 2×40 间隙从 860 起就超出 1920）。模板现在会算
`left0 = max(左侧题名位置, (1920-总宽)/2)` 并保证右缘 ≤1860。

**字幕合成不挂载（整片无字幕）**
独立字幕皮肤里 `data-duration="0"` / `data-width="0"` 会让运行时直接跳过这个合成。
必须写真实时长与画布尺寸（`captions_clauses.py` 已修）。

**子合成里 `getBoundingClientRect()` 量到的位置是错的**
挂载可能带缩放，视口坐标会把元素带到画外。用布局坐标（`offsetLeft/offsetTop` 沿 offsetParent 链）——
光标、连线、指示器都适用。

**屏幕文案读起来是病句**
不要把词级时间戳的碎片按顺序拼成句子（曾拼出"说一句哪个就行"）。屏幕文案按你要表达的句子写，
时间戳只用来定 reveal 时刻。

**同一原型连着几帧，看着像幻灯片**
`story_build.py` 会检查相邻同原型与强构图占比并提示。同原型也要换布局（卡片数、尺寸、pill 形态）；
实在只能同原型，就让两帧的元素构成差得足够远。

## 检查与工具链（look.mjs 相关）

**想自己驱动 HyperFrames 页面截图/定位，`window.__hf` 一直拿不到**
`index.html` 本身**不带 runtime**——`window.__hf` / `window.__player` 是 hyperframes 在渲染或预览时
注入 `dist/hyperframe.runtime.iife.js` 之后才出现的，而且 `__hf.seek` 是个 getter，没有控制桥（父页面
postMessage）时永远返回 `undefined`。
正确入口：`page.addScriptTag({ content: readFileSync(<hyperframes>/dist/hyperframe.runtime.iife.js) })`
→ 等 `window.__player.getDuration() > 0` → `window.__player.pause(); window.__player.seek(t)`。
`look.mjs` 已经封好，不用重写。

**导航用 `waitUntil: 'load'` 会卡 30 秒甚至超时**
带 `data-duration` 的 `<audio>`/`<video>` 预取会把 load 事件拖住。用 `domcontentloaded`，
真正的就绪判断交给 `window.__player` / `window.__timelines` 的轮询。

**只 seek `__timelines['main']`，子合成还是黑屏**
主时间轴不驱动子合成时间轴；`data-composition-src` 的子合成由 runtime 挂载后各自有独立 timeline
（`__timelines['01-hook']` 等）。要么用 `__player.seek`，要么逐个 `seek(t - data-start)`——后者迟早写错。

**双遍确定性报红，但我的代码里没有 Math.random**
真凶通常是 `onUpdate` 回调里改样式、`Date.now()` 算进度、或是第二次 seek 时上一条 `fromTo` 的
`immediateRender` 状态残留。GSAP 的 `to(el, {x: () => Math.random()})` **不会**触发（函数值在 tween
创建时就求值了），所以报红说明状态确实每帧都在变，按上面三条找。

**文字裁切检查依赖"当前在播的场景"**
hyperframes 把所有子合成内联进主文档，非当前场景靠 `opacity` 隐藏。`look.mjs` 只扫 `data-start ≤ t < 结束`
的那几个场景根，并且跳过 `opacity < 0.05` 的节点——所以"字还在入场途中"不会误报，但**同一场景里
被时间轴藏起来又显示出来的旧字幕**要确认它的容器真的被隐藏了。

## 竖版与重配音（抖音实战新增）

**`--target-durations` 传了帧长，总长反而变了**
它期望的是**语音轴长度**（帧长 − head − tail − 0.05，默认即帧长 − 1.45），不是帧长。
换算公式：`target = 上次帧长 − 1.45`（head/tail 用默认值时）。传错不会报错，只会安静变长。

**re-voice 之后画面 cue 对不上了**
atempo 拉伸是均匀的，词时间戳会有 ±0.1~0.8s 漂移。re-voice 后**必须**拿新 audio_meta
核对每帧的关键 cue 词（改一个字/焊死这类落点词），漂移 >0.1s 就 patch 帧里的时刻数字。

**TTS 失败后千万不要在原文件上叠加处理**
alimiter 处理完 mv 覆盖原 wav，第二次 TTS 失败后又对同一文件叠 gain → 双重限幅，人声发闷。
规矩：原始配音留着（`-raw` 后缀），响度处理总是从 raw 一遍过；TTS 网络失败就重试
（7897 抖就等 30s，或换 7899），别动已处理的文件。

**人声"没感情"的常见原因是语速，不是音色**
rate +6~9% 会赶出机器味。经验档：钩子 +5%、讲解 +2~4%、CTA +3~4%，pitch 回 0 附近；
感情靠逐句梯度，不靠整体加速。

**BGM 听着诡异**
tech（小调 120bpm 驱动感）提音量后会阴郁。招生/介绍片用 uplifting（大调 108bpm），
data-volume 0.28–0.34；人声比 BGM 高 13–15 dB。

**样式选择器 `[id="x-panel"]` 与元素实际 id 不匹配 → 整块不渲染，lint/check 都不报**
黑底黑字等于隐形。lint 查语法不查"选择器有没有命中元素"；接触表（`look.mjs` 或 snapshot）
是唯一能看见这类错误的地方。写 CSS 时先确认选择器和 id 一一对应。

**`captions_clauses.py` 每次重跑都会重写 captions.html**
`--band-top`、手改的字号/字体/颜色全部回默认。重跑后要重新打补丁——把补丁写进
重建命令一并跑，别手工改完就以为一劳永逸。

**竖版（抖音 1080×1920）**
`frame_kit.py`/`story_build.py` 是 16:9 写死的（1920 宽度、卡片坐标全部硬编码），竖版必须
手写帧。字幕带 `--band-top 1560`，正文字幕 52px；内容下缘 ≤1500px。转场用硬切（抖音节奏），
帧内自带动效就够。index.html 需要手动注册 `__timelines["main"]`（组装脚本只管 16:9 模板）。

**字幕跨帧合并：一句话被切成两帧时，气泡会横跨两个镜头**
`captions_clauses.py` 的短组合并只看 MIN_CHARS，不看帧边界：F10 结尾的「配音」会和 F11 开头的
「字幕、配乐」合成一组，字幕在错误画面上出现 1–2 秒。已修（合并前比 `frame_of()`，跨帧不合并）；
旧版本遇到这现象就手改 `caption_groups.json` 再生成。检查办法：打印每组 `frame/start/text`，
看有没有一组的 `start` 落在两帧交界处而 `text` 跨了两句台词。

**竖版快节奏版（抖音去同质化）配方**
同一题材重做、平台判「雷同」限流时，换掉的不只是配色，是这四层一起换：

1. **视觉系统**：暖纸 `#F2E9DA` + 墨黑 `#121110` + 电蓝 `#2B3AFF` + 热橙 `#FF4B1F` + 荧光黄 `#FFE24B`；
   思源宋体 900 做巨型标题（编辑部/大字报感），黑体 800 做标签，等宽体做时间码。贴纸＝白底＋5px 黑边＋
   12px 硬阴影；印章＝8px 双线红框；不要渐变、不要发光、不要漂浮粒子。
2. **节奏**：14 个镜头 2.2–4.2s（旧版 7 个 × 8–11s 就是"PPT 感"的来源）。每个 0.2–0.6s 一个动作点，
   t=0 只上旁白正在说的内容。
3. **变速预期差**：在痛点句处让 BGM 硬停 0.3s + 一帧近黑画面（只留低频心跳），下一帧 drop 回来。
   这是抖音"快切之后突然静止"的留人技巧，比全程嗨更抓人。
4. **自证镜头**：讲完能力后插一帧「这条片子，就是它做的」——比任何功能列表都可信。

配套：音效（whoosh/impact/tick）用 numpy 合成后**混进 BGM 轨**的切点位置，不新增 audio 元素，
时间轴和画面天然同步；响度在渲染后用 ffmpeg `loudnorm=I=-14:TP=-1.5` 压一次，`aresample=44100`
（HyperFrames 渲染出的 AAC 可能是 96k，手机端兼容性差）。

**批量改帧坐标后必须 grep 生成文件**
`build_v2.py` 这类生成器里，源字符串是 `[id="f06-c1"]{...}`，而生成后会被正则改成 `#f06-c1{...}`；
用 `#f06-c1` 去 patch 源代码会**静默不命中**，坐标没变但构建照常成功，只有抽帧才看得出来。
规矩：每次批量替换后 `grep -oE '#f06-c1\{[^}]*\}' compositions/frames/*.html` 核对一遍实际值。
