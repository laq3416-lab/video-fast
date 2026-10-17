# -*- coding: utf-8 -*-
"""Clause-level karaoke captions.

The workflow's captions.mjs splits groups by words-per-second density, which for Chinese yields
~2 words per bubble (measured: 219 words → 108 groups, unreadable flicker). This script uses the
script's own punctuation as the phrase boundary — the subtitle then breaks where a reader would
break it: 219 words → ~47 groups, ~7 chars each.

It patches an existing `compositions/captions.html` (keeping its skin + timeline), or writes a
standalone skin when the project doesn't have one yet, and always writes `caption_groups.json`.

    python captions_clauses.py --project <PROJ> [--band-top 836] [--rewrite-template]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SPLIT = re.compile(r"[，。？！；：、,\.\?\!;:—…]")
MAX_CHARS = 15
MIN_CHARS = 5

TEMPLATE = """<template>
<script src="assets/vendor/gsap.min.js"></script>
<style>
/* __FONTFACE__ */
#root { position: absolute; inset: 0; overflow: hidden; container-type: size; }
.caption-layer { position: absolute; inset: 0; z-index: 20; pointer-events: none; }
.caption-stage { position: absolute; left: 0; right: 0; top: __BAND__px; height: 180px;
  display: flex; align-items: center; justify-content: center; }
.caption-group { position: absolute; inset: 0; display: flex; align-items: center;
  justify-content: center; opacity: 0; }
.caption-pill { max-width: 78%; padding: 20px 40px 24px; background: #FAF9F5;
  border: 1px solid rgba(20, 20, 19, 0.12); border-radius: 12px;
  box-shadow: 0 1px 3px rgba(20, 20, 19, 0.08), 0 4px 16px rgba(20, 20, 19, 0.04); }
.caption-line { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.06em 0.16em;
  font-family: "EB Garamond", "Noto Serif SC", Georgia, serif; font-weight: 500;
  font-size: clamp(40px, 2.9cqw, 58px); line-height: 1.3; letter-spacing: -0.02em; }
.caption-word { display: inline-block; padding: 0 0.02em 0.06em;
  color: rgba(20, 20, 19, 0.58); border-bottom: 3px solid transparent; }
