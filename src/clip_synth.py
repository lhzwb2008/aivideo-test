"""无网络时的本地 B-roll：用 ffmpeg 生成竖屏主题占位素材（保证管线可跑通）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

# 各类型配色与 lavfi 风格
_THEMES: dict[str, list[str]] = {
    "landscape_heal": [
        "color=c=0x1a4d6d:s=1080x1920:d={d}",
        "color=c=0x2d6a4f:s=1080x1920:d={d}",
        "color=c=0x4a7c9b:s=1080x1920:d={d}",
    ],
    "cute_animals": [
        "color=c=0xd4a574:s=1080x1920:d={d}",
        "color=c=0xe8b86d:s=1080x1920:d={d}",
        "color=c=0xf5c6a5:s=1080x1920:d={d}",
    ],
    "curiosity_wonder": [
        "color=c=0x1a0a2e:s=1080x1920:d={d}",
        "color=c=0x0f3460:s=1080x1920:d={d}",
        "color=c=0x533483:s=1080x1920:d={d}",
    ],
    "anxiety_hot": [
        "color=c=0x1a1a1a:s=1080x1920:d={d}",
        "color=c=0x3d0000:s=1080x1920:d={d}",
        "color=c=0x2b2b2b:s=1080x1920:d={d}",
    ],
    "urban_lonely": [
        "color=c=0x0a1628:s=1080x1920:d={d}",
        "color=c=0x1e3a5f:s=1080x1920:d={d}",
        "color=c=0x16213e:s=1080x1920:d={d}",
    ],
}


def generate_clip(demo_id: str, index: int, out_path: Path, *, duration: float = 10.0) -> Path:
    """生成一条竖屏 mp4 占位素材。"""
    themes = _THEMES.get(demo_id) or _THEMES["landscape_heal"]
    src = themes[index % len(themes)].format(d=int(max(6, duration)) + 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 慢推镜 + 轻噪点，避免纯色被平台判低质
    vf = (
        f"[0:v]scale=2160:3840:flags=lanczos,"
        "zoompan=z='min(pzoom+0.0005,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={int(duration * 30)}:s=1080x1920:fps=30,"
        "noise=alls=12:allf=t+u,"
        f"trim=duration={duration:.2f},setpts=PTS-STARTPTS"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", src,
        "-vf", vf,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-an",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
