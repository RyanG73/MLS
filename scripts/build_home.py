#!/usr/bin/env python3
"""Aggregate a cross-league HOME payload → webapp/data/home.js (window.HOME_DATA).

First-draft home page (2026-07-11): combines league leaders, tight title races,
relegation battles, biggest probability movers, and latest news — all harvested
from the already-built per-league files + movers.js + news/*.js. Read-only over
webapp/data; run it AFTER the per-league builds (append to build_all.sh).

Missing/empty inputs degrade gracefully (a section just shrinks or drops).
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("webapp/data")

# Cups render as knockout brackets, not tables — no single "leader" metric.
_SKIP = {"ucl", "europa", "conference", "concacaf-champions", "leagues-cup", "power"}

# Rough prominence order so the biggest leagues surface first in the leaders grid.
_PROMINENCE = [
    "epl", "la-liga", "serie-a", "bundesliga", "ligue-1", "mls", "liga-mx",
    "championship", "eredivisie", "primeira", "brazil-serie-a", "argentina-primera",
    "scottish-prem", "belgian-pro", "super-lig", "japan-j1", "saudi-pro",
]


def _load(path: Path) -> dict | None:
    try:
        txt = path.read_text()
        return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception:
        return None


def _live_league_files() -> list[tuple[str, dict]]:
    """(league_id, payload) for every live single-table/conference league."""
    out = []
    # webapp/leagues.js is `window.LEAGUES = [...]` (a JSON array, one dir up from data/).
    try:
        t = (DATA.parent / "leagues.js").read_text()
        registry = json.loads(t[t.index("["): t.rindex("]") + 1])
    except Exception:
        registry = []
    live_ids = [r["id"] for r in registry
                if r.get("status") == "live" and r["id"] not in _SKIP]
    for lid in live_ids:
        d = _load(DATA / f"{lid}.js")
        if not d or d.get("status") == "placeholder":
            continue
        if (d.get("outlook") or {}).get("mode") == "knockout":
            continue
        if not d.get("standings"):
            continue
        out.append((lid, d))
    return out


def _prom_key(lid: str) -> tuple[int, str]:
    return (_PROMINENCE.index(lid) if lid in _PROMINENCE else len(_PROMINENCE), lid)


def build_leaders(files: list[tuple[str, dict]]) -> list[dict]:
    leaders = []
    for lid, d in files:
        cards = (d.get("outlook") or {}).get("cards") or []
        if not cards:
            continue
        metric = cards[0]["key"]        # headline bucket (title/promo/premiers/shield/…)
        st = sorted(d["standings"], key=lambda t: t.get("proj_rank", 999))
        if not st:
            continue
        top = st[0]
        leaders.append({
            "league": lid,
            "name": (d.get("league") or {}).get("name", lid),
            "team": top.get("team"),
            "logo": top.get("logo"),
            "color": top.get("color"),
            "metric": metric,
            "metric_label": cards[0].get("label", metric.title()),
            "pct": round(float(top.get(metric, 0) or 0), 1),
            "preseason": bool((d.get("outlook") or {}).get("preseason")),
            "season_label": (d.get("outlook") or {}).get("season_label", ""),
        })
    leaders.sort(key=lambda x: _prom_key(x["league"]))
    return leaders


def build_tight_races(files: list[tuple[str, dict]]) -> list[dict]:
    """Leagues where the headline race is genuinely contested (small top-2 gap,
    leader below 85%). Ranked tightest-first."""
    races = []
    for lid, d in files:
        cards = (d.get("outlook") or {}).get("cards") or []
        if not cards:
            continue
        metric = cards[0]["key"]
        ranked = sorted(d["standings"], key=lambda t: -float(t.get(metric, 0) or 0))
        if len(ranked) < 2:
            continue
        p1 = float(ranked[0].get(metric, 0) or 0)
        p2 = float(ranked[1].get(metric, 0) or 0)
        if p1 < 30 or p1 > 85:          # runaway or nothing-happening → not a "race"
            continue
        races.append({
            "league": lid,
            "name": (d.get("league") or {}).get("name", lid),
            "metric_label": cards[0].get("label", metric.title()),
            "gap": round(p1 - p2, 1),
            "teams": [{"team": t.get("team"), "logo": t.get("logo"),
                       "pct": round(float(t.get(metric, 0) or 0), 1)}
                      for t in ranked[:3]],
        })
    races.sort(key=lambda r: r["gap"])
    return races[:6]


def build_releg_battles(files: list[tuple[str, dict]]) -> list[dict]:
    """Leagues with the most teams on the relegation bubble (releg% in 15–85)."""
    battles = []
    for lid, d in files:
        if not any(t.get("releg") is not None for t in d["standings"]):
            continue
        bubble = [t for t in d["standings"]
                  if t.get("releg") is not None and 15 <= float(t["releg"]) <= 85]
        if len(bubble) < 2:
            continue
        bubble.sort(key=lambda t: -float(t["releg"]))
        battles.append({
            "league": lid,
            "name": (d.get("league") or {}).get("name", lid),
            "n_contested": len(bubble),
            "teams": [{"team": t.get("team"), "logo": t.get("logo"),
                       "pct": round(float(t["releg"]), 1)} for t in bubble[:4]],
        })
    battles.sort(key=lambda b: -b["n_contested"])
    return battles[:4]


def build_movers() -> list[dict]:
    d = _load(DATA / "movers.js")
    if not d:
        return []
    labels = d.get("metric_labels", {})
    out = []
    for m in d.get("movers", [])[:8]:
        out.append({
            "league": m["league"], "team": m["team"],
            "metric_label": labels.get(m["metric"], m["metric"]),
            "delta": m["delta"], "now": m["now"],
        })
    return out


def build_news(limit: int = 12) -> list[dict]:
    items = []
    for f in glob.glob(str(DATA / "news" / "*.js")):
        d = _load(Path(f))
        if not d:
            continue
        lid = d.get("league")
        lid = lid.get("id") if isinstance(lid, dict) else lid
        for it in d.get("items", []):
            items.append({
                "title": it.get("title"), "link": it.get("link"),
                "source": it.get("source"), "published": it.get("published"),
                "league": lid,
            })
    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    # de-dup by title
    seen, uniq = set(), []
    for it in items:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        uniq.append(it)
    return uniq[:limit]


def main() -> None:
    files = _live_league_files()
    leaders = build_leaders(files)
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "stats": {
            "leagues": len(files),
            "leaders": len(leaders),
        },
        "leaders": leaders,
        "tight_races": build_tight_races(files),
        "releg_battles": build_releg_battles(files),
        "movers": build_movers(),
        "news": build_news(),
    }
    (DATA / "home.js").write_text(
        "window.HOME_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote webapp/data/home.js · {len(files)} leagues · "
          f"{len(leaders)} leaders · {len(payload['tight_races'])} tight races · "
          f"{len(payload['releg_battles'])} releg battles · {len(payload['movers'])} movers · "
          f"{len(payload['news'])} news")


if __name__ == "__main__":
    main()
