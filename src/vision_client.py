"""多模态视觉理解：抽帧后调用 AiHubMix Vision 描述画面。"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from clip_compose import ffprobe_duration
from text_client import api_key, base_url


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def vision_model() -> str:
    return _env("AIHUBMIX_VISION_MODEL", "gpt-4o-mini")


def vision_timeout() -> float:
    return float(_env("AIHUBMIX_VISION_TIMEOUT", "120"))


def extract_keyframes(video_path: Path, out_dir: Path, *, count: int = 3) -> list[Path]:
    """从视频中均匀抽取关键帧。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    dur = max(1.0, ffprobe_duration(video_path))
    frames: list[Path] = []
    for i in range(count):
        t = dur * (0.12 + 0.76 * i / max(1, count - 1))
        out = out_dir / f"frame_{i:02d}.jpg"
        subprocess.run([
            "ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video_path),
            "-frames:v", "1", "-q:v", "3", str(out),
        ], check=True, capture_output=True)
        if out.is_file() and out.stat().st_size > 1000:
            frames.append(out)
    return frames


def _b64_image(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


def describe_frames(
    frames: list[Path],
    *,
    query_hint: str = "",
    context: str = "",
) -> str:
    """根据关键帧返回中文画面描述（客观、具体）。"""
    if not frames:
        return "画面内容不明确"
    parts: list[dict] = [
        {
            "type": "text",
            "text": (
                "你是短视频素材分析师。根据连续截图，用中文客观描述这段 B-roll 里"
                "实际出现的画面：主体、动作、场景、氛围。只写看得见的内容，不要编造。"
                f"{f'搜索词参考：{query_hint}' if query_hint else ''}"
                f"{f'补充：{context}' if context else ''}"
                "输出 2-4 句，≤80 字。"
            ),
        }
    ]
    for fp in frames[:4]:
        b64 = _b64_image(fp)
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    body = {
        "model": vision_model(),
        "messages": [
            {"role": "user", "content": parts},
        ],
        "max_tokens": 256,
    }
    url = f"{base_url()}/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = vision_timeout()
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or []
            msg = (choices[0].get("message") or {}) if choices else {}
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            text = (content or "").strip()
            if text:
                return text
            raise RuntimeError("vision 返回为空")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"vision 调用失败: {last_err}")


def analyze_clip(
    video_path: Path,
    work_dir: Path,
    *,
    query_hint: str = "",
) -> str:
    frames = extract_keyframes(video_path, work_dir / "frames")
    return describe_frames(frames, query_hint=query_hint)
