# -*- coding: utf-8 -*-
"""Element-id safety fixer — the #1 cause of "frame renders blank".

Digit-leading ids (`03-hands-on-panel`) break `querySelector('#03-…')` (SyntaxError → the frame's
timeline never finishes building → content stays at its from-state) and make CSS rules silently dead.
This rewrites ids, `#…` selectors and `getElementById("…")` strings to a letter prefix while leaving
`data-composition-id` intact, then reports anything it could not fix.

    python fix_ids.py --project <PROJ> [--prefix f] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ID_ATTR = re.compile(r'(?<![\w-])id="(\d\d)-')
SEL = re.compile(r"#(\d\d)-")
GET_BY_ID = re.compile(r'getElementById\("(\d\d)-')


def fix_text(s: str, prefix: str) -> tuple[str, int]:
    n = 0
    s, k = ID_ATTR.subn(lambda m: f'id="{prefix}{m.group(1)}-', s); n += k
    s, k = SEL.subn(lambda m: f"#{prefix}{m.group(1)}-", s); n += k
    s, k = GET_BY_ID.subn(lambda m: f'getElementById("{prefix}{m.group(1)}-', s); n += k
    return s, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--glob", default="compositions/**/*.html")
    ap.add_argument("--prefix", default="f")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import glob as g

    files = sorted(g.glob(os.path.join(a.project, a.glob), recursive=True))
    if not files:
        print("no files matched", a.glob)
        return 1
    total = 0
    for f in files:
        s = open(f, encoding="utf-8").read()
        new, n = fix_text(s, a.prefix)
        if n and not a.dry_run:
            open(f, "w", encoding="utf-8").write(new)
        total += n
        print(f"  {'(dry) ' if a.dry_run else ''}{os.path.relpath(f, a.project)}: {n} id(s)")

    # anything still digit-leading is a real problem (data-composition-id is fine by design)
    leftovers = []
    for f in files:
        s = open(f, encoding="utf-8").read()
        for pat, label in ((r'(?<![\w-])id="\d', "id attr"), (r"#\d\d-", "selector"), (r'getElementById\("\d', "getElementById")):
            if re.search(pat, s):
                leftovers.append(f"{os.path.relpath(f, a.project)}: {label}")
    print(f"total rewritten: {total}")
    if leftovers:
        print("STILL UNSAFE (fix by hand):")
        for l in leftovers:
            print("  -", l)
        return 2
    print("ok — every id, selector and getElementById now starts with a letter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
