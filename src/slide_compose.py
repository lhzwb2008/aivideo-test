#!/usr/bin/env python3
"""生图 slide 竖屏合成：Ken Burns + 分句字幕 + BGM。"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import tempfile
from pathlib import Path

from clip_compose import add_bgm, ffprobe_duration
from env import load_env
from paths import ROOT
from tts_client import synthesize as tts_synthesize

load_env()

CANVAS_W, CANVAS_H = 1080, 1920
SUBTITLE_Y = int(os.environ.get("AIVIDEO_SUBTITLE_Y", "1580"))
FONT_PATH = os.environ.get("AIVIDEO_FONT", str(ROOT / "assets" / "HiraginoSansGB.ttc"))

_SENTENCE_SPLIT = re.compile(r"(?<=[，。！？；,.!?])")
_DRAWTEXT_ESCAPE = str.maketrans({"\\": r"\\", ":": r"\:", "'": r"\'", "%": r"\%"})


def _escape_path(p: str) -> str:
    return p.translate(_DRAWTEXT_ESCAPE)


def split_narration(text: str, max_chars: int = 18) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    merged: list[str] = []
    buf = ""
    for p in parts:
        if not buf:
            buf = p
        elif len(buf) + len(p) <= max_chars:
            buf += p
        else:
            merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged or [text[:max_chars]]


def allocate_phrase_times(phrases: list[str], total: float) -> list[tuple[float, float]]:
    if not phrases:
        return [(0.0, total)]
    weights = [max(1, len(p)) for p in phrases]
    total_w = sum(weights)
    t = 0.0
    spans: list[tuple[float, float]] = []
    for w in weights:
        d = total * (w / total_w)
        spans.append((t, t + d))
        t += d
    return spans


def _kenburns(duration: float, direction: int = 0, fps: int = 30) -> str:
    n = max(2, int(round(duration * fps)))
    if direction % 4 == 0:
        zp = "z='min(pzoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif direction % 4 == 1:
        zp = "z='if(eq(on,0),1.08,max(1.0,pzoom-0.0007))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    else:
        zp = f"z=1.06:x='iw/2-(iw/zoom/2)+(on/{n})*60-30':y='ih/2-(ih/zoom/2)'"
    return (
        f"scale=2160:3840:flags=lanczos,"
        f"zoompan={zp}:d={n}:s={CANVAS_W}x{CANVAS_H}:fps={fps}"
    )


def _drawtext(textfile: Path, start: float, end: float, *, y: int | None = None) -> str:
    yy = y if y is not None else SUBTITLE_Y
    parts = [
        f"fontfile={_escape_path(FONT_PATH)}",
        f"textfile={_escape_path(str(textfile))}",
        "fontcolor=white", "fontsize=48", "borderw=4", "bordercolor=black@0.9",
        "box=1", "boxcolor=black@0.35", "boxborderw=14",
        "x=(w-text_w)/2", f"y={yy}-text_h", "line_spacing=8",
        f"enable='between(t,{start:.3f},{end:.3f})'",
    ]
    return "drawtext=" + ":".join(parts)


def compose_slide_clip(
    *,
    image_path: Path,
    audio_path: Path,
    narration: str,
    out_path: Path,
    work_dir: Path,
    kenburns_direction: int = 0,
    hook_text: str = "",
) -> Path:
    duration = max(0.5, ffprobe_duration(audio_path))
    phrases = split_narration(narration)
    spans = allocate_phrase_times(phrases, duration)
    work_dir.mkdir(parents=True, exist_ok=True)

    vf = [_kenburns(duration, kenburns_direction)]
    hook_end = min(2.5, duration * 0.3) if hook_text else 0.0
    if hook_text:
        hf = work_dir / "hook.txt"
        hf.write_text(hook_text[:14], encoding="utf-8")
        vf.append(_drawtext(hf, 0.0, hook_end, y=CANVAS_H // 2 - 40))

    for i, (phrase, (start, end)) in enumerate(zip(phrases, spans)):
        if hook_text and end <= hook_end + 0.05:
            continue
        seg_start = max(start, hook_end) if hook_text else start
        if seg_start >= end - 0.05:
            continue
        tf = work_dir / f"phrase_{i:02d}.txt"
        tf.write_text(phrase, encoding="utf-8")
        vf.append(_drawtext(tf, seg_start, end))

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-i", str(audio_path),
        "-vf", ",".join(vf), "-map", "0:v", "-map", "1:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def concat_clips(clips: list[Path], out_path: Path) -> Path:
    if len(clips) == 1:
        out_path.write_bytes(clips[0].read_bytes())
        return out_path
    with tempfile.TemporaryDirectory(prefix="concat_") as tmp:
        lst = Path(tmp) / "list.txt"
        lst.write_text("\n".join(f"file '{c.resolve()}'" for c in clips) + "\n", encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c", "copy", str(out_path),
        ], check=True, capture_output=True)
    return out_path


def compose_tour_video(script: dict, *, work_dir: Path, out_path: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    stem = script.get("team_id", "tour")

    cold = (script.get("cold_open") or "").strip()
    cover_rel = script.get("cover_image")
    cover = ROOT / cover_rel if cover_rel else None

    if cold and cover and cover.is_file():
        audio = work_dir / "cold_open.mp3"
        tts_synthesize(cold, out_path=audio)
        out = work_dir / "seg_cold.mp4"
        compose_slide_clip(
            image_path=cover, audio_path=audio, narration=cold,
            out_path=out, work_dir=work_dir / "cold",
            hook_text=script.get("team_cn", "")[:8],
        )
        pieces.append(out)

    for i, slide in enumerate(script.get("slides") or []):
        narr = (slide.get("narration") or "").strip()
        if not narr:
            continue
        img_rel = slide.get("image_path")
        if not img_rel:
            continue
        img = ROOT / img_rel
        audio = work_dir / f"seg_{i:02d}.mp3"
        tts_synthesize(narr, out_path=audio)
        out = work_dir / f"seg_{i:02d}.mp4"
        compose_slide_clip(
            image_path=img, audio_path=audio, narration=narr,
            out_path=out, work_dir=work_dir / f"slide_{i:02d}",
            kenburns_direction=i % 4,
        )
        pieces.append(out)

    outro = (script.get("outro") or "").strip()
    if outro:
        last_img_rel = (script.get("slides") or [{}])[-1].get("image_path") or cover_rel
        if last_img_rel:
            audio = work_dir / "outro.mp3"
            tts_synthesize(outro, out_path=audio)
            out = work_dir / "seg_outro.mp4"
            compose_slide_clip(
                image_path=ROOT / last_img_rel, audio_path=audio, narration=outro,
                out_path=out, work_dir=work_dir / "outro",
            )
            pieces.append(out)

    raw = work_dir / "raw.mp4"
    concat_clips(pieces, raw)
    final = work_dir / "final.mp4"
    add_bgm(raw, final)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(final.read_bytes())
    print(f"  成片时长: {ffprobe_duration(out_path):.1f}s", flush=True)
    return out_path


def compose_from_script_file(script_path: Path, *, out_path: Path | None = None) -> Path:
    script = json.loads(script_path.read_text(encoding="utf-8"))
    if "slides" not in script:
        script = script.get("script", script)
    work_dir = ROOT / "logs" / "compose" / script_path.stem
    out = out_path or ROOT / "output" / f"{script_path.stem}.mp4"
    return compose_tour_video(script, work_dir=work_dir, out_path=out)
