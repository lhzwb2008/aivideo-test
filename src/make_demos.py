#!/usr/bin/env python3
"""批量生成 5 类爆量情绪短视频 demo。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from clip_compose import build_from_script
from env import load_env
from paths import ROOT
from clip_synth import generate_clip
from pexels_client import api_key, fetch_clip_fallback, fetch_clip_for_query
from script_generator import generate_script


def load_demo_types() -> list[dict]:
    path = ROOT / "demos" / "types.json"
    return json.loads(path.read_text(encoding="utf-8"))


def gather_clips(script: dict, demo: dict, *, stem: str) -> list[Path]:
    segments = script.get("segments") or []
    n_needed = len(segments) + 2  # cold + outro buffer
    paths: list[Path] = []
    queries = [seg.get("clip_query") or "" for seg in segments]
    fallback_queries = demo.get("clip_queries") or []

    for i in range(n_needed):
        q = ""
        if i < len(queries) and queries[i]:
            q = queries[i]
        elif i < len(fallback_queries):
            q = fallback_queries[i]
        elif fallback_queries:
            q = fallback_queries[i % len(fallback_queries)]

        clip: Path | None = None
        if q and api_key():
            clip = fetch_clip_for_query(q, stem=stem, index=i)
        if clip is None:
            clip = fetch_clip_fallback(demo["id"], i % 3, stem=stem)
        if clip is None and q:
            clip = fetch_clip_for_query(q, stem=stem, index=i + 10)
        if clip:
            paths.append(clip)

    if len(paths) < max(2, len(segments)):
        print(f"  网搜素材不足({len(paths)})，改用本地 ffmpeg 主题占位…", file=sys.stderr)
        cache = ROOT / "assets" / "cache" / "clips"
        for i in range(n_needed):
            out = cache / f"{stem}_synth_{i:02d}.mp4"
            if not (out.is_file() and out.stat().st_size > 10_000):
                generate_clip(demo["id"], i, out, duration=12.0)
            paths.append(out)
    return paths


def run_one(demo: dict, *, skip_compose: bool = False) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = f"{ts}_{demo['id']}"
    log_dir = ROOT / "logs" / stem
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== [{demo['name']}] 生成脚本…", file=sys.stderr)
    script = generate_script(demo)
    script_path = log_dir / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  脚本: {script_path}", file=sys.stderr)

    print(f"=== [{demo['name']}] 下载素材…", file=sys.stderr)
    clips = gather_clips(script, demo, stem=stem)
    print(f"  素材 {len(clips)} 条", file=sys.stderr)

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
