# -*- coding: utf-8 -*-
"""Environment preflight for the video-fast pipeline — run this before any video work.

One shot instead of ten discoveries mid-run: ffmpeg/atempo, proxy, edge-tts reachability,
whisper + model, hyperframes CLI + Chrome, CJK fonts, numpy.

    python preflight.py [--proxy http://127.0.0.1:7897] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
rows: list[tuple[str, str, str]] = []


def add(name: str, status: str, detail: str) -> None:
    rows.append((name, status, detail))


def run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return 127, str(e)


def check_ffmpeg() -> None:
    exe = shutil.which("ffmpeg")
    if not exe:
        add("ffmpeg", FAIL, "not on PATH — install ffmpeg (needs ffprobe too)")
        return
    code, out = run(["ffmpeg", "-version"])
    ver = out.splitlines()[0] if out else "?"
    code2, out2 = run(["ffmpeg", "-hide_banner", "-filters"])
    atempo = "atempo" in out2
    add("ffmpeg", PASS if atempo else WARN,
        f"{ver.split(' Copyright')[0]}" + ("" if atempo else " · atempo filter MISSING (pitch-safe speed-up needed)")
    )
    add("ffprobe", PASS if shutil.which("ffprobe") else FAIL,
        shutil.which("ffprobe") or "not found — needed for duration probing")


def check_proxy(proxy: str) -> None:
    try:
        req = urllib.request.Request(proxy, method="GET")
        urllib.request.urlopen(req, timeout=4)
        add("proxy", PASS, f"{proxy} reachable")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        ok = "Bad Request" in msg or "400" in msg or "HTTP Error" in msg
        add("proxy", PASS if ok else FAIL,
            f"{proxy} " + ("reachable" if ok else f"unreachable ({msg[:60]})"))


def check_edge_tts(proxy: str) -> None:
    try:
        import edge_tts  # noqa: F401
    except Exception as e:  # noqa: BLE001
        add("edge-tts", FAIL, f"python package missing ({e}) — pip install edge-tts")
        return
    code = subprocess.run(
        [sys.executable, "-c",
         "import asyncio,edge_tts\n"
         "async def m():\n"
         "    vs=await edge_tts.list_voices(proxy=%r)\n"
         "    z=[v['ShortName'] for v in vs if v['Locale'].startswith('zh-CN')]\n"
         "    print(len(z),'|',','.join(z[:3]))\n"
         "asyncio.run(m())\n" % proxy],
        capture_output=True, text=True, timeout=60,
    )
    if code.returncode == 0 and code.stdout.strip():
        add("edge-tts (via proxy)", PASS, f"zh-CN voices: {code.stdout.strip()}")
    else:
        add("edge-tts (via proxy)", FAIL,
            f"cannot reach the service — {code.stderr.strip().splitlines()[-1][:90] if code.stderr.strip() else 'no output'}")


def check_whisper() -> None:
    exe = shutil.which("whisper-cli") or r"C:\Users\zz\whisper.cpp\whisper-cli.exe"
    if not (exe and os.path.exists(exe)):
        add("whisper-cli", WARN, "not found — pronunciation check will be skipped")
        return
    cands = [
        os.path.expanduser(r"C:\Users\zz\.cache\hyperframes\whisper\models\ggml-large-v3-turbo.bin"),
        os.path.expanduser(r"C:\Users\zz\whisper.cpp\models\ggml-large-v3-turbo.bin"),
        os.path.expanduser("~/.cache/hyperframes/whisper/models"),
    ]
    model = next((c for c in cands if os.path.isfile(c)), None)
    if not model:
        found = []
        for d in cands:
            if os.path.isdir(d):
                found += [os.path.join(d, f) for f in os.listdir(d) if f.startswith("ggml-")]
        model = found[0] if found else None
    add("whisper-cli", PASS if model else WARN,
        (model or "binary present but no ggml-*.bin model found"))


def check_hyperframes() -> None:
    # npx is a .cmd shim on Windows — run it through the shell so PATH resolution works
    p = subprocess.run("npx --yes hyperframes --version", shell=True, capture_output=True, text=True, timeout=240)
    if p.returncode != 0:
        tail = (p.stdout + p.stderr).strip().splitlines()
        add("hyperframes CLI", FAIL, (tail or ["npx failed"])[-1][:90])
        return
    add("hyperframes CLI", PASS, (p.stdout + p.stderr).strip().splitlines()[-1][:60])
    home = os.path.expanduser("~")
    chrome_dirs = [os.path.join(home, ".cache", "hyperframes", "chrome")]
    found = any(os.path.isdir(d) and os.listdir(d) for d in chrome_dirs)
    add("headless Chrome", PASS if found else WARN,
        chrome_dirs[0] if found else "not downloaded — run: npx hyperframes browser ensure")


def check_fonts() -> None:
    fonts = r"C:\Windows\Fonts"
    pairs = [("NotoSerifSC", "serif SC (display)"), ("NotoSansSC", "sans SC (body)")]
    found = []
    for key, label in pairs:
        hit = [f for f in os.listdir(fonts) if key.lower() in f.lower()] if os.path.isdir(fonts) else []
        if hit:
            found.append(f"{label}: {hit[0]}")
    add("CJK fonts", PASS if len(found) == 2 else WARN,
        " · ".join(found) if found else "no Noto SC found in C:\\Windows\\Fonts")


def check_numpy() -> None:
    try:
        import numpy  # noqa: F401
        add("numpy (BGM synth)", PASS, "available")
    except Exception:  # noqa: BLE001
        add("numpy (BGM synth)", WARN, "missing — pip install numpy (BGM falls back to silence)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="http://127.0.0.1:7897")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    check_ffmpeg()
    check_proxy(a.proxy)
    check_edge_tts(a.proxy)
    check_whisper()
    check_hyperframes()
    check_fonts()
    check_numpy()

    if a.json:
        print(json.dumps([{"check": n, "status": s, "detail": d} for n, s, d in rows], ensure_ascii=False, indent=1))
    else:
        width = max(len(n) for n, _, _ in rows)
        for name, status, detail in rows:
            print(f"[{status}] {name.ljust(width)}  {detail}")
        bad = [n for n, s, _ in rows if s == FAIL]
        print("\n" + ("BLOCKED: fix " + ", ".join(bad) if bad else "all required checks passed"))
    return 1 if any(s == FAIL for _, s, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
