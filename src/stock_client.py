"""统一素材源：pexels（默认）| pixabay | local（本地文件夹）。"""

from __future__ import annotations

import os
from pathlib import Path

import pexels_client
import pixabay_client
from paths import ROOT


def _local_stock_dir(demo_id: str | None = None) -> Path:
    base = ROOT / "assets" / "stock"
    if demo_id:
        return base / demo_id
    return base


def _local_has_clips(demo_id: str | None = None) -> bool:
    d = _local_stock_dir(demo_id)
    if not d.is_dir():
        return False
    return any(d.rglob("*.mp4"))


def provider() -> str:
    raw = os.environ.get("STOCK_PROVIDER", "pexels").strip().lower()
    if raw == "pixabay":
        if pixabay_client.api_key():
            return "pixabay"
        if pexels_client.api_key():
            return "pexels"
        if _local_has_clips():
            return "local"
    if raw == "pexels":
        if pexels_client.api_key():
            return "pexels"
        if pixabay_client.api_key():
            return "pixabay"
        if _local_has_clips():
            return "local"
    if raw == "local" and _local_has_clips():
        return "local"
    return raw if raw in {"pexels", "pixabay", "local"} else "pexels"


def has_stock_source() -> bool:
    p = provider()
    if p == "pexels":
        return bool(pexels_client.api_key())
    if p == "pixabay":
        return bool(pixabay_client.api_key())
    return _local_has_clips()


def fetch_local_clips(demo_id: str, count: int) -> list[Path]:
    """从 assets/stock/<demo_id>/、common/ 或 stock/ 根目录取本地 mp4。"""
    folders = [
        _local_stock_dir(demo_id),
        ROOT / "assets" / "stock" / "common",
        ROOT / "assets" / "stock",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for folder in folders:
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.mp4")):
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                unique.append(p)
    if not unique:
        return []
    return [unique[i % len(unique)] for i in range(count)]


def fetch_clip_for_query(
    query: str,
    *,
    stem: str,
    index: int,
    demo_id: str = "",
) -> Path | None:
    p = provider()
    if p == "local":
        local = fetch_local_clips(demo_id or "common", index + 1)
        return local[index] if index < len(local) else None
    if p == "pexels":
        return pexels_client.fetch_clip_for_query(query, stem=stem, index=index)
    clip = pixabay_client.fetch_clip_for_query(query, stem=stem, index=index)
    if clip is None and pexels_client.api_key():
        clip = pexels_client.fetch_clip_for_query(query, stem=f"{stem}_pex", index=index)
    return clip


def fetch_clip_fallback(demo_id: str, index: int, *, stem: str) -> Path | None:
    if provider() == "local":
        local = fetch_local_clips(demo_id, index + 1)
        return local[index] if index < len(local) else None
    return pexels_client.fetch_clip_fallback(demo_id, index, stem=stem)
