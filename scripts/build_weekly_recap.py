#!/usr/bin/env python3
"""Build webapp/data/weekly.js — the weekly recap payload (launch plan H1).

A point-in-time, quotable snapshot for the syndication playbook: biggest race
movement, the most fragile title/relegation races, where the model disagreed
with the betting market, and the week's high-confidence misses (the public
"show our work" receipt). Assembled from payloads other builders already write:

  webapp/data/movers.js      → biggest odds swings (race movement)
  webapp/data/edge-board.js  → fragile season races + model-vs-market priced rows
  webapp/data/<league>.js    → completed games w/ model probs (hits / misses)

Runs after those in scripts/build_all.sh. The SPA renders it at ?league=weekly
and scripts/build_static_pages.py emits a crawlable /weekly/ page from it.

Run:  python3 scripts/build_weekly_recap.py
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

# Runnable as `python3 scripts/build_weekly_recap.py` and `-m scripts.build_weekly_recap`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import read_js_payload, registry_ids, write_js_payload  # noqa: E402

DATA = Path("webapp/data")
MISS_CONF = 0.60      # a "high-confidence" call: model favorite ≥ 60%
WINDOW_DAYS = 8       # completed-game lookback for hits/misses


def _league_names() -> dict[str, str]:
    reg = read_js_payload("webapp/leagues.js") or []
    return {l["id"]: l["name"] for l in reg}


def _movers(names: dict[str, str]) -> dict:
    d = read_js_payload(DATA / "movers.js")
    if not d or d.get("status") != "ok":
        return {"risers": [], "fallers": [], "window_label": None}
    labels = d.get("metric_labels", {})
    rows = [{"team": m["team"], "league": m["league"],
             "league_name": names.get(m["league"], m["league"]),
             "metric": labels.get(m["metric"], m["metric"]),
             "prev": m["prev"], "now": m["now"], "delta": m["delta"]}
            for m in (d.get("movers") or [])]
    risers = sorted([r for r in rows if r["delta"] > 0],
                    key=lambda r: -r["delta"])[:5]
    fallers = sorted([r for r in rows if r["delta"] < 0],
                     key=lambda r: r["delta"])[:5]
    return {"risers": risers, "fallers": fallers,
            "window_label": d.get("window_label")}


def _fragile_races() -> list[dict]:
    d = read_js_payload(DATA / "edge-board.js")
    races = (d or {}).get("season_races") or []
    # Most uncertain first (closest races are the most quotable).
    top = sorted(races, key=lambda r: -(r.get("uncertainty") or 0))[:6]
    return [{"league": r["league"], "league_name": r["league_name"],
             "label": r["label"], "leader": r["leader"]["team"],
             "leader_prob": r["leader"]["prob"], "margin": r.get("margin"),
             "contenders": [c["team"] for c in (r.get("contenders") or [])[:2]]}
            for r in top]


def _disagreements(names: dict[str, str]) -> list[dict]:
    """Model-vs-market rows from the edge board, when market lines exist."""
    d = read_js_payload(DATA / "edge-board.js")
    priced = (d or {}).get("priced") or []
    rows = []
    for p in priced:
        edge = p.get("edge_pct")
        if edge is None:
            continue
        rows.append({"league_name": names.get(p.get("league"), p.get("league")),
                     "home": p.get("home"), "away": p.get("away"),
                     "pick": p.get("pick") or p.get("side"),
                     "model_pct": p.get("model_pct") or p.get("model_prob"),
                     "market_pct": p.get("market_pct") or p.get("market_prob"),
                     "edge_pct": edge})
    return sorted(rows, key=lambda r: -abs(r["edge_pct"]))[:6]


def _hits_and_misses(names: dict[str, str]) -> dict:
    """High-confidence calls resolved in the last WINDOW_DAYS.

    A call is the model's most likely outcome (H/D/A) when its probability
    is ≥ MISS_CONF. Miss = that outcome did not happen. We publish the misses
    (the costly, credible signal) plus a hit-rate summary.
    """
    cut = (datetime.date.today()
           - datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    calls, hits, misses = 0, 0, []
    for lid in registry_ids():
        d = read_js_payload(DATA / f"{lid}.js")
        if not d:
            continue
        lname = names.get(lid, lid)
        for g in d.get("games") or []:
            if not g.get("result") or (g.get("date") or "") < cut:
                continue
            probs = {"H": g.get("pH"), "D": g.get("pD"), "A": g.get("pA")}
            if any(v is None for v in probs.values()):
                continue
            pick = max(probs, key=probs.get)
            conf = probs[pick]
            if conf < MISS_CONF:
                continue
            calls += 1
            if pick == g["result"]:
                hits += 1
            else:
                fav = g["home"] if pick == "H" else g["away"] if pick == "A" else None
                misses.append({
                    "league_name": lname, "date": g["date"],
                    "home": g["home"], "away": g["away"],
                    "score": f'{g.get("hg")}–{g.get("ag")}',
                    "fav": fav, "fav_pct": round(conf * 100, 1),
                    "outcome": {"H": "home win", "D": "draw",
                                "A": "away win"}[g["result"]]})
    misses.sort(key=lambda m: -m["fav_pct"])
    return {"n_calls": calls, "n_hits": hits,
            "hit_rate": round(hits / calls * 100, 1) if calls else None,
            "misses": misses[:6]}


def _headline(movers: dict, fragile: list[dict]) -> str:
    top = (movers["risers"] + movers["fallers"])
    if top:
        m = max(top, key=lambda r: abs(r["delta"]))
        dirn = "climb" if m["delta"] > 0 else "slide"
        return (f"{m['team']}’s {m['metric'].lower()} odds {dirn} "
                f"{abs(m['delta']):.1f} points to {m['now']:.0f}%")
    if fragile:
        r = fragile[0]
        return (f"{r['league_name']} {r['label'].lower()} race tightens: "
                f"{r['leader']} lead at {r['leader_prob']:.0f}%")
    return "This week across world football"


def main() -> int:
    names = _league_names()
    movers = _movers(names)
    fragile = _fragile_races()
    disagreements = _disagreements(names)
    hm = _hits_and_misses(names)
    now = datetime.datetime.now(datetime.timezone.utc)
    data = {
        "status": "ok",
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "week_label": now.strftime("Week of %B %-d, %Y"),
        "headline": _headline(movers, fragile),
        "movers": movers,
        "fragile_races": fragile,
        "disagreements": disagreements,
        "receipt": hm,
    }
    out = DATA / "weekly.js"
    write_js_payload(out, "WEEKLY_DATA", data)
    print(f"[weekly] wrote {out} · {len(movers['risers'])} risers / "
          f"{len(movers['fallers'])} fallers · {len(fragile)} races · "
          f"{len(disagreements)} disagreements · "
          f"{hm['n_hits']}/{hm['n_calls']} calls hit · "
          f"{len(hm['misses'])} misses shown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
