#!/usr/bin/env python3
"""批量生成 5 类爆量情绪短视频 demo。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from clip_compose import build_from_script
from env import load_env
from paths import ROOT
from clip_synth import generate_clip
import stock_client
from script_generator import generate_script_from_visuals
from vision_client import analyze_clip


def load_demo_types() -> list[dict]:
    path = ROOT / "demos" / "types.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _demo_queries(demo: dict) -> list[str]:
    qs = [q.strip() for q in (demo.get("clip_queries") or []) if q and str(q).strip()]
    return qs[:4] if len(qs) >= 4 else (qs or ["nature", "city", "animals", "sky"])


def download_and_analyze_clips(
    demo: dict,
    *,
    stem: str,
    log_dir: Path,
) -> list[dict]:
    """先下载素材，再视觉理解，返回 clip_infos。"""
    queries = _demo_queries(demo)
    infos: list[dict] = []

    prov = stock_client.provider()
    print(f"=== [{demo['name']}] 下载素材（{prov}）…", file=sys.stderr)
    for i, q in enumerate(queries):
        clip: Path | None = None
        if stock_client.has_stock_source():
            clip = stock_client.fetch_clip_for_query(
                q, stem=stem, index=i, demo_id=demo.get("id", ""),
            )
        if clip is None and not stock_client.has_stock_source():
            clip = stock_client.fetch_clip_fallback(demo["id"], i % 3, stem=stem)
        if clip is None:
            cache = ROOT / "assets" / "cache" / "clips"
            out = cache / f"{stem}_synth_{i:02d}.mp4"
            if not (out.is_file() and out.stat().st_size > 10_000):
                generate_clip(demo["id"], i, out, duration=12.0)
            clip = out
        print(f"    ✓ 素材[{i}]: {clip.name}", file=sys.stderr)

        print(f"    … 理解画面[{i}] …", file=sys.stderr)
        visual = analyze_clip(clip, log_dir / f"analyze_{i:02d}", query_hint=q)
        print(f"      {visual[:60]}…", file=sys.stderr)
        infos.append({
            "index": i,
            "query": q,
            "path": str(clip),
            "visual": visual,
        })

    (log_dir / "clip_infos.json").write_text(
        json.dumps(infos, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return infos


def _latest_log_dir(demo_id: str) -> Path | None:
    candidates = sorted(
        (p for p in (ROOT / "logs").iterdir() if p.is_dir() and p.name.endswith(f"_{demo_id}")),
        key=lambda p: p.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _clips_from_stem(stem: str) -> list[Path]:
    cache = ROOT / "assets" / "cache" / "clips"
    clips = sorted(cache.glob(f"{stem}_*.mp4"))
    return [p for p in clips if p.stat().st_size > 80_000]


def run_one_recompose(demo: dict) -> dict:
    log_dir = _latest_log_dir(demo["id"])
    if not log_dir:
        raise RuntimeError(f"无历史日志 demo={demo['id']}")
    stem = log_dir.name
    script_path = log_dir / "script.json"
    if not script_path.is_file():
        raise RuntimeError(f"缺少脚本 {script_path}")
    script = json.loads(script_path.read_text(encoding="utf-8"))
    clips = _clips_from_stem(stem)
    if len(clips) < 2:
        raise RuntimeError(f"缓存素材不足 stem={stem} got={len(clips)}")

    ts = stem.split("_", 2)
    # stem = 20260605_082449_cute_animals → demo_cute_animals_20260605_082449.mp4
    out_name = f"demo_{demo['id']}_{ts[0]}_{ts[1]}.mp4" if len(ts) >= 2 else f"demo_{demo['id']}_{stem}.mp4"
    out_path = ROOT / "output" / out_name

    print(f"\n=== [{demo['name']}] 仅重合成（复用 {stem}）…", file=sys.stderr)
    build_from_script(script, clips, work_dir=log_dir / "compose_v2", out_path=out_path)

    meta = {
        "demo_id": demo["id"],
        "name": demo["name"],
        "title": script.get("title"),
        "hashtags": script.get("hashtags"),
        "video": str(out_path),
        "script": str(script_path),
        "recomposed": True,
    }
    (log_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  完成: {out_path}", file=sys.stderr)
    return meta


def run_one(demo: dict, *, skip_compose: bool = False) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = f"{ts}_{demo['id']}"
    log_dir = ROOT / "logs" / stem
    log_dir.mkdir(parents=True, exist_ok=True)

    if os.environ.get("STOCK_PROVIDER", "").strip().lower() == "pixabay":
        if stock_client.provider() == "pexels":
            print("  提示: Pixabay 未配置，已自动改用 Pexels", file=sys.stderr)

    clip_infos = download_and_analyze_clips(demo, stem=stem, log_dir=log_dir)

    print(f"=== [{demo['name']}] 根据画面写口播…", file=sys.stderr)
    script = generate_script_from_visuals(demo, clip_infos)
    script_path = log_dir / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  脚本: {script_path}", file=sys.stderr)

    clips = [Path(c["path"]) for c in clip_infos]
    print(f"  素材 {len(clips)} 条（与口播逐段对齐）", file=sys.stderr)

    if skip_compose:
        return {"demo": demo["id"], "script": str(script_path), "clips": [str(c) for c in clips]}

    out_name = f"demo_{demo['id']}_{ts}.mp4"
    out_path = ROOT / "output" / out_name
    print(f"=== [{demo['name']}] 合成视频 → {out_path}", file=sys.stderr)
    build_from_script(script, clips, work_dir=log_dir / "compose", out_path=out_path)

    meta = {
        "demo_id": demo["id"],
        "name": demo["name"],
        "title": script.get("title"),
        "hashtags": script.get("hashtags"),
        "video": str(out_path),
        "script": str(script_path),
    }
    (log_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  完成: {out_path}", file=sys.stderr)
    return meta


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description="生成爆量情绪短视频 demo")
    parser.add_argument("--only", help="只跑某一 demo id，如 landscape_heal")
    parser.add_argument("--skip-compose", action="store_true", help="只生成脚本和素材，不合成")
    parser.add_argument("--limit", type=int, default=0, help="最多跑几条，0=全部")
    parser.add_argument("--recompose", action="store_true", help="复用最近脚本+素材，仅重跑合成")
    args = parser.parse_args()

    demos = load_demo_types()
    if args.only:
        demos = [d for d in demos if d["id"] == args.only]
        if not demos:
            print(f"未知 demo id: {args.only}", file=sys.stderr)
            return 1
    if args.limit > 0:
        demos = demos[: args.limit]

    results: list[dict] = []
    for demo in demos:
        try:
            if args.recompose:
                results.append(run_one_recompose(demo))
            else:
                results.append(run_one(demo, skip_compose=args.skip_compose))
        except Exception as exc:
            print(f"失败 [{demo['id']}]: {exc}", file=sys.stderr)
            results.append({"demo_id": demo["id"], "error": str(exc)})

    summary_path = ROOT / "output" / "demos_summary.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总: {summary_path}", file=sys.stderr)
    ok = sum(1 for r in results if r.get("video"))
    print(f"成功 {ok}/{len(results)}", file=sys.stderr)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
