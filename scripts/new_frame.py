# -*- coding: utf-8 -*-
"""Start a frame from a lint-clean skeleton.

Most first-pass frame bugs come from boilerplate the model re-derives each time: the template wrapper,
the local GSAP tag, the inlined @font-face block, the full-bleed background clip, and registering the
paused timeline. This writes all of that, plus three seek-safe motion helpers, so the creative work
starts from a frame that already passes lint.

    python new_frame.py --project PROJ --id 03-hands-on --duration 11.47 [--kicker "优点 01 · 真动手"]
"""
from __future__ import annotations

import argparse
import os
import sys

FONT_TABLE = [
    ("EBGaramond-400.woff2", "EB Garamond", "normal", "400", "woff2"),
    ("EBGaramond-400i.woff2", "EB Garamond", "italic", "400", "woff2"),
    ("EBGaramond-500.woff2", "EB Garamond", "normal", "500", "woff2"),
    ("Inter-400.woff2", "Inter", "normal", "400", "woff2"),
    ("Inter-500.woff2", "Inter", "normal", "500", "woff2"),
    ("Inter-600.woff2", "Inter", "normal", "600", "woff2"),
    ("JetBrainsMono-400.woff2", "JetBrains Mono", "normal", "400", "woff2"),
    ("JetBrainsMono-500.woff2", "JetBrains Mono", "normal", "500", "woff2"),
    ("NotoSerifSC-VF.ttf", "Noto Serif SC", "normal", "100 900", "truetype"),
    ("NotoSansSC-VF.ttf", "Noto Sans SC", "normal", "100 900", "truetype"),
]

TEMPLATE = """<template>
<script src="assets/vendor/gsap.min.js"></script>

<style>
/* fonts — inlined here on purpose: the renderer is a clean headless Chrome with no system CJK fonts */
__FONTFACE__
</style>

<style>
  #root {
    position: absolute;
    inset: 0;
    overflow: hidden;
    container-type: size; /* frame-relative units: cqw / cqh (never vw) */
    -webkit-font-smoothing: antialiased;
  }

  /* full-bleed ground rides on its own clip layer — never on #root */
  [id="__ID__-bg"] {
    position: absolute;
    inset: 0;
    background-color: #FAF9F5;
    background-image:
      linear-gradient(to right, rgba(20, 20, 19, 0.045) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(20, 20, 19, 0.045) 1px, transparent 1px);
    background-size: 120px 120px;
    background-position: center top;
  }

  [id="__ID__-kicker"] {
    position: absolute;
    left: 0;
    right: 0;
    top: 92px;
    text-align: center;
    font-family: "JetBrains Mono", "Noto Sans SC", monospace;
    font-size: 28px;
    font-weight: 500;
    letter-spacing: 0.16em;
    color: #141413;
    white-space: nowrap;
    transform-origin: 50% 50%;
    will-change: transform, opacity;
  }
  [id="__ID__-kicker"] .fx-spike { color: #CC785C; margin-right: 14px; } /* the frame's ONE coral moment */

  [id="__ID__-hero"] {
    position: absolute;
    left: 0;
    right: 0;
    top: 170px;
    text-align: center;
    font-family: "EB Garamond", "Noto Serif SC", serif;
    font-size: 84px;
    font-weight: 500;
    line-height: 1.1;
    letter-spacing: -0.018em;
    color: #141413;
    white-space: nowrap;
  }
  .fx-w { display: inline-block; will-change: transform, opacity; }

  /* keep every element's bottom edge above y=816 (1080p) — the caption band lives below */
</style>

<div
  id="root"
  data-composition-id="__FRAME__"
  data-start="0"
  data-duration="__DURATION__"
  data-width="1920"
  data-height="1080"
>
  <div class="clip" id="__ID__-bg" data-start="0" data-duration="__DURATION__" data-track-index="0"></div>

  <div id="__ID__-kicker"><span class="fx-spike">✱</span>__KICKER__</div>

  <div id="__ID__-hero">
    <span class="fx-w" data-t="__T1__">__HERO__</span>
  </div>
</div>

<script>
  (function () {
    var DURATION = __DURATION__;
    var tl = gsap.timeline({ paused: true });

    // seek-safe helpers — fromTo entrances only, no CSS transitions, no repeat/yoyo, no random
    function reveal(sel, at, dy) {
      tl.fromTo(sel === undefined ? null : sel,
        { opacity: 0, y: dy === undefined ? 18 : dy },
        { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }, at);
    }
    function typeOn(sel, text, at, dur) {
      var el = document.querySelector(sel);
      tl.set(el, { textContent: "" }, 0);
      var n = text.length;
      for (var i = 1; i <= n; i++) {
        (function (k) { tl.set(el, { textContent: text.slice(0, k) }, at + k * (dur / n)); })(i);
      }
    }
    function jitter(sel, at, amp) {
      var a = amp === undefined ? 3 : amp;
      tl.to(sel, { y: -a, duration: 0.9, ease: "sine.inOut" }, at);
      tl.to(sel, { y: 0, duration: 0.9, ease: "sine.inOut" }, at + 0.9);
    }
    window.__fx = { reveal: reveal, typeOn: typeOn, jitter: jitter };

    // ── scene 1 …: only what the voiceover is saying at t=0 shows up first
    tl.fromTo("#__ID__-kicker", { scale: 0, opacity: 0 },
              { scale: 1, opacity: 1, duration: 0.5, ease: "power3.out" }, 0.08);
    gsap.utils.toArray("#__ID__-hero .fx-w").forEach(function (el) {
      reveal(el, parseFloat(el.getAttribute("data-t")) || 0.6, 16);
    });

    // ── hold: keep it still, at most a low-amplitude jitter
    jitter("#__ID__-hero", DURATION - 2.2, 2);

    tl.to({}, { duration: 0.01 }, DURATION - 0.01);   // anchor: span the whole frame
    window.__timelines["__FRAME__"] = tl;             // key must equal data-composition-id
  })();
</script>
</template>
"""


