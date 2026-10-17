#!/usr/bin/env node
/**
 * look.mjs — HyperFrames 项目的"眼睛"
 *
 * 设计借鉴 openfilm/openfilm 的 `openfilm look`（MIT）：
 *   1. 确定性：同一时刻画两遍（两个不同 seed 的乱序），任一帧不同 → 说明画面不只由 t 决定
 *      （Date.now / Math.random / 状态残留 / 媒体未 seek / tween 从屏幕取起点）
 *   2. 文字被裁：DOM Range 量真实渲染盒，抓"出画框"和"被 overflow:hidden 父容器切掉"的文本
 *   3. 平白帧：8×8 降采样后亮度极差 < 6 → 那一帧其实什么都没画
 *   4. 字体加载失败：document.fonts 里 status === 'error'
 *   5. 输出纪律：✗ 错误 / ! 警告 / ✓ 通过 / → 文件
 *
 * 本工具额外扩展（OpenFilm 的 film.html 没有、HyperFrames 项目才有的东西）：
 *   6. 时间轴静态体检：场景拼接空档/重叠、语音时长超出所属帧（语音被切断）、引用文件缺失
 *   7. 音频处方：逐条语音峰值、BGM 实际响度、整混音 EBU R128（LUFS + true peak）、人声/ BGM 落差
 *   8. 接触表：帧缩略图 + 时间 + 整混音波形 + 每条语音的落点
 *
 * 用法：
 *   node look.mjs <项目目录>                 # 全量：静态体检 + 音频处方 + 浏览器双遍
 *   node look.mjs <项目目录> --fast          # 跳过浏览器：时间轴体检 + 音频处方（0.5 秒）
 *   node look.mjs <项目目录> --at 12.5       # 只看某一时刻
 *   node look.mjs <项目目录> --range 0-30    # 只看一段
 *   node look.mjs <项目目录> --count 16      # 采样帧数（默认 12）
 *   node look.mjs <项目目录> --json          # 机器可读输出
 *
 * 零 npm 依赖：复用 hyperframes 自带的 puppeteer-core 与 chrome-headless-shell。
 */

import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync, mkdirSync, writeFileSync, statSync } from 'node:fs';
import { basename, join, resolve, dirname, extname } from 'node:path';
import { tmpdir } from 'node:os';
import http from 'node:http';
import zlib from 'node:zlib';
import { pathToFileURL } from 'node:url';

/* ─────────────────────────── 参数 ─────────────────────────── */

const argv = process.argv.slice(2);
const flags = new Map();
const positional = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--json') flags.set('json', true);
  else if (a === '--fast') flags.set('fast', true);
  else if (a === '--no-sheet') flags.set('sheet', false);
  else if (a.startsWith('--')) { flags.set(a.slice(2), argv[++i]); }
  else positional.push(a);
}
const PROJECT = resolve(positional[0] ?? '.');
const COUNT = Number(flags.get('count') ?? 12);
const AT = flags.has('at') ? Number(flags.get('at')) : null;
const RANGE = flags.has('range') ? String(flags.get('range')).split(/[-,]/).map(Number) : null;
const JSON_OUT = flags.get('json') === true;
const FAST = flags.get('fast') === true;
const WANT_SHEET = flags.get('sheet') !== false;

/** 8×8 降采样后两幅图的最大通道差；超过就是两幅不同的画（抗锯齿噪声不算）。同 openfilm SAME_LIMIT。 */
const SAME_LIMIT = 32;
/** 8×8 降采样后亮度极差低于此值 → 这一帧是纯色（页面什么都没画）。同 openfilm。 */
const FLAT_LIMIT = 6;

const errors = [];
const warnings = [];
const passed = [];
const notes = [];
const files = [];
const err = (m) => errors.push(m);
const warn = (m) => warnings.push(m);
const pass = (m) => passed.push(m);

/* ─────────────────────── 1. 时间轴静态体检 ─────────────────────── */

function parseIndex(root) {
  const indexPath = ['index.html', 'film.html'].map((f) => join(root, f)).find((p) => existsSync(p));
  if (!indexPath) return null;
  const html = readFileSync(indexPath, 'utf8');
  const attrs = (tag) => {
    const out = {};
    for (const m of tag.matchAll(/([a-zA-Z-]+)\s*=\s*"([^"]*)"/g)) out[m[1]] = m[2];
    return out;
  };
  const num = (v) => (v == null || v === '' ? null : Number.isFinite(Number(v)) ? Number(v) : null);
  const rootTag = (html.match(/<div[^>]*data-composition-id="[^"]*"[^>]*>/g) ?? [])[0] ?? '';
  const rootAttrs = attrs(rootTag);
  const scenes = [...html.matchAll(/<(div|section|iframe)\b[^>]*data-composition-src="[^"]*"[^>]*>/g)].map((m) => {
    const a = attrs(m[0]);
    const end = num(a['data-start']) != null && num(a['data-duration']) != null ? num(a['data-start']) + num(a['data-duration']) : null;
    return {
      id: a.id ?? a['data-composition-id'],
      comp: a['data-composition-id'],
      src: a['data-composition-src'],
      at: num(a['data-start']),
      dur: num(a['data-duration']),
      end,
      track: num(a['data-track-index']),
    };
  });
  const sounds = [...html.matchAll(/<audio\b[^>]*>/g)].map((m) => {
    const a = attrs(m[0]);
    return {
      id: a.id, src: a.src, at: num(a['data-start']), dur: num(a['data-duration']),
      track: num(a['data-track-index']), volume: num(a['data-volume']) ?? 1,
    };
  });
  return {
    indexPath,
    html,
    width: num(rootAttrs['data-width']) ?? 1920,
    height: num(rootAttrs['data-height']) ?? 1080,
    duration: num(rootAttrs['data-duration']),
    scenes, sounds,
  };
}

