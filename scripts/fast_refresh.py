#!/usr/bin/env python3
"""Refresh results and table projections without fitting a model.

The daily builders remain the source of fitted fixture probabilities, ELO, and
market prices. This fast path only:

1. reads the already-published fixture probabilities;
2. checks ESPN for completed results and corrected kickoff times;
3. advances current points / goal difference;
4. re-runs the cheap table Monte Carlo; and
5. records separate forecast, fitted-model, and market clocks.

It is deliberately safe to run repeatedly against the prior live-data snapshot:
only games whose ``result`` is still null can advance the standings.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.payload_utils import read_js_payload, write_js_payload

PAYLOAD_DIR = Path("webapp/data")
REGISTRY = Path("webapp/leagues.js")
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
MATCH_LEAD = dt.timedelta(hours=2)
MATCH_LAG = dt.timedelta(hours=3)


def _utc_now(now: dt.datetime | None = None) -> dt.datetime:
    value = now or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _iso(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(
            str(value).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def load_registry(path: Path = REGISTRY) -> dict[str, dict]:
    rows = read_js_payload(path)
    if not isinstance(rows, list):
        return {}
    return {row["id"]: row for row in rows if isinstance(row, dict) and row.get("id")}


def in_match_window(payload: dict, now: dt.datetime | None = None) -> bool:
    """True around a scheduled kickoff; date-only rows use a full-day fallback."""
    current = _utc_now(now)
    for game in payload.get("games") or []:
        if game.get("result") is not None:
            continue
        kickoff = _iso(game.get("ko"))
        if kickoff and kickoff - MATCH_LEAD <= current <= kickoff + MATCH_LAG:
            return True
        if not kickoff and game.get("date") == current.date().isoformat():
            return True
    return False


def select_leagues(payload_dir: Path = PAYLOAD_DIR,
                   registry_path: Path = REGISTRY,
                   now: dt.datetime | None = None) -> list[str]:
    """Select all feed-backed leagues hourly, or match-window leagues quarterly."""
    current = _utc_now(now)
    hourly_tick = current.minute < 15
    registry = load_registry(registry_path)
    selected = []
    for league_id, row in sorted(registry.items()):
        if not row.get("espn_code") or row.get("status") != "live":
            continue
        payload = read_js_payload(payload_dir / f"{league_id}.js")
        if not isinstance(payload, dict):
            continue
        if not payload.get("sim") or not payload.get("standings") or not payload.get("games"):
            continue
        if payload.get("data_status") != "full_forecast":
            continue
        if hourly_tick or in_match_window(payload, current):
            selected.append(league_id)
    return selected


def fetch_scoreboard(espn_code: str,
                     now: dt.datetime | None = None) -> list[dict]:
    """Fetch a narrow ESPN scoreboard window and return a provider-neutral feed."""
    from data_pipeline.http import espn_get

    current = _utc_now(now)
    lo = (current.date() - dt.timedelta(days=2)).strftime("%Y%m%d")
    hi = (current.date() + dt.timedelta(days=2)).strftime("%Y%m%d")
    response = espn_get(
        f"{ESPN_BASE}/{espn_code}/scoreboard",
        {"dates": f"{lo}-{hi}", "limit": 250},
    )
    rows = []
    for event in response.get("events") or []:
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        competitors = competition.get("competitors") or []
        home = next((row for row in competitors
                     if row.get("homeAway") == "home"), None)
        away = next((row for row in competitors
                     if row.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        home_name = (home.get("team") or {}).get("displayName")
        away_name = (away.get("team") or {}).get("displayName")
        kickoff = event.get("date")
        kickoff_dt = _iso(kickoff)
        if not home_name or not away_name or kickoff_dt is None:
            continue
        completed = bool(
            ((competition.get("status") or {}).get("type") or {}).get(
                "completed"))
        home_goals = away_goals = None
        if completed:
            try:
                home_goals = int(float(home.get("score")))
                away_goals = int(float(away.get("score")))
            except (TypeError, ValueError):
                continue
        rows.append({
            "provider_id": event.get("id"),
            "date": kickoff_dt.date().isoformat(),
            "ko": kickoff,
            "home": home_name,
            "away": away_name,
            "completed": completed,
            "hg": home_goals,
            "ag": away_goals,
        })
    return rows


_CLUB_WORDS = {
    "afc", "cf", "fc", "sc", "club", "de", "football", "futbol", "soccer",
    "the",
}


def _name(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value or "").encode(
        "ascii", "ignore").decode().casefold()
    words = [word for word in re.sub(r"[^a-z0-9]+", " ", plain).split()
             if word not in _CLUB_WORDS]
    return " ".join(words)


def _fixture_score(game: dict, feed: dict) -> float:
    home = difflib.SequenceMatcher(
        None, _name(game.get("home", "")), _name(feed.get("home", ""))).ratio()
    away = difflib.SequenceMatcher(
        None, _name(game.get("away", "")), _name(feed.get("away", ""))).ratio()
    return (home + away) / 2


def _match_game(games: list[dict], feed: dict,
                used: set[int]) -> tuple[int, dict] | None:
    feed_date = dt.date.fromisoformat(feed["date"])
    candidates = []
    for index, game in enumerate(games):
        if index in used:
            continue
        try:
            game_date = dt.date.fromisoformat(str(game.get("date")))
        except ValueError:
            continue
        if abs((game_date - feed_date).days) > 1:
            continue
        score = _fixture_score(game, feed)
        if score >= 0.58:
            candidates.append((score, index, game))
    if not candidates:
        return None
    _, index, game = max(candidates, key=lambda row: row[0])
    return index, game


def _advance_standings(payload: dict, game: dict, hg: int, ag: int) -> None:
    by_team = {row.get("team"): row for row in payload.get("standings") or []}
    home, away = by_team.get(game.get("home")), by_team.get(game.get("away"))
    if home is None or away is None:
        raise ValueError(
            f"standings missing fixture teams: {game.get('home')} / {game.get('away')}")
    home["gp"] = int(home.get("gp") or 0) + 1
    away["gp"] = int(away.get("gp") or 0) + 1
    home["gd"] = int(home.get("gd") or 0) + hg - ag
    away["gd"] = int(away.get("gd") or 0) + ag - hg
    if hg > ag:
        home["pts"] = int(home.get("pts") or 0) + 3
    elif ag > hg:
        away["pts"] = int(away.get("pts") or 0) + 3
    else:
        home["pts"] = int(home.get("pts") or 0) + 1
        away["pts"] = int(away.get("pts") or 0) + 1


def apply_feed(payload: dict, feed_rows: list[dict],
               now: dt.datetime | None = None,
               sims: int | None = None) -> dict:
    """Apply new results/kickoffs and update table projections in-place."""
    current = _utc_now(now)
    games = payload.get("games") or []
    fitted_at = (payload.get("fast_refresh") or {}).get(
        "fitted_model_at") or payload.get("generated")
    market_at = (payload.get("fast_refresh") or {}).get(
        "market_prices_at") or payload.get("generated")
    old_matrix = json.dumps((payload.get("sim") or {}).get("pmatrix"))
    used: set[int] = set()
    results_applied = kickoff_updates = 0
    for feed in feed_rows:
        matched = _match_game(games, feed, used)
        if matched is None:
            continue
        index, game = matched
        used.add(index)
        if feed.get("ko") and game.get("ko") != feed["ko"]:
            game["ko"] = feed["ko"]
            kickoff_updates += 1
        if not feed.get("completed") or game.get("result") is not None:
            continue
        hg, ag = int(feed["hg"]), int(feed["ag"])
        _advance_standings(payload, game, hg, ag)
        game["hg"], game["ag"] = hg, ag
        game["result"] = "H" if hg > ag else ("A" if ag > hg else "D")
        results_applied += 1

    generated = current.strftime("%Y-%m-%d %H:%M UTC")
    updated_targets: list[str] = []
    if results_applied:
        from scripts.archive_intelligence_state import build_snapshot
        from scripts.intelligence.simulation import run_simulation

        payload["generated"] = generated
        snapshot = build_snapshot(
            payload, league_id=(payload.get("league") or {}).get("id"))
        count = int(sims or payload.get("n_sims") or 5000)
        projected = run_simulation(snapshot, n=count)
        for row in payload.get("standings") or []:
            team_id = row.get("team_id")
            values = projected.get(team_id) or {}
            for key, value in values.items():
                row[key] = value
                if key not in updated_targets:
                    updated_targets.append(key)
        played = sum(game.get("result") is not None for game in games)
        payload["played"] = played
        payload["upcoming"] = len(games) - played
        total = max(len(games), 1)
        league = payload.get("league") or {}
        league["pct_complete"] = round(played / total * 100)
        payload["league"] = league

    payload["fast_refresh"] = {
        "mode": "cached_fixture_probabilities",
        "feed_checked_at": generated,
        "forecast_updated_at": generated if results_applied else (
            (payload.get("fast_refresh") or {}).get("forecast_updated_at")
            or payload.get("generated")),
        "fitted_model_at": fitted_at,
        "market_prices_at": market_at,
        "results_applied": results_applied,
        "kickoff_updates": kickoff_updates,
        "updated_targets": sorted(updated_targets),
        "odds_refreshed": False,
    }
    if json.dumps((payload.get("sim") or {}).get("pmatrix")) != old_matrix:
        raise AssertionError("fast refresh mutated the fitted probability matrix")
    return {
        "results_applied": results_applied,
        "kickoff_updates": kickoff_updates,
        "feed_rows": len(feed_rows),
        "generated": payload.get("generated"),
    }


def refresh_league(league_id: str, payload_dir: Path = PAYLOAD_DIR,
                   registry_path: Path = REGISTRY,
                   now: dt.datetime | None = None,
                   sims: int | None = None) -> dict:
    registry = load_registry(registry_path)
    row = registry.get(league_id) or {}
    espn_code = row.get("espn_code")
    if not espn_code:
        raise ValueError(f"{league_id} has no ESPN scoreboard code")
    path = payload_dir / f"{league_id}.js"
    payload = read_js_payload(path)
    if not isinstance(payload, dict):
        raise ValueError(f"no readable payload for {league_id}")
    feed = fetch_scoreboard(espn_code, now=now)
    result = apply_feed(payload, feed, now=now, sims=sims)
    write_js_payload(path, "LEAGUE_DATA", payload)
    return {"league_id": league_id, **result}


def write_live_manifest(payload_dir: Path = PAYLOAD_DIR,
                        now: dt.datetime | None = None) -> dict:
    generated = _utc_now(now).strftime("%Y-%m-%d %H:%M UTC")
    leagues = {}
    for path in sorted(payload_dir.glob("*.js")):
        payload = read_js_payload(path)
        if not isinstance(payload, dict) or not payload.get("fast_refresh"):
            continue
        leagues[path.stem] = payload["fast_refresh"]
    manifest = {
        "schema_version": 1,
        "channel": "live-data",
        "generated": generated,
        "league_count": len(leagues),
        "leagues": leagues,
    }
    write_js_payload(payload_dir / "live-manifest.js", "LIVE_DATA_MANIFEST", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--refresh-selected", action="store_true")
    parser.add_argument("--manifest", action="store_true")
    parser.add_argument("--league")
    parser.add_argument("--sims", type=int)
    args = parser.parse_args()
    if args.select:
        print(json.dumps(select_leagues(), separators=(",", ":")))
        return 0
    if args.refresh_selected:
        results = [
            refresh_league(league_id, sims=args.sims)
            for league_id in select_leagues()
        ]
        print(json.dumps(results, separators=(",", ":")))
        return 0
    if args.manifest:
        print(json.dumps(write_live_manifest(), separators=(",", ":")))
        return 0
    if not args.league:
        parser.error(
            "--league is required unless --select, --refresh-selected, "
            "or --manifest is used")
    print(json.dumps(
        refresh_league(args.league, sims=args.sims),
        separators=(",", ":"),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
