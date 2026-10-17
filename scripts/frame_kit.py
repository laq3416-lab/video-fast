# -*- coding: utf-8 -*-
"""frame_kit — data → frame HTML, for the shapes that repeat across videos.

The point is NOT "one template for everything": a video made of ten identical layouts reads as a
slide deck, which is the failure mode the whole pipeline exists to avoid. The point is that a handful
of *compositional shapes* (kinetic hook, card row, navy panel demo, stack→card, tile gallery, CTA)
recur in almost every explainer, and hand-authoring their boilerplate each time is where the bugs
(skeleton, ids, fonts, cue lookup, seek-safe motion) come from.

So: each archetype here is a **vetted shape with content slots**, and the caller still decides which
shape each beat needs, in what order, with what copy. Each archetype also takes `variant`/count
parameters that change its layout, so consecutive frames of the same archetype do not look identical.

Cues: give `cue` per item and the kit resolves it against the frame's real word timings
(audio_meta.json) — the label's spoken moment is where its reveal lands. Nothing reveals before its
word is spoken, so frames cannot front-load.

    python frame_kit.py --project PROJ --frame frame.json          # one frame
    python frame_kit.py --project PROJ --all frames/*.json         # a batch
    python frame_kit.py --list                                      # what shapes exist
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

# ─────────────────────────── shared pieces ───────────────────────────

FONT_FILES = [
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

INK, CREAM, TILE, TILE2, CORAL, NAVY, NAVY_ELEV = "#141413", "#FAF9F5", "#EFE9DE", "#ECE3D4", "#CC785C", "#181715", "#252320"

BASE_STYLE = """
  #root { position: absolute; inset: 0; overflow: hidden; container-type: size; -webkit-font-smoothing: antialiased; }
  [id="__ID__-bg"] { position: absolute; inset: 0; background-color: __CREAM__;
    background-image: linear-gradient(to right, rgba(20,20,19,0.045) 1px, transparent 1px),
                      linear-gradient(to bottom, rgba(20,20,19,0.045) 1px, transparent 1px);
    background-size: 120px 120px; background-position: center top; }
  [id="__ID__-kicker"] { position: absolute; left: __KX__; right: __KRIGHT__; top: 92px; text-align: __KALIGN__;
    font-family: "JetBrains Mono", "Noto Sans SC", monospace; font-size: 28px; font-weight: 500;
    letter-spacing: 0.16em; color: __INK__; white-space: nowrap; transform-origin: 50% 50%; will-change: transform, opacity; }
  [id="__ID__-kicker"] .fx-spike { color: __CORAL__; margin-right: 14px; }
  .fx-w { display: inline-block; will-change: transform, opacity; }
  [id="__ID__-note"] { position: absolute; left: 0; right: 0; top: __NOTETOP__px; text-align: center;
    font-family: "EB Garamond", "Noto Serif SC", serif; font-size: __NOTEFS__px; font-weight: 500;
    letter-spacing: -0.014em; color: __INK__; white-space: nowrap; will-change: transform, opacity; }
  [id="__ID__-sub"] { position: absolute; left: 0; right: 0; top: __SUBTOP__px; text-align: center;
    font-family: "Inter", "Noto Sans SC", sans-serif; font-size: 34px; font-weight: 400;
    color: rgba(20,20,19,0.72); white-space: nowrap; will-change: transform, opacity; }
  [id="__ID__-underline"] { position: absolute; left: 50%; top: 100%; margin-top: 6px; width: 0; height: 6px;
    background: __CORAL__; will-change: width; }
  [id="__ID__-mockcap"] { position: absolute; left: 0; right: 0; top: 500px; text-align: center;
    transform-origin: 50% 50%; will-change: transform, opacity; }
  [id="__ID__-mockpill"] { display: inline-block; background: __CREAM__;
    border: 1px solid rgba(20,20,19,0.12); border-radius: 12px; padding: 16px 34px 18px;
    box-shadow: 0 1px 3px rgba(20,20,19,0.08), 0 4px 16px rgba(20,20,19,0.04); }
  [id="__ID__-mockpill"] div { font-family: "EB Garamond", "Noto Serif SC", serif; font-size: 40px;
    font-weight: 500; letter-spacing: -0.02em; color: rgba(20,20,19,0.4); }
  [id="__ID__-mockpill"] span { display: inline-block; padding: 0 2px 3px; border-bottom: 3px solid transparent; }
  [id="__ID__-mockpill"] span.is-active { color: __INK__; border-bottom-color: __CORAL__; }
  [id="__ID__-mockpill"] span.is-spoken { color: __INK__; }
