"""世界杯前哨战：新闻 + 赔率 → 约 60 秒口播脚本。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from text_client import chat_complete


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
            if isinstance(obj, dict):
                return obj
            idx = end
        except json.JSONDecodeError:
            idx = start + 1
    raise ValueError(f"无法解析 JSON: {text[:400]}")


def _odds_lines(odds: dict[str, Any]) -> str:
    lines = []
    for i, r in enumerate(odds.get("top") or []):
        delta = r.get("delta")
        if delta is not None and delta != 0:
            sign = "升" if delta > 0 else "降"
            lines.append(f"{i+1}. {r['team_cn']} {r['pct']}%（较昨日{sign}{abs(delta):.1f}个百分点）")
        else:
            lines.append(f"{i+1}. {r['team_cn']} {r['pct']}%")
    vol = odds.get("volume24hr")
    if vol:
        lines.append(f"24小时成交量约 {vol/1_000_000:.1f}M 美元")
    mover = odds.get("biggest_mover")
    if mover and mover.get("delta"):
        lines.append(f"最大波动：{mover['team_cn']} {mover['delta']:+.1f}%")
    return "\n".join(lines)


def _news_lines(news: list[dict[str, str]]) -> str:
    return "\n".join(
        f"- {n['title']}: {n.get('summary', '')[:280]}"
        for n in news[:6]
    )


def _news_segment_count(demo: dict[str, Any]) -> int:
    return int(demo.get("news_segments") or 4)


_CN_NUM = ("一", "二", "三", "四", "五", "六", "七", "八")


def news_label(n: int) -> str:
    """1-based → 第一条新闻"""
    if 1 <= n <= len(_CN_NUM):
        return f"第{_CN_NUM[n - 1]}条新闻"
    return f"第{n}条新闻"


def _short_headline(title: str, *, max_len: int = 26) -> str:
    t = (title or "").strip()
    for sep in ("|", " - ", " – ", " — "):
        if sep in t:
            t = t.split(sep)[0].strip()
    for junk in ("Goal.com", "Sportstar", "beIN SPORTS", "Preview:", "FIFA"):
        t = t.replace(junk, "").strip(" :-")
    return (t or "世界杯快讯")[:max_len]


def _attach_news_headers(script: dict[str, Any], news_ctx: dict[str, Any]) -> dict[str, Any]:
    news = news_ctx.get("news") or []
    news_i = 0
    for seg in script.get("segments") or []:
        if seg.get("type") != "news":
            continue
        seg["news_label"] = news_label(news_i + 1)
        if not seg.get("headline"):
            src = news[news_i]["title"] if news_i < len(news) else ""
            seg["headline"] = _short_headline(src)
        else:
            seg["headline"] = _short_headline(seg["headline"])
        news_i += 1
    return script


def _fallback_script(
    demo: dict[str, Any],
    *,
    odds: dict[str, Any],
    news_ctx: dict[str, Any],
) -> dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%m月%d日")
    mode = news_ctx.get("mode", "news")
    top = odds.get("top") or []
    news = news_ctx.get("news") or []
    n_seg = _news_segment_count(demo)

    def _pick(i: int) -> tuple[str, str]:
        if i < len(news):
            return news[i].get("title", ""), news[i].get("summary", "")[:80]
        return "世界杯备战持续推进", "各队阵容磨合与伤病情况牵动夺冠盘口。"

    segments: list[dict[str, Any]] = []
    for i in range(n_seg):
        title, summary = _pick(i)
        short_title = title.split("|")[0].split("-")[0].strip()[:30]
        body = f"{short_title}，{summary[:28]}"[:48]
        segments.append({
            "type": "news",
            "index": i,
            "news_label": news_label(i + 1),
            "headline": _short_headline(title),
            "narration": body,
            "clip_index": i % 5,
        })

    t0 = top[0] if top else {"team_cn": "西班牙", "pct": 16.0}
    t1 = top[1] if len(top) > 1 else {"team_cn": "法国", "pct": 16.0}
    t2 = top[2] if len(top) > 2 else {"team_cn": "英格兰", "pct": 11.0}
    vol = odds.get("volume24hr") or 0
    vol_txt = f"24小时成交超{vol/1_000_000:.0f}百万美元，" if vol else ""

    segments.append({
        "type": "odds",
        "index": n_seg,
        "narration": (
            f"Polymarket夺冠榜：{t0['team_cn']}{t0['pct']:.1f}%，{t1['team_cn']}{t1['pct']:.1f}%，"
            f"{t2['team_cn']}{t2['pct']:.1f}%。{vol_txt}预测市场非官方博彩。"
        )[:78],
        "clip_index": None,
    })

    lead = top[0]["team_cn"] if top else "西班牙"
    return {
        "demo_id": demo["id"],
        "mode": mode,
        "title": f"世界杯前哨战｜{today}：{lead}领跑夺冠赔率",
        "cold_open": f"世界杯前哨战，{today}，四条重磅新闻，再加实时夺冠赔率。",
        "hashtags": demo.get("hashtags", ""),
        "segments": segments,
        "outro": "关注世界杯前哨战，每天赛况、新闻、赔率，一条看懂。",
        "odds_snapshot": odds,
        "news_context": news_ctx,
    }


def generate_script(
    demo: dict[str, Any],
    *,
    odds: dict[str, Any],
    news_ctx: dict[str, Any],
) -> dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mode = news_ctx.get("mode", "news")
    n_seg = _news_segment_count(demo)
    news_text = _news_lines(news_ctx.get("news") or [])
    odds_text = _odds_lines(odds)

    seg_templates = ",\n    ".join(
        f'{{"type": "news", "index": {i}, "news_label": "{news_label(i + 1)}", "headline": "...", "narration": "...", "clip_index": {i % 5}}}'
        for i in range(n_seg)
    )

    system = """你是「世界杯前哨战」抖音资讯号首席编辑。
