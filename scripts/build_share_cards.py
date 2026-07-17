#!/usr/bin/env python3
"""Generate social share cards (Open Graph + posting assets) as 1200x630 PNGs.

Renders on-brand HTML to PNG via Playwright (already a dev dependency; reuses the
site's Google Fonts and palette for full fidelity). Outputs:

  webapp/assets/og/og-image.png      main branded OG card, wired into index.html
                                     <head>. Intentionally evergreen — social
                                     scrapers cache aggressively, so it carries the
                                     brand + slowly-changing coverage stats, not
                                     volatile per-day probabilities.
  webapp/assets/og/title-race.png    marquee title race (Premier League)
  webapp/assets/og/relegation.png    marquee relegation race (Premier League)
  webapp/assets/og/movers.png        biggest model projection movers (cross-league)

Each card renders independently so one failure never blocks the others. Safe to
re-run; idempotent. Wired into scripts/build_all.sh after the payloads build.

Usage:
    python scripts/build_share_cards.py [--only og|title|releg|movers]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WEBAPP = REPO / "webapp"
OUT_DIR = WEBAPP / "assets" / "og"

ACCENT = "#3ddc84"
INK0 = "#070809"
INK2 = "#0c100d"
LINE = "#18211a"
TXT1 = "#e3e9e4"
TXT2 = "#9fb0a3"
TXT3 = "#54665b"

W, H = 1200, 630


# ── data loading ──────────────────────────────────────────────────────────────
def _load_payload(name: str) -> dict | None:
    from scripts.payload_utils import read_js_payload
    return read_js_payload(WEBAPP / "data" / name)


def _b64_asset(rel: str) -> str:
    p = WEBAPP / rel
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _live_league_count() -> int:
    try:
        from scripts.fetch_league_teams import REGISTRY
        return sum(1 for r in REGISTRY if r[4] == "live")
    except Exception:
        return 0


# ── shared HTML shell ─────────────────────────────────────────────────────────
_FONTS = ("https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800;900"
          "&family=Inter:wght@400;500;600;700&family=Spline+Sans+Mono:wght@600;700&display=swap")


def _shell(body: str, pad: int = 64) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="{_FONTS}" rel="stylesheet">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px}}
  body{{background:
      radial-gradient(1200px 600px at 80% -10%, #0f1712 0%, {INK0} 60%),
      {INK0};
    color:{TXT1};font-family:'Inter',system-ui,sans-serif;
    padding:{pad}px;position:relative;overflow:hidden}}
  .accent-bar{{position:absolute;left:0;top:0;bottom:0;width:8px;background:{ACCENT}}}
  .brand{{display:flex;align-items:center;gap:14px;margin-bottom:8px}}
  .brand img{{height:44px}}
  .brand .nm{{font-family:'Archivo';font-weight:900;font-size:30px;letter-spacing:-.02em}}
  .eyebrow{{font-family:'Spline Sans Mono';font-weight:600;font-size:15px;
    letter-spacing:.14em;text-transform:uppercase;color:{ACCENT}}}
  h1{{font-family:'Archivo';font-weight:800;letter-spacing:-.02em;line-height:1.03}}
  .foot{{position:absolute;left:{pad}px;bottom:{pad}px;font-family:'Spline Sans Mono';
    font-weight:600;font-size:16px;color:{TXT3};letter-spacing:.02em}}
  .foot b{{color:{TXT2}}}
  .rows{{display:flex;flex-direction:column;gap:14px;margin-top:34px}}
  .row{{display:grid;grid-template-columns:230px 1fr 96px;align-items:center;gap:16px}}
  .row .tm{{font-family:'Archivo';font-weight:700;font-size:22px;white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis}}
  .track{{height:16px;background:{INK2};border:1px solid {LINE};border-radius:999px;overflow:hidden}}
  .fill{{height:100%;background:{ACCENT};border-radius:999px}}
  .fill.warn{{background:#e2b53d}}
  .fill.bad{{background:#e25f4f}}
  .val{{font-family:'Spline Sans Mono';font-weight:700;font-size:22px;text-align:right}}
  .delta.up{{color:{ACCENT}}} .delta.dn{{color:#e25f4f}}
</style></head><body><div class="accent-bar"></div>{body}</body></html>"""


def _brand_row(lockup_uri: str) -> str:
    if lockup_uri:
        return f'<div class="brand"><img src="{lockup_uri}" alt="Entenser"></div>'
    return '<div class="brand"><span class="nm">Entenser</span></div>'