"""

JS_HELPERS = """
    var DURATION = __DURATION__;
    // one entrance helper: `props` is the FROM state, and each key's sensible target is inferred
    // (scale → 1, x/y → 0), so a caller can never declare a from-state without a destination — the
    // bug that made every scaled element stay invisible.
    function at(sel, t, props, extra) {
      var from = { opacity: 0, y: 18 };
      var to = { opacity: 1, y: 0, duration: 0.46, ease: "power3.out" };
      for (var k in props) {
        from[k] = props[k];
        if (k === "scale") to.scale = 1;
        else if (k === "x") to.x = 0;
        else if (k === "rotation") to.rotation = 0;
      }
      for (var j in extra) to[j] = extra[j];
      tl.fromTo(sel, from, to, t);
    }
    function jitter(sel, t, amp) {
      var a = amp === undefined ? 2 : amp;
      tl.to(sel, { y: -a, duration: 0.9, ease: "sine.inOut" }, t);
      tl.to(sel, { y: 0, duration: 0.9, ease: "sine.inOut" }, t + 0.9);
    }
"""


def font_faces(project: str) -> str:
    d = os.path.join(project, "assets", "fonts")
    faces = [f"@font-face {{ font-family: '{fam}'; font-style: {style}; font-weight: {w}; "
             f"font-display: swap; src: url('assets/fonts/{fn}') format('{fmt}'); }}"
             for fn, fam, style, w, fmt in FONT_FILES if os.path.exists(os.path.join(d, fn))]
    return "\n".join(faces) or "/* stage fonts into assets/fonts — see composition-contract.md §5 */"


def word_cues(project: str, frame_no: int) -> dict[str, float]:
    """label → spoken start time for one frame, from audio_meta.json (empty when absent)"""
    p = os.path.join(project, "audio_meta.json")
    if not os.path.exists(p) or not frame_no:
        return {}
    try:
        meta = json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, float] = {}
    for v in meta.get("voices", []):
        if int(v.get("frame", 0)) != int(frame_no):
            continue
        for w in v.get("words", []):
            t = (w.get("text") or "").strip()
            if t and t not in out:
                out[t] = round(float(w["start"]), 3)
    return out


def resolve_cue(spec_item: dict, cues: dict[str, float], index: int, count: int, start: float, end: float) -> float:
    """where an item's reveal lands: its spoken word if we can find it, else an even spread
    (never before `start`, never after `end`)"""
    for key in ("cue", "label", "name", "text"):
        val = (spec_item.get(key) or "").strip()
        if not val:
            continue
        if val in cues:
            return max(start, cues[val])
        for w, t in cues.items():                     # partial match: "办公三件套" starts at "办公"
            if val.startswith(w) or w.startswith(val[:2]):
                return max(start, t)
    span = max(end - start, 0.1)
    # fallback spacing: land items through the first ~60% of the window so the last one still holds a beat
    return round(start + span * 0.6 * (index + 0.5) / max(count, 1), 3)


def frame_duration(project: str, frame_no: int, fallback: float) -> float:
    p = os.path.join(project, "audio_meta.json")
    if os.path.exists(p) and frame_no:
        try:
            meta = json.load(open(p, encoding="utf-8"))
            for v in meta["voices"]:
                if int(v["frame"]) == int(frame_no):
                    return round(float(v["duration_s"]), 3)
        except Exception:  # noqa: BLE001
            pass
    return fallback


def shell(frame_id: str, project: str, duration: float, body_html: str, body_js: str, extra_style: str,
          note_top: int = 776, kicker_left: str = "0", kicker_right: str = "0", kicker_align: str = "center",
          final_fade: bool = False, note_fs: int = 46, sub_top: int = 700) -> str:
    css_id = "f" + frame_id if frame_id[:1].isdigit() else frame_id
    style = (BASE_STYLE.replace("__ID__", css_id).replace("__CREAM__", CREAM).replace("__INK__", INK)
             .replace("__CORAL__", CORAL).replace("__NOTETOP__", str(note_top))
             .replace("__NOTEFS__", str(note_fs)).replace("__SUBTOP__", str(sub_top))
             .replace("__KX__", kicker_left).replace("__KRIGHT__", kicker_right).replace("__KALIGN__", kicker_align))
    style = style.replace("__ID__", css_id)
    extra_style = extra_style.replace("__ID__", css_id).replace("__CREAM__", CREAM).replace("__INK__", INK) \
        .replace("__TILE__", TILE).replace("__TILE2__", TILE2).replace("__CORAL__", CORAL) \
        .replace("__NAVY__", NAVY).replace("__NAVY_ELEV__", NAVY_ELEV)
    js = JS_HELPERS.replace("__DURATION__", str(duration)) + body_js
    if final_fade:  # only the last frame may own an exit: every other frame unmounts via its transition
        js += ("    tl.to(gsap.utils.toArray('#root > *'), { opacity: 0, duration: 0.7, ease: 'power2.inOut' }, "
               f"{max(duration - 0.8, 0.1):.2f});\n")
    dur_end = f"{max(duration - 0.01, 0.01):.2f}"
    out = f"""<template>