输出合法 JSON，无 markdown。
风格：专业体育播报、信息密度高、节奏紧凑；每条新闻讲清楚「谁、什么事、有什么影响」。
赔率必须严格使用提供的数据，不得编造比分、伤病或数字。
合规：预测市场赔率需点明非官方博彩；不造谣。"""

    user = f"""为「{demo['brand']}」写总时长约 58–65 秒的竖屏短视频脚本（严格控制字数！）。
日期：{today}
内容模式：{mode}

【新闻素材（可提炼改写，禁止捏造）】
{news_text}

【Polymarket 赔率（必须准确）】
{odds_text}

字数要求（全片目标 58–65 秒，请写满）：
1. cold_open：24–30 字
2. {n_seg} 段 news：每段含 news_label（第一条新闻/第二条新闻…）、headline（≤22字标题）、narration 50–56 字，clip_index 0~{n_seg - 1}
3. 1 段 odds：narration 82–90 字，前三名赔率+24h成交+一句解读，clip_index=null
4. outro：12–16 字
5. title ≤ 28 字

JSON:
{{
  "demo_id": "{demo['id']}",
  "mode": "{mode}",
  "title": "...",
  "cold_open": "...",
  "hashtags": "{demo.get('hashtags', '')}",
  "segments": [
    {seg_templates},
    {{"type": "odds", "index": {n_seg}, "narration": "...", "clip_index": null}}
  ],
  "outro": "..."
}}
"""

    try:
        raw = chat_complete(system=system, user=user, max_tokens=2800, temperature=0.55)
        script = _extract_json(raw)
    except Exception:
        script = _fallback_script(demo, odds=odds, news_ctx=news_ctx)

    script.setdefault("demo_id", demo["id"])
    script.setdefault("hashtags", demo.get("hashtags", ""))
    script.setdefault("mode", mode)
    script["odds_snapshot"] = odds
    script["news_context"] = news_ctx

    segs = script.get("segments") or []
    news_count = sum(1 for s in segs if s.get("type") == "news")
    has_odds = any(s.get("type") == "odds" for s in segs)
    if news_count < n_seg or not has_odds:
        script = _fallback_script(demo, odds=odds, news_ctx=news_ctx)

    script = _enforce_duration_budget(script, demo)
    return _attach_news_headers(script, news_ctx)


def _clip(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        out = text
    else:
        out = text[:max_len]
        for extra in range(0, 10):
            chunk = text[: max_len + extra]
            for sep in ("。", "！", "？"):
                pos = chunk.rfind(sep)
                if pos >= max_len * 0.55:
                    out = chunk[: pos + 1]
                    break
            if out.endswith(("。", "！", "？")):
                break
    if out and out[-1] in "，、；：":
        out = out[:-1] + "。"
    elif out and out[-1] not in "。！？":
        out += "。"
    return out


def _enforce_duration_budget(script: dict[str, Any], demo: dict[str, Any]) -> dict[str, Any]:
    """二次裁剪，确保口播总量约 60 秒。"""
    limits = {
        "cold_open": 30,
        "outro": 16,
        "news": 56,
        "odds": 90,
    }
    if script.get("cold_open"):
        script["cold_open"] = _clip(script["cold_open"], limits["cold_open"])
    if script.get("outro"):
        script["outro"] = _clip(script["outro"], limits["outro"])
    for seg in script.get("segments") or []:
        if seg.get("type") == "odds":
            seg["narration"] = _clip(seg.get("narration", ""), limits["odds"])
        elif seg.get("type") == "news":
            seg["narration"] = _clip(seg.get("narration", ""), limits["news"])
            if seg.get("headline"):
                seg["headline"] = seg["headline"][:26]
    return script
