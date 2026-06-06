"""Polymarket 世界杯夺冠赔率：Gamma API + 精美卡片 + 帧动画。"""

from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from http_util import get
from paths import ROOT

GAMMA_URL = "https://gamma-api.polymarket.com/events"
SNAPSHOT_DIR = ROOT / "assets" / "worldcup" / "snapshots"
HISTORY_PATH = ROOT / "assets" / "worldcup" / "odds_history.json"
CANVAS_W, CANVAS_H = 1080, 1920

TEAM_CN: dict[str, str] = {
    "Spain": "西班牙", "France": "法国", "England": "英格兰", "Portugal": "葡萄牙",
    "Argentina": "阿根廷", "Brazil": "巴西", "Germany": "德国", "Netherlands": "荷兰",
    "Italy": "意大利", "Belgium": "比利时", "Croatia": "克罗地亚", "USA": "美国",
    "Mexico": "墨西哥", "Canada": "加拿大", "Morocco": "摩洛哥", "Japan": "日本",
    "South Korea": "韩国", "Colombia": "哥伦比亚", "Uruguay": "乌拉圭",
    "Switzerland": "瑞士", "Denmark": "丹麦", "Ecuador": "厄瓜多尔", "Senegal": "塞内加尔",
    "Austria": "奥地利", "Norway": "挪威", "Scotland": "苏格兰", "Paraguay": "巴拉圭",
    "Australia": "澳大利亚", "Tunisia": "突尼斯", "Algeria": "阿尔及利亚", "Iran": "伊朗",
    "Ukraine": "乌克兰", "Poland": "波兰", "Serbia": "塞尔维亚", "Ghana": "加纳",
    "Ivory Coast": "科特迪瓦", "Cameroon": "喀麦隆", "Qatar": "卡塔尔",
    "Saudi Arabia": "沙特阿拉伯", "Costa Rica": "哥斯达黎加", "Panama": "巴拿马",
    "Haiti": "海地", "Curaçao": "库拉索", "New Zealand": "新西兰",
    "South Africa": "南非", "Cape Verde": "佛得角", "Jordan": "约旦", "Uzbekistan": "乌兹别克斯坦",
}

TEAM_ACCENT: dict[str, str] = {
    "Spain": "#E63946", "France": "#457B9D", "England": "#FFFFFF", "Portugal": "#2D6A4F",
    "Argentina": "#74C0FC", "Brazil": "#FFD60A", "Germany": "#FFFFFF", "Netherlands": "#FF6B35",
    "Belgium": "#FFD60A", "Italy": "#2B9348", "Croatia": "#E63946", "USA": "#3A86FF",
    "Mexico": "#06D6A0", "Morocco": "#E63946", "Japan": "#FFFFFF",
}

MEDAL = ("#FFD700", "#C8CCD6", "#CD7F32")


def _slug() -> str:
    return os.environ.get("POLYMARKET_SLUG", "world-cup-winner").strip()


def _top_n() -> int:
    try:
        return max(4, int(os.environ.get("POLYMARKET_TOP_N", "8")))
    except ValueError:
        return 8


def _font(size: int):
    from PIL import ImageFont
    font_path = os.environ.get("AIVIDEO_FONT", str(ROOT / "assets" / "HiraginoSansGB.ttc"))
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def _lerp_color(c1: str, c2: str, t: float) -> tuple[int, int, int]:
    r1, g1, b1 = _hex_rgb(c1)
    r2, g2, b2 = _hex_rgb(c2)
    return (
        int(_lerp(r1, r2, t)),
        int(_lerp(g1, g2, t)),
        int(_lerp(b1, b2, t)),
    )