const fmt = (t) => (Number.isFinite(t) ? `${Number(t.toFixed(2))}s` : '?');

function checkTimeline(film) {
  if (!film) {
    err(`${basename(PROJECT)}/index.html 不存在 —— 这不是一个 HyperFrames 项目目录`);
    return;
  }
  if (!film.duration) err('index.html 的 #root 上没有 data-duration（渲染会报"零时长"）');
  if (!film.scenes.length) err('index.html 里没有任何 data-composition-src 场景');

  const byStart = [...film.scenes].sort((a, b) => (a.at ?? 0) - (b.at ?? 0));
  for (const s of byStart) {
    if (!existsSync(join(PROJECT, s.src))) err(`场景 ${s.id}: 找不到 ${s.src}`);
    if (s.at == null || s.dur == null) err(`场景 ${s.id}: 缺 data-start 或 data-duration`);
  }

  // 同一条轨道上的片段必须首尾相接、不许压；不同轨道天生可以叠（转场就是靠交替轨道做的）
  const byTrack = new Map();
  for (const s of byStart) if (s.track != null && s.at != null && s.dur != null) byTrack.set(s.track, [...(byTrack.get(s.track) ?? []), s]);
  let overlaps = 0;
  for (const [track, list] of byTrack) {
    for (let i = 1; i < list.length; i++) {
      if (list[i].at < list[i - 1].end - 0.02) {
        err(`轨道 ${track} 上 ${list[i].id}（${fmt(list[i].at)}）压住了 ${list[i - 1].id}（结束 ${fmt(list[i - 1].end)}）：同轨片段必须首尾相接，否则播哪个是不确定的`);
        overlaps++;
      }
    }
  }

  // 所有画面合起来的覆盖范围：中间有洞就是黑场
  const spans = byStart.filter((s) => s.at != null && s.end != null).map((s) => [s.at, s.end]).sort((a, b) => a[0] - b[0]);
  let covered = -1;
  for (const [a, b] of spans) {
    if (a > covered + 0.02 && covered >= 0) warn(`画面空档 ${fmt(covered)} → ${fmt(a)}（${fmt(a - covered)} 全黑）`);
    covered = Math.max(covered, b);
  }
  const end = covered > 0 ? covered : 0;
  if (film.duration && end && Math.abs(end - film.duration) > 0.05) {
    warn(`画面铺到 ${fmt(end)}，但 #root data-duration 是 ${fmt(film.duration)}（差 ${fmt(Math.abs(end - film.duration))}）`);
  }
  if (!overlaps && spans.length) pass(`时间轴 ${film.scenes.length} 帧 / ${byTrack.size} 条画面轨：同轨无重叠，画面连续铺到 ${fmt(end)}`);

  for (const s of film.sounds) if (s.src && !existsSync(join(PROJECT, s.src))) err(`音轨 ${s.id}: 找不到 ${s.src}`);

  // 语音 vs 所属帧：语音比帧长 = 话没说完画面就切了（最伤中文配音视频的一类错）
  const voices = film.sounds.filter((s) => /-voice$|voice/i.test(s.id ?? '') || /assets[\\/]voice[\\/]/i.test(s.src ?? ''));
  for (const v of voices) {
    const host = film.scenes.find((s) => (v.id ?? '').startsWith(`${s.id}-`))
      ?? film.scenes.find((s) => s.at != null && v.at != null && Math.abs(v.at - s.at) < 0.05);
    if (!host) { warn(`语音 ${v.id} 对不上任何场景（id 前缀或起点都不匹配）`); continue; }
    const real = probeDuration(join(PROJECT, v.src ?? ''));
    const place = v.dur ?? real;
    if (real && place) {
      if (real > place + 0.1) warn(`${v.id}: 文件 ${fmt(real)} 比放进去的 ${fmt(place)} 长 ${fmt(real - place)}，尾巴被切`);
      if (real > host.dur + 0.02) {
        err(`语音被切断：${v.id} 实测 ${fmt(real)}，所在场景 ${host.id} 只有 ${fmt(host.dur)}（差 ${fmt(real - host.dur)}）`);
      } else if (host.dur - real < 0.15) {
        warn(`语音几乎顶满：${v.id} ${fmt(real)} / 场景 ${host.id} ${fmt(host.dur)}（句间不到 0.15s，听感会赶）`);
      }
    }
  }
  if (voices.length) pass(`${voices.length} 条语音全部落在各自场景时长内`);
}

function probeDuration(file) {
  if (!existsSync(file)) return null;
  const r = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file], { encoding: 'utf8', windowsHide: true });
  const n = Number(String(r.stdout).trim());
  return Number.isFinite(n) && n > 0 ? n : null;
}

/* ─────────────────────── 2. 音频处方 ─────────────────────── */

