"""Deterministic public-safe Intelligence conversation card rendering."""
from __future__ import annotations

import html
import io
import json
import textwrap

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1200
HEIGHT = 630
INK = "#070809"
PANEL = "#0c100d"
LINE = "#27352b"
TEXT = "#e3e9e4"
MUTED = "#9fb0a3"
ACCENT = "#3ddc84"
AMBER = "#f4b740"


def _font(size: int, bold: bool = False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int,
              start: int, minimum: int, bold: bool = False):
    for size in range(start, minimum - 1, -2):
        font = _font(size, bold)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum, bold)


def _first(value, key: str):
    if isinstance(value, dict):
        if value.get(key) is not None:
            return value[key]
        for child in value.values():
            found = _first(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first(child, key)
            if found is not None:
                return found
    return None


def card_copy(payload: dict) -> tuple[str, str, str]:
    template = payload.get("template", "material_move")
    insight = payload.get("insight") or {}
    titles = {
        "material_move": "The forecast moved",
        "highest_leverage": "The match that matters most",
        "turning_point": "Season turning point",
        "race_comparison": "The race, in one gap",
        "receipt": "The model receipt",
    }
    title = titles.get(template, "Intelligence receipt")
    primary = "Evidence recorded"
    detail = "Open the verification record for the underlying snapshot."

    if template == "highest_leverage":
        fixture = (insight.get("fixtures") or [{}])[0]
        if fixture:
            primary = f"{fixture.get('home', '')} vs {fixture.get('away', '')}".strip()
            detail = f"{fixture.get('leverage_pp', 0):.1f} percentage-point outcome range"
    elif template == "race_comparison":
        rival = (insight.get("rivals") or [{}])[0]
        if rival:
            primary = f"{payload.get('team', '')} vs {rival.get('team', '')}".strip()
            detail = f"{abs(float(rival.get('gap_pp') or 0)):.1f}pp target-probability gap"
    elif template in {"material_move", "turning_point"}:
        event = (insight.get("events") or [{}])[0]
        if event:
            metric = str(event.get("target_metric") or "forecast").replace("_", " ")
            delta = float(event.get("delta_pp") or 0)
            primary = f"{metric.title()}: {delta:+.1f}pp"
            detail = str(event.get("cause_class") or event.get("event_type") or "evidence-backed update").replace("_", " ")
    elif template == "receipt":
        receipt = (insight.get("receipts") or [{}])[0]
        if receipt:
            primary = str(receipt.get("fixture") or receipt.get("prediction") or "Pre-match forecast locked")
            detail = str(receipt.get("outcome") or receipt.get("forecast") or "Immutable snapshot receipt")
    else:
        delta = _first(insight, "delta_pp")
        if delta is not None:
            primary = f"{float(delta):+.1f} percentage points"
    return title, primary, detail


def render_card_png(payload: dict, verification_url: str) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 8, HEIGHT), fill=ACCENT)
    draw.rectangle((64, 52, WIDTH - 64, HEIGHT - 62), fill=PANEL, outline=LINE, width=2)

    draw.text((98, 84), "ENTENSER  /  INTELLIGENCE RECEIPT",
              font=_font(20, True), fill=ACCENT)
    team = str(payload.get("team") or "Team")
    team_font = _fit_font(draw, team, 1000, 58, 34, True)
    draw.text((98, 132), team, font=team_font, fill=TEXT)

    league = str(payload.get("league") or "")
    generated = str(payload.get("generated") or "")
    draw.text((100, 206), f"{league}  ·  {generated}", font=_font(20), fill=MUTED)
    draw.line((98, 250, WIDTH - 98, 250), fill=LINE, width=2)

    title, primary, detail = card_copy(payload)
    draw.text((98, 286), title.upper(), font=_font(18, True), fill=AMBER)
    primary_font = _fit_font(draw, primary, 1000, 46, 28, True)
    draw.text((98, 326), primary, font=primary_font, fill=TEXT)

    detail_lines = textwrap.wrap(detail, width=70)[:2]
    draw.multiline_text((100, 392), "\n".join(detail_lines), font=_font(22),
                        fill=MUTED, spacing=8)
    snapshot = str(payload.get("snapshot_id") or "")
    draw.text((100, 500), f"Snapshot {snapshot}", font=_font(16), fill=MUTED)
    verify = verification_url.replace("https://", "").replace("http://", "")
    verify_font = _fit_font(draw, verify, 1000, 17, 13)
    draw.text((100, 538), verify, font=verify_font, fill=ACCENT)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_verification_html(payload: dict, image_url: str) -> bytes:
    title, primary, detail = card_copy(payload)
    evidence = payload.get("evidence_ids") or []
    evidence_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in evidence) or "<li>No public evidence reference available.</li>"
    serialized = html.escape(json.dumps(payload, sort_keys=True, indent=2))
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(payload.get("team", "Team"))} intelligence receipt · Entenser</title>
<meta name="robots" content="index,follow"><meta property="og:image" content="{html.escape(image_url)}">
<style>
*{{box-sizing:border-box}}body{{margin:0;background:{INK};color:{TEXT};font:15px Inter,system-ui,sans-serif}}
main{{max-width:920px;margin:0 auto;padding:32px 20px 64px}}header{{border-bottom:1px solid {LINE};padding-bottom:20px}}
.eyebrow{{color:{ACCENT};font:700 12px monospace;text-transform:uppercase}}h1{{font-size:32px;margin:8px 0}}
.receipt{{border-top:2px solid {ACCENT};border-bottom:1px solid {LINE};padding:24px 0;margin:28px 0}}
.receipt h2{{font-size:24px;margin:6px 0}}p,li{{color:{MUTED};line-height:1.55}}img{{width:100%;height:auto;border:1px solid {LINE}}}code{{color:{ACCENT}}}details{{margin-top:24px}}
a{{color:{ACCENT}}}button{{background:{ACCENT};color:#06120b;border:0;border-radius:4px;padding:10px 14px;font-weight:700}}
</style></head><body><main><header><div class="eyebrow">Public intelligence receipt</div>
<h1>{html.escape(payload.get("team", "Team"))}</h1><p>{html.escape(payload.get("league", ""))} · generated {html.escape(payload.get("generated", ""))}</p></header>
<section class="receipt"><div class="eyebrow">{html.escape(title)}</div><h2>{html.escape(primary)}</h2><p>{html.escape(detail)}</p>
<p>Snapshot <code>{html.escape(payload.get("snapshot_id", ""))}</code></p></section>
<img src="{html.escape(image_url)}" width="1200" height="630" alt="{html.escape(title)}">
<h2>Evidence references</h2><ul>{evidence_html}</ul>
<p><a href="https://entenser.com/?league=intel">Open the Intelligence Hub</a></p>
<details><summary>Public-safe record</summary><pre>{serialized}</pre></details></main></body></html>"""
    return page.encode()