<script src="assets/vendor/gsap.min.js"></script>

<style>
{font_faces(project)}
</style>

<style>
{style}
{extra_style}</style>

<div
  id="root"
  data-composition-id="{{FRAME}}"
  data-start="0"
  data-duration="{{DURATION}}"
  data-width="1920"
  data-height="1080"
>
  <div class="clip" id="{{ID}}-bg" data-start="0" data-duration="{{DURATION}}" data-track-index="0"></div>

{body_html}
</div>

<script>
  (function () {{
    var tl = gsap.timeline({{ paused: true }});
{js}    tl.to({{}}, {{ duration: 0.01 }}, {dur_end});    window.__timelines["{frame_id}"] = tl;
  }})();
</script>
</template>
"""
    # one substitution pass over the finished document — never str.format (inline JS/CSS is full of braces)
    return (out.replace("{FRAME}", frame_id).replace("{ID}", css_id)
               .replace("{DURATION}", str(duration)))


def kicker_html(spec: dict) -> str:
    # fall back to the beat label — an empty kicker would leave a lone coral ✱ floating at the top
    text = spec.get("kicker") or spec.get("label") or ""
    return f'  <div id="{{ID}}-kicker"><span class="fx-spike">✱</span>{text}</div>'


def note_html(spec: dict, at: float, jitter_at: float | None = None) -> tuple[str, str]:
    """optional closing line: `note` (+ `sub` above it, `coral` for a voltage underline on it), plus
    the deliberately un-scaled inline sub used by the CTA shape"""
    html, js = "", ""
    if spec.get("sub") and spec.get("sub_place") == "note":
        html += f'  <div id="{{ID}}-sub">{spec["sub"]}</div>\n'
        js += '    at("#{ID}-sub", 2.07, {}, {duration: 0.5});\n'
    if spec.get("note"):
        coral = ' data-coral="1"' if spec.get("note_coral") else ""
        inner = spec["note"] + ('<span id="{ID}-underline"></span>' if spec.get("note_coral") else "")
        html += f'  <div id="{{ID}}-note"{coral}>{inner}</div>\n'
        js += f'    at("#{{ID}}-note", {at}, {{}}, {{duration: 0.5}});\n'
        if spec.get("note_coral"):
            # the underline lives INSIDE the note (left:50% + xPercent −50), so its position can never
            # drift from the glyphs the way a separately-computed y did
            js += ('    gsap.set("#{ID}-underline", { xPercent: -50 });\n'
                   f'    tl.fromTo("#{{ID}}-underline", {{ width: 0 }}, {{ width: {int(len(spec["note"]) * note_fs_for(spec) * 0.52)}, '
                   f'duration: 0.55, ease: "power2.out" }}, {round(at + 1.0, 2)});\n')
        if jitter_at:
            js += f'    jitter("#{{ID}}-note", {jitter_at});\n'
    return html, js


def note_fs_for(spec: dict) -> int:
    return 118 if spec.get("note_size") == "display" else 46


def note_top_for(spec: dict) -> int:
    return 520 if spec.get("note_size") == "display" else 776


def mock_caption_html(spec: dict) -> tuple[str, str]:
    """a miniature karaoke pill — used when the film talks about captions (or about itself)"""
    words = spec.get("mock_caption") or []
    if not words:
        return "", ""
    cues = {"mock": words}
    spans = "".join(f'<span id="{{ID}}-mc{i}">{w}</span>' for i, w in enumerate(words))
    html = ('  <div id="{ID}-mockcap"><div id="{ID}-mockpill"><div>' + spans + "</div></div></div>")
    js = '    at("#{ID}-mockcap", 5.78, {y: 12}, {duration: 0.45});\n'
    times = spec.get("mock_caption_at") or [round(5.78 + i * 0.3, 2) for i in range(len(words))]
    for i, t in enumerate(times):
        js += f'    tl.set("#{{ID}}-mc{i}", {{ className: "is-active" }}, {t});\n'
        if i + 1 < len(times):
            js += f'    tl.set("#{{ID}}-mc{i}", {{ className: "is-spoken" }}, {times[i+1]});\n'
        else:
            js += f'    tl.set("#{{ID}}-mc{i}", {{ className: "is-spoken" }}, {round(t + 0.4, 2)});\n'
    return html, js


# ─────────────────────────── archetypes ───────────────────────────

def build_kinetic_hook(spec: dict, project: str, dur: float) -> str:
    """Two lines of kinetic type + an optional mark. The hook shape: each word lands on its own
    spoken cue, the two lines read as two clauses, and coral is spent once (on the mark or the payoff)."""
    lines = spec["lines"]
    mark = spec.get("mark") or {}
    style = """
  [id="__ID__-l1"] { position: absolute; left: 0; right: 0; top: 268px; text-align: center;
    font-family: "EB Garamond", "Noto Serif SC", serif; font-size: 92px; font-weight: 500;
    line-height: 1.1; letter-spacing: -0.02em; color: __INK__; white-space: nowrap; }
  [id="__ID__-l2"] { position: absolute; left: 0; right: 0; top: 430px; text-align: center;
    font-family: "EB Garamond", "Noto Serif SC", serif; font-size: 112px; font-weight: 500;
    line-height: 1.08; letter-spacing: -0.024em; color: __INK__; white-space: nowrap; }
  [id="__ID__-mark"] { position: absolute; left: 960px; top: 700px; width: 132px; height: 132px;
    margin-left: -66px; margin-top: -66px; border-radius: 9999px; background: __TILE2__;
    border: 1px solid rgba(20,20,19,0.2); display: flex; align-items: center; justify-content: center;
    font-family: "EB Garamond", "Noto Serif SC", serif; font-size: 76px; font-weight: 500; color: __INK__;
    box-shadow: 0 1px 3px rgba(20,20,19,0.08); transform-origin: 50% 50%; will-change: transform, opacity; }
  [id="__ID__-spike"] { position: absolute; left: 1032px; top: 646px;
    font-family: "EB Garamond", "Noto Serif SC", serif; font-size: 40px; color: __CORAL__;
    transform-origin: 50% 50%; will-change: transform, opacity; }