# ── card templates ────────────────────────────────────────────────────────────
def card_og(lockup_uri: str) -> str:
    n = _live_league_count()
    coverage = f"{n} leagues · 5 continental competitions" if n else "Global league coverage"
    body = f"""
    {_brand_row(lockup_uri)}
    <div class="eyebrow" style="margin-top:26px">Market-blind football probabilities</div>
    <h1 style="font-size:60px;margin-top:14px;max-width:980px">Explained, and audited.</h1>
    <p style="color:{TXT2};font-size:24px;line-height:1.4;margin-top:20px;max-width:900px">
      Track league races, compare model odds to the market, and see when the model is
      stable enough to trust.</p>
    <div class="foot"><b>{coverage}</b> · updated daily · entenser.com</div>"""
    return _shell(body)


def _bar_rows(rows: list[tuple[str, float, str]]) -> str:
    out = []
    for name, pct, cls in rows:
        pct = max(0.0, min(100.0, pct))
        out.append(
            f'<div class="row"><div class="tm">{name}</div>'
            f'<div class="track"><div class="fill {cls}" style="width:{pct:.0f}%"></div></div>'
            f'<div class="val">{pct:.0f}%</div></div>')
    return '<div class="rows">' + "".join(out) + "</div>"


def card_race(lockup_uri: str, title: str, eyebrow: str, rows, foot: str) -> str:
    body = f"""
    {_brand_row(lockup_uri)}
    <div class="eyebrow" style="margin-top:22px">{eyebrow}</div>
    <h1 style="font-size:40px;margin-top:10px">{title}</h1>
    {_bar_rows(rows)}
    <div class="foot">{foot}</div>"""
    return _shell(body)


def card_movers(lockup_uri: str, movers: list[dict], labels: dict) -> str:
    out = []
    for m in movers[:5]:
        d = m.get("delta", 0.0)
        arrow = "▲" if d > 0 else "▼"
        cls = "up" if d > 0 else "dn"
        metric = labels.get(m.get("metric"), m.get("metric", ""))
        out.append(
            f'<div class="row" style="grid-template-columns:1fr 150px 150px">'
            f'<div class="tm">{m.get("team","")}</div>'
            f'<div class="val" style="color:{TXT2};font-size:16px;text-align:left">{metric}</div>'
            f'<div class="val delta {cls}">{arrow} {abs(d):.0f} pts</div></div>')
    rows = '<div class="rows">' + "".join(out) + "</div>"
    body = f"""
    {_brand_row(lockup_uri)}
    <div class="eyebrow" style="margin-top:22px">Biggest projection movers</div>
    <h1 style="font-size:40px;margin-top:10px">Where the model changed its mind</h1>
    {rows}
    <div class="foot">Season-outcome probability shifts · entenser.com</div>"""
    return _shell(body)


# ── rendering ─────────────────────────────────────────────────────────────────
def _render(page, html: str, out: Path) -> None:
    page.set_content(html, wait_until="networkidle")
    try:
        page.evaluate("document.fonts && document.fonts.ready")
        page.wait_for_timeout(350)  # let webfonts paint
    except Exception:
        pass
    out.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": W, "height": H})
    print(f"  [OK] {out.relative_to(REPO)}")


def _epl_rows(kind: str):
    d = _load_payload("epl.js")
    if not d:
        return None
    st = d.get("standings", [])
    if kind == "title":
        top = sorted(st, key=lambda r: -(r.get("title") or 0))[:5]
        return [(r["team"], r.get("title") or 0.0, "") for r in top]
    bot = sorted(st, key=lambda r: -(r.get("releg") or 0))[:5]
    return [(r["team"], r.get("releg") or 0.0,
             "bad" if (r.get("releg") or 0) >= 40 else "warn") for r in bot]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["og", "title", "releg", "movers"], default=None)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed — skipping share cards", file=sys.stderr)
        return 0

    lockup = _b64_asset("assets/branding/entenser-lockup-light.png")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1)

        jobs = []
        if args.only in (None, "og"):
            jobs.append(("og-image.png", lambda: card_og(lockup)))
        if args.only in (None, "title"):
            tr = _epl_rows("title")
            if tr:
                jobs.append(("title-race.png", lambda tr=tr: card_race(
                    lockup, "2026-27 Premier League title race",
                    "Preseason priors · market-blind", tr,
                    "Preseason priors — no matches played yet · entenser.com")))
        if args.only in (None, "releg"):
            rr = _epl_rows("releg")
            if rr:
                jobs.append(("relegation.png", lambda rr=rr: card_race(
                    lockup, "2026-27 Premier League relegation risk",
                    "Preseason priors · market-blind", rr,
                    "Preseason priors — skill grows after ~25% of the season · entenser.com")))
        if args.only in (None, "movers"):
            mv = _load_payload("movers.js")
            if mv and mv.get("movers"):
                jobs.append(("movers.png", lambda mv=mv: card_movers(
                    lockup, mv["movers"], mv.get("metric_labels", {}))))

        for fname, builder in jobs:
            try:
                _render(page, builder(), OUT_DIR / fname)
            except Exception as e:  # one card failing never blocks the rest
                ok = False
                print(f"  [WARN] {fname}: {e}", file=sys.stderr)

        browser.close()

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
