"""球队赔率分析专题脚本（无每日新闻、无赔率动效段）。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from text_client import chat_complete
from worldcup_script import _attach_news_headers, _clip, _extract_json, _short_headline


def _team_rows(odds: dict[str, Any], teams: list[str]) -> list[dict[str, Any]]:
    by_name = {r["team"]: r for r in (odds.get("top") or [])}
    all_rows = odds.get("top") or []
    rows: list[dict[str, Any]] = []
    for t in teams:
        if t in by_name:
            rows.append(dict(by_name[t]))
    if len(rows) < len(teams):
        seen = {r["team"] for r in rows}
        for r in all_rows:
            if r["team"] not in seen:
                rows.append(dict(r))
                seen.add(r["team"])
            if len(rows) >= len(teams):
                break
    return rows[: len(teams)]


def _teams_context(rows: list[dict[str, Any]], topic: dict[str, Any]) -> str:
    lines = []
    for i, r in enumerate(rows):
        label = (topic.get("segment_labels") or [f"第{i+1}点"])[i] if i < len(topic.get("segment_labels") or []) else f"第{i+1}点"
        lines.append(f"{label} {r['team_cn']}({r['team']}) 夺冠概率 {r['pct']}%")
    vol = topic.get("_volume24hr")
    if vol:
        lines.append(f"市场24h成交约 {vol/1_000_000:.1f}M 美元")
    return "\n".join(lines)


def _fallback_topic_script(
    demo: dict[str, Any],
    topic: dict[str, Any],
    *,
    odds: dict[str, Any],
    team_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    labels = topic.get("segment_labels") or ["第1点", "第2点", "第3点", "第4点"]
    segments: list[dict[str, Any]] = []
    templates_hot = [
        "阵容厚度+大赛经验支撑高赔，但淘汰赛一场定生死，压力也不小。",
        "与榜首差距极小，纸面实力顶级，关键看临场发挥与点球运气。",
        "进攻端人才井喷，赔率反映争冠预期，后防线稳定性是命门。",
        "核心球员状态在线，市场给出前排定价，小组赛赛程相对友好。",
    ]
    templates_dark = [
        "赔率不算头部，但阵容均衡，淘汰赛一场定胜负时最容易爆冷。",
        "市场定价偏保守，若小组赛顺利出线，八强后赔率可能重估。",
        "南美硬朗打法+老将经验，低赔不代表没机会走更远。",
        "身体对抗强、定位球出色，适合作为高赔下的关注选项。",
    ]
    tpl = templates_dark if "冷门" in topic.get("name", "") or topic["id"] == "dark_horses" else templates_hot

    for i, r in enumerate(team_rows[:4]):
        tag = labels[i] if i < len(labels) else f"第{i+1}点"
        narr = f"{r['team_cn']}夺冠概率{r['pct']:.1f}%。{tpl[i % len(tpl)]}"[:56]
        segments.append({
            "type": "analysis",
            "index": i,
            "news_label": tag,
            "headline": f"{r['team_cn']} {r['pct']:.1f}%",
            "narration": narr,
            "clip_index": i,
            "team": r["team"],
        })

    lead = team_rows[0]["team_cn"] if team_rows else "热门"
    return {
        "demo_id": demo["id"],
        "topic_id": topic["id"],
        "mode": "topic",
        "title": topic.get("title_hint", topic["name"])[:28],
        "cold_open": f"世界杯前哨战，今天聊「{topic['name']}」，用赔率帮你看懂争冠格局。",
        "hashtags": topic.get("hashtags") or demo.get("hashtags", ""),
        "segments": segments,
        "outro": "关注前哨战，带你看懂世界杯赔率逻辑。",
        "odds_snapshot": odds,
        "topic": topic,
        "team_rows": team_rows,
    }


def generate_topic_script(
    demo: dict[str, Any],
    topic: dict[str, Any],
    *,
    odds: dict[str, Any],
) -> dict[str, Any]:
    team_rows = _team_rows(odds, topic.get("teams") or [])
    if not team_rows:
        raise ValueError(f"专题 {topic['id']} 无可用球队赔率")

    topic = dict(topic)
    topic["_volume24hr"] = odds.get("volume24hr")
    ctx = _teams_context(team_rows, topic)
    labels = topic.get("segment_labels") or ["第1点", "第2点", "第3点", "第4点"]

    seg_tpl = ",\n    ".join(
        f'{{"type": "analysis", "index": {i}, "news_label": "{labels[i] if i < len(labels) else f"第{i+1}点"}", '
        f'"headline": "球队名 赔率%", "narration": "...", "clip_index": {i}}}'
        for i in range(min(4, len(team_rows)))
    )

    system = """你是抖音体育涨粉账号「世界杯前哨战」的专题编导。
