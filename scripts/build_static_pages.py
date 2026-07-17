#!/usr/bin/env python3
"""Generate crawlable static league pages + hub + sitemap.xml (launch plan C2).

Emits, from the same payloads the SPA reads:

  webapp/leagues/<id>/index.html   one standalone landing page per league
  webapp/leagues/index.html        the hub page listing every league
  webapp/sitemap.xml               /, /leagues/, and every league page

Design contract (docs/superpowers/plans/2026-08-17-public-launch.md):
  - stdlib only — this runs inside .github/workflows/deploy.yml on bare
    python3 with no pip install. Do not import pandas/jinja2/requests here.
  - pages are lightweight standalone documents (~15-25 KB), NOT copies of the
    SPA; they are self-canonical and link into /?league=<id> for interaction.
  - generated at deploy time; webapp/leagues/ and webapp/sitemap.xml are
    .gitignore'd — never commit the output.
  - a malformed payload for a registry-live league fails the build (a deploy
    missing its canonical pages is worse than no deploy); placeholder or
    missing payloads are skipped.

Run:  python3 scripts/build_static_pages.py [--out webapp] [--site https://entenser.com]
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Runnable both as `python3 scripts/build_static_pages.py` (deploy.yml) and
# `python3 -m scripts.build_static_pages` (build_all.sh).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import read_js_payload  # noqa: E402

SITE = "https://entenser.com"
E = html.escape

# MLS's flat payload carries no outlook.columns; these mirror outlook.cards.
_MLS_COLS = [("playoff", "Playoff"), ("shield", "Shield"), ("cup", "MLS Cup")]

# Plain-language method note (shared with the About copy, launch plan D3).
_METHOD_NOTE = (
    "Entenser is a market-blind football prediction system: the model never "
    "sees betting odds — probabilities come only from match results, expected "
    "goals, and team-strength ratings. Every forecast is graded in public "
    "after the fact, hits and misses alike. We do not claim to beat the "
    "betting market; we claim to show our work."
)

_DS_NOTE = {
    "results_only": ("Results only — no forward-fixture feed exists for this "
                     "league, so projections are built from played matches "
                     "and there is no upcoming-match list."),
    "historical": ("Archive — the newest season available from this league's "
                   "data source is in the past. This page is a historical "
                   "record, not a live forecast."),
}

_CSS = """
:root{--ink:#070809;--ink1:#0e1013;--ink2:#15181d;--line:#242a33;--txt:#e8ecf1;
--txt2:#aeb6c2;--txt3:#78818f;--green:#3ddc84;--red:#ff6b6b;--mono:ui-monospace,Menlo,monospace}
*{box-sizing:border-box;margin:0}
body{background:var(--ink);color:var(--txt);font:15px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif;padding:0 16px 48px}
main{max-width:860px;margin:0 auto}
a{color:var(--green);text-decoration:none}a:hover{text-decoration:underline}
header{display:flex;align-items:baseline;gap:12px;padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:22px}
header .brand{font-weight:800;letter-spacing:.02em;color:var(--txt);font-size:17px}
header nav{margin-left:auto;font-size:13px;color:var(--txt3)}
h1{font-size:26px;line-height:1.25;margin:4px 0 6px}
h2{font-size:17px;margin:30px 0 10px;color:var(--txt)}
.sub{color:var(--txt2);font-size:13.5px}
.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
border:1px solid var(--line);border-radius:5px;padding:2px 7px;color:var(--txt3);margin-left:6px;vertical-align:2px}
.note{background:var(--ink1);border:1px solid var(--line);border-left:3px solid var(--txt3);
border-radius:6px;padding:10px 14px;font-size:13.5px;color:var(--txt2);margin:14px 0}
.callouts{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
.callout{background:var(--ink1);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:150px}
.callout .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--txt3)}
.callout .v{font-family:var(--mono);font-size:18px;font-weight:700}
.callout .t{font-size:13px;color:var(--txt2)}
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--txt3);text-align:right;
padding:8px 10px;border-bottom:1px solid var(--line);background:var(--ink1)}
th.tm,td.tm{text-align:left}
td{padding:7px 10px;border-bottom:1px solid var(--ink2);text-align:right;font-family:var(--mono);font-size:13px}
td.tm{font-family:inherit;font-weight:600;white-space:nowrap}
tr:last-child td{border-bottom:none}
.fx{border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-top:8px}
.fxrow{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid var(--ink2);flex-wrap:wrap}
.fxrow:last-child{border-bottom:none}
.fxrow .d{font-family:var(--mono);font-size:12px;color:var(--txt3);width:88px;flex:none}
.fxrow .t{font-weight:600;flex:1;min-width:200px}
.fxrow .p{font-family:var(--mono);font-size:12.5px;color:var(--txt2);white-space:nowrap}
.cta{display:inline-block;background:var(--green);color:#06121d;font-weight:700;border-radius:8px;
padding:10px 18px;margin:20px 0 4px}
.cta:hover{text-decoration:none;filter:brightness(1.08)}
.sibs{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.sibs a{border:1px solid var(--line);border-radius:6px;padding:5px 10px;font-size:13px;color:var(--txt2)}
footer{margin-top:36px;padding-top:14px;border-top:1px solid var(--line);font-size:12.5px;color:var(--txt3)}
.grp{margin:22px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--txt3)}
ul.lgs{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:6px}
ul.lgs li a{display:block;border:1px solid var(--line);border-radius:7px;padding:8px 12px;color:var(--txt)}
ul.lgs li .c{color:var(--txt3);font-size:12px;margin-left:6px}
""".strip()


def pct(v) -> str:
    """0–100 float → compact display percentage."""
    if v is None:
        return "–"
    if v >= 99.95:
        return ">99%"
    if 0 < v < 1:
        return "<1%"
    r = round(float(v), 1)
    return f"{r:.0f}%" if r == int(r) else f"{r:.1f}%"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%a %b %-d")
    except ValueError:
        return iso


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _season_label(d: dict) -> str:
    lbl = (d.get("outlook") or {}).get("season_label")
    return str(lbl or d.get("season") or "")


def _columns(d: dict) -> list[tuple[str, str]]:
    """(key, label) probability columns for this payload's standings table."""
    mode = (d.get("outlook") or {}).get("mode")
    if mode == "mls":
        return _MLS_COLS
    return [(c["key"], c.get("col", c.get("label", c["key"])))
            for c in (d.get("outlook") or {}).get("columns", [])]


