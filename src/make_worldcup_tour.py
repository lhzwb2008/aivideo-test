#!/usr/bin/env python3
"""32强巡礼：生图 + 口播合成（无博彩内容）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from enrich_slides import enrich_script
from env import load_env
from paths import ROOT
from slide_compose import compose_tour_video
from worldcup_tour_script import generate_team_script, load_teams


def run_one(team: dict, *, skip_images: bool = False, skip_compose: bool = False) -> dict:
    load_env()
    os.environ["VOLCENGINE_TTS_ATEMPO"] = os.environ.get("WORLDCUP_TTS_ATEMPO", "1.14")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = f"{ts}_tour_{team['id']}"
    log_dir = ROOT / "logs" / stem
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== [{team['name_cn']}] 生成脚本…", file=sys.stderr)
    script = generate_team_script(team)
    script_path = log_dir / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  标题: {script.get('title')}", file=sys.stderr)

    if not skip_images:
        print(f"=== [{team['name_cn']}] 生图（封面+4页）…", file=sys.stderr)
        script = enrich_script(script, stem=stem)
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    if skip_compose:
        return {"team_id": team["id"], "title": script.get("title"), "script": str(script_path)}

    out_path = ROOT / "output" / f"worldcup_tour_{team['id']}_{ts}.mp4"
    print(f"=== [{team['name_cn']}] 合成 → {out_path}", file=sys.stderr)
    compose_tour_video(script, work_dir=log_dir / "compose", out_path=out_path)

    meta = {
        "team_id": team["id"],
        "team_cn": team["name_cn"],
        "title": script.get("title"),
        "hashtags": script.get("hashtags"),
        "video": str(out_path),
        "script": str(script_path),
    }
    (log_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  完成: {out_path}", file=sys.stderr)
    return meta


def run(*, only: str = "", skip_images: bool = False, skip_compose: bool = False) -> list[dict]:
    teams = load_teams()
    if only:
        teams = [t for t in teams if t["id"] == only]
        if not teams:
            raise SystemExit(f"未知球队: {only}")

    results: list[dict] = []
    for team in teams:
        try:
            results.append(run_one(team, skip_images=skip_images, skip_compose=skip_compose))
        except Exception as exc:
            print(f"  失败 [{team['id']}]: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            results.append({"team_id": team["id"], "error": str(exc)})
        time.sleep(2)

    summary = ROOT / "output" / "worldcup_tour_summary.json"
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r.get("video"))
    print(f"\n汇总: {summary}", file=sys.stderr)
    print(f"成功 {ok}/{len(results)}", file=sys.stderr)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="世界杯32强巡礼（生图版）")
    parser.add_argument("--only", help="单队 id，如 brazil")
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    args = parser.parse_args()
    results = run(only=args.only, skip_images=args.skip_images, skip_compose=args.skip_compose)
    return 0 if all(r.get("video") or r.get("script") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
