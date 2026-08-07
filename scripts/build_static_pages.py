#!/usr/bin/env python3
"""Generate crawlable static league/club pages + hub + sitemap.xml (launch plan C2).

Emits, from the same payloads the SPA reads:

  webapp/leagues/<id>/index.html   one standalone landing page per league
  webapp/leagues/<id>/clubs/<slug>/index.html
                                    one standalone forecast page per club
  webapp/leagues/index.html        the hub page listing every league
  webapp/sitemap.xml               /, /leagues/, every league and club page

Design contract (docs/superpowers/plans/2026-08-17-public-launch.md):
  - stdlib only — this runs inside .github/workflows/deploy.yml on bare
    python3 with no pip install. Do not import pandas/jinja2/requests here.
  - pages are lightweight standalone documents, NOT copies of the SPA; they
    are self-canonical and link into /?league=<id> for interaction.
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
import email.utils
import html
import io
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

# Runnable both as `python3 scripts/build_static_pages.py` (deploy.yml) and
# `python3 -m scripts.build_static_pages` (build_all.sh).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import read_js_payload  # noqa: E402

SITE = "https://entenser.com"
E = html.escape


def _script_json(value: object) -> str:
    """Serialize JSON safely for an inline script element."""
    return (
        json.dumps(value, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


# MLS's flat payload carries no outlook.columns; these mirror outlook.cards.
_MLS_COLS = [("playoff", "Playoff"), ("shield", "Shield"), ("cup", "MLS Cup")]

# Plain-language method note (shared with the About copy, launch plan D3).
_METHOD_NOTE = (
    "Entenser estimates football outcomes from match results, expected goals, "
    "and team-strength ratings. Every forecast is graded in public after the "
    "fact, with hits and misses shown together."
)

_LOCAL_NAMES = {
    "segunda": ["Segunda División", "LaLiga Hypermotion"],
    "bundesliga-2": ["2. Bundesliga"],
    "serie-b": ["Serie B"],
    "ligue-2": ["Ligue 2"],
    "eerste-divisie": ["Keuken Kampioen Divisie"],
    "sweden-allsvenskan": ["Allsvenskan"],
    "norway-eliteserien": ["Eliteserien"],
    "denmark-superliga": ["Superligaen"],
}

_DS_NOTE = {
    "results_only": ("Results only — no forward-fixture feed exists for this "
                     "league, so projections are built from played matches "
                     "and there is no upcoming-match list."),
    "historical": ("Archive — the newest season available from this league's "
                   "data source is in the past. This page is a historical "
                   "record, not a live forecast."),
}

# GA4 tag for the crawlable static pages. These are separate documents from the
# SPA, so they need their own gtag load — organic search lands here first and
# would otherwise be invisible in GA4. Same guard as webapp/index.html: live
# HTTPS entenser.com only, so local builds and previews never emit events.
# Keep the ID in sync with ANALYTICS.measurementId in webapp/index.html.
_GA_ID = "G-GVSLY1KBHQ"
_GA_TAG = f"""<script>
if(location.protocol==='https:'&&location.hostname==='entenser.com'){{
  window.dataLayer=window.dataLayer||[];
  window.gtag=window.gtag||function(){{window.dataLayer.push(arguments);}};
  gtag('js',new Date()); gtag('config','{_GA_ID}');
  var s=document.createElement('script'); s.async=true;
  s.src='https://www.googletagmanager.com/gtag/js?id={_GA_ID}';
  document.head.appendChild(s);
}}
</script>"""

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
.club-hd{display:flex;align-items:center;gap:14px;margin:4px 0 6px}
.club-hd h1{margin:0}
.club-crest{width:54px;height:54px;object-fit:contain;flex:none}
.club-summary{font-size:15px;color:var(--txt2);margin:16px 0;max-width:760px}
.result{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;
border-radius:4px;font:700 11px var(--mono);flex:none}
.result.w{background:#173a29;color:var(--green)}.result.d{background:#2c3037;color:var(--txt2)}
.result.l{background:#401f23;color:var(--red)}
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
.cw-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.cw-chips a{border:1px solid var(--line2,var(--line));border-radius:999px;
padding:8px 14px;font-size:13.5px;color:var(--txt1);background:var(--ink1);min-height:44px;
display:inline-flex;align-items:center}
.cw-chips a:hover{text-decoration:none;border-color:var(--green);color:var(--green)}
.club-watch-top{margin:10px 0 4px}
.club-watch-top a{display:inline-flex;align-items:center;min-height:44px;
border:1px solid var(--green);border-radius:8px;padding:8px 14px;font-size:14px;
font-weight:600;color:var(--green)}
.club-watch-top a:hover{text-decoration:none;background:var(--ink1)}
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


def pctH(v) -> str:
    """pct() for direct interpolation into HTML text — escapes the `<1%` case."""
    return E(pct(v))


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%a %b %-d")
    except ValueError:
        return iso


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def club_slug(name: str | None) -> str:
    """Stable, readable URL segment for one competition-scoped club."""
    ascii_name = unicodedata.normalize(
        "NFKD", str(name or "").strip()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "club"


def _club_groups(d: dict) -> list[tuple[str, dict, list[str]]]:
    """Group harmless spelling aliases that collapse to one slug.

    A source currently emits both "St. Patrick's Athletic" and
    "St Patrick's Athletic". A single competition-scoped canonical is more
    useful than two near-duplicate pages. The row with the most played matches
    is treated as the representative forecast.
    """
    grouped: dict[str, list[dict]] = {}
    for row in d.get("standings") or []:
        if row.get("team"):
            grouped.setdefault(club_slug(row["team"]), []).append(row)

    # Knockout payloads can carry scheduled participants that are not present
    # in the current-stage standings. They still need real landing pages because
    # the league fixture list links to them.
    game_only: dict[str, dict] = {}
    for game in d.get("games") or []:
        for side, logo_key, id_key, color_key in (
            ("home", "hlogo", "home_id", "hcolor"),
            ("away", "alogo", "away_id", "acolor"),
        ):
            name = game.get(side)
            if not name:
                continue
            slug = club_slug(name)
            candidate = {
                "team": name,
                "team_id": game.get(id_key),
                "logo": game.get(logo_key),
                "color": game.get(color_key),
            }
            existing = game_only.get(slug)
            if existing is None or (
                    not existing.get("logo") and candidate.get("logo")):
                game_only[slug] = candidate
    for slug, row in game_only.items():
        grouped.setdefault(slug, [row])

    out = []
    for slug, rows in grouped.items():
        primary = max(
            rows,
            key=lambda row: (
                row.get("gp") or 0,
                row.get("pts") or 0,
                row.get("proj_pts") or 0,
                sum(value is not None for value in row.values()),
            ),
        )
        aliases = [str(row["team"]) for row in rows]
        out.append((slug, primary, aliases))
    return sorted(out, key=lambda item: item[1]["team"].casefold())


def _club_href(league_id: str, team: str | None) -> str:
    return f"/leagues/{league_id}/clubs/{club_slug(team)}/"


def _club_link(league_id: str, team: str | None) -> str:
    name = str(team or "")
    return f'<a href="{E(_club_href(league_id, name))}">{E(name)}</a>'


def _public_copy(value: str | None) -> str:
    """Remove trading vocabulary from crawlable acquisition surfaces."""
    text = str(value or "")
    replacements = (
        (r"\bbookmakers?\b", "external benchmarks"),
        (r"\bbetting\b", "forecast"),
        (r"\bodds\b", "probabilities"),
        (r"\bmarket\b", "consensus"),
        (r"\bedge\b", "difference"),
        (r"\bkelly\b", "allocation"),
        (r"\bstaking?\b", "allocation"),
        (r"\bbets?\b", "forecasts"),
        (r"\broi\b", "evaluation return"),
        (r"\bclv\b", "closing comparison"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


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


# What topping the final table actually wins. Leagues whose championship is
# decided in a playoff/final must NOT be captioned "Champions: <table leader>" —
# Cavalry FC led the 2024 CPL table but Forge won the final. Keyed on the
# payload's first probability column, which already encodes what the table decides.
_TABLE_PRIZE = {
    "premiers": "Best regular-season record",
    "liguilla": "Top of the table",
    "shield": "Supporters' Shield",
    "playoff": "Top of the table",
    "playoffs": "Top of the table",
    "finals": "Premiers",
    "promo": "Champions",
    "title": "Champions",
}


def _top_row_label(d: dict, cols: list[tuple[str, str]]) -> str:
    if (d.get("outlook") or {}).get("title_by_playoff"):
        # `title` here ranks an aggregate table the championship is not drawn from.
        return "Top of the table"
    return _TABLE_PRIZE.get(cols[0][0], "Top of the table") if cols else "Top of the table"


def _upcoming(d: dict, n: int = 8) -> list[dict]:
    today = _today()
    fx = [g for g in d.get("games") or []
          if not g.get("result") and (g.get("date") or "") >= today]
    fx.sort(key=lambda g: (g.get("date") or "", g.get("id") or 0))
    return fx[:n]


def _forecast_state_label(d: dict) -> str:
    """Customer-facing data state without implying every route is live."""
    data_status = d.get("data_status")
    status = d.get("status")
    if status == "completed":
        return "final"
    if data_status == "historical":
        return "archive"
    if data_status == "results_only":
        return "results only"
    if status == "preseason":
        return "pre-season"
    if d.get("no_fixture_feed"):
        return "fixtures limited"
    return "full forecast"


# ── page fragments ────────────────────────────────────────────────────────────

def _head(title: str, desc: str, canonical: str, og_image: str,
          jsonld: dict | None) -> str:
    ld = (f'<script type="application/ld+json">'
          f'{_script_json(jsonld)}</script>' if jsonld else "")
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
<link rel="alternate" type="application/rss+xml" title="Entenser football forecasts" href="/forecast-feed.xml">
<meta name="theme-color" content="#070809">
<link rel="icon" href="/assets/pwa/icon-192.png">
<style>{_CSS}</style>
{_GA_TAG}
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
            f'<a href="/global-elo/">Global ELO</a> · '
            f'<a href="/leagues/">all leagues</a> · '
            f'<a href="/?league=data-sources">data sources</a> · '
            f'© Entenser</footer>\n</main>\n</body>\n</html>\n')


def _standings_table(d: dict, cols: list[tuple[str, str]], completed: bool,
                     league_id: str) -> str:
    rows = d.get("standings") or []
    if not rows:
        return ""
    if completed:
        heads = "".join(f"<th>{E(h)}</th>" for h in ("GP", "Pts", "GD"))
        body = "".join(
            f'<tr><td>{i + 1}</td><td class="tm">'
            f'{_club_link(league_id, r.get("team"))}</td>'
            f'<td>{r.get("gp", "–")}</td><td>{r.get("pts", "–")}</td>'
            f'<td>{r.get("gd", "–")}</td></tr>'
            for i, r in enumerate(
                sorted(rows, key=lambda r: (-(r.get("pts") or 0),
                                            -(r.get("gd") or 0)))))
        return (f'<div class="tblwrap"><table><thead><tr><th>#</th>'
                f'<th class="tm">Club</th>{heads}</tr></thead>'
                f'<tbody>{body}</tbody></table></div>')
    heads = "".join(f"<th>{E(lbl)}</th>" for _, lbl in cols)

    def _rank_sort(rs):
        return sorted(rs, key=lambda r: (r.get("proj_rank") or 99,
                                         -(r.get("proj_pts") or 0)))

    def _body(rs):
        return "".join(
            f'<tr><td>{i + 1}</td><td class="tm">'
            f'{_club_link(league_id, r.get("team"))}</td>'
            f'<td>{r.get("pts", "–")}</td>'
            f'<td>{r.get("proj_pts", "–")}</td>'
            + "".join(f"<td>{pctH(r.get(k))}</td>" for k, _ in cols)
            + "</tr>"
            for i, r in enumerate(_rank_sort(rs)))

    def _tbl(rs):
        return (f'<div class="tblwrap"><table><thead><tr><th>#</th>'
                f'<th class="tm">Club</th><th>Pts</th><th>Proj</th>{heads}</tr>'
                f'</thead><tbody>{_body(rs)}</tbody></table></div>')

    # Conference leagues (MLS) qualify per conference, so a single merged table
    # shows playoff odds that jump around relative to projected points. Split it.
    confs = [c for c in dict.fromkeys(r.get("conf") for r in rows)
             if isinstance(c, str) and c]
    if len(confs) > 1:
        return "".join(f'<h3 class="grp">{E(c)}</h3>'
                       + _tbl([r for r in rows if r.get("conf") == c])
                       for c in confs)
    return _tbl(rows)


def _callouts(d: dict, cols: list[tuple[str, str]], league_id: str) -> str:
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
                   f'<div class="v">{pctH(r.get(key0))}</div>'
                   f'<div class="t">{_club_link(league_id, r.get("team"))}'
                   f'</div></div>')
    rel = next(((k, l) for k, l in cols if k == "releg"), None)
    if rel:
        worst = sorted(rows, key=lambda r: -(r.get("releg") or 0))[:2]
        for r in worst:
            if (r.get("releg") or 0) <= 0:
                continue
            out.append(f'<div class="callout"><div class="k">Relegation</div>'
                       f'<div class="v">{pctH(r.get("releg"))}</div>'
                       f'<div class="t">{_club_link(league_id, r.get("team"))}'
                       f'</div></div>')
    return f'<div class="callouts">{"".join(out)}</div>' if out else ""


def _fixtures(fx: list[dict], league_id: str) -> str:
    if not fx:
        return ""
    rows = "".join(
        f'<div class="fxrow"><span class="d">{E(_fmt_date(g.get("date")))}</span>'
        f'<span class="t">{_club_link(league_id, g.get("home"))} vs '
        f'{_club_link(league_id, g.get("away"))}</span>'
        f'<span class="p">{pctH((g.get("pH") or 0) * 100)} W · '
        f'{pctH((g.get("pD") or 0) * 100)} D · '
        f'{pctH((g.get("pA") or 0) * 100)} L</span></div>'
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
                         "probabilities from an independently graded model."),
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

def _club_watch_row(lg: dict, rows: list[dict], lid: str, limit: int = 6) -> str:
    """Club-selection path into Club Watch from a league page.

    A league page has no single club, so the honest call to action is *pick a
    club*, not "track this". Each chip carries the same
    ?league=intel&intelLeague=…&team=…&track=1 intent the club pages already
    use, so there is exactly one URL shape for tracking across the site.

    Copy obeys docs/paid-claim-matrix.md: the free boundary is stated, and
    nothing here promises alerts or email — delivery is still shadow-only.
    """
    picks = [r for r in rows if r.get("team")][:limit]
    if not picks:
        return ""
    chips = []
    for r in picks:
        team = r["team"]
        q = urlencode({
            "league": "intel",
            "intelLeague": lid,
            "team": r.get("team_id") or team,
            "track": "1",
        })
        chips.append(f'<a class="cw-chip" href="/?{E(q)}">{E(team)}</a>')
    props = _script_json({
        "competition_id": lid,
        "competition_name": lg.get("name") or lid,
        "country": lg.get("country") or "",
        "surface": "league_page",
    })
    return (
        '<h2>Follow a club through the season</h2>'
        '<p class="sub">Current forecasts for every club stay free. '
        'Entenser Club Watch follows one club\'s season and explains what '
        'changed and what the next match can change.</p>'
        f'<div class="cw-chips" id="cwChips">{"".join(chips)}</div>'
        "<script>document.getElementById('cwChips').addEventListener('click',"
        "function(e){var a=e.target.closest('a');if(!a)return;"
        "if(location.protocol==='https:'&&location.hostname==='entenser.com'"
        f"&&window.gtag){{gtag('event','track_club',Object.assign({props},"
        "{club_name:a.textContent,transport_type:'beacon'}));}}});</script>"
    )


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
        title = f"{name} {season} Forecast & Bracket Probabilities — Entenser"
        desc = (f"{name} {season} projections: advancement and match "
                f"probabilities from an independently graded model. "
                f"Updated {generated[:10]}.")
    else:
        title = f"{name} Predictions {season}: {lbl0} Probabilities & Projected Table — Entenser"
        probability_bits = ", ".join(
            f"{r['team']} {pct(r.get(key0))}" for r in top2 if r.get(key0))
        desc = (f"{name} {season} forecast: "
                + (f"{probability_bits} {lbl0.lower()} probabilities, "
                   if probability_bits else "")
                + "full projected table and win/draw/loss probabilities for "
                  f"every match. Every forecast is graded in public. "
                  f"Updated {generated[:10]}.")

    # ── body ──
    parts = [_head(title, desc, canonical, f"{site}/assets/og/og-image.png",
                   _jsonld(lg, d, canonical, fx, site))]
    badge = _forecast_state_label(d)
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
        champ = (d.get("outlook") or {}).get("champion")
        if champ:
            sub.append(f"Champions: {champ}")
        elif rows:
            top = max(rows, key=lambda r: (r.get("pts") or 0))["team"]
            sub.append(f"{_top_row_label(d, cols)}: {top}")
    sub.append(f"updated {generated[:10]}")
    aliases = _LOCAL_NAMES.get(lid) or []
    if aliases:
        sub.append("also known as " + " / ".join(aliases))
    parts.append(f'<div class="sub">{E(" · ".join(sub))}</div>')

    if ds in _DS_NOTE:
        parts.append(f'<div class="note">{E(_DS_NOTE[ds])}</div>')
    if d.get("no_fixture_feed"):
        parts.append('<div class="note">The new season has started but no '
                     'fixture list has been published for it yet, so there is '
                     'nothing left for the model to simulate — the probability '
                     'columns below just restate the matches already played, '
                     'not a forecast. They become meaningful once the schedule '
                     'appears.</div>')
    if d.get("format_approximate"):
        parts.append('<div class="note">This competition uses a split-round '
                     'or playoff format that the model approximates as a '
                     'plain table — details under competition rules below.'
                     '</div>')

    if not completed:
        parts.append(_callouts(d, cols, lid))

    if rows and not knockout:
        parts.append(f'<h2>{"Final table" if completed else "Projected table"}</h2>')
        parts.append(_standings_table(d, cols, completed, lid))
    parts.append(_fixtures(fx, lid))

    rules = (d.get("outlook") or {}).get("rules")
    if rules:
        parts.append(f'<h2>Competition rules</h2>'
                     f'<p class="sub">{E(_public_copy(rules))}</p>')

    parts.append(_club_watch_row(lg, rows, lid))

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


# ── per-club page ─────────────────────────────────────────────────────────────

def _club_jsonld(lg: dict, d: dict, row: dict, canonical: str,
                 site: str) -> dict:
    league_url = f"{site}/leagues/{lg['id']}/"
    team = str(row["team"]).strip()
    sports_team = {
        "@type": "SportsTeam",
        "name": team,
        "sport": "Soccer",
        "url": canonical,
        "memberOf": {
            "@type": "SportsOrganization",
            "name": lg["name"],
            "url": league_url,
        },
    }
    if row.get("logo"):
        sports_team["logo"] = row["logo"]
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Entenser",
                     "item": f"{site}/"},
                    {"@type": "ListItem", "position": 2, "name": "Leagues",
                     "item": f"{site}/leagues/"},
                    {"@type": "ListItem", "position": 3, "name": lg["name"],
                     "item": league_url},
                    {"@type": "ListItem", "position": 4, "name": team,
                     "item": canonical},
                ],
            },
            sports_team,
            {
                "@type": "Dataset",
                "name": f"{team} {lg['name']} forecast",
                "description": (
                    f"Daily-refreshed {team} season outlook, table projection "
                    f"and match probabilities in {lg['name']}."
                ),
                "url": canonical,
                "dateModified": (d.get("generated") or "")[:10],
                "creator": {
                    "@type": "Organization",
                    "name": "Entenser",
                    "url": f"{site}/",
                },
                "isAccessibleForFree": True,
            },
        ],
    }


def _club_games(d: dict, slug: str) -> tuple[list[dict], list[dict]]:
    games = [
        game for game in d.get("games") or []
        if slug in {club_slug(game.get("home")), club_slug(game.get("away"))}
    ]
    played = sorted(
        (game for game in games if game.get("result")),
        key=lambda game: game.get("date") or "",
        reverse=True,
    )[:5]
    upcoming = sorted(
        (game for game in games
         if not game.get("result") and (game.get("date") or "") >= _today()),
        key=lambda game: (game.get("date") or "", game.get("id") or 0),
    )[:5]
    return played, upcoming


def _club_projected_position(d: dict, row: dict) -> tuple[float | None, int, str]:
    """Expected rank plus the relevant field size and optional conference."""
    if row.get("proj_rank") is not None:
        return (
            float(row["proj_rank"]),
            (d.get("outlook") or {}).get("n_teams")
            or len(d.get("standings") or []),
            "",
        )
    conference = row.get("conf") if isinstance(row.get("conf"), str) else ""
    peers = [
        candidate for candidate in d.get("standings") or []
        if not conference or candidate.get("conf") == conference
    ]
    if not peers or row.get("proj_pts") is None:
        return None, len(peers), conference
    peers.sort(key=lambda candidate: (
        -(candidate.get("proj_pts") or 0),
        -(candidate.get("pts") or 0),
        candidate.get("team") or "",
    ))
    slug = club_slug(row.get("team"))
    for index, candidate in enumerate(peers, 1):
        if club_slug(candidate.get("team")) == slug:
            return float(index), len(peers), conference
    return None, len(peers), conference


def _club_match_rows(games: list[dict], slug: str, league_id: str,
                     completed: bool) -> str:
    rows = []
    for game in games:
        home = club_slug(game.get("home")) == slug
        opponent = game.get("away") if home else game.get("home")
        venue = game.get("venue")
        context = f' · {E(venue)}' if venue else ""
        if completed:
            hg, ag = game.get("hg"), game.get("ag")
            if hg is not None and ag is not None:
                club_goals, opp_goals = (hg, ag) if home else (ag, hg)
                outcome = "W" if club_goals > opp_goals else (
                    "D" if club_goals == opp_goals else "L")
                detail = f"{club_goals}–{opp_goals}"
            else:
                result = game.get("result")
                outcome = "D" if result == "D" else (
                    "W" if (result == "H") == home else "L")
                detail = outcome
            rows.append(
                f'<div class="fxrow"><span class="result {outcome.lower()}">'
                f'{outcome}</span><span class="d">{E(_fmt_date(game.get("date")))}</span>'
                f'<span class="t">{"vs" if home else "at"} '
                f'{_club_link(league_id, opponent)}{context}</span>'
                f'<span class="p">{E(detail)}</span></div>'
            )
        else:
            win = game.get("pH") if home else game.get("pA")
            draw = game.get("pD")
            loss = game.get("pA") if home else game.get("pH")
            rows.append(
                f'<div class="fxrow"><span class="d">'
                f'{E(_fmt_date(game.get("date")))}</span>'
                f'<span class="t">{"vs" if home else "at"} '
                f'{_club_link(league_id, opponent)}{context}</span>'
                f'<span class="p">{pctH((win or 0) * 100)} W · '
                f'{pctH((draw or 0) * 100)} D · '
                f'{pctH((loss or 0) * 100)} L</span></div>'
            )
    return "".join(rows)


def _club_summary(lg: dict, d: dict, row: dict,
                  cols: list[tuple[str, str]]) -> str:
    team = str(row["team"]).strip()
    league = lg["name"]
    completed = d.get("status") == "completed"
    bits = []
    if completed:
        bits.append(
            f"{team} finished with {row.get('pts', '–')} points from "
            f"{row.get('gp', '–')} matches in {league}.")
    else:
        projected_rank, _, conference = _club_projected_position(d, row)
        if projected_rank is not None:
            rank_label = (
                f"{projected_rank:.1f}" if projected_rank % 1 else
                f"{int(projected_rank)}")
            bits.append(
                f"{team} are projected to finish {rank_label}"
                f"{f' in the {conference}' if conference else ''} in {league}")
            if row.get("proj_pts") is not None:
                bits[-1] += f" with {float(row['proj_pts']):.1f} points."
            else:
                bits[-1] += "."
        else:
            bits.append(f"Current {team} projections for {league}.")
    probabilities = [
        f"{pct(row.get(key))} {label.lower()}"
        for key, label in cols if row.get(key) is not None
    ][:3]
    if probabilities and not completed:
        bits.append("The current model outlook is " + ", ".join(probabilities) + ".")
    bits.append("Forecasts update with new results and are graded in public.")
    return " ".join(bits)


def club_page(lg: dict, d: dict, row: dict, aliases: list[str],
              site: str) -> str:
    lid, league = lg["id"], lg["name"]
    team = str(row["team"]).strip()
    slug = club_slug(team)
    canonical = f"{site}/leagues/{lid}/clubs/{slug}/"
    season = _season_label(d)
    completed = d.get("status") == "completed"
    generated = d.get("generated") or ""
    cols = _columns(d)
    played, upcoming = _club_games(d, slug)

    if completed:
        title = f"{team} {season} Results & Final {league} Position — Entenser"
        desc = (
            f"{team} {season} {league} results, final position and model "
            f"forecast record. Updated {generated[:10]}."
        )
    else:
        title = f"{team} Predictions {season}: {league} Forecast — Entenser"
        headline = next(
            (f"{pct(row.get(key))} {label.lower()} probability"
             for key, label in cols if row.get(key) is not None),
            "season projection",
        )
        detail = (
            "projected finish, points, strength rating and upcoming match "
            "probabilities" if row.get("proj_rank") is not None
            or row.get("proj_pts") is not None else
            "competition outlook and match win/draw/loss probabilities"
        )
        desc = (f"{team} {season} forecast in {league}: {headline}, {detail}. "
                f"Updated {generated[:10]}.")

    parts = [_head(
        title, desc, canonical, f"{site}/assets/og/og-image.png",
        _club_jsonld(lg, d, row, canonical, site),
    )]
    analytics_props = {
        "club_id": row.get("team_id") or team,
        "club_name": team,
        "competition_id": lid,
        "competition_name": league,
        "country": lg.get("country") or "",
        "surface": "club_page",
        "data_state": _forecast_state_label(d),
    }
    safe_analytics = _script_json(analytics_props)
    parts.append(
        "<script>if(location.protocol==='https:'&&"
        "location.hostname==='entenser.com'&&window.gtag){"
        f"gtag('event','club_page_view',{safe_analytics});"
        "}</script>"
    )
    crest = (
        f'<img class="club-crest" src="{E(row["logo"])}" '
        f'alt="{E(team)} crest">' if row.get("logo") else ""
    )
    badge = _forecast_state_label(d)
    parts.append(
        f'<div class="club-hd">{crest}<div><h1>{E(team)} forecast'
        f'<span class="badge">{badge}</span></h1>'
        f'<div class="sub"><a href="/leagues/{E(lid)}/">{E(league)}</a>'
        f' · {E(season)} · updated {E(generated[:10])}</div></div></div>'
    )
    parts.append(f'<p class="club-summary">{E(_club_summary(lg, d, row, cols))}</p>')
    # A Club Watch path above the fold, not only after every table. FotMob puts
    # Follow above the data; ours sat below ~260 words of it. Same intent URL as
    # the footer CTA so there is one tracking shape, distinct id so both can
    # carry their own handler.
    _top_watch_q = urlencode({
        "league": "intel", "intelLeague": lid,
        "team": row.get("team_id") or team, "track": "1",
    })
    parts.append(
        f'<p class="club-watch-top"><a id="clubWatchTop" href="/?{E(_top_watch_q)}">'
        f'Track {E(team)} with Club Watch →</a></p>'
    )
    parts.append(
        "<script>document.getElementById('clubWatchTop').addEventListener("
        "'click',function(){if(location.protocol==='https:'&&"
        "location.hostname==='entenser.com'&&window.gtag){"
        f"gtag('event','track_club',Object.assign({safe_analytics},"
        "{placement:'above_fold',transport_type:'beacon'}));}});</script>"
    )

    metrics = []
    if row.get("pts") is not None:
        metrics.append(("Current", f"{row.get('pts')} pts",
                        f"{row.get('gp', '–')} matches"))
    projected_rank, field_size, conference = _club_projected_position(d, row)
    if projected_rank is not None:
        rank_label = (
            f"{projected_rank:.1f}" if projected_rank % 1 else
            f"{int(projected_rank)}")
        metrics.append((
            "Expected finish",
            f"#{rank_label}",
            f"of {field_size}{f' · {conference}' if conference else ''}",
        ))
    if row.get("proj_pts") is not None and not completed:
        metrics.append(("Projected points", f"{float(row['proj_pts']):.1f}", season))
    rating = row.get("global_elo")
    if rating is None:
        rating = row.get("elo")
    if rating is not None:
        # Called "Crossbar" 2026-08-01 to 2026-08-06, then renamed Global ELO
        # (owner: the coined name did not tell a reader what the number was).
        # The payload field was `global_elo` throughout; the label now matches it.
        metrics.append(("Global ELO", f"{float(rating):.0f}", "cross-league strength"))
    for key, label in cols:
        if row.get(key) is not None:
            metrics.append((label, pct(row.get(key)), "season probability"))
    if metrics:
        parts.append('<div class="callouts">' + "".join(
            f'<div class="callout"><div class="k">{E(label)}</div>'
            f'<div class="v">{E(value)}</div><div class="t">{E(note)}</div></div>'
            for label, value, note in metrics
        ) + "</div>")
        if row.get("global_elo") is not None:
            parts.append(
                f'<p class="sub">Global ELO puts {E(team)} on the same strength scale as every '
                f'other club we forecast — <a href="/global-elo/">how the scale works</a>.</p>')

    if upcoming:
        parts.append("<h2>Upcoming matches — win probabilities</h2><div class=\"fx\">")
        parts.append(_club_match_rows(upcoming, slug, lid, False))
        parts.append("</div>")
    if played:
        parts.append("<h2>Recent results</h2><div class=\"fx\">")
        parts.append(_club_match_rows(played, slug, lid, True))
        parts.append("</div>")

    if len(aliases) > 1:
        parts.append(
            '<div class="note">Source naming variants consolidated on this '
            f'page: {E(" / ".join(alias.strip() for alias in aliases))}.</div>'
        )

    peers = [
        (peer_slug, peer)
        for peer_slug, peer, _ in _club_groups(d) if peer_slug != slug
    ]
    peers.sort(key=lambda item: (
        item[1].get("proj_rank") or 999,
        -(item[1].get("pts") or 0),
        item[1]["team"],
    ))
    if peers:
        parts.append('<h2>More clubs in ' + E(league) + '</h2><div class="sibs">')
        parts.extend(
            f'<a href="/leagues/{E(lid)}/clubs/{E(peer_slug)}/">'
            f'{E(peer["team"].strip())}</a>'
            for peer_slug, peer in peers[:12]
        )
        parts.append(f'<a href="/leagues/{E(lid)}/">Full {E(league)} forecast</a></div>')

    watch_query = urlencode({
        "league": "intel",
        "intelLeague": lid,
        "team": row.get("team_id") or team,
        "track": "1",
    })
    parts.append(
        f'<a class="cta" id="clubWatchCTA" href="/?{E(watch_query)}">'
        f'Track {E(team)} with Club Watch →</a>'
    )
    parts.append(
        "<script>document.getElementById('clubWatchCTA').addEventListener("
        "'click',function(){if(location.protocol==='https:'&&"
        "location.hostname==='entenser.com'&&window.gtag){"
        f"gtag('event','track_club',Object.assign({safe_analytics},"
        "{transport_type:'beacon'}));}});</script>"
    )
    query = urlencode({"league": lid, "team": team})
    parts.append(
        f'<p><a href="/?{E(query)}">Open the free interactive {E(team)} dashboard →</a></p>'
    )
    parts.append(f'<h2>How these forecasts work</h2>'
                 f'<p class="sub">{E(_METHOD_NOTE)}</p>')
    parts.append(_footer(generated))
    return "".join(parts)


# ── hub page ──────────────────────────────────────────────────────────────────

def hub_page(registry: list[dict], site: str) -> str:
    canonical = f"{site}/leagues/"
    with_pages = [lg for lg in registry if lg.get("_has_page")]
    full = sum(1 for lg in with_pages
               if (lg.get("data_status") or "full_forecast") == "full_forecast")
    title = "Football League Predictions — Title, Playoff & Relegation Probabilities — Entenser"
    desc = (f"Season forecasts for {len(with_pages)} football competitions "
            f"across six confederations — {full} with full live projections. "
            "Independent model, every forecast graded in public.")
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
                "South America", "Other Europe", "Asia", "Africa", "Cups"]:
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

def weekly_page(w: dict, site: str, path: str = "weekly/",
                archive_links: list[tuple[str, str]] | None = None) -> str:
    """Crawlable weekly recap (launch plan H1). `path` is the page's directory
    under the site root ("weekly/" for the latest, "weekly/<date>/" for an
    archived one, roadmap 1.5); `archive_links` renders a "Past weeks" nav."""
    canonical = f"{site}/{path}"
    generated = w.get("generated") or ""
    week = w.get("week_label") or "This week"
    headline = _public_copy(
        w.get("headline") or "This week across world football")
    title = f"{week}: Football Forecast Recap — Movers, Races & Misses — Entenser"
    desc = (f"{headline}. Biggest title/relegation probability shifts, the closest "
            "races, and this week's high-confidence model misses — from a "
            "forecast model graded in public.")[:300]
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

    if archive_links:
        parts.append('<h2>Past weeks</h2><div class="fx">')
        for url, date in archive_links:
            parts.append(f'<div class="fxrow"><span class="t">'
                         f'<a href="{url}">Week of {E(date)}</a></span></div>')
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
            "independently graded in public.")
    jsonld = {"@context": "https://schema.org", "@type": "WebPage",
              "name": title, "url": canonical}
    parts = [_head(title, desc, canonical, f"{site}/assets/og/og-image.png",
                   jsonld)]
    parts.append("<h1>Just finished the World Cup? Here's what to follow next.</h1>")
    parts.append('<div class="sub">The tournament is over, but the club '
                 'season is always running. These are the races we forecast '
                 'that a new US fan is most likely to pick up — updated daily, '
                 'with every forecast graded after the fact.</div>')
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
    # MLS-style payloads qualify per conference; without this column the
    # probability columns are unreadable in a flat merged file.
    has_conf = any(isinstance(r.get("conf"), str) and r["conf"] for r in rows)
    fields = (["rank", "team"] + (["conference"] if has_conf else [])
              + ["played", "points", "proj_points"] + [k for k, _ in cols])
    w = csv.writer(buf)
    w.writerow(fields)

    def _grp(r):
        return (r.get("conf") or "") if has_conf else ""

    srt = sorted(rows, key=lambda r: (_grp(r), r.get("proj_rank") or 99,
                                      -(r.get("proj_pts") or 0)))
    rank = {}
    for r in srt:
        grp = _grp(r)
        rank[grp] = i = rank.get(grp, 0) + 1  # rank is within-conference
        w.writerow([i, r.get("team", "")]
                   + ([r.get("conf", "")] if has_conf else [])
                   + [r.get("gp", ""), r.get("pts", ""), r.get("proj_pts", "")]
                   + [r.get(k, "") for k, _ in cols])
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
            "projections as CSV, free with attribution. Independently graded model, "
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
                 'Columns: projected rank, club, played, points, '
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


# ── European forecast acquisition surface ────────────────────────────────────

_EUROPE_FORECAST_GROUPS = [
    ("UK football pyramid", [
        "epl", "championship", "league-one", "league-two", "national-league",
        "scottish-prem", "scottish-champ", "scottish-league-one",
        "scottish-league-two",
    ]),
    ("Netherlands and the Nordics", [
        "eredivisie", "eerste-divisie", "sweden-allsvenskan",
        "norway-eliteserien", "denmark-superliga",
    ]),
    ("Germany", ["bundesliga", "bundesliga-2"]),
    ("Spain and Italy", ["la-liga", "segunda", "serie-a", "serie-b"]),
]


def europe_forecast_page(payloads: dict, names: dict, site: str) -> str:
    canonical = f"{site}/football-forecasts/"
    covered = sum(
        league_id in payloads
        for _, league_ids in _EUROPE_FORECAST_GROUPS for league_id in league_ids)
    title = "Football Forecasts Beyond the Big Five — Entenser"
    desc = (
        f"Independently graded title, promotion and relegation forecasts for "
        f"{covered} European competitions, from the Premier League to the "
        f"National League, Eerste Divisie and Nordic leagues.")
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": desc,
        "url": canonical,
    }
    parts = [_head(
        title, desc, canonical, f"{site}/assets/og/og-image.png", jsonld)]
    parts.append("<h1>Football forecasts beyond the usual five leagues</h1>")
    parts.append(
        '<div class="sub">Title races, promotion fights and relegation danger '
        'across the full English pyramid and under-covered European leagues. '
        'Every forecast is updated from match data and graded after the fact.</div>')
    parts.append('<div class="callouts">'
                 f'<div class="callout"><div class="k">European coverage</div>'
                 f'<div class="v">{covered}</div><div class="t">competitions on this page</div></div>'
                 '<div class="callout"><div class="k">Public record</div>'
                 '<div class="v">Every week</div><div class="t">hits and misses together</div></div>'
                 '</div>')
    for group, league_ids in _EUROPE_FORECAST_GROUPS:
        rows = []
        for league_id in league_ids:
            payload = payloads.get(league_id)
            if not payload:
                continue
            aliases = _LOCAL_NAMES.get(league_id) or []
            note = (" · " + " / ".join(aliases)) if aliases else ""
            lead = _lead_line(payload) or "current season forecast"
            rows.append(
                f'<div class="fxrow"><span class="t"><a href="/leagues/{E(league_id)}/">'
                f'{E(names.get(league_id, league_id))}</a>'
                f'<span class="sub">{E(note.lstrip(" ·"))}</span></span>'
                f'<span class="p">{E(lead)}</span></div>')
        if rows:
            parts.append(f'<h2>{E(group)}</h2><div class="fx">'
                         + "".join(rows) + "</div>")
    parts.append(f'<h2>How these forecasts work</h2>'
                 f'<p class="sub">{E(_METHOD_NOTE)}</p>')
    parts.append('<a class="cta" href="/leagues/">Browse all competitions →</a>')
    parts.append(_footer(_today()))
    return "".join(parts)


# ── betting-free first-party RSS ─────────────────────────────────────────────

def forecast_rss(recaps: list[tuple[str, dict]], site: str) -> str:
    items = []
    for path, recap in recaps[:20]:
        headline = _public_copy(
            recap.get("headline") or recap.get("week_label")
            or "This week across world football")
        generated = recap.get("generated") or ""
        try:
            parsed = datetime.fromisoformat(
                generated.replace(" UTC", "+00:00"))
        except ValueError:
            parsed = datetime.now(timezone.utc)
        link = f"{site}/{path}"
        summary = (
            f"{headline}. The closest league races and this week's "
            "high-confidence forecast record.")
        items.append(
            "<item>"
            f"<title>{E(headline)}</title>"
            f"<link>{E(link)}</link><guid>{E(link)}</guid>"
            f"<pubDate>{email.utils.format_datetime(parsed)}</pubDate>"
            f"<description>{E(summary)}</description>"
            "</item>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        '<title>Entenser football forecasts</title>'
        f'<link>{E(site)}/football-forecasts/</link>'
        '<description>Independently graded football forecasts, league races, '
        'and weekly model accountability.</description>'
        + "".join(items) + "</channel></rss>\n"
    )


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

# ── /global-elo/ — the cross-league strength scale (P6) ───────────────────────
# Shipped as "Crossbar" on 2026-08-01, renamed Global ELO on 2026-08-06: a coined
# word made the reader learn a name before they could read a number, and the
# internal field had always been `global_elo` anyway. /crossbar/ still resolves
# (see crossbar_redirect_page). It names a *scale*, never an accuracy claim —
# every sentence here has to survive docs/paid-claim-matrix.md.
#
# Comparison rows are read from the live payloads rather than written down, so
# this page cannot drift from what the rest of the site publishes.
_GLOBAL_ELO_SHOWCASE = [
    "epl", "brazil-serie-a", "eredivisie", "championship",
    "norway-eliteserien", "argentina-primera", "liga-mx", "mls", "japan-j1",
]
_GLOBAL_ELO_QUALITY_COPY = {
    "tier_bridge": "measured against a league it shares promotion with",
    "fitted": "fitted from continental matches this league actually played",
    "confederation_anchor": "anchored on its confederation's results",
    "calibrated_prior": "set from a published coefficient, not yet fitted",
    "confederation_prior": "set from a confederation prior, not yet fitted",
    "estimated_prior": "an estimate pending more continental evidence",
    "suspended_estimate": "frozen, with no qualifying continental match since 2022",
}


def _global_elo_rows(payloads: dict, registry: list[dict]) -> list[dict]:
    names = {lg["id"]: lg.get("name") or lg["id"] for lg in registry}
    rows = []
    for lid in _GLOBAL_ELO_SHOWCASE:
        d = payloads.get(lid)
        if not d:
            continue
        vals = [(s.get("team"), s.get("global_elo"))
                for s in (d.get("standings") or [])
                if s.get("global_elo") is not None and s.get("team")]
        if not vals:
            continue
        vals.sort(key=lambda x: -x[1])
        ordered = sorted(v for _, v in vals)
        rows.append({
            "league": names.get(lid, lid), "top_team": vals[0][0],
            "top": vals[0][1], "median": ordered[len(ordered) // 2],
            "quality": (d.get("elo_scale") or {}).get("quality") or "",
        })
    # Sorted by the scale itself. Showcase order is editorial; presenting it
    # unsorted would undercut the one thing the table is meant to show.
    rows.sort(key=lambda r: -r["top"])
    return rows


def crossbar_redirect_page(site: str) -> str:
    """Keep the retired /crossbar/ URL alive, pointing at /global-elo/.

    The scale was called Crossbar between 2026-08-01 and 2026-08-06, and in that
    window the URL shipped in every league-page footer, every club page, the
    sitemap and the RSS feed. GitHub Pages serves this site, so there is no
    server-side redirect to configure — the 301 has to be a page. It carries a
    canonical to the new URL so the indexed one consolidates rather than
    competing, and it is deliberately NOT in the sitemap: a sitemap should list
    destinations, not forwarding addresses.
    """
    target = f"{site}/global-elo/"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>Global ELO — Entenser</title>\n'
        f'<link rel="canonical" href="{target}">\n'
        '<meta name="robots" content="noindex, follow">\n'
        f'<meta http-equiv="refresh" content="0; url=/global-elo/">\n'
        '<style>body{background:#070809;color:#e8ecf1;font:15px/1.55 -apple-system,'
        "'Segoe UI',Roboto,sans-serif;padding:48px 16px;text-align:center}"
        'a{color:#3ddc84}</style>\n</head>\n<body>\n'
        '<p>Crossbar is now called <a href="/global-elo/">Global ELO</a>.</p>\n'
        '<script>location.replace("/global-elo/");</script>\n'
        '</body>\n</html>\n')


def global_elo_page(payloads: dict, registry: list[dict], site: str) -> str:
    canonical = f"{site}/global-elo/"
    rows = _global_elo_rows(payloads, registry)
    everything = [s.get("global_elo") for d in payloads.values()
                  for s in (d.get("standings") or [])
                  if s.get("global_elo") is not None]
    n_clubs = len(everything)
    n_leagues = sum(1 for d in payloads.values()
                    if any(s.get("global_elo") is not None
                           for s in (d.get("standings") or [])))
    lo, hi = (min(everything), max(everything)) if everything else (0, 0)
    quality_counts: dict[str, int] = {}
    for d in payloads.values():
        q = (d.get("elo_scale") or {}).get("quality")
        if q:
            quality_counts[q] = quality_counts.get(q, 0) + 1
    generated = max((d.get("generated") or "") for d in payloads.values()) if payloads else ""

    title = "Global ELO — one strength scale across every league we forecast — Entenser"
    desc = (f"Global ELO puts {n_clubs:,} clubs from {n_leagues} competitions on a single "
            "comparable strength scale, so a Championship side and a Brasileirão side can be "
            "read against each other. Built without bookmaker odds.")
    jsonld = {"@context": "https://schema.org", "@type": "DefinedTerm",
              "name": "Global ELO", "url": canonical,
              "description": ("Entenser's shared cross-league club strength scale. A club's "
                              "domestic rating plus a league offset, so clubs in different "
                              "competitions sit on one axis."),
              "inDefinedTermSet": {"@type": "DefinedTermSet",
                                   "name": "Entenser football forecasting",
                                   "url": f"{site}/"}}
    p = [_head(title, desc, canonical, f"{site}/assets/og/og-image.png", jsonld)]
    p.append("<h1>Global ELO</h1>")
    p.append('<div class="sub">One strength scale across every league we forecast.</div>')
    p.append(
        "<p><b>Global ELO is a single number for how strong a club is, on a scale that means the "
        "same thing in every competition.</b> Bayern and a Norwegian champion and an MLS side all "
        "sit on the same axis, so you can read them against each other instead of guessing how two "
        "leagues compare.</p>")
    p.append(
        f'<div class="note">Right now Global ELO covers <b>{n_clubs:,} clubs</b> across '
        f'<b>{n_leagues} competitions</b>, running from about <b>{lo:,}</b> to <b>{hi:,}</b>. '
        f'Higher is stronger. Updated {E(generated[:10])}.</div>')

    if rows:
        p.append("<h2>How to read it</h2>")
        p.append("<p>The strongest club in each competition, and that competition's midpoint. "
                 "The gaps between leagues are the point.</p>")
        p.append('<div class="tblwrap"><table><thead><tr><th>Competition</th>'
                 '<th>Strongest club</th><th>Global ELO</th>'
                 '<th>League midpoint</th></tr></thead><tbody>')
        for r in rows:
            p.append(f'<tr><td class="tm">{E(r["league"])}</td>'
                     f'<td class="tm">{E(r["top_team"])}</td>'
                     f'<td>{r["top"]:,}</td>'
                     f'<td>{r["median"]:,}</td></tr>')
        p.append("</tbody></table></div>")
        p.append(
            '<p class="sub">Read a few rows against each other and the scale starts doing work: '
            'the top of a second tier can sit level with the top of a first tier somewhere else, '
            'and a dominant club in a smaller league can outrate most of a bigger one.</p>')

    p.append("<h2>What Global ELO is not</h2>")
    p.append(
        "<ul>"
        "<li><b>Not a form table.</b> It moves with results, but it is a measure of strength over "
        "time, not of who is hot this month.</li>"
        "<li><b>Not built from bookmaker odds.</b> No betting line is an input to anything "
        "Entenser publishes. That is the whole point of the model, and it is why Global ELO can "
        "disagree with the market.</li>"
        "<li><b>Not a betting rating.</b> It is not a price, not an edge, and not advice.</li>"
        "<li><b>Not a trophy count.</b> History only reaches Global ELO through results the model "
        "has actually seen.</li>"
        "</ul>")

    p.append("<h2>How it is built</h2>")
    p.append(
        "<p>Every club has a domestic rating earned from its own league's results. Global ELO adds "
        "one offset per league, placing that whole league on the shared axis. The offset comes "
        "from continental matches — clubs from different leagues actually playing each other — "
        "and from promotion and relegation links between tiers.</p>")
    p.append(
        '<div class="note"><b>The offset cannot change a forecast.</b> Adding the same number to '
        'every club in a league leaves the differences inside that league untouched, and those '
        'differences are what the match and season forecasts use. Moving a league up or down the '
        'Global ELO scale does not move any of its probabilities.</div>')

    p.append("<h2>Where it is weakest</h2>")
    if quality_counts:
        p.append("<p>Not every league's placement rests on the same evidence:</p><ul>")
        for q, n in sorted(quality_counts.items(), key=lambda kv: -kv[1]):
            copy = _GLOBAL_ELO_QUALITY_COPY.get(q, q.replace("_", " "))
            p.append(f"<li><b>{n} competition{'s' if n != 1 else ''}</b> — {E(copy)}.</li>")
        p.append("</ul>")
    p.append(
        "<p>Comparisons <b>within</b> a league are the most reliable thing here, because they "
        "rest on clubs playing each other every week. Comparisons <b>between confederations</b> "
        "are the least reliable: they lean on a much smaller pool of intercontinental matches, "
        "and they should move as competitions like the Club World Cup add evidence. Treat a "
        "50-point gap across confederations as noise, not a ranking.</p>")
    p.append(
        '<p class="sub">Global ELO changes when the evidence does. A recalibration on 2026-08-01 '
        'moved several European clubs by dozens of places once ten top divisions that had been '
        'missing a coefficient were given one. We publish those corrections rather than quietly '
        'restating them.</p>')

    p.append("<h2>Check our work</h2>")
    p.append(
        '<p>Every forecast Entenser publishes is graded in public afterwards, hits and misses '
        'together. <a href="/?league=about">Read the methodology and the scoring record</a>, or '
        '<a href="/leagues/">browse the competitions</a>.</p>')
    p.append(_footer(generated))
    return "".join(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="webapp", help="webapp root to write into")
    ap.add_argument("--site", default=SITE, help="canonical site origin")
    ap.add_argument("--weekly-archive", default="data/weekly-archive",
                    help="dir of dated weekly recap JSON (F-3 archive, roadmap 1.5)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    site = args.site.rstrip("/")

    registry = read_js_payload(out / "leagues.js")
    if not registry:
        print(f"FATAL: cannot read {out / 'leagues.js'}", file=sys.stderr)
        return 1
    names = {lg["id"]: lg["name"] for lg in registry}

    pages: list[tuple[str, str]] = []   # league (loc, lastmod)
    club_pages: list[tuple[str, str]] = []
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
        for slug, row, aliases in _club_groups(d):
            club_dir = page_dir / "clubs" / slug
            club_dir.mkdir(parents=True, exist_ok=True)
            (club_dir / "index.html").write_text(
                club_page(lg, d, row, aliases, site), encoding="utf-8")
            club_pages.append(
                (f"{site}/leagues/{lg['id']}/clubs/{slug}/", lastmod))
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
    (out / "global-elo").mkdir(parents=True, exist_ok=True)
    (out / "global-elo" / "index.html").write_text(
        global_elo_page(payloads, registry, site), encoding="utf-8")
    (out / "crossbar").mkdir(parents=True, exist_ok=True)
    (out / "crossbar" / "index.html").write_text(
        crossbar_redirect_page(site), encoding="utf-8")

    # Weekly recap page (launch plan H1) — optional: only when weekly.js exists.
    # Dated archive pages (roadmap 1.5) come from the F-3 archive; the latest
    # /weekly/ page links to them under a "Past weeks" nav.
    extra: list[tuple[str, str]] = []
    archive_dir = Path(args.weekly_archive)
    archive_links: list[tuple[str, str]] = []
    rss_recaps: list[tuple[str, dict]] = []
    if archive_dir.is_dir():
        for jf in sorted(archive_dir.glob("*.json"), reverse=True):
            date = jf.stem
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                continue
            try:
                aw = json.loads(jf.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if aw.get("status") != "ok":
                continue
            page_path = f"weekly/{date}/"
            (out / "weekly" / date).mkdir(parents=True, exist_ok=True)
            (out / "weekly" / date / "index.html").write_text(
                weekly_page(aw, site, page_path), encoding="utf-8")
            extra.append((f"{site}/{page_path}", date))
            archive_links.append((f"/{page_path}", date))
            rss_recaps.append((page_path, aw))

    w = read_js_payload(out / "data" / "weekly.js")
    if w and w.get("status") == "ok":
        (out / "weekly").mkdir(parents=True, exist_ok=True)
        (out / "weekly" / "index.html").write_text(
            weekly_page(w, site, "weekly/", archive_links), encoding="utf-8")
        extra.append((f"{site}/weekly/", (w.get("generated") or "")[:10]))
        rss_recaps.insert(0, ("weekly/", w))
    (out / "forecast-feed.xml").write_text(
        forecast_rss(rss_recaps, site), encoding="utf-8")
    if exported:
        extra.append((f"{site}/open-data/", max_lastmod))
        extra.append((f"{site}/global-elo/", max_lastmod))

    # Forecast-first European acquisition page. It deliberately links into the
    # existing league documents rather than creating a second data experience.
    if any(league_id in payloads for _, league_ids in _EUROPE_FORECAST_GROUPS
           for league_id in league_ids):
        (out / "football-forecasts").mkdir(parents=True, exist_ok=True)
        (out / "football-forecasts" / "index.html").write_text(
            europe_forecast_page(payloads, names, site), encoding="utf-8")
        extra.append((f"{site}/football-forecasts/", max_lastmod))

    # World Cup → domestic on-ramp (launch plan H2) — needs the US leagues.
    if any(lid in payloads for lid, _ in _WC_ONRAMP):
        (out / "after-the-world-cup").mkdir(parents=True, exist_ok=True)
        (out / "after-the-world-cup" / "index.html").write_text(
            world_cup_page(payloads, names, site), encoding="utf-8")
        extra.append((f"{site}/after-the-world-cup/", max_lastmod))

    entries = ([(f"{site}/", max_lastmod),
                (f"{site}/leagues/", max_lastmod)]
               + extra + sorted(pages) + sorted(club_pages))
    (out / "sitemap.xml").write_text(sitemap(entries), encoding="utf-8")
    print(f"wrote {len(pages)} league pages + {len(club_pages)} club pages + hub"
          f"{' + weekly' if w and w.get('status') == 'ok' else ''}"
          f" + {len(exported)} CSV exports + European forecasts + RSS + sitemap "
          f"({len(entries)} URLs, lastmod {max_lastmod})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
