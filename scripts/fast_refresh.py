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

from data_pipeline.names import clean_display_name
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
        # "Feed-backed" means ESPN OR the spine: a league routed to
        # API-Football needs no ESPN slug, and gating on espn_code alone
        # would silently exclude exactly the leagues the migration exists
        # to serve (canadian-pl has no working ESPN slug at all).
        if row.get("status") != "live":
            continue
        if not row.get("espn_code") and not uses_spine(league_id):
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
        home_name = clean_display_name((home.get("team") or {}).get("displayName"))
        away_name = clean_display_name((away.get("team") or {}).get("displayName"))
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


_FINISHED_AF = {"FT", "AET", "PEN"}


def uses_spine(league_id: str) -> bool:
    """True when the source registry routes this league's fixtures to
    API-Football first (spec §6.1). Unrouted leagues keep ESPN, unchanged."""
    from data_pipeline.source_registry import sources_for
    return sources_for(league_id, "fixtures", default="espn")[0] == "api_football"


def fetch_spine_scoreboard(league_id: str,
                           now: dt.datetime | None = None) -> list[dict]:
    """API-Football equivalent of fetch_scoreboard — same provider-neutral row
    shape, same ±2-day window, one request per refresh.

    This exists because the fast refresh was the ORIGINAL failure that
    motivated the migration (seven consecutive 403s on 2026-08-07) and yet
    stayed ESPN-only through Stage 3: leagues already migrated in
    build_league_data still died here behind the ESPN circuit breaker.
    """
    from data_pipeline import api_football

    af_id, seasons = api_football.LEAGUE[league_id]
    current = _utc_now(now)
    lo = (current.date() - dt.timedelta(days=2)).isoformat()
    hi = (current.date() + dt.timedelta(days=2)).isoformat()
    payload = api_football._get(
        "fixtures",
        {"league": af_id, "season": max(seasons), "from": lo, "to": hi})
    names = api_football._team_names().get(league_id, {})
    rows = []
    for event in payload.get("response") or []:
        fixture, teams = event.get("fixture") or {}, event.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        kickoff = fixture.get("date")
        kickoff_dt = _iso(kickoff)
        if not home or not away or kickoff_dt is None:
            continue
        completed = (fixture.get("status") or {}).get("short") in _FINISHED_AF
        goals = event.get("goals") or {}
        home_goals = away_goals = None
        if completed:
            try:
                home_goals = int(goals.get("home"))
                away_goals = int(goals.get("away"))
            except (TypeError, ValueError):
                continue
        rows.append({
            "provider_id": str(fixture.get("id")),
            "date": kickoff_dt.date().isoformat(),
            "ko": kickoff,
            "home": names.get(home, home),
            "away": names.get(away, away),
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


def _tokens(value: str) -> tuple[str, ...]:
    """Token set after normalisation and club-word stripping.

    Same shape as build_dashboard_data._toks and the spine name-map deriver, so
    "Arsenal FC" and "Arsenal" are one club everywhere in this repository.
    """
    return tuple(sorted(_name(value).split()))


def _sides(game: dict, feed: dict) -> tuple[float, float]:
    """Per-side similarity. Deliberately NOT averaged — see _match_game."""
    return (
        difflib.SequenceMatcher(
            None, _name(game.get("home", "")), _name(feed.get("home", ""))).ratio(),
        difflib.SequenceMatcher(
            None, _name(game.get("away", "")), _name(feed.get("away", ""))).ratio(),
    )


def _fixture_score(game: dict, feed: dict) -> float:
    """Confidence in a whole fixture: its WEAKER side.

    Averaging the two sides was the defect. It let a perfect home match carry a
    hopeless away one, and a fixture is identified by both of its clubs or by
    neither. A pair is only as good as the side you are least sure of.
    """
    return min(_sides(game, feed))


# A fixture matched by name alone must clear this on BOTH sides, and beat the
# runner-up by MATCH_MARGIN. Measured against real confusables at the old
# average-of-two-sides ≥ 0.58 rule: Bristol City/Stoke City scored 0.727,
# Sheffield United/Sheffield Wednesday 0.686, Manchester United/Manchester City
# 0.812 — 13 of 15 genuinely different clubs cleared it. Fuzzy matching was
# banned outright in check_standings for exactly the Bristol City case; this
# path kept it while writing scorelines into the table every fifteen minutes.
MATCH_FLOOR = 0.90
MATCH_MARGIN = 0.10


def _match_game(games: list[dict], feed: dict,
                used: set[int]) -> tuple[int, dict] | None:
    """The payload fixture this feed row refers to, or None if unsure.

    Two tiers, and both refuse rather than guess:

    1. **Token-exact on both clubs.** Handles the real spelling variation
       ("Arsenal FC" vs "Arsenal") with no room for a near miss. Two exact
       candidates on the same day is a genuine ambiguity, so it refuses.
    2. **Similarity, but only when decisive.** Both sides must clear
       MATCH_FLOOR and the best must beat the runner-up by MATCH_MARGIN.

    Refusing costs one refresh cycle — `apply_feed` skips an unmatched row and
    the next tick retries. Guessing costs a result attributed to the wrong club,
    which propagates into the table, the simulation and the published forecast,
    and nothing downstream can tell.
    """
    feed_date = dt.date.fromisoformat(feed["date"])
    feed_home, feed_away = _tokens(feed.get("home", "")), _tokens(feed.get("away", ""))

    exact, scored = [], []
    for index, game in enumerate(games):
        if index in used:
            continue
        try:
            game_date = dt.date.fromisoformat(str(game.get("date")))
        except ValueError:
            continue
        if abs((game_date - feed_date).days) > 1:
            continue
        if (_tokens(game.get("home", "")) == feed_home
                and _tokens(game.get("away", "")) == feed_away):
            exact.append((index, game))
        home, away = _sides(game, feed)
        scored.append((min(home, away), index, game))

    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None                       # same clubs, same day, twice — ambiguous

    if not scored:
        return None
    scored.sort(key=lambda row: -row[0])
    best, index, game = scored[0]
    if best < MATCH_FLOOR:
        return None
    if len(scored) > 1 and best - scored[1][0] < MATCH_MARGIN:
        return None                       # two plausible fixtures; pick neither
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
    # A COMPLETED feed row that matches nothing is the failure this tightening
    # could introduce: results quietly stop being applied and the payload still
    # looks healthy, which is the same shape as an unmapped club. Refusing is
    # right, refusing silently is not — so unmatched completed rows are counted
    # and reported. A club that needs an alias shows up here instead of as a
    # league that mysteriously stopped updating.
    unmatched: list[str] = []
    for feed in feed_rows:
        matched = _match_game(games, feed, used)
        if matched is None:
            if feed.get("completed"):
                unmatched.append(
                    f"{feed.get('date')} {feed.get('home')} v {feed.get('away')}")
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
        # Operational only — deliberately NOT written into payload["fast_refresh"],
        # which ships to the client. This belongs in the run report a human reads.
        "unmatched": unmatched,
        "generated": payload.get("generated"),
    }


class FeedUnavailable(RuntimeError):
    """Every source for one league's fixtures failed.

    A distinct type because `refresh_selected` must isolate exactly this and
    nothing else: a league whose upstreams are all down is a skippable league,
    while a ValueError or the pmatrix AssertionError is a payload bug that has
    to stop the run. Catching a bare RuntimeError there would swallow both.
    """


def _routed_feed(league_id: str, espn_code: str | None,
                 now: dt.datetime | None = None) -> tuple[list[dict], str]:
    """Fixture rows from the first source that answers, in registry order.

    `source_registry` has declared an ORDER for fixtures since 2026-08-08 —
    `["api_football", "espn"]` for a routed league — and `build_league_data`
    honours it through `resolve()`. This path did not: it picked one source
    from `uses_spine()` and called it, so on 2026-08-14 a missing
    API_FOOTBALL_KEY took down the whole run 12 times rather than falling
    through to an ESPN that was answering.

    Not reusing `source_registry.resolve()` deliberately. That helper treats an
    empty result as a failure, which is right for a standings frame and wrong
    here: a league with no fixtures in the +/-2-day window legitimately returns
    zero rows, and demoting that to "source failed" would fall through to ESPN
    on a perfectly good answer and then raise when ESPN agreed there were none.
    Failures are still recorded in source_health, so a fallback stays visible.
    """
    from data_pipeline.source_health import record_fetch
    from data_pipeline.source_registry import sources_for

    fetchers = {
        "api_football": lambda: fetch_spine_scoreboard(league_id, now=now),
        "espn": (lambda: fetch_scoreboard(espn_code, now=now)) if espn_code else None,
    }
    errors: list[str] = []
    for source in sources_for(league_id, "fixtures", default="espn"):
        fetch = fetchers.get(source)
        if fetch is None:
            errors.append(f"{source}: no fetcher for this league")
            continue
        try:
            return fetch(), source
        except Exception as exc:  # noqa: BLE001 — recorded, then the next source
            errors.append(f"{source}: {exc}")
            record_fetch(source, f"fast_refresh:{league_id}", ok=False,
                         error=str(exc))
    raise FeedUnavailable(
        f"every fixture source failed for {league_id}: " + "; ".join(errors))


def refresh_league(league_id: str, payload_dir: Path = PAYLOAD_DIR,
                   registry_path: Path = REGISTRY,
                   now: dt.datetime | None = None,
                   sims: int | None = None) -> dict:
    registry = load_registry(registry_path)
    row = registry.get(league_id) or {}
    espn_code = row.get("espn_code")
    if not uses_spine(league_id) and not espn_code:
        raise ValueError(f"{league_id} has no ESPN scoreboard code")
    path = payload_dir / f"{league_id}.js"
    payload = read_js_payload(path)
    if not isinstance(payload, dict):
        raise ValueError(f"no readable payload for {league_id}")
    feed, source = _routed_feed(league_id, espn_code, now=now)
    result = apply_feed(payload, feed, now=now, sims=sims)
    write_js_payload(path, "LEAGUE_DATA", payload)
    return {"league_id": league_id, "source": source, **result}


# One league losing its feed must not strand every other league. On 2026-08-07 a
# 403 on bol.1 propagated out of the refresh loop and aborted the whole run (see
# runs 31221990714 / 31218282187); projections went stale site-wide behind a
# single unavailable competition, and the job had failed for hours unnoticed.
#
# Blanket tolerance is the opposite mistake. ESPN rate-limits by IP and then
# refuses EVERY endpoint (data_pipeline.http), so a real block fails most leagues
# at once — publishing that snapshot would advertise fresh data for a run where
# almost nothing advanced. Above this share of failures the run stays loud and
# the workflow's alert fires; the next quarter-hourly tick retries anyway.
_FAILURE_TOLERANCE = 0.5


def refresh_selected(league_ids: list[str], sims: int | None = None) -> dict:
    """Refresh each league independently, reporting rather than raising on feed loss."""
    # Imported here, not at module scope: the workflow runs --select on the
    # runner's bare Python before `pip install -r requirements.txt`, so this
    # file must stay importable without requests — same reason espn_get and
    # run_simulation are deferred into their callers.
    import requests

    refreshed: list[dict] = []
    failed: list[dict] = []
    for league_id in league_ids:
        try:
            refreshed.append(refresh_league(league_id, sims=sims))
        except (requests.RequestException, FeedUnavailable) as exc:
            # Feed loss only. A ValueError or the pmatrix AssertionError is a
            # payload bug, not a dead upstream, and must still stop the run.
            #
            # FeedUnavailable joined this tuple on 2026-08-15. RequestException
            # alone described a one-source world: once a league could try two
            # sources, "this league has no feed" stopped being any single
            # transport error, and the failure that actually hit production was
            # not a transport error at all — a missing API_FOOTBALL_KEY raises
            # RuntimeError, which sailed straight through this handler and
            # aborted every remaining league, which is precisely the blast
            # radius this isolation exists to prevent.
            print(f"fast refresh: {league_id} feed unavailable, skipped — {exc}",
                  file=sys.stderr)
            failed.append({"league_id": league_id, "error": str(exc)})
    return {"refreshed": refreshed, "failed": failed}


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
        report = refresh_selected(select_leagues(), sims=args.sims)
        print(json.dumps(report, separators=(",", ":")))
        attempted = len(report["refreshed"]) + len(report["failed"])
        return int(len(report["failed"]) > attempted * _FAILURE_TOLERANCE)
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
