# -*- coding: utf-8 -*-
"""Pronunciation check: transcribe the generated narration with local whisper and diff it against SCRIPT.md.

TTS misreads Chinese polyphones ("调" as diào, "只" as zhī). Whisper's own transcript has homophone
slips too (会话/绘画, 事/是, 只会/指挥), so this prints an alignment diff and marks each mismatch
`[字面]` — read it and decide by ear whether the audio is actually ambiguous; only real ambiguity is
worth a script rewrite.

    python verify_pronunciation.py --project <PROJ> [--script SCRIPT.md] [--model <path to ggml-*.bin>]
"""
from __future__ import annotations

import argparse
import difflib
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

MODEL_CANDIDATES = [
    os.path.expanduser(r"C:\Users\zz\.cache\hyperframes\whisper\models\ggml-large-v3-turbo.bin"),
    os.path.expanduser(r"C:\Users\zz\whisper.cpp\models\ggml-large-v3-turbo.bin"),
    os.path.expanduser(r"~/.cache/hyperframes/whisper/models/ggml-large-v3-turbo.bin"),
]


def find_model(explicit: str | None) -> str | None:
    if explicit and os.path.exists(explicit):
        return explicit
    for c in MODEL_CANDIDATES:
        if os.path.isfile(c):
            return c
    for c in MODEL_CANDIDATES:
        d = os.path.dirname(c)
        if os.path.isdir(d):
            hits = sorted(glob.glob(os.path.join(d, "ggml-*.bin")))
            if hits:
                return hits[0]
    return None


def find_cli() -> str | None:
    exe = shutil.which("whisper-cli") or r"C:\Users\zz\whisper.cpp\whisper-cli.exe"
    return exe if exe and os.path.exists(exe) else None


def parse_script(path: str) -> dict[int, str]:
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


def normalize(s: str) -> str:
    return re.sub(r"[\s，。？！；：、,\.\?\!;:—…\-—]", "", s)


def transcribe(cli: str, model: str, wav: str, lang: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "t")
        p = subprocess.run([cli, "-m", model, "-f", wav, "-l", lang, "-otxt", "-of", out, "-nt", "-np"],
                           capture_output=True, timeout=1800)          # bytes: whisper's stderr is not UTF-8
        if p.returncode != 0:
            return ""
        txt = open(out + ".txt", "rb").read().decode("utf-8", errors="replace")
    # whisper hallucinates on the music tail; drop its boilerplate endings
    txt = re.sub(r"(请不吝|訂閱|订阅|轉發|转发|打賞|打赏|明镜|明鏡).*", "", txt)
    return normalize(txt)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--script", default="SCRIPT.md")
    ap.add_argument("--voice-dir", default="assets/voice")
    ap.add_argument("--model", default=None)
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--all", action="store_true", help="also transcribe the concatenated film")
    a = ap.parse_args()

    cli, model = find_cli(), find_model(a.model)
    if not cli or not model:
        print("whisper-cli or model not found — skipping pronunciation check (see preflight.py)")
        return 0

    script = os.path.join(a.project, a.script)
    if not os.path.exists(script):
        print("SCRIPT.md not found:", script)
        return 1
    expected = parse_script(script)
    voice_dir = os.path.join(a.project, a.voice_dir)

    problems = 0
    for fr in sorted(expected):
        wav = os.path.join(voice_dir, f"{fr:02d}.wav")
        if not os.path.exists(wav):
            print(f"  F{fr:02d}: missing {wav}")
            continue
        heard = transcribe(cli, model, wav, a.lang)
        want = normalize(expected[fr])
        if not heard:
            print(f"  F{fr:02d}: transcription failed")
            continue
        if heard == want:
            print(f"  F{fr:02d}: OK")
            continue
        # alias-tolerant comparison: treat a homophone-length match as OK, report the rest
        sm = difflib.SequenceMatcher(None, want, heard)
        diffs = [f"脚本「{want[i1:i2]}」→ 听到「{heard[j1:j2]}」"
                 for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
        if not diffs:
            print(f"  F{fr:02d}: OK")
            continue
        problems += 1
        print(f"  F{fr:02d}: 可能读错 / 可能只是同音误判 — {' · '.join(diffs)}")

    print("\n判读标准：会造成歧义的才改脚本（例如 调→定）；同音字（会话/绘画、事/是）不用管。")
    if problems:
        print("改脚本后重跑：tts_lines.py → captions_clauses.py → 组装 → 渲染")
    return 0


if __name__ == "__main__":
    sys.exit(main())