"""
    cues = word_cues(project, spec.get("frame_no", 0))

    def place(words, start):
        """spoken cue if the word was found in the narration, else keep stepping forward"""
        out, t = [], start
        for w in words:
            hit = cues.get(w)
            if hit is None:
                for spoken, when in cues.items():
                    if len(w) > 1 and w.startswith(spoken):
                        hit = when
                        break
            t = max(t, hit) if hit is not None else t
            out.append((w, round(t, 2)))
            t += float(spec.get("step", 0.34))
        return out

    s1 = place(lines[0], 0.6)
    s2 = place(lines[1], (s1[-1][1] + 0.7) if s1 else 2.6)
    l1 = "".join(f'<span class="fx-w" id="{{ID}}-l1w{i}">{w}</span>' for i, (w, _) in enumerate(s1))
    l2 = "".join(f'<span class="fx-w" id="{{ID}}-l2w{i}">{w}</span>' for i, (w, _) in enumerate(s2))

    mark_html, mark_js = "", ""
    if mark:
        mark_html = ("  <div id=\"{ID}-mark\">" + mark.get("glyph", "π") + "</div>\n"
                     "  <div id=\"{ID}-spike\">✱</div>")
        want = mark.get("at_word")
        mark_t = next((t for w, t in s2 if w == want), s2[-1][1] if s2 else dur - 2)
        mark_js = (f'    at("#{{ID}}-mark", {round(mark_t + 0.1, 2)}, {{scale: 0}}, {{duration: 0.6}});\n'
                   f'    at("#{{ID}}-spike", {round(mark_t + 0.36, 2)}, {{scale: 0.9}}, {{duration: 0.4}});\n'
                   f'    jitter("#{{ID}}-mark", {round(max(dur - 1.8, 0.5), 2)});\n')

    html = f"""{kicker_html(spec)}
  <div id="{{ID}}-l1">{l1}</div>
  <div id="{{ID}}-l2">{l2}</div>
{mark_html}"""
    js = '    at("#{ID}-kicker", 0.08, {scale: 0}, {duration: 0.5});\n'
    for i, (w, t) in enumerate(s1):
        js += f'    at("#{{ID}}-l1w{i}", {t}, {{}}, {{duration: 0.42}});\n'
    for i, (w, t) in enumerate(s2):
        js += f'    at("#{{ID}}-l2w{i}", {t}, {{y: 22}}, {{duration: 0.46}});\n'
    js += mark_js
    return shell(spec["id"], project, dur, html, js, style, kicker_left="0",
                 final_fade=bool(spec.get("final")))


def build_card_row(spec: dict, project: str, dur: float) -> str:
    """A row of cards (documents, images, use cases) that assemble one by one on their cues,
    with optional tags below and a closing note. `figures` picks the card's invented visual."""
    cards = spec["cards"]
    tags = spec.get("tags") or []
    style = """
  [id="__ID__-title"] { position: absolute; left: 150px; top: 232px; width: 620px;
    font-family: "EB Garamond", "Noto Serif SC", serif; font-size: 82px; font-weight: 500;
    line-height: 1.16; letter-spacing: -0.02em; color: __INK__; }
  [id="__ID__-sub"] { position: absolute; left: 150px; top: 560px; width: 620px;
    font-family: "Inter", "Noto Sans SC", sans-serif; font-size: 30px; font-weight: 400;
    line-height: 1.6; color: rgba(20,20,19,0.72); white-space: pre-line; }
  .fx-card { position: absolute; width: __CARDW__px; height: 380px; background: __TILE__;
    border: 1px solid rgba(20,20,19,0.12); border-radius: 12px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(20,20,19,0.08), 0 4px 16px rgba(20,20,19,0.04);
    padding: 24px; box-sizing: border-box; transform-origin: 50% 50%; will-change: transform, opacity; }
  .fx-card-label { font-family: "JetBrains Mono", "Noto Sans SC", monospace; font-size: 26px;
    font-weight: 500; color: __INK__; }
  .fx-card-fig { position: absolute; left: 24px; right: 24px; bottom: 24px; }
  .fx-tag { position: absolute; font-family: "JetBrains Mono", "Noto Sans SC", monospace;
    font-size: 20px; font-weight: 500; letter-spacing: 0.06em; color: __INK__; background: __CREAM__;
    border: 1px solid rgba(20,20,19,0.12); border-radius: 9999px; padding: 8px 18px; white-space: nowrap;
    transform-origin: 50% 50%; will-change: transform, opacity; }
"""
    n = len(cards)
    gap = 40
    width = 330
    if n >= 4:
        gap, width = 32, 280
    left0 = 860 if spec.get("title") else 176
    if n == 1:
        # a single card is a different composition, not a row of one: centre it and let it breathe
        gap, width, left0 = 0, 420, 750
    else:
        total = n * width + (n - 1) * gap
        left0 = max(left0, round((1920 - total) / 2))   # never overflow the right margin
    if left0 + n * width + (n - 1) * gap > 1860:
        left0 = 1860 - (n * width + (n - 1) * gap)
    cues = word_cues(project, spec.get("frame_no", 0))
    style = style.replace("__CARDW__", str(width))
    if n == 1:
        style += ('\n  .fx-card { height: 420px; }\n'
                  '  [id="__ID__-title"] { left: 0; right: 0; text-align: center; width: auto; top: 150px; }\n'
                  '  [id="__ID__-sub"] { left: 0; right: 0; text-align: center; width: auto; top: 320px; }\n')
    cards_html, cards_js = [], ""
    for i, c in enumerate(cards):
        left = left0 + i * (width + gap)
        fig = c.get("figure", "lines")
        fig_html = {
            "lines": '<div class="fx-card-fig"><div style="height:9px;background:rgba(20,20,19,0.16);border-radius:3px;margin-bottom:12px;width:86%"></div>'
                     '<div style="height:9px;background:rgba(20,20,19,0.16);border-radius:3px;margin-bottom:12px;width:66%"></div>'
                     '<div style="height:9px;background:rgba(20,20,19,0.16);border-radius:3px;width:74%"></div></div>',
            "grid": '<div class="fx-card-fig" style="display:flex;flex-wrap:wrap;gap:7px">' + "".join(
                f'<div style="width:56px;height:30px;border-radius:4px;background:rgba(20,20,19,{0.10 if k % 3 else 0.26})"></div>'
                for k in range(9)) + '</div>',
            "panel": '<div class="fx-card-fig" style="height:150px;border-radius:8px;background:rgba(20,20,19,0.14)"></div>',
            "circle": '<div class="fx-card-fig" style="height:150px;display:flex;align-items:center;justify-content:center">'
                      '<div style="width:110px;height:110px;border-radius:9999px;border:2px solid rgba(20,20,19,0.45)"></div></div>',
            "chart": '<div class="fx-card-fig"><svg width="100%" height="140" viewBox="0 0 280 140" preserveAspectRatio="none">'
                     '<path d="M 6 130 L 90 70 L 170 96 L 274 12" fill="none" stroke="rgba(20,20,19,0.55)" stroke-width="3"/>'
                     '<circle cx="90" cy="70" r="6" fill="#CC785C"/></svg></div>',
            "before_after": '<div class="fx-card-fig"><svg width="100%" height="140" viewBox="0 0 280 140" preserveAspectRatio="none">'
                            '<rect x="0" y="0" width="130" height="140" fill="rgba(20,20,19,0.16)"/>'
                            '<rect x="150" y="0" width="130" height="140" fill="rgba(204,120,92,0.45)"/>'
                            '<path d="M 118 70 L 146 70" stroke="rgba(20,20,19,0.7)" stroke-width="3"/>'
                            '<path d="M 140 63 L 152 70 L 140 77" fill="none" stroke="rgba(20,20,19,0.7)" stroke-width="3"/></svg></div>',
        }.get(fig, "")
        cards_html.append(f'''  <div class="fx-card" id="{{ID}}-c{i+1}" style="left: {left}px; top: 250px;">
    <div class="fx-card-label">{c.get("label","")}</div>
    {fig_html}
  </div>''')
        t = resolve_cue(c, cues, i, n, 1.0, dur - 2.5)
        cards_js += f'    at("#{{ID}}-c{i+1}", {t}, {{y: 34, scale: 0.96}}, {{duration: 0.55}});\n'
        coral = c.get("coral")
        if coral:
            cards_js += (f'    tl.fromTo("#{{ID}}-c{i+1}", {{ boxShadow: "0 0 0 0 rgba(204,120,92,0)" }},'
                         f' {{ boxShadow: "0 0 0 3px rgba(204,120,92,0.45)", duration: 0.4, ease: "power2.out" }}, {round(t+0.2,2)});\n')
    tags_html, tags_js = "", ""
    for i, tg in enumerate(tags):
        t = resolve_cue({"cue": tg if isinstance(tg, str) else tg.get("cue", ""),
                         "label": tg if isinstance(tg, str) else tg.get("label", "")},
                        cues, i, len(tags), 3.0, dur - 2.0)
        label = tg if isinstance(tg, str) else tg.get("label", "")
        tags_html += f'  <div class="fx-tag" id="{{ID}}-t{i+1}" style="left: {left0 + i*200}px; top: 668px;">{label}</div>\n'
        tags_js += f'    at("#{{ID}}-t{i+1}", {t}, {{scale: 0.9}}, {{duration: 0.4}});\n'
    title = "".join(f'<span class="fx-w" data-t="{round(1.2 + i*0.25,2)}">{w}</span>' for i, w in enumerate(spec.get("title", [])))
    note_html_, note_js = note_html(spec, spec.get("note_at", dur - 2.0), dur - 1.6)
    html = f"""{kicker_html(spec)}
  <div id="{{ID}}-title">{title}</div>
  <div id="{{ID}}-sub">{spec.get("sub","")}</div>
{"".join(cards_html)}{tags_html}{note_html_}"""
    js = '    at("#{ID}-kicker", 0.08, {scale: 0}, {duration: 0.5});\n'
    js += '    gsap.utils.toArray("#{ID}-title .fx-w").forEach(function (el) { at(el, parseFloat(el.getAttribute("data-t")), {}, {duration: 0.45}); });\n'
    if spec.get("sub"):
        js += '    at("#{ID}-sub", 2.2, {}, {duration: 0.5});\n'
    js += cards_js + tags_js + note_js
    return shell(spec["id"], project, dur, html, js, style, final_fade=bool(spec.get("final")))


