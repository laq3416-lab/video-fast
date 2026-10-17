# HyperFrames 合成契约（压缩版）

写帧之前读这一份就够。它替代 `hyperframes` / `hyperframes-core` / `faceless-explainer` 的常规阅读；
只有需要 registry 积木、3D、着色器、媒体调色时才回退到那些技能。

## 1 合成文件形状

一个帧 = 一个 HTML 文件，内容**只有一个 `<template>` 片段**：首字节是 `<template`，末尾是 `</template>`。
不要 `<!doctype>`、`<html>`、`<head>`、`<body>`，也不要模板之外的任何标记。

```html
<template>
<script src="assets/vendor/gsap.min.js"></script>   <!-- 本地，勿用 CDN -->
<style>
  /* @font-face 全部内联（见 §5） */
</style>
<style>
  #root { position: absolute; inset: 0; overflow: hidden; container-type: size; }
  [id="f03-hands-on-bg"] { position: absolute; inset: 0; background-color: #FAF9F5; }
  [id="f03-hands-on-title"] { position: absolute; left: 0; right: 0; top: 150px; text-align: center; }
</style>

<div id="root"
     data-composition-id="03-hands-on"
     data-start="0" data-duration="11.47"
     data-width="1920" data-height="1080">
  <div class="clip" id="f03-hands-on-bg" data-start="0" data-duration="11.47" data-track-index="0"></div>
  <div id="f03-hands-on-title">真的动手</div>
</div>

<script>
  (function () {
    var tl = gsap.timeline({ paused: true });
    tl.fromTo("#f03-hands-on-title",
      { opacity: 0, y: 18 }, { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }, 0.3);
    tl.to({}, { duration: 0.01 }, 11.46);          // 锚点：让时间轴铺满整段
    window.__timelines["03-hands-on"] = tl;        // 必须注册，键 = data-composition-id
  })();
</script>
</template>
```

要点：

- **`data-composition-id` 必须与 `window.__timelines[...]` 的键、文件名一致**，否则运行时无法嵌套时间轴
  （lint 报 `timeline_id_mismatch`），画面会停在初始态
- 时间轴**只有一条**、`paused: true`、同步构建（异步里构建也可以，但注册要在构建完成后）
- 渲染长度取根的 `data-duration`，不是时间轴长度：短了会截断，长了会停最后一帧
- `window.__timelines` 由运行时预建，不必自己初始化

## 2 data-* 与 clip

| 属性 | 归属 | 说明 |
| --- | --- | --- |
| `data-composition-id` | 根 | 子合成标识，等于帧 id |
| `data-start` / `data-duration` | 根、`class="clip"` | 根写 `0` / 帧长；clip 写自己的窗口 |
| `data-width` / `data-height` | 根 | 画布尺寸，1080p 为 1920/1080 |
| `data-track-index` | `class="clip"` | 同轨不重叠，异轨可叠加 |
| `data-media-start` | 视频/音频 clip | 素材内起点（掐头） |
| `data-volume` | 音频 | 0–1 |

- **全幅底色/网格/渐变必须放在一个 `class="clip"` 的背景层上**，不要画在 `#root` 上：
  根在组装时被裁到自己的时间窗，画在根上的底色不可靠，深色内容会落到宿主黑底上
- clip 元素的三个属性缺一不可（`data-start` / `data-duration` / `data-track-index`）

## 3 样式与选择器

- 根样式写在 `#root` 规则里，**不要**给根加 class 再写 `.xxx`：渲染时类被作用域化后匹配不到，
  整帧会变成无样式（预览里看不出来，别信预览）
- **元素 id 用字母开头**（本项目约定 `f<帧号>-<帧名>-<元素>`）：
  以数字开头的 id 会让 `querySelector('#03-x')` 抛 SyntaxError、CSS 规则静默失效
- 尺寸单位用 `cqw`/`cqh`（配合根的 `container-type: size`）或 px；**不要用 `vw`**
- 自定义 id、容易被复用的 class 都带帧前缀，避免多帧组装后互相污染

## 4 动效（seek-safe）

帧是被逐帧 seek 的暂停时间轴，下面这些不是风格偏好，是硬约束：

- 入场用 `fromTo`（显式写起始态），不要依赖 CSS 初始隐藏——那样 seek 到 0 会闪
- 禁 `repeat` / `yoyo` 无限循环；需要的"活着的感觉"用有限的来回两段补间实现
- 禁 `Math.random` / `Date.now`：每次渲染必须完全相同
- 禁 CSS `transition` / `@keyframes` 驱动动效（浏览器时钟与 seek 时钟不同步，会跳）
- 一个元素不要既用 CSS `transform` 定位又用 GSAP 动 transform 属性：GSAP 会整体覆盖
  `transform`，定位被丢掉。用 `margin`/`inset` 定位，或把偏移折进 `xPercent`/`yPercent`
- 抖动不要用相对值（`y: "-=3"` 再 `"+=3"`），lint 报 `gsap_relative_value_second_writer`；
  用绝对值（`y: -3` → `y: 0`）