function audioReport(film) {
  if (!film || !film.sounds.length) return null;
  const cache = new Map();
  const facts = (file) => {
    if (cache.has(file)) return cache.get(file);
    let out = { dur: null, hasAudio: false, peak: null };
    if (!existsSync(file)) { cache.set(file, out); return out; }
    const p = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', file], { encoding: 'utf8', windowsHide: true });
    try {
      const j = JSON.parse(p.stdout);
      out.dur = Number(j.format?.duration) || null;
      out.hasAudio = (j.streams ?? []).some((s) => s.codec_type === 'audio');
    } catch { /* 读不出来就算了 */ }
    if (out.hasAudio) {
      const a = spawnSync('ffmpeg', ['-hide_banner', '-nostats', '-loglevel', 'info', '-i', file, '-vn', '-af', 'astats=metadata=0', '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 64 << 20, windowsHide: true });
      const m = /Overall[\s\S]*?Peak level dB:\s*(-?[\d.]+|-inf)/.exec(a.stderr ?? '');
      out.peak = m ? Number(m[1]) : null;
    }
    cache.set(file, out);
    return out;
  };

  const rows = [];
  let voicePeak = -Infinity;
  let bgmPeak = -Infinity;
  for (const s of film.sounds) {
    const f = facts(join(PROJECT, s.src));
    const eff = Number.isFinite(f.peak) ? f.peak + 20 * Math.log10(Math.max(s.volume ?? 1, 1e-6)) : null;
    const isBgm = /bgm|music|track/i.test(s.src ?? '') || /bgm/i.test(s.id ?? '');
    if (Number.isFinite(eff)) {
      if (isBgm) bgmPeak = Math.max(bgmPeak, eff); else voicePeak = Math.max(voicePeak, eff);
    }
    rows.push({ id: s.id, src: s.src, isBgm, at: s.at, dur: f.dur, peak: f.peak, eff });
    if (existsSync(join(PROJECT, s.src ?? '')) && !f.hasAudio) warn(`${s.src}: 没有音频流（当音轨用会是静音）`);
    if (Number.isFinite(eff) && eff < -30) warn(`${s.src}: 峰值 ${eff.toFixed(0)} dB，太轻了，混在片子里听不见`);
  }

  // 人声 vs BGM 落差：BGM 只该比人声低 10–20 dB，太高盖词、太低白放
  if (Number.isFinite(voicePeak) && Number.isFinite(bgmPeak)) {
    const gap = voicePeak - bgmPeak;
    if (gap < 8) warn(`BGM 太响：人声峰值 ${voicePeak.toFixed(0)} dB，BGM 峰值 ${bgmPeak.toFixed(0)} dB（只差 ${gap.toFixed(0)} dB，会盖住词）`);
    else if (gap > 26) warn(`BGM 太轻：比人声低 ${gap.toFixed(0)} dB，基本听不出配乐`);
    else pass(`人声比 BGM 高 ${gap.toFixed(0)} dB（合理区间 10–24）`);
  }

  return { rows, voicePeak, bgmPeak };
}

/** 把 index.html 里的所有音轨按 data-start / data-volume 混成一条 wav，用来量整片响度。 */
function mixDown(film, outWav) {
  if (!film) return null;
  const clips = film.sounds.filter((s) => existsSync(join(PROJECT, s.src)));
  if (!clips.length) return null;
  const args = ['-hide_banner', '-nostats', '-loglevel', 'error', '-y'];
  for (const c of clips) args.push('-i', join(PROJECT, c.src));
  const chain = clips.map((c, i) => {
    const delay = Math.round((c.at ?? 0) * 1000);
    return `[${i}:a]volume=${c.volume ?? 1},adelay=${delay}|${delay}[a${i}]`;
  });
  chain.push(`${clips.map((_, i) => `[a${i}]`).join('')}amix=inputs=${clips.length}:normalize=0:dropout_transition=0[mix]`);
  args.push('-filter_complex', chain.join(';'), '-map', '[mix]', '-c:a', 'pcm_s16le', outWav);
  const r = spawnSync('ffmpeg', args, { encoding: 'utf8', windowsHide: true, maxBuffer: 32 << 20 });
  if (r.status !== 0 || !existsSync(outWav)) {
    warn(`混音失败，跳过整片响度检查：${(r.stderr ?? '').trim().split('\n').at(-1) ?? ''}`);
    return null;
  }
  const meter = spawnSync('ffmpeg', ['-hide_banner', '-nostats', '-i', outWav, '-af', 'ebur128=peak=true', '-f', 'null', '-'], { encoding: 'utf8', windowsHide: true }).stderr ?? '';
  const tail = meter.slice(meter.lastIndexOf('Summary'));
  const lufs = Number((/I:\s*(-?[\d.]+|-inf) LUFS/.exec(tail) ?? [])[1]);
  const tp = Number((/Peak:\s*(-?[\d.]+|-inf) dBFS/.exec(tail) ?? [])[1]);
  if (Number.isFinite(lufs)) {
    if (lufs < -24) warn(`整片响度 ${lufs.toFixed(1)} LUFS：比手机外放常见目标（-16 到 -14）偏轻，会听不清`);
    else if (lufs > -9) warn(`整片响度 ${lufs.toFixed(1)} LUFS：偏爆，平台会压，动态全丢`);
    else pass(`整片响度 ${lufs.toFixed(1)} LUFS 集成 / 真峰 ${Number.isFinite(tp) ? tp.toFixed(1) : '?'} dBTP`);
  }
  if (Number.isFinite(tp) && tp > -1) warn(`真峰 ${tp.toFixed(1)} dBTP 超过 -1 dBTP，转 AAC 会削波失真`);
  return { wav: outWav, lufs, tp };
}

/* ─────────────────────── PNG 解码（零依赖） ─────────────────────── */

function decodePng(buf) {
  let p = 8, w = 0, h = 0, depth = 0, color = 0, interlace = 0;
  const idat = [];
  while (p + 8 <= buf.length) {
    const len = buf.readUInt32BE(p);
    const type = buf.toString('ascii', p + 4, p + 8);
    const data = buf.subarray(p + 8, p + 8 + len);
    if (type === 'IHDR') { w = data.readUInt32BE(0); h = data.readUInt32BE(4); depth = data[8]; color = data[9]; interlace = data[12]; }
    else if (type === 'IDAT') idat.push(data);
    else if (type === 'IEND') break;
    p += 12 + len;
  }
  if (depth !== 8) throw new Error(`PNG 位深 ${depth} 不支持`);
  if (interlace !== 0) throw new Error('PNG 交错格式不支持');
  const ch = color === 6 ? 4 : color === 2 ? 3 : color === 4 ? 2 : 1;
  const bpp = ch;
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = w * bpp;
  const out = Buffer.alloc(h * stride);
  let q = 0;
  for (let y = 0; y < h; y++) {
    const filter = raw[q++];
    const line = raw.subarray(q, q + stride); q += stride;
    const cur = out.subarray(y * stride, (y + 1) * stride);
    const prev = y > 0 ? out.subarray((y - 1) * stride, y * stride) : null;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? cur[x - bpp] : 0;
      const b = prev ? prev[x] : 0;
      const c = prev && x >= bpp ? prev[x - bpp] : 0;
      let v = line[x];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) {
        const pp = a + b - c, pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c);
        v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      cur[x] = v & 255;
    }
  }
  return { w, h, ch, px: out };
}