输出合法 JSON，无 markdown。
风格：口语化、有观点、信息密度高；用预测市场赔率做分析，但不要写成博彩推荐。
不得编造球队没有的数据；赔率数字必须与素材一致。
合规：强调「预测市场/非官方博彩」，不造谣。"""

    user = f"""为专题「{topic['name']}」写 55–65 秒竖屏短视频脚本。
专题角度：{topic.get('angle', '')}

【球队赔率素材（必须准确引用）】
{ctx}

结构（不要每日新闻、不要赔率变化动效，全是球队分析口播）：
1. cold_open：24–30 字，钩子+专题名
2. 恰好 {len(team_rows[:4])} 段 analysis：
   - news_label 用指定标签：{labels}
   - headline ≤18字，格式如「西班牙 16.0%」
   - narration 每段 50–56 字：赔率含义+1句实力/风险解读
3. outro：12–16 字
4. title ≤28 字，涨粉向、有悬念

JSON:
{{
  "topic_id": "{topic['id']}",
  "title": "...",
  "cold_open": "...",
  "hashtags": "{topic.get('hashtags', '')}",
  "segments": [{seg_tpl}],
  "outro": "..."
}}
"""

    try:
        raw = chat_complete(system=system, user=user, max_tokens=2600, temperature=0.6)
        script = _extract_json(raw)
    except Exception:
        script = _fallback_topic_script(demo, topic, odds=odds, team_rows=team_rows)

    script.setdefault("demo_id", demo["id"])
    script.setdefault("topic_id", topic["id"])
    script.setdefault("mode", "topic")
    script.setdefault("hashtags", topic.get("hashtags") or demo.get("hashtags", ""))
    script["odds_snapshot"] = odds
    script["topic"] = topic
    script["team_rows"] = team_rows

    segs = script.get("segments") or []
    if len(segs) < min(4, len(team_rows)):
        script = _fallback_topic_script(demo, topic, odds=odds, team_rows=team_rows)

    script = _enforce_topic_budget(script)
    return _attach_analysis_headers(script, team_rows, topic)


def _attach_analysis_headers(
    script: dict[str, Any],
    team_rows: list[dict[str, Any]],
    topic: dict[str, Any],
) -> dict[str, Any]:
    labels = topic.get("segment_labels") or []
    for i, seg in enumerate(script.get("segments") or []):
        if seg.get("type") not in ("analysis", "news"):
            continue
        seg["type"] = "analysis"
        if i < len(labels):
            seg["news_label"] = labels[i]
        if i < len(team_rows):
            r = team_rows[i]
            seg["headline"] = _short_headline(seg.get("headline") or f"{r['team_cn']} {r['pct']:.1f}%", max_len=18)
            if not seg.get("headline") or "%" not in seg.get("headline", ""):
                seg["headline"] = f"{r['team_cn']} {r['pct']:.1f}%"
        seg.setdefault("clip_index", i)
    return script


def _enforce_topic_budget(script: dict[str, Any]) -> dict[str, Any]:
    limits = {"cold_open": 30, "outro": 16, "analysis": 56}
    if script.get("cold_open"):
        script["cold_open"] = _clip(script["cold_open"], limits["cold_open"])
    if script.get("outro"):
        script["outro"] = _clip(script["outro"], limits["outro"])
    for seg in script.get("segments") or []:
        seg["narration"] = _clip(seg.get("narration", ""), limits["analysis"])
        if seg.get("headline"):
            seg["headline"] = seg["headline"][:18]
    return script


def load_topics() -> list[dict]:
    path = __import__("paths").ROOT / "demos" / "worldcup_topics.json"
    return json.loads(path.read_text(encoding="utf-8"))
