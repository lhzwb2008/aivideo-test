"""世界杯新闻 / 赛况采集（Exa + 兜底）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import exa_client


def _fmt_results(results: list[dict], *, limit: int = 8) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in results:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        key = title[:60].lower()
        if key in seen:
            continue
        seen.add(key)
        summary = r.get("summary") or ""
        if isinstance(summary, dict):
            summary = summary.get("text") or summary.get("summary") or ""
        hl = r.get("highlights") or []
        if isinstance(hl, list) and hl and not summary:
            summary = " ".join(str(x) for x in hl[:3])
        items.append({
            "title": title,
            "summary": (summary or "")[:400],
            "url": (r.get("url") or "").strip(),
        })
        if len(items) >= limit:
            break
    return items


def fetch_news(*, mode: str = "news") -> list[dict[str, str]]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=3)
    queries = (
        ["2026 FIFA World Cup match results scores today", "World Cup 2026 goals highlights today"]
        if mode == "results"
        else [
            "2026 FIFA World Cup news injury squad preview",
            "World Cup 2026 USA Mexico Canada opening matches",
            "FIFA World Cup 2026 team news transfer",
        ]
    )
    summary_q = "比赛比分和关键事件" if mode == "results" else "这条新闻的核心事实与对世界杯的影响"

    all_items: list[dict[str, str]] = []
    for query in queries:
        try:
            results = exa_client.search(
                query,
                num_results=6,
                start_published_date=start.strftime("%Y-%m-%d"),
                summary_query=summary_q,
            )
            all_items.extend(_fmt_results(results, limit=6))
        except Exception:
            continue
        if len(all_items) >= 8:
            break

    # 去重保序
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for it in all_items:
        k = it["title"][:60].lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(it)
        if len(deduped) >= 8:
            break

    return deduped or _fallback_news(mode=mode)


def _fallback_news(*, mode: str) -> list[dict[str, str]]:
    if mode == "results":
        return [{
            "title": "2026世界杯今日赛果速递",
            "summary": "正赛期间将同步当日比分、进球者与出线形势变化。",
            "url": "",
        }]
    return [
        {"title": "2026美加墨世界杯即将开幕", "summary": "48支球队参赛，小组赛6月中旬打响，西班牙与法国并列夺冠热门。", "url": ""},
        {"title": "美国队揭幕战对阵巴拉圭", "summary": "波切蒂诺带队主场亮相洛杉矶，高位压迫体系面临大考。", "url": ""},
        {"title": "内马尔伤情牵动巴西前景", "summary": "巴西核心右腿伤势未愈，能否赶上对摩洛哥首战仍是未知数。", "url": ""},
        {"title": "各队公布最终大名单", "summary": "伤病减员、战术磨合与更衣室氛围，直接影响夺冠盘口走向。", "url": ""},
        {"title": "Polymarket 夺冠盘交易创高", "summary": "预测市场24小时成交活跃，西班牙法国英格兰领跑概率榜。", "url": ""},
    ]


def pick_mode_for_today() -> str:
    today = datetime.now(timezone.utc).date()
    if today >= datetime(2026, 6, 11).date():
        return "results"
    return "news"


def bundle_context(*, mode: str | None = None) -> dict[str, Any]:
    mode = mode or pick_mode_for_today()
    news = fetch_news(mode=mode)
    return {"mode": mode, "news": news}
