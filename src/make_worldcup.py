#!/usr/bin/env python3
"""世界杯前哨战：每日资讯 + Polymarket 赔率 → 竖屏短视频（约 60 秒）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from clip_compose import add_bgm, compose_news_segment, compose_segment, concat_clips, ffprobe_duration
from env import load_env
from odds_video import compose_odds_segment
from paths import ROOT
from polymarket_client import fetch_and_prepare
from tts_client import synthesize as tts_synthesize
import stock_client
from worldcup_news import bundle_context
from worldcup_script import generate_script


def load_config() -> dict:
    path = ROOT / "demos" / "worldcup_sentinel.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _demo_queries(demo: dict) -> list[str]:
    qs = [q.strip() for q in (demo.get("clip_queries") or []) if q and str(q).strip()]
    n = int(demo.get("news_segments") or 4)
    return qs[: max(n, 3)]


def download_clips(demo: dict, *, stem: str) -> list[Path]:
    queries = _demo_queries(demo)
    clips: list[Path] = []
    print(f"=== 下载足球 B-roll（{stock_client.provider()}）…", file=sys.stderr)
    for i, q in enumerate(queries):
        clip: Path | None = None
        if stock_client.has_stock_source():
            clip = stock_client.fetch_clip_for_query(
                q, stem=stem, index=i, demo_id=demo.get("id", "worldcup"),
            )
        if clip is None:
            from clip_synth import generate_clip
            cache = ROOT / "assets" / "cache" / "clips"
            out = cache / f"{stem}_synth_{i:02d}.mp4"
            if not (out.is_file() and out.stat().st_size > 10_000):
                generate_clip("anxiety_hot", i, out, duration=16.0)
            clip = out
        print(f"    ✓ 素材[{i}]: {clip.name}", file=sys.stderr)
        clips.append(clip)
    return clips


def build_video(
    script: dict,
    clips: list[Path],
    *,
    odds_data: dict,
    work_dir: Path,
    out_path: Path,
) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    odds_card = Path(odds_data["card_png"])

    cold = (script.get("cold_open") or "").strip()
    if cold:
        co_audio = work_dir / "cold_open.mp3"
        tts_synthesize(cold, out_path=co_audio)
        co_out = work_dir / "seg_cold.mp4"
        compose_segment(
            video_path=clips[0],
            audio_path=co_audio,
            narration=cold,
            on_screen="世界杯前哨战",
            out_path=co_out,
            work_dir=work_dir / "cold_phrases",
        )
        pieces.append(co_out)

    for i, seg in enumerate(script.get("segments") or []):
        narr = (seg.get("narration") or "").strip()
        if not narr:
            continue
        audio = work_dir / f"seg_{i:02d}.mp3"
        tts_synthesize(narr, out_path=audio)
        seg_out = work_dir / f"seg_{i:02d}.mp4"

        if seg.get("type") == "odds":
            odds_rows = (script.get("odds_snapshot") or {}).get("top") or []
            compose_odds_segment(
                odds_rows=odds_rows,
                audio_path=audio,
                narration=narr,
                out_path=seg_out,
                work_dir=work_dir / f"odds_{i:02d}",
                subtitle=odds_data.get("date", ""),
                volume24hr=odds_data.get("volume24hr"),
            )
        elif seg.get("type") == "news":
            clip_idx = int(seg.get("clip_index", i))
            clip_idx = max(0, min(clip_idx, len(clips) - 1))
            compose_news_segment(
                video_path=clips[clip_idx],
                audio_path=audio,
                narration=narr,
                news_label=seg.get("news_label", f"第{i + 1}条新闻"),
                headline=seg.get("headline", "世界杯快讯"),
                news_index=int(seg.get("index", i)) + 1,
                out_path=seg_out,
                work_dir=work_dir / f"phrases_{i:02d}",
            )
        else:
            clip_idx = int(seg.get("clip_index", i))
            clip_idx = max(0, min(clip_idx, len(clips) - 1))
            compose_segment(
                video_path=clips[clip_idx],
                audio_path=audio,
                narration=narr,
                on_screen="",
                out_path=seg_out,
                work_dir=work_dir / f"phrases_{i:02d}",
            )
        pieces.append(seg_out)

    outro = (script.get("outro") or "").strip()
    if outro:
        ou_audio = work_dir / "outro.mp3"
        tts_synthesize(outro, out_path=ou_audio)
        ou_out = work_dir / "seg_outro.mp4"
        compose_segment(
            video_path=clips[-1],
            audio_path=ou_audio,
            narration=outro,
            on_screen="",
            out_path=ou_out,
            work_dir=work_dir / "outro_phrases",
        )
        pieces.append(ou_out)

    raw = work_dir / "raw_concat.mp4"
    concat_clips(pieces, raw)
    final = work_dir / "final.mp4"
    add_bgm(raw, final)

    dur = ffprobe_duration(final)
    print(f"  成片时长: {dur:.1f}s", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if final.resolve() != out_path.resolve():
        out_path.write_bytes(final.read_bytes())
    return out_path


def run(*, skip_compose: bool = False, date_str: str = "") -> dict:
    load_env()
    os.environ["VOLCENGINE_TTS_ATEMPO"] = os.environ.get("WORLDCUP_TTS_ATEMPO", "1.14")
    demo = load_config()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    day = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = f"{ts}_worldcup_sentinel"
    log_dir = ROOT / "logs" / stem
    log_dir.mkdir(parents=True, exist_ok=True)

    print("=== [世界杯前哨战] 拉取 Polymarket 赔率…", file=sys.stderr)
    odds = fetch_and_prepare(today=day)
    (log_dir / "odds.json").write_text(json.dumps(odds, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Top1: {odds['top'][0]['team_cn']} {odds['top'][0]['pct']}%", file=sys.stderr)

    print("=== 采集新闻/赛况…", file=sys.stderr)
    news_ctx = bundle_context()
    (log_dir / "news.json").write_text(json.dumps(news_ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  模式: {news_ctx['mode']}, 条目: {len(news_ctx['news'])}", file=sys.stderr)

    print("=== 生成口播脚本…", file=sys.stderr)
    script = generate_script(demo, odds=odds, news_ctx=news_ctx)
    script_path = log_dir / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  标题: {script.get('title')}", file=sys.stderr)
    print(f"  段落: {len(script.get('segments') or [])} + 冷开场/结尾", file=sys.stderr)

    clips = download_clips(demo, stem=stem)
    (log_dir / "clips.json").write_text(
        json.dumps([str(c) for c in clips], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if skip_compose:
        return {
            "title": script.get("title"),
            "script": str(script_path),
            "odds_card": odds["card_png"],
            "clips": [str(c) for c in clips],
        }

    out_name = f"worldcup_sentinel_{ts}.mp4"
    out_path = ROOT / "output" / out_name
    print(f"=== 合成视频 → {out_path}", file=sys.stderr)
    build_video(
        script,
        clips,
        odds_data=odds,
        work_dir=log_dir / "compose",
        out_path=out_path,
    )

    meta = {
        "brand": demo["brand"],
        "title": script.get("title"),
        "hashtags": script.get("hashtags"),
        "mode": script.get("mode"),
        "video": str(out_path),
        "script": str(script_path),
        "odds_card": odds["card_png"],
    }
    (log_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  完成: {out_path}", file=sys.stderr)
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="生成世界杯前哨战每日短视频")
    parser.add_argument("--skip-compose", action="store_true", help="只拉数据与脚本，不合成")
    parser.add_argument("--date", default="", help="指定日期 YYYY-MM-DD（赔率快照）")
    args = parser.parse_args()
    try:
        meta = run(skip_compose=args.skip_compose, date_str=args.date)
        summary = ROOT / "output" / "worldcup_last.json"
        summary.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"失败: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
