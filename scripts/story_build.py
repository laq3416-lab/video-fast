# -*- coding: utf-8 -*-
"""story_build — one story.json → the whole film's plan files (and optionally its frames).

Two things are always hand-written: the narration (what the video says) and the choice of shape per
beat (which archetype carries it). Everything downstream of those two decisions is mechanical:
SCRIPT.md with per-line delivery, STORYBOARD.md with the frame order and transitions, then the
frames themselves.

Variety is enforced, not left to discipline: two adjacent beats may not use the same archetype, and
the loudest shapes (kinetic-hook / panel-demo) may not exceed a share of the film — that is the rule
that keeps a generated video from reading as a slide deck.

    python story_build.py --project PROJ --story story.json            # plan + frames
    python story_build.py --project PROJ --story story.json --plan-only # SCRIPT.md + STORYBOARD.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ARCHETYPES = ("kinetic-hook", "card-row", "panel-demo")
LOUD = {"kinetic-hook", "panel-demo"}


def check_variety(frames: list[dict]) -> list[str]:
    """returns advisory notes; the caller prints them. Variety is a quality rule, not a hard block."""
    notes = []
    for a, b in zip(frames, frames[1:]):
        if a.get("archetype") == b.get("archetype"):
            notes.append(f"相邻帧 {a['id']} 与 {b['id']} 用了同一个原型（{a['archetype']}）——"
                         f"建议换一个，否则连看会觉得是同一张幻灯片")
    loud = sum(1 for f in frames if f.get("archetype") in LOUD)
    if len(frames) and loud / len(frames) > 0.5:
        notes.append(f"强构图原型占了 {loud}/{len(frames)}——超过一半容易单调，"
                     f"中间几帧可换成 card-row")
    return notes


def write_script(project: str, story: dict, frames: list[dict]) -> str:
    lines = [f"# SCRIPT — {story.get('title','video')}", "",
             f"**Voice:** edge-tts {story.get('voice','zh-CN-YunxiNeural')}（逐句微调语速与音高）",
             "**Voice settings:** rate ±4% · pitch ±4Hz", "",
             f"**Voice direction:** {story.get('direction','朋友安利好东西——热情、有起伏，不念稿。')}", ""]
    if story.get("notes"):
        lines += [f"**注：** {story['notes']}", ""]
    for f in frames:
        lines += [f"## Line {f['frame_no']} — {f.get('label', f['id'])} (Frame {f['frame_no']})", "",
                  f"**Time:** {f.get('time','')}", f"**Delivery:** {f.get('delivery','自然讲述')}"
                  f" rate {f.get('rate','+0%')} · pitch {f.get('pitch','+0Hz')}", "",
                  f"    {f['script']}", ""]
    text = "\n".join(lines) + "\n"
    path = os.path.join(project, "SCRIPT.md")
    open(path, "w", encoding="utf-8").write(text)
    return path


def write_storyboard(project: str, story: dict, frames: list[dict]) -> str:
    head = ["---",
            f"format: {story.get('format','1920x1080')}",
            f"duration: {sum(float(f.get('duration', 8)) for f in frames):.0f}s",
            f'message: "{story.get("message","")}"',
            f"arc: {story.get('arc','hook → 主体 → 收尾')}",
            f"audience: {story.get('audience','')}",
            "mode: autonomous",
            f"music: {story.get('music','none')}",
            "---", "",
            "## Video direction", "",
            f"- **palette**：{story.get('palette','奶油纸底 / 墨色正文 / 珊瑚橙每帧一次 / 暖海军蓝只给终端面板')}",
            "- **type**：中文 Noto Serif SC（展示）/ Noto Sans SC（正文），拉丁 EB Garamond，命令 JetBrains Mono",
            "- **motion**：power3 长尾；reveal 跟台词；hold 只留低幅抖动；禁回弹 / 无限循环 / CSS 动画",
            f"- **rhythm**：{story.get('rhythm','开场快、主体同构但构图各异、收尾留白')}",
            "- **caption keep-out**：内容下缘 ≤ 816px（字幕带 top=836px）",
            "- **negative list**：无紫蓝 AI 渐变、无漂浮装饰、无 front-load", ""]
    body = []
    for f in frames:
        anim = "animated"
        lines = [f"## Frame {f['frame_no']} — {f.get('label', f['id'])}", "",
                 f"- duration: {f.get('duration', 8)}s",
                 f"- scene: {f.get('scene','')}",
                 f'- voiceover: "{f["script"]}"',
                 f"- transition_in: {f.get('transition_in','crossfade')}",
                 f"- status: {anim}",
                 f"- src: compositions/frames/{f['id']}.html",
                 f"- archetype: {f['archetype']}", ""]
        body += lines
    text = "\n".join(head + body) + "\n"
    path = os.path.join(project, "STORYBOARD.md")
    open(path, "w", encoding="utf-8").write(text)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--story", required=True)
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--out-dir", default="compositions/frames")
    a = ap.parse_args()

    story = json.load(open(a.story, encoding="utf-8"))
    frames = story["frames"]
    for i, f in enumerate(frames, 1):
        f.setdefault("frame_no", i)
        f.setdefault("id", f"{i:02d}-{f['archetype']}")
    if not os.path.exists(os.path.join(a.project, "assets", "voice")):
        os.makedirs(os.path.join(a.project, "assets", "voice"), exist_ok=True)

    sp = write_script(a.project, story, frames)
    bp = write_storyboard(a.project, story, frames)
    print(f"  {os.path.relpath(sp, a.project)} + {os.path.relpath(bp, a.project)} written "
          f"({len(frames)} beats)")

    for note in check_variety(frames):
        print("  ! " + note)

    if a.plan_only:
        return 0

    # frames: the kit reads audio_meta.json for durations and word cues, so run the narration first
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import frame_kit  # noqa: E402

    out_dir = os.path.join(a.project, a.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    for f in frames:
        spec = dict(f)
        html = frame_kit.build_frame(spec, a.project)
        path = os.path.join(out_dir, f"{f['id']}.html")
        open(path, "w", encoding="utf-8").write(html)
        print(f"  {f['id']:22s} {f['archetype']}")
    print("\nnext: tts_lines → verify_pronunciation → captions_clauses → bgm_synth → "
          "sync_frame_durations → assemble → transitions → lint/check → snapshot → render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
