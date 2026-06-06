#!/usr/bin/env python3
"""竖屏混剪：网搜视频片段 + TTS 口播 + 分句字幕 + 拼接。"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import tempfile
from pathlib import Path

from env import load_env
from paths import ROOT
from tts_client import synthesize as tts_synthesize

CANVAS_W = 1080
CANVAS_H = 1920
# 距底边留白，避开抖音底部 UI（评论/简介区）
SUBTITLE_BOTTOM_MARGIN = int(os.environ.get("AIVIDEO_SUBTITLE_BOTTOM", "200"))
FONT_PATH = os.environ.get("AIVIDEO_FONT", str(ROOT / "assets" / "HiraginoSansGB.ttc"))


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]).decode().strip()
    return float(out)


_SENTENCE_SPLIT = re.compile(r"(?<=[，。！？；,.!?])")


def split_narration(text: str, max_chars: int = 18) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    if not parts:
        parts = [text]
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


_DRAWTEXT_ESCAPE = str.maketrans({"\\": r"\\", ":": r"\:", "'": r"\'", "%": r"\%"})


def _escape_path(p: str) -> str:
    return p.translate(_DRAWTEXT_ESCAPE)


def _drawtext(
    textfile: Path,
    start: float,
    end: float,
    *,
    style: str = "caption",
) -> str:
    """caption=底部分句跟读；hook=冷开场居中大字；news_*=新闻顶栏。"""
    if style == "hook":
        parts = [
            f"fontfile={_escape_path(FONT_PATH)}",
            f"textfile={_escape_path(str(textfile))}",
            "fontcolor=white",
            "fontsize=58",
            "borderw=5",
            "bordercolor=black@0.85",
            "shadowcolor=black@0.55",
            "shadowx=3",
            "shadowy=3",
            "x=(w-text_w)/2",
            "y=(h-text_h)/2-60",
            "line_spacing=8",
            f"enable='between(t,{start:.3f},{end:.3f})'",
        ]
    else:
        parts = [
            f"fontfile={_escape_path(FONT_PATH)}",
            f"textfile={_escape_path(str(textfile))}",
            "fontcolor=white",
            "fontsize=46",
            "borderw=4",
            "bordercolor=black@0.9",
            "shadowcolor=black@0.45",
            "shadowx=2",
            "shadowy=2",
            "box=1",
            "boxcolor=black@0.28",
            "boxborderw=14",
            "x=(w-text_w)/2",
            f"y=h-{SUBTITLE_BOTTOM_MARGIN}-text_h",
            "line_spacing=6",
            f"enable='between(t,{start:.3f},{end:.3f})'",
        ]
    return "drawtext=" + ":".join(parts)


def _video_fit_portrait(duration: float, fps: int = 30) -> str:
    """竖屏裁切，保留视频原始动态（不用 zoompan，避免只取第一帧当静图）。"""
    return (
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{CANVAS_H},"
        f"fps={fps},"
        f"trim=duration={duration:.3f},"
        "setpts=PTS-STARTPTS"
    )


def compose_segment(
    *,
    video_path: Path,
    audio_path: Path,
    narration: str,
    on_screen: str,
    out_path: Path,
    work_dir: Path,
    kenburns_direction: int = 0,
) -> Path:
    duration = max(0.5, ffprobe_duration(audio_path))
    phrases = split_narration(narration)
    spans = allocate_phrase_times(phrases, duration)

    work_dir.mkdir(parents=True, exist_ok=True)
    vf_parts = [_video_fit_portrait(duration)]

    # 素材比口播长时随机取一段，避免每段都从第一帧开始
    src_dur = ffprobe_duration(video_path)
    start_s = 0.0
    if src_dur > duration + 0.8:
        start_s = random.uniform(0.0, src_dur - duration - 0.3)

    show_hook = (on_screen or "").strip()
    hook_end = min(2.2, duration * 0.35) if show_hook else 0.0

    if show_hook:
        hook_file = work_dir / "hook.txt"
        hook_file.write_text(on_screen.strip()[:14], encoding="utf-8")
        vf_parts.append(_drawtext(hook_file, 0.0, hook_end, style="hook"))

    for i, (phrase, (start, end)) in enumerate(zip(phrases, spans)):
        # 冷开场大字期间不叠底部字幕，避免上下两行打架
        if show_hook and end <= hook_end + 0.05:
            continue
        seg_start = max(start, hook_end) if show_hook else start
        if seg_start >= end - 0.05:
            continue
        tf = work_dir / f"phrase_{i:02d}.txt"
        tf.write_text(phrase, encoding="utf-8")
        vf_parts.append(_drawtext(tf, seg_start, end, style="caption"))

    filter_chain = ",".join(vf_parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    loop = src_dur < duration - 0.2
    cmd = ["ffmpeg", "-y"]
    if start_s > 0:
        cmd += ["-ss", f"{start_s:.3f}"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(video_path), "-i", str(audio_path)]
    cmd += [
        "-vf", filter_chain,
        "-map", "0:v", "-map", "1:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        str(out_path),
    ]
    _ = kenburns_direction  # 保留参数兼容，视频段不再用静图推拉
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _wrap_headline_lines(text: str, *, max_line: int = 13, max_lines: int = 2) -> list[str]:
    text = (text or "").strip() or "世界杯快讯"
    if len(text) <= max_line:
        return [text]
    lines: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= max_line and ch in "，。！？、 ":
            lines.append(buf.strip())
            buf = ""
            if len(lines) >= max_lines:
                break
    if buf and len(lines) < max_lines:
        lines.append(buf.strip())
    return lines[:max_lines] if lines else [text[: max_line * max_lines]]


def _news_index_from_label(news_label: str, *, fallback: int = 1) -> int:
    cn = ("一", "二", "三", "四", "五", "六", "七", "八")
    for i, c in enumerate(cn, 1):
        if c in (news_label or ""):
            return i
    m = re.search(r"\d+", news_label or "")
    return int(m.group()) if m else fallback


def _load_font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def render_news_header_png(
    *,
    news_label: str,
    headline: str,
    out_path: Path,
    news_index: int | None = None,
    brand: str = "世界杯前哨战",
) -> Path:
    """绘制新闻顶栏透明 PNG（PIL 精修，替代 drawtext）。"""
    from PIL import Image, ImageDraw

    idx = news_index or _news_index_from_label(news_label)
    lines = _wrap_headline_lines(headline)

    w, h = CANVAS_W, 320
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    card_x1, card_y1, card_x2, card_y2 = 28, 52, 1052, 286
    # 卡片阴影
    draw.rounded_rectangle(
        (card_x1 + 4, card_y1 + 6, card_x2 + 4, card_y2 + 6),
        radius=28, fill=(0, 0, 0, 90),
    )
    # 主卡片
    draw.rounded_rectangle(
        (card_x1, card_y1, card_x2, card_y2),
        radius=28, fill=(10, 16, 38, 215), outline=(45, 95, 200, 160), width=2,
    )
    # 顶部色带
    draw.rounded_rectangle((card_x1, card_y1, card_x2, card_y1 + 5), radius=28, fill=(0, 196, 160, 230))
    draw.rectangle((card_x1, card_y1 + 3, card_x2, card_y1 + 5), fill=(255, 214, 10, 220))

    # 左侧序号圆环
    cx, cy, r = 98, 168, 46
    draw.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=(255, 214, 10, 200))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 168, 140, 255))
    draw.ellipse((cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6), fill=(0, 130, 110, 255))

    f_num = _load_font(44)
    num_text = f"{idx:02d}"
    nb = draw.textbbox((0, 0), num_text, font=f_num)
    nw, nh = nb[2] - nb[0], nb[3] - nb[1]
    draw.text((cx - nw // 2, cy - nh // 2 - 4), num_text, font=f_num, fill=(255, 255, 255, 255))

    tx = 168
    f_brand = _load_font(24)
    f_tag = _load_font(26)
    f_head = _load_font(48)

    draw.text((tx, 78), brand, font=f_brand, fill=(120, 150, 210, 230))
    draw.text((tx + 200, 80), "|", font=f_brand, fill=(80, 100, 140, 180))
    tag = (news_label or f"第{idx}条新闻").strip()
    draw.rounded_rectangle((tx + 220, 72, tx + 220 + min(280, len(tag) * 28 + 36), 112), radius=14, fill=(25, 55, 110, 200))
    draw.text((tx + 236, 76), tag, font=f_tag, fill=(255, 230, 140, 255))

    hy = 128
    for line in lines:
        # 标题阴影
        draw.text((tx + 2, hy + 2), line, font=f_head, fill=(0, 0, 0, 140))
        draw.text((tx, hy), line, font=f_head, fill=(255, 255, 255, 255))
        hy += 58

    # 底部分隔线
    draw.rectangle((tx, card_y2 - 22, card_x2 - 36, card_y2 - 20), fill=(60, 120, 220, 120))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def compose_news_segment(
    *,
    video_path: Path,
    audio_path: Path,
    narration: str,
    news_label: str,
    headline: str,
    out_path: Path,
    work_dir: Path,
    news_index: int | None = None,
) -> Path:
    """新闻段：PIL 顶栏卡片 + 底部分句字幕。"""
    duration = max(0.5, ffprobe_duration(audio_path))
    phrases = split_narration(narration)
    spans = allocate_phrase_times(phrases, duration)

    work_dir.mkdir(parents=True, exist_ok=True)
    header_png = work_dir / "news_header.png"
    render_news_header_png(
        news_label=news_label,
        headline=headline,
        out_path=header_png,
        news_index=news_index,
    )

    caption_filters: list[str] = []
    for i, (phrase, (start, end)) in enumerate(zip(phrases, spans)):
        tf = work_dir / f"phrase_{i:02d}.txt"
        tf.write_text(phrase, encoding="utf-8")
        caption_filters.append(_drawtext(tf, start, end, style="caption"))

    video_fit = _video_fit_portrait(duration)
    caption_chain = ",".join(caption_filters) if caption_filters else "null"
    overlay_y = 48

    if caption_filters:
        fc = (
            f"[0:v]{video_fit}[base];"
            f"[1:v]scale={CANVAS_W}:-1[hdr];"
            f"[base][hdr]overlay=0:{overlay_y}:format=auto[ov];"
            f"[ov]{caption_chain}[vout]"
        )
    else:
        fc = (
            f"[0:v]{video_fit}[base];"
            f"[1:v]scale={CANVAS_W}:-1[hdr];"
            f"[base][hdr]overlay=0:{overlay_y}:format=auto[vout]"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    src_dur = ffprobe_duration(video_path)
    start_s = 0.0
    if src_dur > duration + 0.8:
        start_s = random.uniform(0.0, src_dur - duration - 0.3)
    loop = src_dur < duration - 0.2

    cmd = ["ffmpeg", "-y"]
    if start_s > 0:
        cmd += ["-ss", f"{start_s:.3f}"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(video_path), "-loop", "1", "-i", str(header_png), "-i", str(audio_path)]
    cmd += [
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "2:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def concat_clips(clips: list[Path], out_path: Path) -> Path:
    if len(clips) == 1:
        if clips[0].resolve() != out_path.resolve():
            out_path.write_bytes(clips[0].read_bytes())
        return out_path
    with tempfile.TemporaryDirectory(prefix="concat_") as tmp:
        list_file = Path(tmp) / "list.txt"
        lines = [f"file '{c.resolve()}'" for c in clips]
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(out_path),
        ], check=True, capture_output=True)
    return out_path


def add_bgm(video_path: Path, out_path: Path, *, bgm_dir: Path | None = None) -> Path:
    if os.environ.get("AIVIDEO_BGM_ENABLED", "1").strip() in {"0", "false", "no"}:
        return video_path
    d = bgm_dir or (ROOT / "assets" / "bgm")
    tracks = sorted(d.glob("*.mp3")) if d.is_dir() else []
    if not tracks:
        return video_path
    bgm = random.choice(tracks)
    vol = _env_float("AIVIDEO_BGM_VOLUME", 0.28)
    dur = ffprobe_duration(video_path)
    fade = min(1.2, dur * 0.08)
    af = (
        f"[1:a]volume={vol},afade=t=in:st=0:d={fade:.2f},"
        f"afade=t=out:st={max(0, dur - fade):.2f}:d={fade:.2f}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(bgm),
        "-filter_complex", af, "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", str(out_path),
    ], check=True, capture_output=True)
    return out_path


def build_from_script(
    script: dict,
    clip_paths: list[Path],
    *,
    work_dir: Path,
    out_path: Path,
) -> Path:
    """根据脚本与已下载素材合成成片。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    segments = script.get("segments") or []
    if len(clip_paths) < len(segments):
        raise ValueError(f"素材不足: need {len(segments)}, got {len(clip_paths)}")

    pieces: list[Path] = []
    stem = script.get("demo_id", "demo")

    cold = (script.get("cold_open") or "").strip()
    if cold:
        co_audio = work_dir / "cold_open.mp3"
        tts_synthesize(cold, out_path=co_audio)
        co_clip = clip_paths[0]
        co_out = work_dir / "seg_cold.mp4"
        compose_segment(
            video_path=co_clip,
            audio_path=co_audio,
            narration=cold,
            on_screen=script.get("title", "")[:12],
            out_path=co_out,
            work_dir=work_dir / "cold_phrases",
            kenburns_direction=0,
        )
        pieces.append(co_out)

    for i, seg in enumerate(segments):
        narr = (seg.get("narration") or "").strip()
        if not narr:
            continue
        audio = work_dir / f"seg_{i:02d}.mp3"
        tts_synthesize(narr, out_path=audio)
        clip_idx = int(seg.get("clip_index", i))
        clip_idx = max(0, min(clip_idx, len(clip_paths) - 1))
        seg_out = work_dir / f"seg_{i:02d}.mp4"
        compose_segment(
            video_path=clip_paths[clip_idx],
            audio_path=audio,
            narration=narr,
            on_screen="",  # 正文段只用底部分句字幕，不再顶部叠字
            out_path=seg_out,
            work_dir=work_dir / f"phrases_{i:02d}",
            kenburns_direction=i % 4,
        )
        pieces.append(seg_out)

    outro = (script.get("outro") or "").strip()
    if outro:
        ou_audio = work_dir / "outro.mp3"
        tts_synthesize(outro, out_path=ou_audio)
        ou_out = work_dir / "seg_outro.mp4"
        compose_segment(
            video_path=clip_paths[-1],
            audio_path=ou_audio,
            narration=outro,
            on_screen="",
            out_path=ou_out,
            work_dir=work_dir / "outro_phrases",
            kenburns_direction=2,
        )
        pieces.append(ou_out)

    raw = work_dir / "raw_concat.mp4"
    concat_clips(pieces, raw)
    final = work_dir / "final.mp4"
    add_bgm(raw, final)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if final.resolve() != out_path.resolve():
        out_path.write_bytes(final.read_bytes())
    return out_path