def _upcoming(d: dict, n: int = 8) -> list[dict]:
    today = _today()
    fx = [g for g in d.get("games") or []
          if not g.get("result") and (g.get("date") or "") >= today]
    fx.sort(key=lambda g: (g.get("date") or "", g.get("id") or 0))
    return fx[:n]


# ── page fragments ────────────────────────────────────────────────────────────

def _head(title: str, desc: str, canonical: str, og_image: str,
          jsonld: dict | None) -> str:
    ld = (f'<script type="application/ld+json">'
          f'{json.dumps(jsonld, separators=(",", ":"))}</script>' if jsonld else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{E(og_image)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#070809">
<link rel="icon" href="/assets/pwa/icon-192.png">
<style>{_CSS}</style>
{ld}
</head>
<body>
<main>
<header><a class="brand" href="/">Entenser</a>
<nav><a href="/leagues/">All leagues</a> · <a href="/?league=about">About</a></nav></header>
"""


def _footer(generated: str) -> str:
    return (f'<footer>Data updated {E(generated or "recently")} · '
            f'rebuilt daily from public match data · '
            f'<a href="/?league=about">methodology</a> · '
            f'<a href="/?league=data-sources">data sources</a> · '
            f'© Entenser</footer>\n</main>\n</body>\n</html>\n')


def _standings_table(d: dict, cols: list[tuple[str, str]], completed: bool) -> str:
    rows = d.get("standings") or []
    if not rows:
        return ""
    if completed:
        heads = "".join(f"<th>{E(h)}</th>" for h in ("GP", "Pts", "GD"))
        body = "".join(
            f'<tr><td>{i + 1}</td><td class="tm">{E(r.get("team", ""))}</td>'
            f'<td>{r.get("gp", "–")}</td><td>{r.get("pts", "–")}</td>'
            f'<td>{r.get("gd", "–")}</td></tr>'
            for i, r in enumerate(
                sorted(rows, key=lambda r: (-(r.get("pts") or 0),
                                            -(r.get("gd") or 0)))))
        return (f'<div class="tblwrap"><table><thead><tr><th>#</th>'
                f'<th class="tm">Club</th>{heads}</tr></thead>'
                f'<tbody>{body}</tbody></table></div>')
    heads = "".join(f"<th>{E(lbl)}</th>" for _, lbl in cols)
    srt = sorted(rows, key=lambda r: (r.get("proj_rank") or 99,
                                      -(r.get("proj_pts") or 0)))
    body = "".join(
        f'<tr><td>{i + 1}</td><td class="tm">{E(r.get("team", ""))}</td>'
        f'<td>{r.get("pts", "–")}</td>'
        f'<td>{r.get("proj_pts", "–")}</td>'
        + "".join(f"<td>{pct(r.get(k))}</td>" for k, _ in cols)
        + "</tr>"
        for i, r in enumerate(srt))
    return (f'<div class="tblwrap"><table><thead><tr><th>#</th>'
            f'<th class="tm">Club</th><th>Pts</th><th>Proj</th>{heads}</tr>'
            f'</thead><tbody>{body}</tbody></table></div>')


def _callouts(d: dict, cols: list[tuple[str, str]]) -> str:
    rows = d.get("standings") or []
    if not rows or not cols:
        return ""
    out = []
    key0, lbl0 = cols[0]
    top = sorted(rows, key=lambda r: -(r.get(key0) or 0))[:3]
    for r in top:
        if (r.get(key0) or 0) <= 0:
            continue
        out.append(f'<div class="callout"><div class="k">{E(lbl0)}</div>'
                   f'<div class="v">{pct(r.get(key0))}</div>'
                   f'<div class="t">{E(r.get("team", ""))}</div></div>')
    rel = next(((k, l) for k, l in cols if k == "releg"), None)
    if rel:
        worst = sorted(rows, key=lambda r: -(r.get("releg") or 0))[:2]
        for r in worst:
            if (r.get("releg") or 0) <= 0:
                continue
            out.append(f'<div class="callout"><div class="k">Relegation</div>'
                       f'<div class="v">{pct(r.get("releg"))}</div>'
                       f'<div class="t">{E(r.get("team", ""))}</div></div>')
    return f'<div class="callouts">{"".join(out)}</div>' if out else ""


def _fixtures(fx: list[dict]) -> str:
    if not fx:
        return ""
    rows = "".join(
        f'<div class="fxrow"><span class="d">{E(_fmt_date(g.get("date")))}</span>'
        f'<span class="t">{E(g.get("home", ""))} vs {E(g.get("away", ""))}</span>'
        f'<span class="p">{pct((g.get("pH") or 0) * 100)} W · '
        f'{pct((g.get("pD") or 0) * 100)} D · '
        f'{pct((g.get("pA") or 0) * 100)} L</span></div>'
        for g in fx)
    return f'<h2>Upcoming matches — win probabilities</h2><div class="fx">{rows}</div>'


def _jsonld(lg: dict, d: dict, canonical: str, fx: list[dict],
            site: str) -> dict:
    name = lg["name"]
    graph: list[dict] = [{
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Entenser",
             "item": f"{site}/"},
            {"@type": "ListItem", "position": 2, "name": "Leagues",
             "item": f"{site}/leagues/"},
            {"@type": "ListItem", "position": 3, "name": name,
             "item": canonical}]},
        {"@type": "Dataset",
         "name": f"{name} season projections and match win probabilities",
         "description": (f"Daily-refreshed {name} title, qualification and "
                         "relegation probabilities plus match win/draw/loss "
                         "probabilities from a market-blind model (no "
                         "bookmaker odds used as inputs)."),
         "url": canonical,
         "dateModified": (d.get("generated") or "")[:10],
         "creator": {"@type": "Organization", "name": "Entenser",
                     "url": f"{site}/"},
         "isAccessibleForFree": True,
         "distribution": [{"@type": "DataDownload",
                           "encodingFormat": "application/javascript",
                           "contentUrl": f"{site}/data/{lg['id']}.js"}]}]
    for g in fx:
        ev = {"@type": "SportsEvent",
              "name": f"{g.get('home')} vs {g.get('away')}",
              "sport": "Soccer",
              "startDate": g.get("ko") or g.get("date"),
              "homeTeam": {"@type": "SportsTeam", "name": g.get("home")},
              "awayTeam": {"@type": "SportsTeam", "name": g.get("away")},
              "organizer": {"@type": "SportsOrganization", "name": name}}
        if g.get("venue"):
            ev["location"] = {"@type": "Place", "name": g["venue"]}
        graph.append(ev)
    return {"@context": "https://schema.org", "@graph": graph}


# ── per-league page ───────────────────────────────────────────────────────────

def league_page(lg: dict, d: dict, registry: list[dict], site: str) -> str:
    lid, name = lg["id"], lg["name"]
    canonical = f"{site}/leagues/{lid}/"
    status = d.get("status")
    mode = (d.get("outlook") or {}).get("mode")
    ds = d.get("data_status") or lg.get("data_status") or "full_forecast"
    season = _season_label(d)
    cols = _columns(d)
    completed = status == "completed"
    knockout = mode == "knockout"
    generated = d.get("generated") or ""
    fx = [] if completed else _upcoming(d)

    # ── title + description ──
    key0, lbl0 = (cols[0] if cols else (None, "Title"))
    rows = d.get("standings") or []
    top2 = sorted(rows, key=lambda r: -(r.get(key0) or 0))[:2] if key0 else []
    if completed:
        title = f"{name} {season} Final Table & Results — Entenser"
        desc = (f"Final {name} {season} standings and results, with the "
                f"season's model forecast record. Updated {generated[:10]}.")
    elif knockout:
        title = f"{name} {season} Forecast & Bracket Odds — Entenser"
        desc = (f"{name} {season} projections: advancement odds and match "
                f"probabilities from a market-blind model. "
                f"Updated {generated[:10]}.")
    else:
        title = f"{name} Predictions {season}: {lbl0} Odds & Projected Table — Entenser"
        odds_bits = ", ".join(f"{r['team']} {pct(r.get(key0))}" for r in top2
                              if r.get(key0))
        desc = (f"{name} {season} forecast: "
                + (f"{odds_bits} {lbl0.lower()} odds, " if odds_bits else "")
                + "full projected table and win/draw/loss probabilities for "
                  f"every match. No bookmaker odds in the model; every "
                  f"forecast graded in public. Updated {generated[:10]}.")

    # ── body ──
    parts = [_head(title, desc, canonical, f"{site}/assets/og/og-image.png",
                   _jsonld(lg, d, canonical, fx, site))]
    badge = {"preseason": "pre-season", "completed": "final",
             "knockout_live": "live bracket"}.get(status, "live")
    parts.append(f'<h1>{E(name)} {E(season)} '
                 f'{"results" if completed else "forecast"}'
                 f'<span class="badge">{badge}</span></h1>')

    sub = []
    if status == "preseason":
        sub.append("Pre-season projection — schedule out, no matches played "
                   "yet; probabilities are statistical priors")
    elif status == "live":
        pct_done = (d.get("league") or {}).get("pct_complete")
        if pct_done is not None:
            sub.append(f"{pct_done}% of the season played")
    elif completed:
        champ = ((d.get("outlook") or {}).get("champion")
                 or (max(rows, key=lambda r: (r.get("pts") or 0))["team"]
                     if rows else None))
        if champ:
            sub.append(f"Champions: {champ}")
    sub.append(f"updated {generated[:10]}")
    parts.append(f'<div class="sub">{E(" · ".join(sub))}</div>')

    if ds in _DS_NOTE:
        parts.append(f'<div class="note">{E(_DS_NOTE[ds])}</div>')
    if d.get("format_approximate"):
        parts.append('<div class="note">This competition uses a split-round '
                     'or playoff format that the model approximates as a '
                     'plain table — details under competition rules below.'
                     '</div>')

    if not completed:
        parts.append(_callouts(d, cols))

    if rows and not knockout:
        parts.append(f'<h2>{"Final table" if completed else "Projected table"}</h2>')
        parts.append(_standings_table(d, cols, completed))
    parts.append(_fixtures(fx))

    rules = (d.get("outlook") or {}).get("rules")
    if rules:
        parts.append(f'<h2>Competition rules</h2>'
                     f'<p class="sub">{E(rules)}</p>')

    parts.append(f'<h2>How these forecasts work</h2>'
                 f'<p class="sub">{E(_METHOD_NOTE)}</p>')
    parts.append(f'<a class="cta" href="/?league={E(lid)}">'
                 f'Open the interactive {E(name)} dashboard →</a>')

    sibs = [x for x in registry
            if x.get("group") == lg.get("group") and x["id"] != lid
            and x.get("_has_page")][:12]
    if sibs:
        parts.append('<h2>More leagues</h2><div class="sibs">'
                     + "".join(f'<a href="/leagues/{E(x["id"])}/">'
                               f'{E(x["name"])}</a>' for x in sibs)
                     + f'<a href="/leagues/">All {len(registry)} leagues</a>'
                       '</div>')
    parts.append(_footer(generated))
    return "".join(parts)


# ── hub page ──────────────────────────────────────────────────────────────────

def hub_page(registry: list[dict], site: str) -> str:
    canonical = f"{site}/leagues/"
    with_pages = [lg for lg in registry if lg.get("_has_page")]
    full = sum(1 for lg in with_pages
               if (lg.get("data_status") or "full_forecast") == "full_forecast")
    title = "Football League Predictions — Title, Playoff & Relegation Odds — Entenser"
    desc = (f"Season forecasts for {len(with_pages)} football competitions "
            f"across six confederations — {full} with full live projections. "
            "Market-blind model, every forecast graded in public.")
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage",
              "name": title, "url": canonical}
    parts = [_head(title, desc, canonical, f"{site}/assets/og/og-image.png",
                   jsonld)]
    parts.append("<h1>Every league we forecast</h1>")
    parts.append(f'<div class="sub">{len(registry)} competitions tracked · '
                 f'{full} with full live forecasts · the rest labeled '
                 f'results-only or archive</div>')
    groups: dict[str, list[dict]] = {}
    for lg in with_pages:
        groups.setdefault(lg.get("group") or "Other", []).append(lg)
    for grp in ["England", "Spain", "Italy", "Germany", "France", "Americas",
                "South America", "Other Europe", "Asia", "Cups"]:
        if grp not in groups:
            continue
        parts.append(f'<div class="grp">{E(grp)}</div><ul class="lgs">')
        for lg in groups.pop(grp):
            note = {"results_only": " <span class='c'>results only</span>",
                    "historical": " <span class='c'>archive</span>"}.get(
                        lg.get("data_status") or "", "")
            tier = (f" <span class='c'>{E(lg['country'])} · tier {lg['tier']}</span>"
                    if lg.get("tier") else "")
            parts.append(f'<li><a href="/leagues/{E(lg["id"])}/">'
                         f'{E(lg["name"])}{tier}{note}</a></li>')
        parts.append("</ul>")
    for grp, lgs in groups.items():   # anything not in the preferred order
        parts.append(f'<div class="grp">{E(grp)}</div><ul class="lgs">')
        parts.extend(f'<li><a href="/leagues/{E(lg["id"])}/">{E(lg["name"])}'
                     f'</a></li>' for lg in lgs)
        parts.append("</ul>")
    parts.append('<a class="cta" href="/">Open the interactive dashboard →</a>')
    parts.append(_footer(_today()))
    return "".join(parts)


# ── weekly recap page ─────────────────────────────────────────────────────────

def weekly_page(w: dict, site: str) -> str:
    """Crawlable /weekly/ recap from webapp/data/weekly.js (launch plan H1)."""
    canonical = f"{site}/weekly/"
    generated = w.get("generated") or ""
    week = w.get("week_label") or "This week"
    headline = w.get("headline") or "This week across world football"
    title = f"{week}: Football Model Recap — Movers, Races & Misses — Entenser"
    desc = (f"{headline}. Biggest title/relegation odds swings, the closest "
            "races, and this week's high-confidence model misses — from a "
            "market-blind model graded in public.")[:300]
    jsonld = {"@context": "https://schema.org", "@type": "Article",
              "headline": headline, "url": canonical,
              "datePublished": generated[:10], "dateModified": generated[:10],
              "author": {"@type": "Organization", "name": "Entenser"},
              "publisher": {"@type": "Organization", "name": "Entenser"}}
    parts = [_head(title, desc, canonical, f"{site}/assets/og/movers.png", jsonld)]
    parts.append(f'<h1>{E(week)}</h1>')
    parts.append(f'<div class="sub">{E(headline)} · updated {E(generated[:10])}</div>')

    mv = w.get("movers") or {}
    risers, fallers = mv.get("risers") or [], mv.get("fallers") or []
    if risers or fallers:
        parts.append('<h2>Biggest race movement this week</h2>')

        def mv_rows(rows, arrow):
            return "".join(
                f'<div class="fxrow"><span class="t">{E(r["team"])} '
                f'<span class="sub">{E(r["league_name"])} · {E(r["metric"])}</span></span>'
                f'<span class="p">{r["prev"]:.0f}% {arrow} {r["now"]:.0f}% '
                f'({"+" if r["delta"] >= 0 else ""}{r["delta"]:.1f})</span></div>'
                for r in rows)
        parts.append('<div class="fx">' + mv_rows(risers, "→") + mv_rows(fallers, "→")
                     + '</div>')

    fragile = w.get("fragile_races") or []
    if fragile:
        parts.append('<h2>Closest races right now</h2><div class="fx">')
        for r in fragile:
            cont = ", ".join(r.get("contenders") or [])
            parts.append(
                f'<div class="fxrow"><span class="t">{E(r["league_name"])} '
                f'{E(r["label"])}</span><span class="p">{E(r["leader"])} '
                f'{r["leader_prob"]:.0f}%{f" · chased by {E(cont)}" if cont else ""}'
                '</span></div>')
        parts.append('</div>')

    dis = w.get("disagreements") or []
    if dis:
        parts.append('<h2>Where the model disagrees with the market</h2><div class="fx">')
        for r in dis:
            parts.append(
                f'<div class="fxrow"><span class="t">{E(r["home"])} vs {E(r["away"])} '
                f'<span class="sub">{E(r["league_name"])}</span></span>'
                f'<span class="p">model {r.get("model_pct")}% vs market '
                f'{r.get("market_pct")}% · {r["edge_pct"]:+.1f}pp</span></div>')
        parts.append('</div>')

    rc = w.get("receipt") or {}
    misses = rc.get("misses") or []
    if rc.get("n_calls"):
        parts.append('<h2>The receipt — how our high-confidence calls did</h2>')
        parts.append(f'<p class="sub">Of {rc["n_calls"]} calls where the model '
                     f'was at least 60% on an outcome this week, {rc["n_hits"]} '
                     f'hit ({rc.get("hit_rate")}%). We publish the misses too:</p>')
        if misses:
            parts.append('<div class="fx">')
            for m in misses:
                parts.append(
                    f'<div class="fxrow"><span class="t">{E(m["home"])} '
                    f'{E(m["score"])} {E(m["away"])} '
                    f'<span class="sub">{E(m["league_name"])} · {E(m["date"])}</span>'
                    f'</span><span class="p">had {E(m["fav"] or "favorite")} at '
                    f'{m["fav_pct"]:.0f}% · {E(m["outcome"])}</span></div>')
            parts.append('</div>')

    parts.append(f'<h2>How this works</h2><p class="sub">{E(_METHOD_NOTE)}</p>')
    parts.append('<a class="cta" href="/">Open the interactive dashboard →</a>')
    parts.append('<div class="sibs"><a href="/leagues/">All leagues</a>'
                 '<a href="/?league=about">About the model</a></div>')
    parts.append(_footer(generated))
    return "".join(parts)


# ── World Cup → domestic on-ramp (launch plan H2) ──────────────────────────────

# US-fan leagues the post-tournament cohort is most likely to pick up next.
_WC_ONRAMP = [("mls", "the league most new US fans follow first"),
              ("nwsl", "the top US women's league"),
              ("liga-mx", "Mexico's top flight — the most-watched league on US TV"),
              ("leagues-cup", "MLS vs Liga MX, head to head"),
              ("usl-championship", "US second division"),
              ("canadian-pl", "Canada's top flight")]


def _lead_line(d: dict) -> str | None:
    """Best current headline for a league: its top title/playoff contender."""
    cols = _columns(d)
    rows = d.get("standings") or []
    if not cols or not rows:
        return None
    key, label = cols[0]
    top = max(rows, key=lambda r: (r.get(key) or 0))
    if not top.get(key):
        return None
    return f"{top['team']} lead the {label.lower()} race at {pct(top.get(key))}"


def world_cup_page(payloads: dict, names: dict, site: str) -> str:
    canonical = f"{site}/after-the-world-cup/"
    title = "What to Watch After the World Cup — MLS, NWSL & Liga MX Forecasts — Entenser"
    desc = ("Just finished the World Cup and want more? Live title, playoff "
            "and relegation forecasts for MLS, NWSL, Liga MX and more — "
            "market-blind, graded in public.")
    jsonld = {"@context": "https://schema.org", "@type": "WebPage",
              "name": title, "url": canonical}
    parts = [_head(title, desc, canonical, f"{site}/assets/og/og-image.png",
                   jsonld)]
    parts.append("<h1>Just finished the World Cup? Here's what to follow next.</h1>")
    parts.append('<div class="sub">The tournament is over, but the club '
                 'season is always running. These are the races we forecast '
                 'that a new US fan is most likely to pick up — updated daily, '
                 'no betting odds in the model.</div>')
    parts.append('<div class="fx">')
    for lid, blurb in _WC_ONRAMP:
        d = payloads.get(lid)
        if not d:
            continue
        lead = _lead_line(d) or "season in progress"
        parts.append(
            f'<div class="fxrow"><span class="t">'
            f'<a href="/leagues/{E(lid)}/">{E(names.get(lid, lid))}</a> '
            f'<span class="sub">{E(blurb)}</span></span>'
            f'<span class="p">{E(lead)}</span></div>')
    parts.append('</div>')
    parts.append('<a class="cta" href="/leagues/">See all leagues →</a>')
    parts.append(f'<h2>How these forecasts work</h2><p class="sub">{E(_METHOD_NOTE)}</p>')
    parts.append(_footer(_today()))
    return "".join(parts)


# ── open data: per-league CSV + /data/ index (launch plan H3) ──────────────────

def league_csv(d: dict, cols: list[tuple[str, str]]) -> str:
    """Projected table as CSV: one row per team, probabilities as columns."""
    rows = d.get("standings") or []
    buf = io.StringIO()
    fields = ["rank", "team", "played", "points", "proj_points"] + [k for k, _ in cols]
    w = csv.writer(buf)
    w.writerow(fields)
    srt = sorted(rows, key=lambda r: (r.get("proj_rank") or 99,
                                      -(r.get("proj_pts") or 0)))
    for i, r in enumerate(srt, 1):
        w.writerow([i, r.get("team", ""), r.get("gp", ""), r.get("pts", ""),
                    r.get("proj_pts", "")] + [r.get(k, "") for k, _ in cols])
    return buf.getvalue()


def data_page(exported: list[dict], site: str) -> str:
    """The /open-data/ index — attribution terms + one download link per league.

    Deliberately NOT /data/ — webapp/data/ holds the SPA's *.js payloads, and
    an index.html there would both shadow the directory listing and (in tests,
    where data/ is symlinked) write back into the real repo.
    """
    canonical = f"{site}/open-data/"
    title = "Open Data — Football Projection Downloads (CSV) — Entenser"
    desc = ("Download Entenser's title, qualification and relegation "
            "projections as CSV, free with attribution. Market-blind model, "
            f"{len(exported)} competitions, refreshed daily.")
    jsonld = {"@context": "https://schema.org", "@type": "DataCatalog",
              "name": "Entenser football projections", "url": canonical,
              "dataset": [{"@type": "Dataset", "name": e["name"],
                           "distribution": {"@type": "DataDownload",
                                            "encodingFormat": "text/csv",
                                            "contentUrl": e["url"]}}
                          for e in exported]}
    parts = [_head(title, desc, canonical, f"{site}/assets/og/og-image.png",
                   jsonld)]
    parts.append("<h1>Open data</h1>")
    parts.append('<div class="sub">Our projections, free to use with '
                 'attribution. Refreshed daily.</div>')
    parts.append('<div class="note">Please credit <b>Entenser '
                 '(entenser.com)</b> and link back when you use these files. '
                 'The model is market-blind — no bookmaker odds are used as '
                 'inputs — so the numbers are independent of the betting '
                 'market. Columns: projected rank, club, played, points, '
                 'projected points, then one probability column per outcome '
                 '(percentages).</div>')
    parts.append('<h2>Per-league downloads</h2><ul class="lgs">')
    for e in exported:
        parts.append(f'<li><a href="{E(e["path"])}">{E(e["name"])} '
                     f'<span class="c">CSV</span></a></li>')
    parts.append("</ul>")
    parts.append('<a class="cta" href="/leagues/">Browse the forecasts →</a>')
    parts.append(_footer(_today()))
    return "".join(parts)


# ── sitemap ───────────────────────────────────────────────────────────────────

def sitemap(entries: list[tuple[str, str]]) -> str:
    body = "".join(f"<url><loc>{E(loc)}</loc>"
                   + (f"<lastmod>{E(lm)}</lastmod>" if lm else "")
                   + "</url>"
                   for loc, lm in entries)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'{body}</urlset>\n')


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="webapp", help="webapp root to write into")
    ap.add_argument("--site", default=SITE, help="canonical site origin")
    args = ap.parse_args(argv)
    out = Path(args.out)
    site = args.site.rstrip("/")

    registry = read_js_payload(out / "leagues.js")
    if not registry:
        print(f"FATAL: cannot read {out / 'leagues.js'}", file=sys.stderr)
        return 1
    names = {lg["id"]: lg["name"] for lg in registry}

    pages: list[tuple[str, str]] = []   # (loc, lastmod)
    payloads: dict[str, dict] = {}
    failures: list[str] = []
    for lg in registry:
        d = read_js_payload(out / "data" / f"{lg['id']}.js")
        if d is None:
            if lg.get("status") == "live":
                failures.append(f"{lg['id']}: payload missing/unparseable")
            continue
        if d.get("status") == "placeholder":
            continue
        payloads[lg["id"]] = d
        lg["_has_page"] = True

    if failures:
        for f in failures:
            print(f"FATAL: {f}", file=sys.stderr)
        return 1

    max_lastmod = ""
    exported: list[dict] = []
    (out / "exports").mkdir(parents=True, exist_ok=True)
    for lg in registry:
        if not lg.get("_has_page"):
            continue
        d = payloads[lg["id"]]
        page_dir = out / "leagues" / lg["id"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(
            league_page(lg, d, registry, site), encoding="utf-8")
        lastmod = (d.get("generated") or "")[:10]
        max_lastmod = max(max_lastmod, lastmod)
        pages.append((f"{site}/leagues/{lg['id']}/", lastmod))
        # Open-data CSV (launch plan H3) — table leagues with a projected table.
        cols = _columns(d)
        if (d.get("standings") and cols
                and (d.get("outlook") or {}).get("mode") != "knockout"):
            (out / "exports" / f"{lg['id']}.csv").write_text(
                league_csv(d, cols), encoding="utf-8")
            exported.append({"name": lg["name"],
                             "path": f"/exports/{lg['id']}.csv",
                             "url": f"{site}/exports/{lg['id']}.csv"})

    (out / "leagues").mkdir(parents=True, exist_ok=True)
    (out / "leagues" / "index.html").write_text(hub_page(registry, site),
                                                encoding="utf-8")
    (out / "open-data").mkdir(parents=True, exist_ok=True)
    (out / "open-data" / "index.html").write_text(data_page(exported, site),
                                                  encoding="utf-8")

    # Weekly recap page (launch plan H1) — optional: only when weekly.js exists.
    extra: list[tuple[str, str]] = []
    w = read_js_payload(out / "data" / "weekly.js")
    if w and w.get("status") == "ok":
        (out / "weekly").mkdir(parents=True, exist_ok=True)
        (out / "weekly" / "index.html").write_text(weekly_page(w, site),
                                                   encoding="utf-8")
        extra.append((f"{site}/weekly/", (w.get("generated") or "")[:10]))
    if exported:
        extra.append((f"{site}/open-data/", max_lastmod))

    # World Cup → domestic on-ramp (launch plan H2) — needs the US leagues.
    if any(lid in payloads for lid, _ in _WC_ONRAMP):
        (out / "after-the-world-cup").mkdir(parents=True, exist_ok=True)
        (out / "after-the-world-cup" / "index.html").write_text(
            world_cup_page(payloads, names, site), encoding="utf-8")
        extra.append((f"{site}/after-the-world-cup/", max_lastmod))

    entries = ([(f"{site}/", max_lastmod),
                (f"{site}/leagues/", max_lastmod)]
               + extra + sorted(pages))
    (out / "sitemap.xml").write_text(sitemap(entries), encoding="utf-8")
    print(f"wrote {len(pages)} league pages + hub"
          f"{' + weekly' if w and w.get('status') == 'ok' else ''}"
          f" + {len(exported)} CSV exports + open-data + sitemap "
          f"({len(entries)} URLs, lastmod {max_lastmod})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
