#!/usr/bin/env python3
"""爆量情绪短视频脚本：先理解素材画面，再写口播。"""

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


def generate_script_from_visuals(
    demo: dict[str, Any],
    clip_infos: list[dict[str, Any]],
) -> dict[str, Any]:
    """根据已下载素材的视觉描述生成口播（解说必须与画面对齐）。"""
    if not clip_infos:
        raise ValueError("clip_infos 为空")

    hot_ctx = ""
    if demo.get("use_exa_hot"):
        hot_ctx = fetch_hot_snippet()

    visual_lines = []
    for c in clip_infos:
        visual_lines.append(
            f"片段{c['index']}: 搜索词={c.get('query','')}; 画面={c.get('visual','')}"
        )
    visuals_text = "\n".join(visual_lines)

    system = """你是短视频爆款文案策划。你必须根据「已确定的素材画面描述」写口播，严禁描写画面里没有的内容。
输出合法 JSON，无 markdown 外壳。
风格：口语化、情绪价值、有钩子；焦虑类可反问，治愈类温柔。
合规：不造谣、不人身攻击、不捏造数据。"""

    user = f"""为「{demo['name']}」类型写 35–55 秒竖屏短视频脚本。

类型特点：{demo.get('hook_style', '')}
{f'热点参考（仅泛化共鸣）：\\n{hot_ctx}' if hot_ctx else ''}

【已下载素材，口播必须逐段对应】
{visuals_text}

规则（重要）：
1. segments 数量必须等于 {len(clip_infos)}，且 segments[i] 的 narration 只描述「片段i」的画面
2. cold_open 基于片段0的画面写 2 秒钩子，可悬念/反问，但不要写片段0没有的东西
3. 不要写与画面无关的动物/场景/物体
4. 每段 narration 15-35 字，口语化
5. outro 一句引导点赞收藏

JSON:
{{
  "demo_id": "{demo['id']}",
  "title": "发布标题（≤28字）",
  "cold_open": "基于片段0的钩子",
  "hashtags": "{demo.get('hashtags', '')}",
  "segments": [
    {{"index": 0, "narration": "描述片段0", "clip_index": 0}},
    ...
  ],
  "outro": "结尾引导"
}}
"""

    raw = chat_complete(system=system, user=user, max_tokens=2048, temperature=0.7)
    script = _extract_json(raw)
    script.setdefault("demo_id", demo["id"])
    script.setdefault("hashtags", demo.get("hashtags", ""))

    segs = script.get("segments") or []
    if len(segs) != len(clip_infos):
        raise ValueError(f"segments 数量 {len(segs)} 与素材 {len(clip_infos)} 不一致")

    for i, seg in enumerate(segs):
        seg["clip_index"] = i
        seg["clip_query"] = clip_infos[i].get("query", "")
        seg["visual"] = clip_infos[i].get("visual", "")

    script["clip_infos"] = clip_infos
    return script


# 保留旧接口供调试
def generate_script(demo: dict[str, Any]) -> dict[str, Any]:
    """已弃用：请先下载素材并调用 generate_script_from_visuals。"""
    raise RuntimeError("请使用「先下载素材→视觉理解→generate_script_from_visuals」流程")
