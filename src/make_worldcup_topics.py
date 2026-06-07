#!/usr/bin/env python3
"""批量生成世界杯球队赔率分析专题视频（涨粉向，无赔率动效段）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from env import load_env
from make_worldcup import build_video, load_config
from paths import ROOT
from polymarket_client import fetch_odds_safe
import stock_client
from worldcup_topic_script import generate_topic_script, load_topics


def _topic_queries(topic: dict, demo: dict) -> list[str]:
    qs = [q.strip() for q in (topic.get("clip_queries") or []) if q and str(q).strip()]
    if qs:
        return qs[:4]
    return (demo.get("clip_queries") or ["soccer world cup fans"])[:4]


def download_clips_for_topic(topic: dict, demo: dict, *, stem: str) -> list[Path]:
    queries = _topic_queries(topic, demo)
    clips: list[Path] = []
    print(f"  下载素材（{stock_client.provider()}）…", file=sys.stderr)
    for i, q in enumerate(queries):
        clip: Path | None = None
        if stock_client.has_stock_source():
            clip = stock_client.fetch_clip_for_query(
                q, stem=stem, index=i, demo_id=topic.get("id", "worldcup"),
            )
        if clip is None:
            from clip_synth import generate_clip
            cache = ROOT / "assets" / "cache" / "clips"
            out = cache / f"{stem}_synth_{i:02d}.mp4"
            if not (out.is_file() and out.stat().st_size > 10_000):
                generate_clip("anxiety_hot", i, out, duration=16.0)
            clip = out
        print(f"    ✓ [{i}] {clip.name}", file=sys.stderr)
        clips.append(clip)
    return clips


def run_one_topic(
    topic: dict,
    *,
    demo: dict,
    odds: dict[str, object],
    skip_compose: bool = False,
) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = f"{ts}_{topic['id']}"
    log_dir = ROOT / "logs" / stem
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== 专题 [{topic['name']}] 生成脚本…", file=sys.stderr)
    script = generate_topic_script(demo, topic, odds=odds)
    script_path = log_dir / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  标题: {script.get('title')}", file=sys.stderr)

    clips = download_clips_for_topic(topic, demo, stem=stem)
    (log_dir / "clips.json").write_text(
        json.dumps([str(c) for c in clips], ensure_ascii=False, indent=2), encoding="utf-8",
    )

    if skip_compose:
        return {"topic_id": topic["id"], "title": script.get("title"), "script": str(script_path)}

    out_path = ROOT / "output" / f"worldcup_{topic['id']}_{ts}.mp4"
    print(f"  合成 → {out_path}", file=sys.stderr)
    build_video(script, clips, odds_data=odds, work_dir=log_dir / "compose", out_path=out_path)

    meta = {
        "topic_id": topic["id"],
        "topic_name": topic["name"],
        "brand": demo["brand"],
        "title": script.get("title"),
        "hashtags": script.get("hashtags"),
        "video": str(out_path),
        "script": str(script_path),
    }
    (log_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  完成: {out_path}", file=sys.stderr)
    return meta


def run(*, only: str = "", skip_compose: bool = False) -> list[dict]:
    load_env()
    os.environ["VOLCENGINE_TTS_ATEMPO"] = os.environ.get("WORLDCUP_TTS_ATEMPO", "1.14")
    demo = load_config()
    topics = load_topics()
    if only:
        topics = [t for t in topics if t["id"] == only]
        if not topics:
            raise SystemExit(f"未知专题: {only}")

    print("=== 拉取 Polymarket 赔率（共用）…", file=sys.stderr)
    odds = fetch_odds_safe()
    print(f"  共 {len(odds.get('top') or [])} 支球队数据", file=sys.stderr)

    results: list[dict] = []
    for topic in topics:
        try:
            results.append(run_one_topic(topic, demo=demo, odds=odds, skip_compose=skip_compose))
        except Exception as exc:
            print(f"  失败 [{topic['id']}]: {exc}", file=sys.stderr)
            results.append({"topic_id": topic["id"], "error": str(exc)})
        time.sleep(1)

    summary = ROOT / "output" / "worldcup_topics_summary.json"
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r.get("video"))
    print(f"\n汇总: {summary}", file=sys.stderr)
    print(f"成功 {ok}/{len(results)}", file=sys.stderr)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="批量生成世界杯球队赔率分析专题")
    parser.add_argument("--only", help="只跑某一专题 id")
    parser.add_argument("--skip-compose", action="store_true")
    args = parser.parse_args()
    try:
        results = run(only=args.only, skip_compose=args.skip_compose)
        return 0 if all(r.get("video") or r.get("script") for r in results) else 1
    except Exception as exc:
        print(f"失败: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
