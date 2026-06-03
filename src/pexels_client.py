"""Pexels 免费素材库：搜索竖屏友好视频并下载到本地缓存。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from paths import ROOT


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def api_key() -> str:
    return _env("PEXELS_API_KEY")


def cache_dir() -> Path:
    d = ROOT / "assets" / "cache" / "clips"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _proxy_url() -> str:
    return _env("PEXELS_HTTP_PROXY") or _env("HTTPS_PROXY") or _env("https_proxy") or _env("YOUTUBE_HTTP_PROXY")


def _direct_opener() -> urllib.request.OpenerDirector:
    """绕过系统/环境变量代理，避免 127.0.0.1 代理未开时 Connection refused。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open(req: urllib.request.Request, *, timeout: float, use_proxy: bool) -> bytes:
    if use_proxy:
        proxy = _proxy_url()
        if not proxy:
            raise urllib.error.URLError("no proxy configured")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        opener = _direct_opener()
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def _get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 120) -> bytes:
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) aivideo-test/1.0",
        "Referer": "https://www.pexels.com/",
        "Accept": "*/*",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        return _open(req, timeout=timeout, use_proxy=False)
    except (urllib.error.URLError, TimeoutError, OSError):
        if _proxy_url():
            return _open(req, timeout=timeout, use_proxy=True)
        raise


def search_videos(query: str, *, per_page: int = 5, orientation: str = "portrait") -> list[dict]:
    """搜索 Pexels 视频；无 API Key 时返回空列表。"""
    key = api_key()
    if not key:
        return []
    q = urllib.parse.quote(query)
    url = (
        f"https://api.pexels.com/videos/search?query={q}"
        f"&per_page={per_page}&orientation={orientation}"
    )
    raw = _get(url, headers={"Authorization": key})
    data = json.loads(raw.decode("utf-8"))
    return data.get("videos") or []


def pick_best_file(video: dict) -> str | None:
    """从 Pexels video 对象里选最接近 1080p 竖屏的 mp4。"""
    files = video.get("video_files") or []
    mp4s = [f for f in files if (f.get("file_type") or "").lower() == "video/mp4"]
    if not mp4s:
        return None
    # 优先高度接近 1920 或 1280
    def score(f: dict) -> tuple[int, int]:
        h = int(f.get("height") or 0)
        w = int(f.get("width") or 0)
        portrait_bonus = 1 if h >= w else 0
        return (portrait_bonus, h)

    best = max(mp4s, key=score)
    return best.get("link")


def download_url(url: str, out_path: Path, *, timeout: float = 180) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = _get(url, timeout=timeout)
    out_path.write_bytes(data)
    return out_path


def fetch_clip_for_query(query: str, *, stem: str, index: int) -> Path | None:
    """按关键词搜索并下载一条素材；失败返回 None。"""
    videos = search_videos(query, per_page=10, orientation="portrait")
    if not videos:
        videos = search_videos(query, per_page=10, orientation="landscape")
    # 不同 index 换一条，避免全片重复
    if videos and index:
        videos = videos[index % len(videos):] + videos[: index % len(videos)]
    for v in videos:
        link = pick_best_file(v)
        if not link:
            continue
        safe_q = "".join(c if c.isalnum() else "_" for c in query)[:40]
        out = cache_dir() / f"{stem}_{index:02d}_{safe_q}.mp4"
        if out.is_file() and out.stat().st_size > 50_000:
            return out
        try:
            download_url(link, out)
            if out.stat().st_size > 50_000:
                return out
        except (urllib.error.URLError, RuntimeError, OSError):
            continue
    return None


def load_fallback_urls(demo_id: str) -> list[str]:
    path = ROOT / "demos" / "fallback_clips.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get(demo_id) or [])


def fetch_clip_fallback(demo_id: str, index: int, *, stem: str) -> Path | None:
    urls = load_fallback_urls(demo_id)
    if index >= len(urls):
        return None
    out = cache_dir() / f"{stem}_fb_{index:02d}.mp4"
    if out.is_file() and out.stat().st_size > 50_000:
        return out
    try:
        download_url(urls[index], out)
        return out if out.is_file() and out.stat().st_size > 50_000 else None
    except (urllib.error.URLError, RuntimeError, OSError):
        return None
