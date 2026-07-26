#!/usr/bin/env python3
"""Matches to Watch → webapp/data/match-leverage.js.

Ranks upcoming fixtures by how much the RESULT moves the league table, using
conditional simulation: pin each fixture to home / draw / away, re-simulate the
rest of the season, and measure the expected L1 movement in every club's
outcome probabilities. See scripts/match_leverage.py for the method and its
per-league CLI.

Why a static payload rather than an Intel-hub API feature: the hub is
auth-gated and team-scoped, but leverage is a property of the FIXTURE, not the
viewer. Computing it once per build and letting the client intersect it with
the reader's own pinned leagues/teams (FavStore, already in index.html) gives
personalisation with no auth round-trip, and the hub can consume the same file
when it wants to.

Three rails, because raw leverage answers "where is the table most volatile"
rather than "what should I watch". Ranked globally, a 16-team Bolivian table
with 30 games left genuinely does swing more per match than an August Premier
League, so an unranked board fills with fixtures nobody asked about:

  yours       the reader's pinned leagues/teams, ordered by leverage. Assembled
              CLIENT-side; this file just supplies the ingredients.
  normalised  leverage as a WITHIN-LEAGUE percentile, so a big-five fixture can
              compete with a volatile small league on equal terms.
  world       raw global leverage, explicitly framed as the exotic rail.

Usage:
    python3 scripts/build_match_leverage.py --days 7 --sims 3000
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.match_leverage import leverage_for_league
from scripts.payload_utils import write_js_payload

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "webapp" / "data"
OUT = DATA / "match-leverage.js"


def _registry() -> dict[str, dict]:
    txt = (ROOT / "webapp" / "leagues.js").read_text(encoding="utf-8")
    return {r["id"]: r for r in json.loads(txt.split("=", 1)[1].rstrip().rstrip(";"))}


def _crest_index() -> dict[str, str]:
    p = DATA / "logos.js"
    if not p.exists():
        return {}
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", p.read_text(encoding="utf-8"), re.DOTALL)
    try:
        return json.loads(m.group(1)) if m else {}
    except Exception:
        return {}


def build(days: int, sims: int, scope: str) -> dict:
    reg = _registry()
    crests = _crest_index()
    rows: list[dict] = []
    for lid in sorted(reg):
        try:
            got = leverage_for_league(lid, days, sims, scope=scope)
        except Exception as e:                       # noqa: BLE001
            print(f"  [skip] {lid}: {type(e).__name__}: {e}")
            continue
        if not got:
            continue
        # Within-league percentile: rank 1.0 = this league's most pivotal
        # fixture in the window. This is what lets rail 2 compare across
        # leagues of wildly different volatility.
        ordered = sorted(got, key=lambda r: r["leverage"])
        n = len(ordered)
        for i, r in enumerate(ordered):
            r["pct"] = round((i + 1) / n, 4) if n > 1 else 1.0
        for r in got:
            meta = reg.get(r["league"], {})
            r["league_name"] = meta.get("name", r["league"])
            r["country"] = meta.get("country")
            # Tier is what lets the normalised rail break the pct=1.0 tie that
            # every league's top fixture shares. Without it that rail re-sorts
            # on raw leverage and reproduces exactly the bias it exists to fix.
            r["tier"] = meta.get("tier") or 9
            r["home_logo"] = crests.get(r["home"])
            r["away_logo"] = crests.get(r["away"])
        rows += got
        print(f"  {lid:24} {len(got):3} fixture(s), top leverage {max(x['leverage'] for x in got):6.2f}")

    rows.sort(key=lambda r: -r["leverage"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {
        "status": "live",
        "horizon_days": days,
        "scope": scope,
        "n_leagues": len({r["league"] for r in rows}),
        "fixtures": rows,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        # Copy the UI leans on, kept with the data so the two cannot drift.
        "explainer": (
            "Leverage is how much this result moves the league table: we replay "
            "the rest of the season with the match pinned to a home win, a draw "
            "and an away win, and measure how far every club's title, European "
            "and relegation probabilities shift. A dead rubber between two safe clubs "
            "scores near zero; a game that decides someone else's season scores "
            "high even if neither side is famous."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--sims", type=int, default=3000)
    ap.add_argument("--scope", choices=["all", "pair"], default="all",
                    help="'all' sums the swing across every club in the table "
                         "(the request's 'biggest swing in table odds'); "
                         "'pair' counts only the two clubs playing.")
    a = ap.parse_args()

    data = build(a.days, a.sims, a.scope)
    write_js_payload(OUT, "MATCH_LEVERAGE", data)
    fx = data["fixtures"]
    print(f"\n[leverage] wrote {OUT} ({OUT.stat().st_size // 1024} KB) · "
          f"{len(fx)} fixtures across {data['n_leagues']} leagues, next {a.days} day(s)")
    for r in fx[:8]:
        print(f"    {r['date']}  {r['league_name'][:18]:18} "
              f"{r['home'][:20]:20} v {r['away'][:20]:20} {r['leverage']:6.2f}")


if __name__ == "__main__":
    main()
