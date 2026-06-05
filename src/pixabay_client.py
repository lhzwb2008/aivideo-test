"""Pixabay 免费视频 API：搜索并下载到本地缓存。"""

from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path

from http_util import get
from paths import ROOT


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def api_key() -> str:
    return _env("PIXABAY_API_KEY")


def cache_dir() -> Path:
    d = ROOT / "assets" / "cache" / "clips"
    d.mkdir(parents=True, exist_ok=True)
    return d


def search_videos(
    query: str,
    *,
    per_page: int = 15,
    min_height: int = 720,
    video_type: str = "film",
) -> list[dict]:
    key = api_key()
    if not key:
        return []
    params = {
        "key": key,
        "q": query,
        "per_page": str(per_page),
        "min_height": str(min_height),
        "video_type": video_type,
        "safesearch": "true",
        "order": "popular",
    }
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(params)
    raw = get(url, referer="https://pixabay.com/", timeout=60)
    data = json.loads(raw.decode("utf-8"))
    return data.get("hits") or []


def pick_best_url(hit: dict) -> str | None:
    """优先竖屏或较高分辨率 medium/large。"""
    videos = hit.get("videos") or {}
    candidates: list[tuple[int, int, str]] = []
    for name in ("large", "medium", "small"):
        v = videos.get(name) or {}
        url = (v.get("url") or "").strip()
        if not url:
            continue
        w = int(v.get("width") or 0)
        h = int(v.get("height") or 0)
        portrait = 1 if h >= w else 0
        candidates.append((portrait, h, url))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def download_url(url: str, out_path: Path, *, timeout: float = 180) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # download=1 触发浏览器式下载，CDN 更稳定
    dl = url if "download=1" in url else (url + ("&" if "?" in url else "?") + "download=1")
    data = get(dl, referer="https://pixabay.com/", timeout=timeout)
    out_path.write_bytes(data)
    return out_path


def fetch_clip_for_query(query: str, *, stem: str, index: int) -> Path | None:
    hits = search_videos(query, per_page=15)
    if hits and index:
        hits = hits[index % len(hits) :] + hits[: index % len(hits)]
    for hit in hits:
        link = pick_best_url(hit)
        if not link:
            continue
        safe_q = "".join(c if c.isalnum() else "_" for c in query)[:40]
        vid = hit.get("id", index)
        out = cache_dir() / f"{stem}_px_{index:02d}_{vid}_{safe_q}.mp4"
        if out.is_file() and out.stat().st_size > 80_000:
            return out
        try:
            download_url(link, out)
            if out.stat().st_size > 80_000:
                return out
        except Exception:
            continue
    return None
