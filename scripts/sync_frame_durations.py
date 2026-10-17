# -*- coding: utf-8 -*-
"""Push per-frame durations from audio_meta.json into the frame compositions and STORYBOARD.

Run whenever the narration changed: a frame's own `data-duration` (root + every `class="clip"` layer)
must equal its narration window, or content gets clipped early / the wrapper unmounts too soon.
Also moves a final frame's fade so it still lands inside its (possibly shorter) duration.

    python sync_frame_durations.py --project <PROJ> [--storyboard STORYBOARD.md]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT_DUR = re.compile(r'(data-composition-id="[^"]+"[\s\S]{0,240}?data-duration=")[\d.]+(")')
CLIP_DUR = re.compile(r'(class="clip" id="[^"]+" data-start="0" data-duration=")[\d.]+(")')
SB_DUR = re.compile(r"(?m)^(\s*[-*]\s+duration\s*:\s*)[\d.]+s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--storyboard", default="STORYBOARD.md")
    ap.add_argument("--fade-lead", type=float, default=0.85,
                    help="seconds before the end where a final-frame fade should start")
    a = ap.parse_args()

    meta_path = os.path.join(a.project, "audio_meta.json")
    if not os.path.exists(meta_path):
        print("no audio_meta.json — nothing to sync (silent film?)")
        return 1
    meta = json.load(open(meta_path, encoding="utf-8"))
    durs = {int(v["frame"]): round(float(v["duration_s"]), 3) for v in meta.get("voices", [])}
    total = round(sum(durs.values()), 3)
    print("durations:", ", ".join(f"F{k}={v}" for k, v in sorted(durs.items())), f"→ total {total}s")

    frames_dir = os.path.join(a.project, "compositions", "frames")
    for name in sorted(os.listdir(frames_dir)) if os.path.isdir(frames_dir) else []:
        if not name.endswith(".html"):
            continue
        m = re.match(r"(\d+)", name)
        if not m or int(m.group(1)) not in durs:
            continue
        n = int(m.group(1))
        d = durs[n]
        p = os.path.join(frames_dir, name)
        s = open(p, encoding="utf-8").read()
        s = ROOT_DUR.sub(lambda x: f"{x.group(1)}{d}{x.group(2)}", s, count=1)
        s = CLIP_DUR.sub(lambda x: f"{x.group(1)}{d}{x.group(2)}", s)
        # a final frame may own an exit fade; keep it inside the (possibly shorter) duration
        def _fade(mm: re.Match) -> str:
            at = float(mm.group(2))
            if at >= d - a.fade_lead:  # would start after the frame ends — pull it earlier
                return f"{mm.group(1)}{round(d - a.fade_lead, 2)}{mm.group(3)}"
            return mm.group(0)

        s = re.sub(r"(\{\s*opacity: 0, duration: [\d.]+, ease: \"[^\"]*\"\s*\},\s*)([\d.]+)(\s*\))",
                   _fade, s)
        # and the end anchor that keeps the timeline spanning the whole frame
        s = re.sub(r"(tl\.to\(\{\}, \{ duration: 0\.01 \}, )([\d.]+)(\))",
                   lambda mm: f"{mm.group(1)}{round(d - 0.01, 2)}{mm.group(3)}", s)
        open(p, "w", encoding="utf-8").write(s)
        print(f"  {name} → {d}s")

    sb = os.path.join(a.project, a.storyboard)
    if os.path.exists(sb):
        lines = open(sb, encoding="utf-8").read().splitlines(keepends=True)
        cur, updated = None, 0
        seen: set[int] = set()
        # enumerate(), never a manual counter: a `continue` that skips `i += 1` rewrites the wrong
        # line — that exact bug once overwrote the next frame's heading and silently dropped a frame
        # from the assembly.
        for i, ln in enumerate(lines):
            m = re.match(r"^#{2,3}\s+(?:frame|beat|scene)\b.*?(\d+)", ln, re.I)
            if m:
                cur = int(m.group(1))
                continue
            dm = SB_DUR.match(ln)
            if not dm or cur is None:
                continue
            if cur in seen:            # a stray duplicate duration line: drop it
                lines[i] = ""
                continue
            seen.add(cur)
            if cur in durs:
                lines[i] = f"{dm.group(1)}{durs[cur]}s\n"
                updated += 1
        open(sb, "w", encoding="utf-8").write("".join(lines))
        print(f"  {a.storyboard}: {updated} frame duration(s) updated")

    print(f"\nnext (order matters): re-assemble the index → re-inject transitions (they pad each frame's\n"
          f"  own duration by the transition length, so this order is what keeps wrapper and frame in step)\n"
          f"  → `npx hyperframes lint && npx hyperframes check` → snapshot → render. Full length {total}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
