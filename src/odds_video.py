"""赔率动画：逐帧进度条生长 + 光晕脉动 + 口播字幕。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from clip_compose import (
    CANVAS_W,
    _drawtext,
    allocate_phrase_times,
    ffprobe_duration,
    split_narration,
)
from polymarket_client import render_odds_frame_sequence


def _frames_to_silent_video(
    frames_dir: Path,
    out_path: Path,
    *,
    fps: int = 24,
    pad_to: float | None = None,
) -> Path:
    pattern = str(frames_dir / "frame_%05d.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", pattern]
    if pad_to and pad_to > 0:
        cmd += ["-vf", f"tpad=stop_mode=clone:stop_duration={pad_to:.3f}"]
    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-an", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def compose_odds_segment(
    *,
    odds_rows: list[dict[str, Any]],
    audio_path: Path,
    narration: str,
    out_path: Path,
    work_dir: Path,
    subtitle: str = "",
    volume24hr: float | None = None,
) -> Path:
    """赔率段：帧动画 + TTS + 分句字幕 + 轻微镜头推近。"""
    duration = max(2.0, ffprobe_duration(audio_path))
    work_dir.mkdir(parents=True, exist_ok=True)
    fps = 24

    frames_dir = work_dir / "frames"
    _, anim_duration = render_odds_frame_sequence(
        odds_rows,
        frames_dir,
        duration=duration,
        fps=fps,
        subtitle=subtitle,
        volume24hr=volume24hr,
    )

    silent = work_dir / "odds_silent.mp4"
    pad = max(0.0, duration - anim_duration)
    _frames_to_silent_video(frames_dir, silent, fps=fps, pad_to=pad)

    phrases = split_narration(narration, max_chars=18)
    spans = allocate_phrase_times(phrases, duration)

    canvas_h = 1920
    vf_parts = [
        f"scale={CANVAS_W}:{canvas_h}:flags=lanczos,fps={fps}",
    ]

    badge = work_dir / "badge.txt"
    badge.write_text("Polymarket 实时", encoding="utf-8")
    vf_parts.append(_drawtext(badge, 0.0, min(2.8, duration * 0.12), style="hook"))

    for i, (phrase, (start, end)) in enumerate(zip(phrases, spans)):
        if start < 2.0:
            start = 2.0
        if start >= end - 0.05:
            continue
        tf = work_dir / f"phrase_{i:02d}.txt"
        tf.write_text(phrase, encoding="utf-8")
        vf_parts.append(_drawtext(tf, start, end, style="caption"))

    filter_chain = ",".join(vf_parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(audio_path),
        "-vf", filter_chain,
        "-map", "0:v", "-map", "1:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ], check=True, capture_output=True)
    return out_path