.caption-word.is-active { color: #141413; border-bottom-color: #CC785C; }
.caption-word.is-spoken { color: #141413; border-bottom-color: transparent; }
</style>
<div id="root" data-composition-id="captions" data-timeline-locked data-start="0"
     data-duration="__DURATION__" data-fps="30" data-width="__W__" data-height="__H__">
  <div class="caption-layer" aria-hidden="true"><div id="caption-stage" class="caption-stage"></div></div>
</div>
<script>
  var GROUPS = [];
  var DURATION = 0;
  (function () {
    var stage = document.getElementById("caption-stage");
    GROUPS.forEach(function (group, g) {
      var groupEl = document.createElement("div");
      groupEl.className = "caption-group"; groupEl.id = "caption-group-" + g;
      var pill = document.createElement("div"); pill.className = "caption-pill";
      var line = document.createElement("div"); line.className = "caption-line";
      (group.words || []).forEach(function (w, i) {
        var span = document.createElement("span");
        span.className = "caption-word"; span.id = "caption-word-" + g + "-" + i;
        span.textContent = String(w.text); line.appendChild(span);
      });
      pill.appendChild(line); groupEl.appendChild(pill); stage.appendChild(groupEl);
    });
    var tl = gsap.timeline({ paused: true });
    GROUPS.forEach(function (group, g) {
      var groupEl = document.getElementById("caption-group-" + g);
      var words = group.words || [];
      var next = GROUPS[g + 1];
      var end = (g === GROUPS.length - 1) ? DURATION
        : Math.min(Number(next.start), Number(group.end) + 0.3);
      var start = Math.max(0, Number(group.start));
      if (end <= start) end = start + 0.01;
      tl.set(groupEl, { opacity: 1 }, start);
      tl.set(groupEl, { opacity: 0 }, end);
      words.forEach(function (w, i) {
        var el = document.getElementById("caption-word-" + g + "-" + i);
        var at = Math.max(start, Number(w.start));
        tl.set(el, { className: "caption-word" }, start);
        tl.set(el, { className: "caption-word is-active" }, at);
        if (i + 1 < words.length) {
          tl.set(el, { className: "caption-word is-spoken" },
                 Math.max(start, Number(words[i + 1].start)));
        }
      });
      if (words.length) {
        var lastEl = document.getElementById("caption-word-" + g + "-" + (words.length - 1));
        tl.set(lastEl, { className: "caption-word is-spoken" },
               Math.min(end, Number(words[words.length - 1].end) + 0.1));
      }
    });
    tl.to({}, { duration: DURATION }, 0);
    window.__timelines["captions"] = tl;
  })();
</script>
</template>
"""


def frame_starts(storyboard: str) -> dict[int, float]:
    starts: dict[int, float] = {}
    acc, cur = 0.0, None
    for line in open(storyboard, encoding="utf-8").read().splitlines():
        m = re.match(r"^#{2,3}\s+(?:frame|beat|scene)\b.*?(\d+)", line, re.I)
        if m:
            cur = int(m.group(1))
            starts[cur] = acc
            continue
        d = re.match(r"^\s*[-*]\s+duration\s*:\s*([\d.]+)s", line, re.I)
        if d and cur is not None:
            acc += float(d.group(1))
    return starts


def script_lines(path: str) -> dict[int, str]:
    out: dict[int, str] = {}
    cur = None
    for line in open(path, encoding="utf-8").read().splitlines():
        h = re.match(r"^#{2,3}\s+.*?\(frame\s+(\d+)\)", line, re.I)
        if h:
            cur = int(h.group(1))
            out[cur] = ""
            continue
        if cur is None or re.match(r"^\s*\*\*", line):
            continue
        t = re.match(r"^(?: {4,}|\t)(.+)$", line)
        if t:
            out[cur] += t.group(1).strip()
    return out


def nchars(t: str) -> int:
    return len(re.sub(r"\s", "", t))


def build_groups(meta: dict, starts: dict[int, float], script: dict[int, str]) -> list[dict]:
    groups: list[list[dict]] = []
    for v in meta.get("voices", []):
        fr = int(v["frame"])
        base = starts.get(fr, 0.0)
        words = [{"text": (w.get("text") or "").strip(), "start": base + w["start"], "end": base + w["end"]}
                 for w in v.get("words", []) if (w.get("text") or "").strip()]
        clauses = [c.strip() for c in SPLIT.split(script.get(fr, "")) if c.strip()]
        wi = 0
        for clause in clauses:
            need, got, chunk = nchars(clause), 0, []
            while wi < len(words) and got < need:
                chunk.append(words[wi])
                got += nchars(words[wi]["text"])
                wi += 1
            while sum(nchars(w["text"]) for w in chunk) > MAX_CHARS:
                acc, cut = 0, 0
                for k, w in enumerate(chunk):
                    if acc + nchars(w["text"]) > MAX_CHARS and k > 0:
                        cut = k
                        break
                    acc += nchars(w["text"])
                if not cut:
                    break
                groups.append(chunk[:cut])
                chunk = chunk[cut:]
            if chunk:
                groups.append(chunk)
        if wi < len(words):
            (groups[-1].extend(words[wi:]) if groups else groups.append(words[wi:]))

    merged: list[list[dict]] = []
    for g in groups:
        if merged and sum(nchars(w["text"]) for w in merged[-1]) < MIN_CHARS and \
                sum(nchars(w["text"]) for w in merged[-1]) + sum(nchars(w["text"]) for w in g) <= MAX_CHARS:
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)

    out = []
    order = sorted(starts.items(), key=lambda kv: kv[1])
    for gi, g in enumerate(merged):
        fr = order[0][0] if order else 1
        for f, st in order:
            if g[0]["start"] >= st - 0.01:
                fr = f
        out.append({"id": f"caption-group-{gi}", "frame": fr,
                    "start": round(g[0]["start"], 3), "end": round(g[-1]["end"] + 0.12, 3),
                    "text": " ".join(w["text"] for w in g),
                    "words": [{"id": f"caption-word-{gi}-{k}", "text": w["text"],
                               "start": round(w["start"], 3), "end": round(w["end"], 3)}
                              for k, w in enumerate(g)]})
    for i, grp in enumerate(out[:-1]):
        if out[i + 1]["start"] < grp["end"]:
            grp["end"] = out[i + 1]["start"]
    return out


def font_face_block(project: str) -> str:
    d = os.path.join(project, "assets", "fonts")
    faces = []
    table = {
        "EBGaramond-400.woff2": ("EB Garamond", "normal", "400"),
        "EBGaramond-400i.woff2": ("EB Garamond", "italic", "400"),
        "EBGaramond-500.woff2": ("EB Garamond", "normal", "500"),
        "Inter-400.woff2": ("Inter", "normal", "400"),
        "Inter-500.woff2": ("Inter", "normal", "500"),
        "NotoSerifSC-VF.ttf": ("Noto Serif SC", "normal", "100 900"),
        "NotoSansSC-VF.ttf": ("Noto Sans SC", "normal", "100 900"),
    }
    for fn, (fam, style, weight) in table.items():
        if os.path.exists(os.path.join(d, fn)):
            fmt = "woff2" if fn.endswith("woff2") else "truetype"
            faces.append(f"@font-face {{ font-family: '{fam}'; font-style: {style}; font-weight: {weight}; "
                         f"font-display: swap; src: url('assets/fonts/{fn}') format('{fmt}'); }}")
    return "\n".join(faces) or "/* no local fonts staged — see references/composition-contract.md §5 */"


def canvas_size(project: str) -> tuple[int, int]:
    """read the canvas from STORYBOARD's `format:` global (default 1920x1080)"""
    try:
        first = open(os.path.join(project, "STORYBOARD.md"), encoding="utf-8").read(600)
        m = re.search(r"^format:\s*(\d+)\s*[x×]\s*(\d+)", first, re.M)
        if m:
            return int(m.group(1)), int(m.group(2))
    except OSError:
        pass
    return 1920, 1080


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--storyboard", default="STORYBOARD.md")
    ap.add_argument("--script", default="SCRIPT.md")
    ap.add_argument("--band-top", type=int, default=836, help="caption band top in px (900 = bottom 16.7%%)")
    ap.add_argument("--rewrite-template", action="store_true", help="regenerate captions.html from scratch")
    a = ap.parse_args()

    meta_path = os.path.join(a.project, "audio_meta.json")
    if not os.path.exists(meta_path):
        print("no audio_meta.json — run tts_lines.py first (captions need word timings)")
        return 1
    meta = json.load(open(meta_path, encoding="utf-8"))
    starts = frame_starts(os.path.join(a.project, a.storyboard))
    script = script_lines(os.path.join(a.project, a.script))
    if not starts or not script:
        print("could not read frame durations from STORYBOARD.md or text from SCRIPT.md")
        return 1

    canvas_w, canvas_h = canvas_size(a.project)
    groups = build_groups(meta, starts, script)
    # the composition must stay mounted for the WHOLE film (its last group can end before the film does)
    film = max((starts.get(int(v["frame"]), 0.0) + float(v["duration_s"]) for v in meta.get("voices", [])),
               default=0.0)
    total = round(film or (max((g["end"] for g in groups), default=0.0)), 3)
    chars = [sum(nchars(w["text"]) for w in g["words"]) for g in groups]
    nwords = sum(len(v.get("words", [])) for v in meta.get("voices", []))
    print(f"{nwords} words → {len(groups)} clause groups "
          f"(avg {sum(chars) / max(len(chars), 1):.1f} chars, max {max(chars, default=0)})")

    out_json = os.path.join(a.project, "caption_groups.json")
    json.dump({"total_duration_s": total, "width": canvas_w, "height": canvas_h, "groups": groups},
              open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    html = os.path.join(a.project, "compositions", "captions.html")
    os.makedirs(os.path.dirname(html), exist_ok=True)
    payload = json.dumps(groups, ensure_ascii=False, separators=(",", ":"))
    if not os.path.exists(html) or a.rewrite_template:
        tpl = TEMPLATE.replace("/* __FONTFACE__ */", font_face_block(a.project)).replace("__BAND__", str(a.band_top))
        tpl = tpl.replace("var GROUPS = [];", f"var GROUPS = {payload};")
        tpl = tpl.replace("var DURATION = 0;", f"var DURATION = {total};")
        # a caption composition with data-duration="0" / 0×0 canvas never mounts — write the real numbers
        tpl = (tpl.replace("__DURATION__", str(total))
                  .replace("__W__", str(canvas_w)).replace("__H__", str(canvas_h)))
        open(html, "w", encoding="utf-8").write(tpl)
        print(f"wrote standalone caption skin → {os.path.relpath(html, a.project)}")
    else:
        s = open(html, encoding="utf-8").read()
        s, n = re.subn(r"var GROUPS = \[.*?\];\n", f"var GROUPS = {payload};\n", s, count=1, flags=re.S)
        s = re.sub(r"var DURATION = [\d.]+;", f"var DURATION = {total};", s, count=1)
        s = re.sub(r"--cap-band-top: \d+px;", f"--cap-band-top: {a.band_top}px;", s)
        s = s.replace("gap: 0.12em 0.3em;", "gap: 0.06em 0.16em;")
        s = s.replace("top: var(--cap-band-top, 900px);", "top: var(--cap-band-top, 836px);")
        if n != 1:
            print("! GROUPS array not found — pass --rewrite-template to regenerate the skin")
            return 2
        open(html, "w", encoding="utf-8").write(s)
        print(f"patched {os.path.relpath(html, a.project)} (band top {a.band_top}px, tight word gap)")

    for g in groups[:6]:
        print("   ", g["frame"], f"{g['start']:7.2f}", g["text"])
    print("\n重建字幕必须在组装之前；组装/重建之后要复检字幕带位置。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