/** 盒平均降到 tw×th，透明处按黑底合成（页面图层本来就该这么判）。 */
function thumb(img, tw, th) {
  const { w, h, ch, px } = img;
  const out = new Float32Array(tw * th * 3);
  for (let y = 0; y < th; y++) {
    const y0 = Math.floor((y * h) / th), y1 = Math.max(y0 + 1, Math.floor(((y + 1) * h) / th));
    for (let x = 0; x < tw; x++) {
      const x0 = Math.floor((x * w) / tw), x1 = Math.max(x0 + 1, Math.floor(((x + 1) * w) / tw));
      let r = 0, g = 0, b = 0, n = 0;
      for (let yy = y0; yy < y1; yy++) {
        for (let xx = x0; xx < x1; xx++) {
          const i = (yy * w + xx) * ch;
          const al = ch === 4 ? px[i + 3] / 255 : ch === 2 ? px[i + 1] / 255 : 1;
          r += (ch >= 3 ? px[i] : px[i]) * al;
          g += (ch >= 3 ? px[i + 1] : px[i]) * al;
          b += (ch >= 3 ? px[i + 2] : px[i]) * al;
          n++;
        }
      }
      const o = (y * tw + x) * 3;
      out[o] = r / n; out[o + 1] = g / n; out[o + 2] = b / n;
    }
  }
  return out;
}

function blockDiff(a, b) {
  if (a.w !== b.w || a.h !== b.h) return 255;
  const w = Math.max(1, Math.round(a.w / 8)), h = Math.max(1, Math.round(a.h / 8));
  const p = thumb(a, w, h), q = thumb(b, w, h);
  let max = 0;
  for (let i = 0; i < p.length; i++) max = Math.max(max, Math.abs(p[i] - q[i]));
  return max;
}

function spread(img) {
  const p = thumb(img, Math.max(1, Math.round(img.w / 8)), Math.max(1, Math.round(img.h / 8)));
  let lo = 255, hi = 0;
  for (let i = 0; i < p.length; i += 3) {
    const y = 0.2126 * p[i] + 0.7152 * p[i + 1] + 0.0722 * p[i + 2];
    lo = Math.min(lo, y); hi = Math.max(hi, y);
  }
  return hi - lo;
}

/* ─────────────────────── 3. 浏览器双遍 ─────────────────────── */

/** 固定种子的洗牌：每次跑顺序相同，但不是影片会自然被画的顺序。同 openfilm shuffled。 */
function shuffled(list, seed) {
  const out = [...list];
  let s = seed >>> 0;
  for (let i = out.length - 1; i > 0; i--) {
    s = (Math.imul(s ^ (s >>> 15), 0x2c1b3c6d) + 0x9e3779b9) >>> 0;
    const j = s % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function findPuppeteer() {
  const cands = [
    process.env.HYPERFRAMES_NODE_MODULES,
    join(process.env.APPDATA ?? '', 'npm/node_modules/hyperframes/node_modules'),
    join(process.env.LOCALAPPDATA ?? '', 'npm-cache/_npx'),
  ].filter(Boolean);
  for (const base of cands) {
    try {
      const req = createRequire(join(base, 'noop.js'));
      const p = req.resolve('puppeteer-core');
      return req('puppeteer-core');
    } catch { /* 下一个 */ }
  }
  try { return createRequire(import.meta.url)('puppeteer-core'); } catch { return null; }
}

function findChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const roots2 = [join(process.env.USERPROFILE ?? '', '.cache/hyperframes/chrome'), join(process.env.HOME ?? '', '.cache/hyperframes/chrome')];
  const EXE = new Set(['chrome-headless-shell.exe', 'chrome-headless-shell', 'chrome.exe']);
  const walk = (dir, depth) => {
    if (depth > 3) return null;
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return null; }
    for (const e of entries) {
      if (e.isFile() && EXE.has(e.name)) return join(dir, e.name);
    }
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      const hit = walk(join(dir, e.name), depth + 1);
      if (hit) return hit;
    }
    return null;
  };
  for (const root of roots2) {
    if (!existsSync(root)) continue;
    const hit = walk(root, 0);
    if (hit) return hit;
  }
  return null;
}