def _fmt_volume(v: float | None) -> str:
    if not v:
        return "24h 成交活跃"
    if v >= 1_000_000_000:
        return f"24h ${v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"24h ${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"24h ${v / 1_000:.0f}K"
    return f"24h ${v:.0f}"


def fetch_raw_event() -> dict[str, Any]:
    slug = _slug()
    url = f"{GAMMA_URL}?slug={slug}"
    raw = get(url, timeout=60)
    data = json.loads(raw.decode("utf-8"))
    if not data:
        raise RuntimeError(f"Polymarket 无事件 slug={slug}")
    return data[0]


def parse_odds(event: dict[str, Any], *, top_n: int | None = None) -> list[dict[str, Any]]:
    n = top_n or _top_n()
    rows: list[dict[str, Any]] = []
    for m in event.get("markets") or []:
        q = (m.get("question") or "").strip()
        if "win the 2026 FIFA World Cup" not in q:
            continue
        prices_raw = m.get("outcomePrices") or "[]"
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        if not prices:
            continue
        team = q.replace("Will ", "").replace(" win the 2026 FIFA World Cup?", "")
        pct = round(float(prices[0]) * 100, 1)
        rows.append({"team": team, "team_cn": TEAM_CN.get(team, team), "pct": pct})
    rows.sort(key=lambda x: -x["pct"])
    return rows[:n]


def _today_str(d: date | None = None) -> str:
    return (d or datetime.now(timezone.utc).date()).isoformat()


def load_history() -> dict[str, Any]:
    if not HISTORY_PATH.is_file():
        return {"snapshots": {}}
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def save_history(history: dict[str, Any]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def _yesterday_key(today: str, history: dict[str, Any]) -> str | None:
    dates = sorted(history.get("snapshots", {}).keys())
    prior = [d for d in dates if d < today]
    return prior[-1] if prior else None


def attach_deltas(rows: list[dict[str, Any]], *, today: str | None = None) -> list[dict[str, Any]]:
    today = today or _today_str()
    history = load_history()
    prev_key = _yesterday_key(today, history)
    prev_map: dict[str, float] = {}
    if prev_key:
        for r in history["snapshots"][prev_key].get("top") or []:
            prev_map[r["team"]] = float(r["pct"])

    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        if r["team"] in prev_map:
            delta = round(r["pct"] - prev_map[r["team"]], 1)
            item["delta"] = delta
            item["dir"] = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        else:
            item["delta"] = None
            item["dir"] = "new"
        out.append(item)
    return out


def snapshot_today(rows: list[dict[str, Any]], *, today: str | None = None) -> dict[str, Any]:
    today = today or _today_str()
    history = load_history()
    history.setdefault("snapshots", {})[today] = {
        "date": today,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "top": [{"team": r["team"], "team_cn": r["team_cn"], "pct": r["pct"]} for r in rows],
    }
    save_history(history)
    return history["snapshots"][today]


def _draw_gradient_bg(img) -> None:
    """分块渐变背景（无 numpy 依赖）。"""
    from PIL import ImageDraw

    w, h = img.size
    draw = ImageDraw.Draw(img)
    bands = 48
    for i in range(bands):
        y1 = i * h // bands
        y2 = (i + 1) * h // bands
        t = (y1 + y2) / 2 / max(h, 1)
        if t < 0.55:
            c = _lerp_color("#080c20", "#12183a", t / 0.55)
        else:
            c = _lerp_color("#12183a", "#060816", (t - 0.55) / 0.45)
        draw.rectangle((0, y1, w, y2), fill=c)


def _glow_circle(draw, cx: int, cy: int, r: int, color: str, alpha: int = 40) -> None:
    from PIL import Image
    r1, g1, b1 = _hex_rgb(color)
    for i in range(r, 0, -8):
        a = int(alpha * (i / r))
        draw.ellipse(
            (cx - i, cy - i, cx + i, cy + i),
            fill=(r1, g1, b1, a) if hasattr(draw, "fill") else (r1 // 3, g1 // 3, b1 // 3),
        )


def _row_progress(frame_t: float, row_i: int, n_rows: int) -> float:
    """单行进度：错峰入场 + 弹性收尾。"""
    start = 0.12 + row_i * 0.07
    dur = 0.22
    raw = (frame_t - start) / dur
    if raw <= 0:
        return 0.0
    if raw >= 1:
        return 1.0
    # ease out cubic
    return 1 - pow(1 - raw, 3)


def _delta_progress(frame_t: float, row_i: int) -> float:
    start = 0.55 + row_i * 0.04
    raw = (frame_t - start) / 0.18
    return max(0.0, min(1.0, raw))


def render_odds_frame(
    rows: list[dict[str, Any]],
    *,
    frame_t: float = 1.0,
    subtitle: str = "",
    volume24hr: float | None = None,
    pulse: float = 0.0,
) -> "Image.Image":
    """绘制单帧赔率榜。frame_t∈[0,1] 控制动画进度，pulse 用于榜首光晕脉动。"""
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))
    base = Image.new("RGB", (CANVAS_W, CANVAS_H))
    _draw_gradient_bg(base)
    img.paste(base)
    draw = ImageDraw.Draw(img)

    # 装饰光斑
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((700, -80, 1100, 320), fill=(22, 82, 240, 55))
    od.ellipse((-120, 1200, 380, 1700), fill=(255, 214, 10, 35))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(img)

    f_brand = _font(28)
    f_title = _font(46)
    f_sub = _font(28)
    f_badge = _font(24)
    f_rank = _font(32)
    f_name = _font(38)
    f_en = _font(22)
    f_pct = _font(42)
    f_delta = _font(26)
    f_foot = _font(22)

    header_alpha = max(0.0, min(1.0, frame_t / 0.12))

    # 顶栏玻璃卡片
    hdr_y1, hdr_y2 = 48, 248
    hdr_fill = (20, 28, 58, int(220 * header_alpha))
    draw.rounded_rectangle((36, hdr_y1, 1044, hdr_y2), radius=24, fill=hdr_fill, outline=(60, 100, 220, int(180 * header_alpha)), width=2)

    if header_alpha > 0.1:
        draw.text((60, 68), "POLYMARKET", fill=(100, 160, 255, int(255 * header_alpha)), font=f_brand)
        draw.text((60, 108), "2026 世界杯夺冠赔率", fill=(255, 255, 255, int(255 * header_alpha)), font=f_title)
        sub = subtitle or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        draw.text((60, 168), f"更新 {sub}", fill=(180, 195, 230, int(220 * header_alpha)), font=f_sub)

        vol_text = _fmt_volume(volume24hr)
        tw = draw.textlength(vol_text, font=f_badge)
        bx1, by1 = int(1044 - tw - 56), 108
        draw.rounded_rectangle((bx1, by1, 1044 - 36, by1 + 44), radius=14, fill=(22, 82, 240, int(200 * header_alpha)))
        draw.text((bx1 + 14, by1 + 8), vol_text, fill=(255, 255, 255, int(255 * header_alpha)), font=f_badge)

        live_a = int(200 + 55 * math.sin(pulse * math.pi * 2))
        draw.ellipse((60, 200, 78, 218), fill=(255, 70, 70, live_a))
        draw.text((88, 196), "LIVE", fill=(255, 120, 120, int(255 * header_alpha)), font=f_badge)

    y = 280
    bar_max = 560
    max_pct = max((r["pct"] for r in rows), default=20.0)
    scale = max(max_pct, 18.0)

    for i, r in enumerate(rows):
        row_prog = _row_progress(frame_t, i, len(rows))
        if row_prog <= 0 and frame_t < 0.12:
            continue

        box_h = 158
        accent = TEAM_ACCENT.get(r["team"], "#3A86FF")
        is_top = i == 0
        glow_boost = 1.0 + 0.15 * math.sin(pulse * math.pi * 2) if is_top and frame_t >= 0.7 else 1.0

        card_alpha = int(210 * min(1.0, row_prog * 1.5))
        bg = (24, 32, 68, card_alpha) if i % 2 == 0 else (16, 22, 48, card_alpha)
        outline = (255, 215, 0, int(160 * row_prog)) if i == 0 else (50, 70, 120, int(100 * row_prog))
        ow = 3 if i == 0 else 1
        draw.rounded_rectangle((40, y, 1040, y + box_h - 8), radius=20, fill=bg, outline=outline, width=ow)

        # 排名徽章
        medal_c = MEDAL[i] if i < 3 else "#4A5568"
        draw.ellipse((58, y + 22, 108, y + 72), fill=(*_hex_rgb(medal_c), int(255 * row_prog)))
        draw.text((72 if i < 9 else 66, y + 30), str(i + 1), fill=(20, 20, 30, int(255 * row_prog)), font=f_rank)

        # 色条指示
        ar, ag, ab = _hex_rgb(accent)
        draw.rounded_rectangle((122, y + 28, 138, y + 68), radius=6, fill=(ar, ag, ab, int(255 * row_prog)))

        draw.text((152, y + 16), r["team_cn"], fill=(255, 255, 255, int(255 * row_prog)), font=f_name)
        draw.text((152, y + 60), r["team"], fill=(160, 175, 210, int(220 * row_prog)), font=f_en)

        # 动态进度条
        target_w = int(bar_max * (r["pct"] / scale) * glow_boost)
        anim_w = int(target_w * row_prog)
        track_y1, track_y2 = y + 100, y + 132
        draw.rounded_rectangle((152, track_y1, 152 + bar_max, track_y2), radius=10, fill=(30, 40, 70, int(200 * row_prog)))
        if anim_w > 4:
            draw.rounded_rectangle((152, track_y1, 152 + anim_w, track_y2), radius=10, fill=(ar, ag, ab, int(255 * row_prog)))
            # 高光
            draw.rounded_rectangle((152, track_y1, 152 + anim_w, track_y1 + 10), radius=10, fill=(255, 255, 255, int(40 * row_prog)))

        pct_prog = row_prog
        pct_text = f"{r['pct'] * pct_prog:.1f}%" if pct_prog < 1 else f"{r['pct']:.1f}%"
        draw.text((860, y + 18), pct_text, fill=(255, 255, 255, int(255 * row_prog)), font=f_pct)

        d_prog = _delta_progress(frame_t, i)
        delta = r.get("delta")
        if d_prog > 0:
            if delta is not None:
                if delta > 0:
                    d_text, d_color = f"▲ +{delta:.1f}%", "#3DFF8A"
                elif delta < 0:
                    d_text, d_color = f"▼ {delta:.1f}%", "#FF5C6A"
                else:
                    d_text, d_color = "— 持平", "#9AA8C7"
            else:
                d_text, d_color = "● 实时", "#6CB6FF"
            da = int(255 * d_prog)
            dr, dg, db = _hex_rgb(d_color)
            draw.rounded_rectangle((850, y + 72, 1020, y + 112), radius=10, fill=(dr, dg, db, int(40 * d_prog)))
            draw.text((862, y + 78), d_text, fill=(dr, dg, db, da), font=f_delta)

        y += box_h

    draw.text((52, CANVAS_H - 72), "数据来源 polymarket.com · 预测市场 · 非官方博彩", fill=(120, 135, 170, 200), font=f_foot)

    return img.convert("RGB")


def render_odds_card(
    rows: list[dict[str, Any]],
    out_path: Path,
    *,
    subtitle: str = "",
    volume24hr: float | None = None,
) -> Path:
    img = render_odds_frame(rows, frame_t=1.0, subtitle=subtitle, volume24hr=volume24hr, pulse=0.0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", quality=95)
    return out_path


def render_odds_frame_sequence(
    rows: list[dict[str, Any]],
    out_dir: Path,
    *,
    duration: float,
    fps: int = 24,
    subtitle: str = "",
    volume24hr: float | None = None,
) -> tuple[list[Path], float]:
    """生成动画帧序列（仅入场动画段，尾部由 ffmpeg 定格延长）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    anim_duration = min(max(duration * 0.78, 10.0), 15.0)
    anim_frames = max(24, int(anim_duration * fps))
    paths: list[Path] = []
    anim_end = 0.72

    for i in range(anim_frames):
        t = i / max(anim_frames - 1, 1)
        if t <= anim_end:
            frame_t = t / anim_end
            pulse = 0.0
        else:
            frame_t = 1.0
            pulse = (t - anim_end) / (1 - anim_end) * 2.5

        img = render_odds_frame(
            rows, frame_t=frame_t, subtitle=subtitle,
            volume24hr=volume24hr, pulse=pulse,
        )
        p = out_dir / f"frame_{i:05d}.png"
        img.save(p, "PNG", optimize=True)
        paths.append(p)

    return paths, anim_duration


def fetch_and_prepare(*, today: str | None = None) -> dict[str, Any]:
    today = today or _today_str()
    event = fetch_raw_event()
    rows = parse_odds(event)
    rows = attach_deltas(rows, today=today)
    snapshot_today(rows, today=today)

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    card_path = SNAPSHOT_DIR / f"{today.replace('-', '')}_odds.png"
    vol = event.get("volume24hr")
    render_odds_card(rows, card_path, subtitle=f"{today} UTC", volume24hr=vol)

    biggest_mover = None
    for r in rows:
        d = r.get("delta")
        if d is not None and d != 0:
            if biggest_mover is None or abs(d) > abs(biggest_mover.get("delta", 0)):
                biggest_mover = r

    return {
        "date": today,
        "event_title": event.get("title") or "World Cup Winner",
        "volume24hr": vol,
        "top": rows,
        "biggest_mover": biggest_mover,
        "card_png": str(card_path),
        "polymarket_url": os.environ.get("POLYMARKET_URL", "https://polymarket.com/event/world-cup-winner"),
    }


def png_to_mp4_preview(png_path: Path, out_path: Path, *, duration: float = 3.0) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(png_path),
        "-vf", "scale=1080:1920:flags=lanczos,fps=30",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-an", str(out_path),
    ], check=True, capture_output=True)
    return out_path
