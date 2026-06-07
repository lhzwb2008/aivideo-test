"""32强巡礼：单队 slide 脚本（纯足球内容，无博彩）。"""

from __future__ import annotations

import json
import re
from typing import Any

from text_client import chat_complete
from worldcup_script import _clip, _extract_json


def _fallback_team_script(team: dict[str, Any]) -> dict[str, Any]:
    cn = team["name_cn"]
    nick = team.get("nickname", "")
    star = team.get("star_hint", "")
    return {
        "team_id": team["id"],
        "team_cn": cn,
        "team_en": team.get("name_en", ""),
        "nickname": nick,
        "title": f"{cn}｜32强巡礼：{nick}出征2026",
        "cold_open": f"世界杯32强巡礼，今天带你认识{nick}{cn}。",
        "hashtags": f"#世界杯 #2026世界杯 #{cn} #32强巡礼 #足球",
        "slides": [
            {
                "headline": "球队底色",
                "narration": f"{cn}的传统底色是进攻与激情，{nick}从来不缺世界级球星，球迷文化也极具辨识度。",
                "image_prompt": f"{team.get('name_en','')} national team fans in stadium with flag colors {team.get('colors','')}",
                "on_image_text": [nick, "传统豪门", "进攻基因"],
            },
            {
                "headline": "核心看点",
                "narration": f"本届最大看点在锋线：{star}，他的状态将直接决定{cn}能走多远。",
                "image_prompt": f"star football striker silhouette celebrating goal, {team.get('colors','')} kit",
                "on_image_text": ["核心锋线", star[:8] if star else "球星", "决定上限"],
            },
            {
                "headline": "世界杯记忆",
                "narration": f"{cn}拥有辉煌世界杯历史，既有冠军荣耀，也有遗憾出局，今年目标只会更高。",
                "image_prompt": "world cup trophy memories montage, vintage and modern stadium",
                "on_image_text": ["冠军荣耀", "经典瞬间", "2026再出发"],
            },
            {
                "headline": "球迷理由",
                "narration": f"如果你爱激情足球，{cn}永远值得追。关注前哨战，后续还有32强完整巡礼。",
                "image_prompt": f"crowd celebrating with fireworks and national colors {team.get('colors','')}",
                "on_image_text": ["值得追", "激情足球", "关注巡礼"],
            },
        ],
        "outro": f"想看哪支球队？评论区点名，我继续做巡礼。",
    }


def generate_team_script(team: dict[str, Any]) -> dict[str, Any]:
    cn = team["name_cn"]
    system = """你是世界杯科普短视频编导，栏目「世界杯前哨战·32强巡礼」。
输出合法 JSON。内容仅限足球：历史、球星、打法、球迷文化、世界杯期待。
严禁：赔率、博彩、下注、预测市场、百分比夺冠概率、赌场、彩票。"""

    user = f"""为球队写 50–60 秒竖屏巡礼脚本。
球队：{cn}（{team.get('name_en','')}），绰号{team.get('nickname','')}
球星线索：{team.get('star_hint','')}

结构：
1. cold_open 28–36字
2. slides 恰好4页，每页 narration 72–88字（完整句，勿截断），image_prompt 英文场景描述，on_image_text 2–3个中文短语
3. outro 18–24字
4. title ≤26字

JSON:
{{
  "team_id": "{team['id']}",
  "team_cn": "{cn}",
  "nickname": "{team.get('nickname','')}",
  "title": "...",
  "cold_open": "...",
  "hashtags": "#世界杯 #{cn} #32强巡礼",
  "slides": [
    {{"headline":"球队底色","narration":"...","image_prompt":"...","on_image_text":["..."]}},
    {{"headline":"核心看点","narration":"...","image_prompt":"...","on_image_text":["..."]}},
    {{"headline":"世界杯记忆","narration":"...","image_prompt":"...","on_image_text":["..."]}},
    {{"headline":"球迷理由","narration":"...","image_prompt":"...","on_image_text":["..."]}}
  ],
  "outro": "..."
}}
"""

    try:
        raw = chat_complete(system=system, user=user, max_tokens=2200, temperature=0.55)
        script = _extract_json(raw)
    except Exception:
        script = _fallback_team_script(team)

    script.setdefault("team_id", team["id"])
    script.setdefault("team_cn", cn)
    script.setdefault("nickname", team.get("nickname", ""))

    if len(script.get("slides") or []) < 4:
        script = _fallback_team_script(team)

    return _enforce_script(script)


def _enforce_script(script: dict[str, Any]) -> dict[str, Any]:
    banned = ("赔率", "博彩", "下注", "Polymarket", "彩票", "赌场", "夺冠概率", "%")
    for key, lim in (("cold_open", 36), ("outro", 24), ("title", 28)):
        if script.get(key):
            script[key] = _clip(script[key], lim)
    for slide in script.get("slides") or []:
        narr = slide.get("narration", "")
        for w in banned:
            narr = narr.replace(w, "")
        slide["narration"] = _clip(narr, 88)
        slide["headline"] = (slide.get("headline") or "")[:12]
    return script


def load_teams() -> list[dict]:
    path = __import__("paths").ROOT / "demos" / "worldcup_tour_teams.json"
    return json.loads(path.read_text(encoding="utf-8"))