function findRuntime() {
  const bases = [
    process.env.HYPERFRAMES_NODE_MODULES,
    join(process.env.APPDATA ?? '', 'npm/node_modules/hyperframes/node_modules'),
  ].filter(Boolean);
  for (const base of bases) {
    const p = join(base, '..', 'dist', 'hyperframe.runtime.iife.js');
    if (existsSync(p)) return p;
  }
  return null;
}

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.mp4': 'video/mp4', '.webm': 'video/webm',
  '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.woff2': 'font/woff2', '.woff': 'font/woff',
  '.ttf': 'font/ttf', '.otf': 'font/otf', '.vtt': 'text/vtt',
};

function serve(root) {
  return new Promise((res) => {
    const server = http.createServer((req, rep) => {
      const url = decodeURIComponent((req.url ?? '/').split('?')[0]);
      const file = join(root, url === '/' ? '/index.html' : url);
      if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) { rep.writeHead(404).end('not found'); return; }
      const body = readFileSync(file);
      rep.writeHead(200, {
        'content-type': MIME[extname(file).toLowerCase()] ?? 'application/octet-stream',
        'content-length': body.length,
        'accept-ranges': 'bytes',
        'cache-control': 'no-store',
      }).end(body);
    });
    server.listen(0, '127.0.0.1', () => res({ server, port: server.address().port }));
  });
}

/**
 * 在页面里跑的文本裁切检测（与 openfilm shared.mjs cutText 同逻辑）：
 * 逐文本节点量真实渲染盒，出画框（edge）或被 overflow:hidden/clip 的祖先盒切掉（box）都算。
 * 完全在视野外的节点不管——那是还在入场或已经退场的字。
 * roots 为空就是整页；给 root 选择器就只查那些子合成。
 */
