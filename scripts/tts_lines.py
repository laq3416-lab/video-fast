# -*- coding: utf-8 -*-
"""Narration generator: per-line TTS with word timings, tail trimming, and timeline-exact frame lengths.

Why this exists: edge-tts gives excellent Chinese voices but (a) needs an explicit proxy, (b) appends
~0.9s of trailing silence per segment, and (c) any new take drifts off the cue times a storyboard was
authored against. This script fixes all three: it trims to the last word boundary, adds a fixed head
pad, pads the tail to the target frame length, and can warp a new take back onto the previous
timings (`atempo`) so picture cues stay locked when you change voice or wording.

    # pick a voice (writes samples for the user to choose)
    python tts_lines.py --script SCRIPT.md --samples
    # generate
    python tts_lines.py --project PROJ --script PROJ/SCRIPT.md --voice zh-CN-YunxiNeural \
        --head 0.5 --tails "0.9,1.8,0.9,0.9,1.8,0.9,1.8,0.9,2.5,5.5"
    # re-voice without breaking the edit (previous per-frame voice lengths come from the old audio_meta)
    python tts_lines.py --project PROJ --script PROJ/SCRIPT.md --voice zh-CN-XiaoxiaoNeural \
        --target-durations 5.69,10.85,10.92,10.15,10.85,9.71,8.27,8.01,4.50,5.47

SCRIPT.md shape: `## Line N — label (Frame N)`, a `**Delivery:** ... rate +3% · pitch +4Hz` row,
and the spoken text indented by four spaces or one tab. Only the indented text is spoken.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys

import edge_tts  # type: ignore

SAMPLE_LINE = "如果 AI 不只是给你出主意——而是直接动手，把活做完呢？"
VOICES = [
    ("zh-CN-YunxiNeural", "男声 · 阳光"),
    ("zh-CN-XiaoxiaoNeural", "女声 · 温暖"),
    ("zh-CN-YunyangNeural", "男声 · 沉稳"),
]


def parse_script(md: str) -> list[dict]:
    out: list[dict] = []
    cur: dict | None = None

    def flush() -> None:
        nonlocal cur
        if cur and cur["text"].strip():
            out.append(cur)
        cur = None

    for line in md.splitlines():
        h = re.match(r"^#{2,3}\s+.*?\(frame\s+(\d+)\)", line, re.I)
        if h:
            flush()
            cur = {"frame": int(h.group(1)), "text": "", "rate": "+0%", "pitch": "+0Hz"}
            continue
        if not cur:
            continue
        m = re.search(r"rate\s*([-+]\d+)%\s*[··]\s*pitch\s*([-+]?\d+)Hz", line)
        if m:
            cur["rate"], cur["pitch"] = f"{m.group(1)}%", f"{m.group(2)}Hz"
        if re.match(r"^\s*\*\*", line):
            continue
        t = re.match(r"^(?: {4,}|\t)(.+)$", line)
        if t:
            cur["text"] += (" " if cur["text"] else "") + t.group(1).strip()
    flush()
    return out


async def gen_line(text: str, voice: str, rate: str, pitch: str, out_path: str, proxy: str | None) -> list[dict]:
    words: list[dict] = []
    audio = bytearray()
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, proxy=proxy, boundary="WordBoundary")
    async for ch in chunk_stream(comm):
        if ch["type"] == "audio":
            audio.extend(ch["data"])
        elif ch["type"] == "WordBoundary":
            words.append({
                "text": ch["text"],
                "start": round(ch["offset"] / 1e7, 3),
                "end": round((ch["offset"] + ch["duration"]) / 1e7, 3),
            })
    with open(out_path, "wb") as f:
        f.write(bytes(audio))
    return words


async def chunk_stream(comm):  # thin wrapper so tests can stub it
    async for ch in comm.stream():
        yield ch


def dur_of(path: str) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(p.stdout.strip())


def ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def parse_tails(spec: str, n: int) -> list[float]:
    vals = [float(x) for x in spec.split(",") if x.strip()]
    if len(vals) < n:
        vals += [vals[-1] if vals else 0.9] * (n - len(vals))
    return vals[:n]


async def do_samples(script: str | None, proxy: str | None, outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    text = SAMPLE_LINE
    if script and os.path.exists(script):
        lines = parse_script(open(script, encoding="utf-8").read())
        if lines:
            text = lines[0]["text"]
    for i, (voice, tag) in enumerate(VOICES, 1):
        p = os.path.join(outdir, f"{i}-{voice}.mp3")
        await gen_line(text, voice, "+0%", "+0Hz", p, proxy)
        print(f"  {i}. {voice} ({tag}) — {dur_of(p):.2f}s → {p}")
    print("\n让用户挑一个音色再生成全片；主推第一个（男声阳光），除非题材更适合其他。")


async def main_async(a) -> int:
    script_path = os.path.abspath(a.script)
    if not os.path.exists(script_path):
        print(f"SCRIPT.md not found: {script_path}")
        return 1
    lines = parse_script(open(script_path, encoding="utf-8").read())
    if not lines:
        print("no spoken lines parsed — check the `## ... (Frame N)` headings and indented text")
        return 1

    if a.samples:
        await do_samples(script_path, a.proxy, a.sample_dir or os.path.join(os.path.dirname(script_path), "voice-samples"))
        return 0

    project = os.path.abspath(a.project or os.path.dirname(script_path))
    voice_dir = os.path.join(project, "assets", "voice")
    os.makedirs(voice_dir, exist_ok=True)
    scratch = a.scratch or os.path.join(project, ".voice-tmp")
    os.makedirs(scratch, exist_ok=True)

    targets = [float(x) for x in a.target_durations.split(",")] if a.target_durations else []
    tails = parse_tails(a.tails, len(lines))
    meta_voices, report = [], []

    for i, ln in enumerate(lines):
        fr, nn = ln["frame"], f"{ln['frame']:02d}"
        raw = os.path.join(scratch, f"{nn}-raw.mp3")
        words = await gen_line(ln["text"], a.voice, ln["rate"], ln["pitch"], raw, a.proxy)
        if not words:
            print(f"  ! F{nn}: no word boundaries returned — check the text/voice")
        src_dur = dur_of(raw)
        speech_end = words[-1]["end"] if words else src_dur
        target_voice = targets[i] if i < len(targets) and targets[i] > 0 else None

        warped = os.path.join(scratch, f"{nn}-warp.wav")
        scale = 1.0  # warped-axis time = source time × scale
        if target_voice and abs(target_voice - src_dur) > 0.005:
            ratio = src_dur / target_voice  # atempo >1 speeds up → output = src/ratio = target
            ffmpeg(["-i", raw, "-filter:a", f"atempo={ratio:.6f}", "-ar", "44100", "-ac", "1", warped])
            scale = 1.0 / ratio
        else:
            ffmpeg(["-i", raw, "-ar", "44100", "-ac", "1", warped])
        speech_end *= scale

        # trim the take's own trailing silence, then place it: head pad + voice + tail
        keep = speech_end + a.voice_pad
        frame_dur = round(a.head + speech_end + tails[i] + 0.05, 3)
        out = os.path.join(voice_dir, f"{nn}.wav")
        ffmpeg(["-i", warped,
                "-af", f"atrim=0:{keep:.3f},adelay={int(a.head * 1000)}|{int(a.head * 1000)},apad",
                "-t", str(frame_dur), "-ar", "44100", "-ac", "1", out])

        # word times on the final axis: warped scale + head pad
        ws = [{"id": f"w{k}", "text": w["text"],
               "start": round(w["start"] * scale + a.head, 3),
               "end": round(w["end"] * scale + a.head, 3)} for k, w in enumerate(words)]
        meta_voices.append({"frame": fr, "path": f"assets/voice/{nn}.wav",
                            "duration_s": frame_dur, "words": ws, "source": "host"})
        report.append({"frame": fr, "voice_src": round(src_dur, 3), "frame_dur": frame_dur,
                       "tail": tails[i], "words": len(ws), "text": ln["text"]})
        print(f"  F{nn}: voice {src_dur:5.2f}s → frame {frame_dur:5.2f}s "
              f"(tail {tails[i]}s, {len(ws)} words)")

    total = round(sum(v["duration_s"] for v in meta_voices), 3)
    meta_path = os.path.join(project, "audio_meta.json")
    old = {}
    if os.path.exists(meta_path):
        try:
            old = json.load(open(meta_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            old = {}
    bgm = old.get("bgm") or {"path": "assets/bgm/track.wav", "volume": 0.14, "query": "uplifting corporate tech",
                             "duration_s": total + 4, "source": "host"}
    bgm["duration_s"] = total + 4
    meta = {"bgm": bgm, "bgm_pending": False, "voices": meta_voices, "sfx": old.get("sfx", [])}
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(report, open(os.path.join(project, "voice_words_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\naudio_meta.json written · film length {total}s ({int(total // 60)}m{total % 60:04.1f}s)")
    print("next: python verify_pronunciation.py --project <PROJ>   # catch misread characters")
    print("      python captions_clauses.py --project <PROJ>      # clause-level captions")
    print(f"      python bgm_synth.py --out {os.path.join(project, 'assets/bgm/track.wav')} --duration {total + 4:.1f}")
    if not shutil.which("ffmpeg"):
        print("WARNING: ffmpeg missing — nothing was produced correctly")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="SCRIPT.md (single source of truth for narration)")
    ap.add_argument("--project", help="project root (defaults to SCRIPT.md's directory)")
    ap.add_argument("--voice", default="zh-CN-YunxiNeural")
    ap.add_argument("--proxy", default="http://127.0.0.1:7897", help="edge-tts needs this explicitly")
    ap.add_argument("--head", type=float, default=0.5, help="silence before speech inside each frame")
    ap.add_argument("--tails", default="0.9", help="comma list of per-frame trailing silence (s); last value repeats")
    ap.add_argument("--voice-pad", type=float, default=0.18, help="kept after the last word before the tail")
    ap.add_argument("--target-durations", default="", help="previous per-frame VOICE lengths → atempo-warp to keep cues")
    ap.add_argument("--samples", action="store_true", help="write one sample per candidate voice and stop")
    ap.add_argument("--sample-dir", default="")
    ap.add_argument("--scratch", default="")
    a = ap.parse_args()
    return asyncio.run(main_async(a))


if __name__ == "__main__":
    sys.exit(main())