def build_panel_demo(spec: dict, project: str, dur: float) -> str:
    """The navy surface shape: a terminal / browser / code panel (optionally typing a command on),
    plus a row of action chips that light up in sequence on their cues, plus an optional travelling
    cursor. One coral accent. This also covers the install-command CTA when `final` is set."""
    kind = spec.get("panel", "terminal")
    chips = spec.get("chips") or []
    typed = spec.get("type_cmd")  # type-on text, e.g. a command or a path
    pill = spec.get("panel_size") == "pill"   # the compact install-command / path shape
    geometry = {"left": 460, "top": 250, "width": 1000, "height": 122} if pill else \
               {"left": 360, "top": 190, "width": 1200, "height": 470}
    body_font = 34 if pill else 26
    style = """
  [id="__ID__-panel"] { position: absolute; left: __PL__px; top: __PT__px; width: __PW__px; height: __PH__px;
    background: __NAVY__; border: 1px solid rgba(250,249,245,0.14); border-radius: 8px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(20,20,19,0.08), 0 4px 16px rgba(20,20,19,0.04);
    transform-origin: 50% 50%; will-change: transform, opacity; }
  [id="__ID__-bar"] { height: 54px; background: __NAVY_ELEV__; border-bottom: 1px solid rgba(250,249,245,0.14);
    display: flex; align-items: center; gap: 10px; padding: 0 22px;
    font-family: "JetBrains Mono", "Noto Sans SC", monospace; font-size: 20px; color: rgba(250,249,245,0.62); }
  [id="__ID__-bar"] .fx-dot { width: 12px; height: 12px; border-radius: 9999px; background: rgba(250,249,245,0.2); }
  [id="__ID__-body"] { padding: __BODYPAD__; font-family: "JetBrains Mono", "Noto Sans SC", monospace;
    font-size: __BODYFS__px; line-height: 1.75; color: #FAF9F5; white-space: pre-wrap; }
  .fx-caret { display: inline-block; width: 14px; height: 30px; background: #FAF9F5; vertical-align: -5px; margin-left: 5px; }
  [id="__ID__-row"] { position: absolute; left: __PL__px; top: __ROWTOP__px; width: __PW__px;
    display: flex; justify-content: space-between; }
  .fx-chip { height: 64px; padding: 0 30px; background: __TILE__; border: 1px solid rgba(20,20,19,0.12);
    border-radius: 9999px; display: flex; align-items: center; gap: 12px;
    font-family: "Inter", "Noto Sans SC", sans-serif; font-size: 26px; font-weight: 500; color: __INK__;
    white-space: nowrap; transform-origin: 50% 50%; will-change: transform, opacity; }
  .fx-chip .fx-d2 { width: 12px; height: 12px; border-radius: 9999px; background: rgba(20,20,19,0.25); }
  [id="__ID__-cursor"] { position: absolute; left: 0; top: 0; width: 26px; height: 34px;
    transform-origin: 0% 0%; will-change: transform, opacity; }
  [id="__ID__-cursor"] path { fill: __INK__; }
  [id="__ID__-ripple"] { position: absolute; left: 0; top: 0; width: 22px; height: 22px;
    margin-left: -11px; margin-top: -11px; border-radius: 9999px; border: 2px solid __CORAL__;
    transform-origin: 50% 50%; will-change: transform, opacity; }
"""
    cues = word_cues(project, spec.get("frame_no", 0))
    style = (style.replace("__PL__", str(geometry["left"])).replace("__PT__", str(geometry["top"]))
             .replace("__PW__", str(geometry["width"])).replace("__PH__", str(geometry["height"]))
             .replace("__ROWTOP__", str(geometry["top"] + geometry["height"] + 30))
             .replace("__BODYFS__", str(body_font))
             .replace("__BODYPAD__", "0 40px" if pill else "26px 30px"))
    if pill:
        style += '\n  [id="__ID__-panel"] { display: flex; align-items: center; }\n'
    bar = {"terminal": "pi — ~/project", "browser": "https://example.com/report",
           "code": "pi -p \"脚本模式\""}.get(kind, "pi")
    body = "" if typed else (spec.get("body") or "")
    body_inner = body if body else '<span id="{ID}-typed"></span><span class="fx-caret" id="{ID}-caret"></span>'
    html = f"""{kicker_html(spec)}
  <div id="{{ID}}-panel">
    <div id="{{ID}}-bar"><span class="fx-dot"></span><span class="fx-dot"></span><span class="fx-dot"></span>
      <span style="margin-left:16px">{bar}</span></div>
    <div id="{{ID}}-body">{body_inner}</div>
  </div>
  <div id="{{ID}}-row">
"""
    js = '    at("#{ID}-kicker", 0.08, {scale: 0}, {duration: 0.5});\n'
    js += f'    at("#{{ID}}-panel", 1.0, {{y: 18, scale: 0.96}}, {{duration: 0.6}});\n'
    if typed:
        start = float(spec.get("type_at", 1.15))
        span = float(spec.get("type_span", 1.3))
        js += f'    at("#{{ID}}-caret", {round(start - 0.05, 2)}, {{}}, {{duration: 0.2}});\n'
        js += '    tl.set("#{ID}-typed", { textContent: "" }, 0);\n'
        js += f'    var CMD = {json.dumps(typed, ensure_ascii=False)};\n'
        js += (f'    for (var ci = 1; ci <= CMD.length; ci++) {{\n'
               f'      (function (k) {{ tl.set("#{{ID}}-typed", {{ textContent: CMD.slice(0, k) }}, '
               f'{round(start, 3)} + k * ({round(span / max(len(typed), 1), 4)})); }})(ci);\n'
               f'    }}\n')
        for b in range(int(max(dur - start - 2.0, 1) / 0.7)):
            js += (f'    tl.to("#{{ID}}-caret", {{ opacity: 0, duration: 0.26 }}, {round(start + span + 0.4 + b * 0.7, 2)});\n'
                   f'    tl.to("#{{ID}}-caret", {{ opacity: 1, duration: 0.26 }}, {round(start + span + 0.66 + b * 0.7, 2)});\n')
    for i, c in enumerate(chips):
        label = c if isinstance(c, str) else c.get("label", "")
        html += f'    <div class="fx-chip" id="{{ID}}-chip{i+1}"><span class="fx-d2"></span>{label}</div>\n'
        t = resolve_cue(c if isinstance(c, dict) else {"label": label}, cues, i, len(chips), 2.2, dur - 2.0)
        js += f'    at("#{{ID}}-chip{i+1}", {t}, {{y: 16}}, {{duration: 0.45}});\n'
        js += f'    tl.to("#{{ID}}-chip{i+1}", {{ borderColor: "rgba(93,184,114,0.7)", duration: 0.25, ease: "power2.out" }}, {round(t+0.1,2)});\n'
        js += f'    tl.to("#{{ID}}-chip{i+1} .fx-d2", {{ backgroundColor: "#5DB872", duration: 0.25, ease: "power2.out" }}, {round(t+0.1,2)});\n'
    html += "  </div>\n"
    if spec.get("cursor") and chips:
        html += ('  <div id="{ID}-cursor"><svg width="26" height="34" viewBox="0 0 26 34">'
                 '<path d="M2 2 L2 26 L8.5 20 L13 31 L18 29 L13.5 18.5 L22 18 Z"/></svg></div>\n'
                 '  <div id="{ID}-ripple"></div>')
    note_html_, note_js = note_html(spec, spec.get("note_at", dur - 2.2), dur - 1.6)
    html += note_html_
    mock_html, mock_js = mock_caption_html(spec)
    html += mock_html
    if spec.get("note_coral"):
        pass  # the underline ships inside the note element (see note_html)
    if spec.get("cursor") and chips:
        # cursor targets are measured in LAYOUT space: a mounted sub-composition can be scaled, and
        # getBoundingClientRect would then report host-scale pixels (the cursor flies off-frame)
        js += ('    var rowEl = document.getElementById("{ID}-row");\n'
               '    var cursorEl = document.getElementById("{ID}-cursor");\n'
               '    var rippleEl = document.getElementById("{ID}-ripple");\n'
               '    at(cursorEl, 2.4, {}, {duration: 0.3});\n')
        for i, c in enumerate(chips):
            label = c if isinstance(c, str) else c.get("label", "")
            t = resolve_cue(c if isinstance(c, dict) else {"label": label}, cues, i, len(chips), 2.2, dur - 2.0)
            js += (f'    var c{i+1} = document.getElementById("{{ID}}-chip{i+1}");\n'
                   f'    var x{i+1} = rowEl.offsetLeft + c{i+1}.offsetLeft + c{i+1}.offsetWidth / 2;\n'
                   f'    var y{i+1} = rowEl.offsetTop + c{i+1}.offsetTop + c{i+1}.offsetHeight / 2;\n'
                   f'    tl.to(cursorEl, {{ x: x{i+1} - 13, y: y{i+1} - 17, duration: 0.45, ease: "power2.inOut" }}, {round(max(t-0.45,0.5),2)});\n'
                   f'    tl.set(rippleEl, {{ x: x{i+1}, y: y{i+1} }}, {t});\n'
                   f'    tl.fromTo(rippleEl, {{ opacity: 0.9, scale: 0.4 }}, {{ opacity: 0, scale: 2.6, duration: 0.55, ease: "power2.out" }}, {t});\n')
        js += f'    tl.to(cursorEl, {{ opacity: 0, duration: 0.4 }}, {round(dur - 3.4,2)});\n'
    js += note_js + mock_js
    return shell(spec["id"], project, dur, html, js, style, final_fade=bool(spec.get("final")),
                 note_top=note_top_for(spec), note_fs=note_fs_for(spec),
                 sub_top=spec.get("sub_top", 700))