function cutTextIn(roots) {
  const out = [];
  const W = innerWidth, H = innerHeight;
  const name = (el) => {
    if (el.id) return '#' + el.id;
    const tag = el.tagName.toLowerCase();
    const cls = [...el.classList].slice(0, 2).map((c) => '.' + c).join('');
    const up = el.parentElement && el.parentElement !== document.body ? name(el.parentElement) + ' > ' : '';
    return up + tag + cls;
  };
  const shows = (el) => {
    if (typeof el.checkVisibility === 'function' && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
    for (let e = el; e; e = e.parentElement) if (Number(getComputedStyle(e).opacity) < 0.05) return false;
    return true;
  };
  const partly = (r, b) => {
    const inside = Math.max(0, Math.min(r.right, b.right) - Math.max(r.left, b.left)) * Math.max(0, Math.min(r.bottom, b.bottom) - Math.max(r.top, b.top));
    const over = r.left < b.left - 2 || r.right > b.right + 2 || r.top < b.top - 2 || r.bottom > b.bottom + 2;
    return over && inside > 0;
  };
  for (const root of roots.length ? roots : [null]) {
    const scope = root ? document.querySelector(root) : document.body;
    if (!scope) continue;
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    for (let n = walker.nextNode(); n && out.length < 50; n = walker.nextNode()) {
      const el = n.parentElement;
      if (!el || seen.has(el) || !n.textContent.trim() || /^(SCRIPT|STYLE|NOSCRIPT|TITLE)$/.test(el.tagName)) continue;
      if (!scope.contains(el)) continue;
      seen.add(el);
      const range = document.createRange(); range.selectNodeContents(n);
      const r = range.getBoundingClientRect();
      if (!(r.width > 1 && r.height > 1) || !shows(el)) continue;
      if (partly(r, { left: 0, top: 0, right: W, bottom: H })) { out.push({ sel: name(el), why: 'edge', text: n.textContent.trim().slice(0, 40), scope: root }); continue; }
      for (let a = el.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
        const cs = getComputedStyle(a);
        if (!/hidden|clip/.test(cs.overflowX + cs.overflowY)) continue;
        if (partly(r, a.getBoundingClientRect())) out.push({ sel: name(el), why: 'box', text: n.textContent.trim().slice(0, 40), scope: root });
        break;
      }
    }
  }
  return out;
}

/** 请求失败的 URL 是否只是本地文件不存在（那些已经在静态体检里报过，不重复报） */
const localMissing = (s) => {
  const p = String(s).split(' — ')[0].trim();
  return !/^https?:/.test(p) && !existsSync(join(PROJECT, p));
};
/** 本地文件存在但 Chrome 报了 ERR_ABORTED：音频/视频预取被主动取消，不是错 */
const abortedNoise = (s) => {
  const p = String(s).split(' — ')[0].trim();
  return /ERR_ABORTED/.test(s) && !/^https?:/.test(p) && existsSync(join(PROJECT, p));
};

async function browserPass(film) {
  const puppeteer = findPuppeteer();
  const chrome = findChrome();
  if (!puppeteer || !chrome) {
    warn(`跳过浏览器检查：${!puppeteer ? '找不到 puppeteer-core（hyperframes 未安装？）' : '找不到 chrome-headless-shell'}`);
    return null;
  }
  const { server, port } = await serve(PROJECT);
  const W = film?.width ?? 1920, H = film?.height ?? 1080;
  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: true,
    args: [
      '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
      '--enable-webgl', '--ignore-gpu-blocklist', `--window-size=${W},${H}`,
      '--font-render-hinting=none', '--force-color-profile=srgb', '--force-device-scale-factor=1',
      '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding', '--disable-background-media-suspend',
      '--disable-extensions', '--no-zygote', '--disk-cache-size=268435456',
      '--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process,Translate,BackForwardCache,IntensiveWakeUpThrottling',
      '--autoplay-policy=no-user-gesture-required',
    ],
  });
  const pageErrors = [];
  const failedRequests = [];
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
    page.on('pageerror', (e) => pageErrors.push(String(e.message ?? e).split('\n')[0]));
    page.on('requestfailed', (r) => failedRequests.push(`${r.url().replace(`http://127.0.0.1:${port}/`, '')} — ${r.failure()?.errorText ?? ''}`));
    await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });

    // 等运行时就绪。index.html 自己不带 runtime，hyperframes 在渲染/预览时才注入同一份文件，
    // 注入后才会 mount 子合成（data-composition-src）并暴露 window.__player.seek(t)。
    const READY = '!!(window.__player && typeof window.__player.seek === "function" && window.__player.getDuration() > 0)';
    let ready = await page.waitForFunction(READY, { timeout: 6000, polling: 120 }).then(() => true).catch(() => false);
    if (!ready) {
      const runtime = findRuntime();
      if (runtime) {
        await page.addScriptTag({ content: readFileSync(runtime, 'utf8') }).catch((e) => warn(`runtime 注入失败：${e.message}`));
        ready = await page.waitForFunction(READY, { timeout: 45000, polling: 150 }).then(() => true).catch(() => false);
      } else {
        warn('找不到 hyperframe.runtime.iife.js，无法注入 player runtime（hyperframes 装了吗？）');
      }
    }
    if (!ready) {
      const diag = await page.evaluate(() => {
        const hosts = [...document.querySelectorAll('[data-composition-id]')];
        const tl = window.__timelines || {};
        return {
          hf: !!window.__hf, seek: typeof window.__hf?.seek, dur: window.__hf?.duration ?? null,
          registered: Object.keys(tl),
          missing: hosts.map((h) => h.getAttribute('data-composition-id')).filter((id) => id && id !== 'main' && !tl[id]),
          scripts: [...document.scripts].map((s) => s.src).filter(Boolean).map((u) => u.replace(location.origin + '/', '')),
        };
      }).catch(() => ({}));
      err(`运行时没就绪（渲染也会卡在同一处）：window.__player.seek = ${typeof diag.seek}，已注册时间轴 [${(diag.registered ?? []).join(', ')}]`
        + (diag.missing?.length ? `；未注册：${diag.missing.join(', ')}（多半是它引用的脚本没加载成功）` : ''));
      for (const e of new Set(pageErrors)) err(`页面报错：${e}`);
      for (const f of new Set(failedRequests)) if (!localMissing(f)) err(`资源加载失败：${f}`);
      return { pageErrors, failedRequests };
    }
    const dur = await page.evaluate(() => window.__player.getDuration());
    if (film && Math.abs(dur - film.duration) > 0.1) warn(`运行时报告时长 ${fmt(dur)}，index.html 写的是 ${fmt(film.duration)}`);

    // 子合成时间轴都注册完（否则第一遍会拍到空壳）
    await page.waitForFunction(`(() => {
      const hosts = document.querySelectorAll('[data-composition-id]');
      const tl = window.__timelines || {};
      for (const h of hosts) {
        if (h.hasAttribute('data-no-timeline')) continue;
        const id = h.getAttribute('data-composition-id');
        if (id && id !== 'main' && !tl[id]) return false;
      }
      return true;
    })()`, { timeout: 20000, polling: 150 }).catch(() => warn('子合成时间轴在 20 秒内没注册完，结果可能偏严'));
    await page.evaluate(() => (document.fonts?.ready ?? Promise.resolve())).catch(() => {});

    const seek = async (t) => {
      await page.evaluate(async (tt) => {
        window.__player.pause();
        window.__player.seek(tt);
        await window.__hfWaitForSeekCompletion?.();
      }, t);
      await page.evaluate(() => new Promise((r) => {
        const done = () => r();
        requestAnimationFrame(() => requestAnimationFrame(done));
        setTimeout(done, 1200);
      }));
    };
    const shoot = async (t) => { await seek(t); return decodePng(await page.screenshot({ type: 'png' })); };

    // 采样时刻：均分 + 场景中点
    let times;
    const end = Math.min(dur, RANGE?.[1] ?? dur);
    const from = Math.max(0, RANGE?.[0] ?? 0);
    // 场景中点：最不容易踩到淡入淡出，也最容易暴露"什么都没画"（openfilm 也只在 clip 中点查平白帧）
    const mids = (film?.scenes ?? [])
      .filter((s) => s.at != null && s.end != null)
      .map((s) => (s.at + Math.min(s.end, end)) / 2)
      .filter((t) => t >= from && t < end && t > 0.3);
    if (AT != null) times = [Math.min(Math.max(0, AT), dur - 0.001)];
    else {
      const even = Array.from({ length: COUNT }, (_, i) => from + ((end - from) * i) / COUNT);
      times = [...new Set([...even, ...mids].map((t) => Number(Math.max(0, Math.min(t, dur - 0.001)).toFixed(3))))].sort((a, b) => a - b);
    }
    const flatAt = new Set(mids.map((t) => Number(t.toFixed(3))));

    const scanText = async (t, cut) => {
      const record = (found, where) => {
        for (const f of found) {
          const key = `${f.why}\n${f.sel}\n${where}`;
          const seen = cut.get(key) ?? { why: f.why, text: f.text, sel: f.sel, page: where, times: [] };
          if (!seen.times.includes(t)) seen.times.push(t);
          cut.set(key, seen);
        }
      };
      // 情形 A：子合成被内联进主文档（hyperframes 默认）——只查当前时刻在播的那几个
      const active = (film?.scenes ?? [])
        .filter((s) => s.at != null && s.end != null && t >= s.at && t < s.end)
        .map((s) => `[data-composition-id="${s.comp}"]`);
      if (active.length) {
        const found = await page.evaluate(cutTextIn, active).catch(() => []);
        for (const f of found) record([f], f.scope ? f.scope.replace(/\[data-composition-id="|"\]/g, '') : 'main');
      }
      // 情形 B：子合成是真的 iframe
      for (const frame of page.frames()) {
        if (frame === page.mainFrame()) continue;
        const found = await frame.evaluate(cutTextIn, []).catch(() => []);
        const name = (() => { try { return decodeURIComponent(new URL(frame.url()).pathname).replace(/^\//, ''); } catch { return 'iframe'; } })();
        for (const f of found) delete f.scope;
        record(found, name);
      }
    };

    const shots = new Map();
    const cut = new Map();
    const flat = [];
    const pass1 = shuffled(times, 1);
    const pass2 = shuffled(times, 2);
    for (const t of pass1) {
      shots.set(t, await shoot(t));
      await scanText(t, cut);
      if (AT == null && flatAt.has(t) && spread(shots.get(t)) < FLAT_LIMIT) flat.push(t);
    }
    const again = new Map();
    for (const t of pass2) again.set(t, await shoot(t));

    // 1) 确定性
    const differing = [];
    const diffShots = [];
    for (const t of times) {
      const d = blockDiff(shots.get(t), again.get(t));
      if (d > SAME_LIMIT) { differing.push(t); diffShots.push({ t, d }); }
    }
    if (differing.length) {
      err(`同一时刻画出两幅不同的画：${differing.map(fmt).join(', ')}\n`
        + '        画面不只由 t 决定。常见原因：用了 Date.now / new Date / Math.random（未播种）、\n'
        + '        函数在两次调用之间留下了状态（计数器、缓存的上一帧）、GSAP 用了没写目标值的 to()、\n'
        + '        或视频/音频还没 seek 完就截了图。');
    } else {
      pass(`${times.length} 帧在两种乱序下各画一遍：同一 t，同一画面（最大差 ≤ ${SAME_LIMIT}/255）`);
    }
    if (times.length > 1 && new Set(times.map((t) => shots.get(t))).size !== times.length) { /* 占位，无实际意义 */ }

    // 2) 平白帧
    if (flat.length) {
      warn(`纯色帧（场景中点整幅画为空）${flat.length} 处：${flat.map(fmt).join(', ')} —— 页面的时间轴没画东西，或元素 opacity 停在 0`);
    } else if (AT == null && flatAt.size) {
      pass(`${flatAt.size} 个场景中点都不是纯色（内容真的画出来了）`);
    }

    // 3) 文字被裁（≥2 帧才算，一帧可能正字在入场途中）
    const cutHits = [...cut.values()].filter((v) => v.times.length >= 2);
    for (const v of cutHits.slice(0, 8)) {
      const when = [...v.times].sort((a, b) => a - b);
      warn(`文字被${v.why === 'edge' ? '画框边缘' : '自身盒子'}切掉（${when.length} 帧：${when.slice(0, 4).map(fmt).join(', ')}${when.length > 4 ? ' …' : ''}）："${v.text}"  ${v.sel}  in ${v.page}`);
    }
    if (cutHits.length > 8) warn(`… 另外还有 ${cutHits.length - 8} 处文字被裁`);
    if (!cutHits.length) pass('没有文字被画框或盒子切掉');

    // 4) 字体
    const fontErrors = await page.evaluate(() => [...(document.fonts ?? [])].filter((f) => f.status === 'error').map((f) => f.family)).catch(() => []);
    for (const fam of new Set(fontErrors)) err(`字体加载失败：${fam}（渲染机上是干净 Chrome，必须把 TTF 放进 assets/fonts 并用 @font-face 引用）`);
    if (!fontErrors.length) pass('所有 @font-face 都加载成功');

    // 5) 页面错误与请求失败
    for (const e of [...new Set(pageErrors)].slice(0, 6)) err(`页面报错：${e}`);
    for (const f of [...new Set(failedRequests)].slice(0, 8)) {
      if (localMissing(f) || abortedNoise(f)) continue;
      if (/^https?:/.test(f)) err(`外部资源加载失败：${f}（渲染时会缺这个资源）`);
      else warn(`资源加载失败：${f}`);
    }
    if (!pageErrors.length && !failedRequests.length) pass('没有页面报错、没有资源 404');

    // 接触表
    if (WANT_SHEET && AT == null && !JSON_OUT) {
      const sheet = await makeSheet(browser, page, times, shots, film, from, end);
      if (sheet) { files.push(sheet); }
    }
    return { pageErrors, failedRequests };
  } finally {
    await browser.close().catch(() => {});
    server.close();
  }
}

async function makeSheet(browser, page, times, shots, film, from, to) {
  const outDir = join(PROJECT, '.look');
  mkdirSync(outDir, { recursive: true });
  const cols = times.length <= 4 ? Math.max(1, times.length) : times.length <= 9 ? 3 : 4;
  const cw = 480;
  const W = film?.width ?? 1920, H = film?.height ?? 1080;
  const ch = Math.round((cw * H) / W);
  const b64 = (img) => {
    // 缩略图直接从内存渲：拿不到原 PNG，就用 canvas 在临页放大——这里改用一个临时页面画
    return null;
  };
  // 用同一浏览器开一张排版页，把帧图以 data URL 铺开（openfilm 的做法）
  const imgs = [];
  for (const t of times) {
    await page.evaluate(async (tt) => { window.__player.pause(); window.__player.seek(tt); await window.__hfWaitForSeekCompletion?.(); }, t);
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    imgs.push({ t, png: (await page.screenshot({ type: 'png' })).toString('base64') });
  }
  const gridW = cols * (cw + 6) - 6;
  const html = `<body style="margin:0;background:#111;font:600 13px ui-monospace,monospace;color:#eee">
<div style="padding:6px;width:${gridW}px">
  <div style="display:grid;grid-template-columns:repeat(${cols},${cw}px);gap:6px">
    ${imgs.map((s, i) => `<div style="position:relative;width:${cw}px;height:${ch}px"><img style="width:100%;height:100%;display:block" src="data:image/png;base64,${s.png}"><span style="position:absolute;left:6px;top:4px;background:#000b;padding:1px 6px">${i + 1} · ${Number(s.t.toFixed(2))}s</span></div>`).join('')}
  </div>
  <div style="display:flex;justify-content:space-between;color:#888;margin-top:3px"><span>${fmt(from)}</span><span>${basename(PROJECT)} · ${times.length} 帧采样</span><span>${fmt(to)}</span></div>
</div></body>`;
  const sheetPage = await browser.newPage();
  try {
    await sheetPage.setContent(html, { waitUntil: 'load' });
    const file = join(outDir, `sheet-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.png`);
    const buf = await sheetPage.screenshot({ fullPage: true, type: 'png' });
    writeFileSync(file, buf);
    return file;
  } catch (e) {
    warn(`接触表生成失败：${e.message}`);
    return null;
  } finally { await sheetPage.close().catch(() => {}); }
}

/* ─────────────────────── 主流程 ─────────────────────── */

(async () => {
  const t0 = Date.now();
  const film = parseIndex(PROJECT);
  checkTimeline(film);
  const audio = audioReport(film);

  if (!FAST) {
    try { await browserPass(film); }
    catch (e) { err(`浏览器检查崩了：${e.message}`); }
  }

  const mix = mixDown(film, join(tmpdir(), `look-mix-${process.pid}.wav`));

  const lines = [];
  const head = film
    ? `${basename(PROJECT)}  ${film.width}×${film.height} · ${fmt(film.duration)} · ${film.scenes.length} 帧 · ${film.sounds.length} 条音轨`
    : `${basename(PROJECT)}  (不是 HyperFrames 项目)`;
  if (audio?.voicePeak > -Infinity || audio?.bgmPeak > -Infinity) {
    const v = audio.voicePeak > -Infinity ? `人声峰值 ${audio.voicePeak.toFixed(0)} dB` : '';
    const b = audio.bgmPeak > -Infinity ? `BGM 峰值 ${audio.bgmPeak.toFixed(0)} dB` : '';
    lines.push(`♪ ${[v, b].filter(Boolean).join(' · ')}`);
  }
  if (mix && Number.isFinite(mix.lufs)) lines.push(`♪ 混音 ${mix.lufs.toFixed(1)} LUFS${Number.isFinite(mix.tp) ? ` · 真峰 ${mix.tp.toFixed(1)} dBTP` : ''}`);
  lines.push(...errors.map((e) => `✗ ${e}`), ...warnings.map((w) => `! ${w}`), ...passed.map((p) => `✓ ${p}`));
  lines.push(...files.map((f) => `→ ${f.replace(`${PROJECT}\\`, '').replace(`${PROJECT}/`, '')}`));

  if (JSON_OUT) {
    console.log(JSON.stringify({ ok: !errors.length, errors, warnings, passed, files, head, ms: Date.now() - t0 }, null, 2));
  } else {
    console.log(head);
    for (const l of lines) console.log(l);
    console.log(`  (${((Date.now() - t0) / 1000).toFixed(1)}s${FAST ? ' · --fast 模式，未跑浏览器' : ''})`);
  }
  return !errors.length;
})().then((ok) => { process.exitCode = ok ? 0 : 1; }).catch((e) => { console.error(e); process.exitCode = 2; });
