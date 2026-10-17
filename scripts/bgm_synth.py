# -*- coding: utf-8 -*-
"""Self-made BGM: a licence-free music bed synthesized with numpy (no model, no network, seconds to render).

The point is not "AI music"; it is a *bed* that (a) never fights the voiceover, (b) always exists,
(c) has no licensing question. Built as chords + arpeggio + bass + kick/hat with a sidechain pump,
then soft-clipped and faded so the end lands on the video's last frame.

    python bgm_synth.py --out PROJ/assets/bgm/track.wav --duration 107 --style uplifting
    styles: uplifting (108bpm, major) · calm (92bpm, soft) · tech (120bpm, minor, driving)
"""
from __future__ import annotations

import argparse
import os
import sys
import wave

import numpy as np

SR = 44100
STYLES = {
    # name: (bpm, chord roots as midi triads, pluck gain, pad gain, kick gain)
    "uplifting": (108, [[45, 57, 61, 64], [40, 52, 56, 59], [42, 54, 57, 61], [50, 62, 66, 69]], 0.075, 0.028, 0.5),
    "calm": (92, [[45, 57, 60, 64], [41, 53, 57, 60], [38, 50, 53, 57], [43, 55, 59, 62]], 0.055, 0.036, 0.28),
    "tech": (120, [[45, 57, 60, 63], [45, 57, 60, 63], [43, 55, 58, 62], [41, 53, 56, 60]], 0.08, 0.03, 0.55),
}


def mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def synth(duration: float, style: str, seed: int = 42) -> np.ndarray:
    bpm, chords, pluck_gain, pad_gain, kick_gain = STYLES[style]
    beat = 60.0 / bpm
    bar = 4 * beat
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    L = np.zeros(n)
    R = np.zeros(n)

    def add(buf: np.ndarray, start: float, length: float, freq: float, amp: float, kind: str) -> None:
        i0 = int(start * SR)
        m = min(int(length * SR), n - i0)
        if m <= 0 or i0 >= n:
            return
        t = np.arange(m) / SR
        if kind == "pluck":
            env = np.exp(-t * 5.5) * np.minimum(t / 0.008, 1.0)
            sig = (np.sin(2 * np.pi * freq * t) + 0.45 * np.sin(2 * np.pi * 2 * freq * t)
                   + 0.22 * np.sin(2 * np.pi * 3 * freq * t)) * env
        elif kind == "pad":
            env = np.minimum(t / min(0.6, max(length * 0.3, 0.05)), 1.0) * np.exp(-np.maximum(t - (length - 0.8), 0) * 2.0)
            saw = lambda f: 2 * ((t * f) % 1.0) - 1.0  # noqa: E731
            sig = (saw(freq * 0.997) + saw(freq * 1.004)) * 0.5 * env
        else:  # bass
            env = np.exp(-t * 3.0)
            sig = (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 0.5 * t)) * env
        buf[i0:i0 + m] += amp * sig

    chord_dur = 2 * bar
    for ci in range(int(np.ceil(duration / chord_dur))):
        chord = chords[ci % len(chords)]
        c0 = ci * chord_dur
        # pad is filtered per chord segment (a full-length one-pole pass per chord is needlessly slow)
        seg_len = min(int(chord_dur * SR), n - int(c0 * SR))
        if seg_len > 1:
            seg = np.zeros(seg_len)
            for m in chord[1:]:
                t = np.arange(seg_len) / SR
                f = mtof(m)
                env = np.minimum(t / min(0.6, max(chord_dur * 0.3, 0.05)), 1.0) * \
                    np.exp(-np.maximum(t - (chord_dur - 0.8), 0) * 2.0)
                saw1 = 2 * ((t * f * 0.997) % 1.0) - 1.0
                saw2 = 2 * ((t * f * 1.004) % 1.0) - 1.0
                seg += pad_gain * (saw1 + saw2) * 0.5 * env
            alpha = 0.06  # one-pole lowpass — keeps the pad behind the voice
            for i in range(1, seg_len):
                seg[i] += alpha * (seg[i - 1] - seg[i])
            i0 = int(c0 * SR)
            L[i0:i0 + seg_len] += seg
            R[i0:i0 + seg_len] += seg
        for b in range(2):
            b0 = c0 + b * bar
            add(L, b0, beat * 1.6, mtof(chord[0]), 0.16, "bass")
            add(R, b0, beat * 1.6, mtof(chord[0]), 0.16, "bass")
            add(L, b0 + 2 * beat, beat * 1.6, mtof(chord[0] + 7), 0.13, "bass")
            add(R, b0 + 2 * beat, beat * 1.6, mtof(chord[0] + 7), 0.13, "bass")
        pattern = [0, 1, 2, 3, 2, 1, 2, 3, 0, 2, 1, 3, 2, 3, 1, 2]
        for b in range(2):
            for s in range(16):
                note = chord[pattern[s]] + 12
                at = c0 + b * bar + s * (beat / 4)
                vel = pluck_gain * (1.0 if s % 4 == 0 else (0.72 if s % 2 == 0 else 0.55))
                vel *= 0.9 + 0.2 * rng.random()
                sl, sr_ = np.zeros(n), np.zeros(n)
                add(sl, at, beat * 1.2, mtof(note) * 0.9985, vel, "pluck")
                add(sr_, at, beat * 1.2, mtof(note) * 1.0015, vel, "pluck")
                pan = 0.35 * np.sin(s * 0.9)
                L += sl * (1 - max(pan, 0) * 0.6)
                R += sr_ * (1 - max(-pan, 0) * 0.6)

    t_k = np.arange(int(0.14 * SR)) / SR
    kick = np.sin(2 * np.pi * (120 * np.exp(-t_k * 22) + 45) * t_k) * np.exp(-t_k * 26)
    duck = np.ones(n)
    for b in range(int(duration / beat) + 1):
        i0 = int(b * beat * SR)
        m = min(len(kick), n - i0)
        if m <= 0:
            continue
        L[i0:i0 + m] += kick[:m] * kick_gain
        R[i0:i0 + m] += kick[:m] * kick_gain
        duck[i0:i0 + m] = np.minimum(duck[i0:i0 + m], 1 - 0.35 * np.exp(-t_k[:m] * 18))
    L *= duck
    R *= duck

    hat_t = np.arange(int(0.03 * SR)) / SR
    hat = np.diff(rng.standard_normal(len(hat_t)) * np.exp(-hat_t * 180), prepend=0.0)
    for b in range(int(duration / beat) + 1):
        i0 = int((b + 0.5) * beat * SR)
        m = min(len(hat), n - i0)
        if m <= 0:
            continue
        L[i0:i0 + m] += hat[:m] * 0.05
        R[i0:i0 + m] += hat[:m] * 0.05

    swell = int(2 * bar * SR)
    if swell < n:
        ramp = np.linspace(0.55, 1.0, swell)
        L[:swell] *= ramp
        R[:swell] *= ramp

    mix = np.tanh(np.stack([L, R], axis=1) * 1.1)
    fade_in = min(int(1.2 * SR), n)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    fade_out = min(int(6.0 * SR), n)
    mix[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    peak = np.abs(mix).max()
    if peak > 0:
        mix *= 0.5 / peak
    return mix.astype(np.float32)


def write_wav(path: str, data: np.ndarray) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(data.shape[1] if data.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=float, required=True, help="film length + 2–4s of tail")
    ap.add_argument("--style", default="uplifting", choices=sorted(STYLES))
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    data = synth(a.duration, a.style, a.seed)
    write_wav(a.out, data)
    rms = float(np.sqrt((data.astype(np.float64) ** 2).mean()))
    print(f"BGM {a.style} · {a.duration:.1f}s · peak {np.abs(data).max():.2f} · rms {rms:.3f} → {a.out}")
    print("在 audio_meta.json 里用 volume 0.12–0.16 当床底；这条轨已自带 1.2s 淡入 / 6s 淡出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