- 缓动默认长尾（`power3.out` / `expo.out`），禁 `back`/`bounce`/`elastic` 式回弹
- 每个元素只做**入场**，不做退场：帧的退场由组装时的转场负责；只有最后一帧可以有淡出
- 首屏元素 0.5s 内可见

## 5 字体

渲染机是干净的 headless Chrome，**系统字体名一律不可用**（`Microsoft YaHei`、`PingFang` 等写了等于没写，
lint 报 `font_family_without_font_face`）。做法：把字体文件放进 `<PROJ>/assets/fonts/`，
在**每个帧文件内**内联 `@font-face`。

本机现成可用的字体：

| 用途 | 文件 | 来源 |
| --- | --- | --- |
| 中文展示/正文 | `NotoSerifSC-VF.ttf` / `NotoSansSC-VF.ttf` | 从 `C:\Windows\Fonts\` 拷进项目（可变字重 100–900） |
| 拉丁展示 | `EBGaramond-400/500.woff2` | Google Fonts latin 子集（走代理下载） |
| 拉丁正文 | `Inter-400/500/600.woff2` | 同上 |
| 等宽/代码 | `JetBrainsMono-400/500.woff2` | 同上 |

```css
@font-face { font-family: 'Noto Serif SC'; font-style: normal; font-weight: 100 900;
             font-display: swap; src: url('assets/fonts/NotoSerifSC-VF.ttf') format('truetype'); }
```

- 资源路径一律 **root-relative**（`assets/fonts/...`）：子合成以项目根为 base URL，写 `../` 会 404
- 字体族栈示例：`"EB Garamond", "Noto Serif SC", serif`、`"Inter", "Noto Sans SC", sans-serif`、
  `"JetBrains Mono", "Noto Sans SC", monospace`

## 6 版式与留白

- **字幕带占底部约 17%**：1080p 下内容下缘 ≤ 816px（本项目字幕带上移到 836px 起，内容仍按 816 规划）；
  背景/环境层可全幅
- 主视觉占画面 40–60%，不要一个小簇飘在空处；构图至少 3 层（背景/中景/主体）
- 层次靠"尺寸 3:1 + 字重 + 位置（上三分之一最好用）"组合，不要只靠"更大"区分主次
- 相邻帧换构图模板（居中 → 60/40 → 全宽），别十帧一个样
- 屏幕上写短标签/关键词/数字/公式；**不要印旁白整句**

## 7 组装与转场

项目根：`STORYBOARD.md`（每帧 `duration` 与 `src`）、`index.html`（组装产物）、`compositions/frames/*.html`、
`compositions/captions.html`、`assets/`。

- 组装脚本按 STORYBOARD 的帧序与时长生成 `index.html`，把每帧挂到自己的轨道并附上配音 `<audio>`
- 转场注入脚本按每帧 `transition_in` 写 tween：`cut | crossfade | blur-crossfade | push-slide LEFT/RIGHT/UP/DOWN | zoom-through | squeeze`
- 全片挑 2–3 种转场重复用；单帧 push-slide 的位移量与时长要一致，否则看起来像不同作品
- 转场会给帧加尾部 padding，帧自身的 `data-duration` 要与之一致（`sync_frame_durations.py` 负责）

## 8 质量门

| 命令 | 作用 | 门槛 |
| --- | --- | --- |
| `npx hyperframes lint` | 结构/选择器/字体/动效规则 | 0 error。`id_override_reduced_specificity` 之类 warning 可忽略 |
| `npx hyperframes check` | runtime JS 错误 + 版式重叠/溢出 + 对比度 | 必须 pass |
| `npx hyperframes snapshot --at a,b,c` | 抽帧合成 contact-sheet | 渲染前必看 |
| `npx hyperframes render --quality high -o renders/video.mp4` | 出片 | 1080p/30fps 约 1.2× 实时 |

常见 check 报错与解法：

- `content_overlap`：字块重叠被判不可读。**刻意的**叠字（例如旧词残影 + 新词替换）在元素或
  场景内层容器上加 `data-layout-allow-overlap`；加在场景根上无效
- `text_box_overflow`：字溢出容器，调整容器或字号；对字幕高亮词的 1–4px 溢出属已知误报，忽略
- 对比度不足：靠加深浅色文字（例如 `rgba(20,20,19,0.45)` → `0.64`）解决，别改背景

## 9 音频侧数据（audio_meta.json）

```jsonc
{
  "bgm": { "path": "assets/bgm/track.wav", "volume": 0.14, "duration_s": 107.3, "source": "host" },
  "bgm_pending": false,
  "voices": [
    { "frame": 1, "path": "assets/voice/01.wav", "duration_s": 6.64, "source": "host",
      "words": [ { "id": "w0", "text": "如果", "start": 0.61, "end": 0.9 } ] }   // 帧内相对时间
  ],
  "sfx": []
}
```

- `duration_s` 就是该帧的画面时长；`words` 为帧内相对时间（含 0.5s 抬头静音）
- 字幕时间 = 帧起点 + 帧内词时间；帧起点 = STORYBOARD 中前面各帧时长累加
- BGM 时长 ≥ 全片时长 + 2s（合成时留出收尾淡出）
- 自己合成的音频标 `"source": "host"`，workflow 的音频脚本会保留它们、不会覆盖
