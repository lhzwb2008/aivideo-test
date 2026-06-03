#!/usr/bin/env python3
"""爆量情绪短视频脚本生成：网搜素材关键词 + 口播分段。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import exa_client
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


def fetch_hot_snippet() -> str:
    """用 Exa 拉一条近期社会/情绪热点摘要，供焦虑类脚本参考。"""
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=3)
        results = exa_client.search(
            "中国 年轻人 焦虑 职场 热点 情绪 2025 2026",
            num_results=6,
            start_published_date=start.strftime("%Y-%m-%d"),
            summary_query="这条新闻让人焦虑的点是什么",
        )
        bits: list[str] = []
        for r in results[:4]:
            title = (r.get("title") or "").strip()
            summary = (r.get("summary") or "")
            if isinstance(summary, dict):
                summary = summary.get("text") or summary.get("summary") or ""
            hl = r.get("highlights") or []
            if isinstance(hl, list) and hl:
                summary = summary or " ".join(str(x) for x in hl[:2])
            if title:
                bits.append(f"- {title}: {(summary or '')[:200]}")
        return "\n".join(bits) if bits else ""
    except Exception:
        return ""


def generate_script(demo: dict[str, Any]) -> dict[str, Any]:
    """为某一 demo 类型生成完整脚本 JSON。"""
    hot_ctx = ""
    if demo.get("use_exa_hot"):
        hot_ctx = fetch_hot_snippet()

    clip_queries = demo.get("clip_queries") or []
    system = """你是短视频爆款文案策划，专做情绪价值、刷流量向的竖屏短视频（非财经、非荐股）。
输出必须是合法 JSON，不要 markdown 包裹外的说明。
风格：口语化、有钩子、有节奏；焦虑类可用反问和紧迫感，治愈类要温柔留白。
合规：不造谣具体事件、不人身攻击、不写虚假数据；热点只可泛化共鸣，不捏造新闻细节。"""

    user = f"""请为「{demo['name']}」类型生成一条 35–55 秒的竖屏短视频脚本。

类型特点：{demo.get('hook_style', '')}
建议素材搜索词（每条 segment 用其中一个，可微调英文）：{json.dumps(clip_queries, ensure_ascii=False)}
{f'近期热点参考（可泛化共鸣，勿捏造细节）：\\n{hot_ctx}' if hot_ctx else ''}

JSON schema:
{{
  "demo_id": "{demo['id']}",
  "title": "发布标题（带情绪钩子，≤28字）",
  "cold_open": "前2秒口播钩子（一句话）",
  "hashtags": "{demo.get('hashtags', '')}",
  "segments": [
    {{
      "narration": "该段口播（15-35字）",
      "clip_query": "Pexels 英文搜索词（2-5词）",
      "on_screen": "可选画面大字（≤12字，可空）"
    }}
  ],
  "outro": "结尾一句引导点赞收藏（可选）"
}}

要求：
- segments 数量 3–4 段，每段 narration 独立成句
- clip_query 用英文、适合搜 stock 视频
- 总口播字数约 120–180 字（含 cold_open 和 outro）
"""

    raw = chat_complete(system=system, user=user, max_tokens=2048, temperature=0.85)
    script = _extract_json(raw)
    script.setdefault("demo_id", demo["id"])
    script.setdefault("hashtags", demo.get("hashtags", ""))
    segs = script.get("segments") or []
    if len(segs) < 2:
        raise ValueError("segments 过少")
    return script