def font_faces(project: str) -> str:
    d = os.path.join(project, "assets", "fonts")
    faces = [f"@font-face {{ font-family: '{fam}'; font-style: {style}; font-weight: {w}; "
             f"font-display: swap; src: url('assets/fonts/{fn}') format('{fmt}'); }}"
             for fn, fam, style, w, fmt in FONT_TABLE if os.path.exists(os.path.join(d, fn))]
    if not faces:
        return ("/* no fonts staged in assets/fonts — copy NotoSerifSC-VF.ttf/NotoSansSC-VF.ttf from "
                "C:\\Windows\\Fonts and the Latin woff2s; see references/composition-contract.md §5 */")
    return "\n".join(faces)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--id", required=True, help="frame id, e.g. 03-hands-on (also the file name)")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--kicker", default="标签")
    ap.add_argument("--hero", default="关键词")
    ap.add_argument("--cue", type=float, default=0.6, help="when the hero word lands (voiceover cue)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    fid = a.id
    if not fid or fid[0].isdigit() is False or True:
        pass  # ids may start with digits in the FILE name; the CSS id prefix below is what must not
    css_id = "f" + fid if fid[0].isdigit() else fid
    path = a.out or os.path.join(a.project, "compositions", "frames", f"{fid}.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        print(f"refusing to overwrite an existing frame: {path} (pass --out to write elsewhere)")
        return 1

    html = (TEMPLATE
            .replace("__FONTFACE__", font_faces(a.project))
            .replace("__FRAME__", fid)
            .replace("__ID__", css_id)
            .replace("__DURATION__", str(a.duration))
            .replace("__KICKER__", a.kicker)
            .replace("__HERO__", a.hero)
            .replace("__T1__", str(a.cue)))
    open(path, "w", encoding="utf-8").write(html)
    print(f"wrote {os.path.relpath(path, a.project)}")
    print(f"  composition id : {fid}   (data-composition-id == window.__timelines key)")
    print(f"  css id prefix  : {css_id}   (letter-first, so querySelector never throws)")
    print(f"  duration       : {a.duration}s  (keep == audio_meta voices[frame].duration_s)")
    print(f"  helpers        : window.__fx.reveal / typeOn / jitter")
    print("\nremember: short on-screen copy only (never the narration sentence), hero 40–60% of frame, "
          "content above y=816, one coral moment per frame.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
