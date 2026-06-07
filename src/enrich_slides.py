#!/usr/bin/env python3
"""为世界杯巡礼脚本批量生图。"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from image_client import (
    build_worldcup_cover_prompt,
    build_worldcup_slide_prompt,
    generate_image,
    save_b64_image,
)
from paths import ROOT


def image_dir_for(stem: str) -> Path:
    return ROOT / "logs" / "images" / stem


def _download_url(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        path.write_bytes(resp.read())


def enrich_script(script: dict, *, stem: str, force: bool = False) -> dict:
    out_dir = image_dir_for(stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    team_cn = script.get("team_cn") or script.get("title", "")[:4]
    nickname = script.get("nickname") or ""

    cover_path = out_dir / "cover.png"
    if force or not (cover_path.is_file() and cover_path.stat().st_size > 5000):
        prompt = build_worldcup_cover_prompt(
            team_cn=team_cn,
            nickname=nickname,
            subtitle="32强巡礼",
        )
        print(f"  [cover] 生图…", flush=True)
        result = generate_image(prompt)
        if result.get("b64_json"):
            save_b64_image(result["b64_json"], cover_path)
        elif result.get("url"):
            _download_url(str(result["url"]), cover_path)
        script["cover_image"] = str(cover_path.relative_to(ROOT))

    slides = script.get("slides") or []
    total = len(slides)
    for i, slide in enumerate(slides, start=1):
        png = out_dir / f"slide_{i:02d}.png"
        if not force and png.is_file() and png.stat().st_size > 5000:
            slide["image_path"] = str(png.relative_to(ROOT))
            continue
        prompt = build_worldcup_slide_prompt(
            str(slide.get("image_prompt") or ""),
            team_cn=team_cn,
            on_image_text=slide.get("on_image_text") or [],
            page_index=i,
            total_pages=total,
        )
        print(f"  [{i}/{total}] 生图…", flush=True)
        result = generate_image(prompt)
        if result.get("b64_json"):
            save_b64_image(result["b64_json"], png)
        elif result.get("url"):
            _download_url(str(result["url"]), png)
        slide["image_path"] = str(png.relative_to(ROOT))

    return script


def enrich_script_file(path: Path, *, force: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    script = data.get("script", data)
    stem = path.stem
    script = enrich_script(script, stem=stem, force=force)
    path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    return script