BUILDERS = {
    "kinetic-hook": (build_kinetic_hook, "两行动能大字 + 可选徽标（开场钩子、结论句）"),
    "card-row": (build_card_row, "一排卡片按台词逐张拼入 + 可选标签行 + 收尾句（清单、对比、场景）"),
    "panel-demo": (build_panel_demo, "暖海军蓝面板（终端/浏览器/代码）+ 动作芯片逐个点亮 + 可选光标（演示）"),
}


def build_frame(spec: dict, project: str) -> str:
    kind = spec.get("archetype")
    if kind not in BUILDERS:
        raise SystemExit(f"unknown archetype '{kind}' — try: {', '.join(BUILDERS)}")
    dur = frame_duration(project, spec.get("frame_no", 0), float(spec.get("duration", 8.0)))
    spec.setdefault("frame_no", 0)
    if kind == "kinetic-hook":
        return BUILDERS[kind][0](spec, project, dur)
    if kind == "card-row":
        return BUILDERS[kind][0](spec, project, dur)
    return BUILDERS[kind][0](spec, project, dur)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    ap.add_argument("--frame", help="frame spec json")
    ap.add_argument("--all", nargs="*", help="many frame specs")
    ap.add_argument("--out-dir", default="compositions/frames")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for k, (_, desc) in BUILDERS.items():
            print(f"  {k:14s} {desc}")
        return 0
    if not a.project:
        print("--project is required (unless --list)")
        return 1

    specs = []

    def load(path: str):
        data = json.load(open(path, encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("frames"), list):
            for i, f in enumerate(data["frames"], 1):   # a story.json is accepted as a batch
                f.setdefault("frame_no", i)
                f.setdefault("id", f"{i:02d}-{f.get('archetype','frame')}")
                specs.append(f)
        elif isinstance(data, list):
            specs.extend(data)
        else:
            specs.append(data)

    if a.frame:
        load(a.frame)
    for pattern in (a.all or []):
        for f in sorted(glob.glob(pattern)):
            load(f)
    if not specs:
        print("nothing to build — pass --frame or --all")
        return 1

    out_dir = os.path.join(a.project, a.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    for spec in specs:
        html = build_frame(spec, a.project)
        path = os.path.join(out_dir, f"{spec['id']}.html")
        open(path, "w", encoding="utf-8").write(html)
        print(f"  {spec['id']:22s} {spec['archetype']:14s} → {os.path.relpath(path, a.project)}")
    print(f"\n{len(specs)} frame(s) written. Next: sync durations → assemble → transitions → "
          f"lint/check → snapshot → render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
