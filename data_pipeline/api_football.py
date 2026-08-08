"""API-Football (api-sports.io) adapter — schedule + results + crests for leagues
with no football-data / ESPN coverage.

Round-4 use (2026-07-11, docs/superpowers/specs/2026-07-11-*):
  - Canadian Premier League: everything (not on football-data OR ESPN).
  - Finland Veikkausliiga: upcoming-fixtures override only (results+odds come from
    football-data; ESPN `fin.1` is empty).

Auth: env `API_FOOTBALL_KEY` (free tier: 100 requests/day). A gitignored `.env`
at the repo root is loaded automatically. Requests are disk-cached per
(league, season); only the current season is re-fetched, so a daily build costs
~1 request per league. The value is never logged.

Canonical frame matches data_pipeline.understat._COLS so downstream code is
source-agnostic.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from data_pipeline.understat import _COLS

_BASE = "https://v3.football.api-sports.io"
_CACHE = Path("data/api_football")
_FINISHED = {"FT", "AET", "PEN"}          # completed match statuses
_HDR_KEY = "x-apisports-key"

# Our league slug → (API-Football league id, [seasons]). IDs are confirmed live
# via `find_league_id()` before the first real build (see the plan's Task 9/10).
LEAGUE: dict[str, tuple[int, list[int]]] = {
    # IDs confirmed live via find_league_id (2026-07-11). CPL is the only league
    # that depends on API-Football (not on football-data OR ESPN). The FREE plan
    # only serves seasons 2022–2024, so CPL ships results-only off the latest free
    # season (2024); widen this range once a paid plan unlocks the current season.
    # Finland/Poland are NOT here — their results+odds come from current
    # football-data and they ship results-only (the free tier can't serve their
    # 2026 upcoming fixtures anyway).
    "canadian-pl":            (479, [2022, 2023, 2024]),
    # Round 5 (2026-07-14): K League 1 (South Korea) has NO working ESPN slug
    # (kor.1 / kor.k1 / k.league.1 all confirmed live to return 0 teams) and
    # is not on football-data.co.uk. Ships results-only off the free plan's
    # 2022-2024 seasons, same treatment as CPL.
    "k-league-1":             (292, [2022, 2023, 2024]),
}

# Some leagues' /fixtures response mixes in a promotion/relegation playoff vs a
# team from the tier below (not part of the league table). Found in K League 1
# (id 292): every season carries a bare "Relegation Round" fixture (no dash-
# number, distinct from the real "Relegation Round - N" bottom-6 split games)
# that pits K League 1's relegation-round loser against a K League 2 side —
# confirmed by diffing round-by-round team sets across all 3 free seasons
# (2022-2024), each of which has exactly 12 real K League 1 teams in "Regular
# Season" rounds plus exactly one extra name appearing ONLY in the bare
# "Relegation Round". Excluded by exact round-name match so standings don't
# pick up a 13th team for a handful of matches.
ROUND_EXCLUDE: dict[int, set[str]] = {
    292: {"Relegation Round"},
}

# Some leagues' /fixtures response uses inconsistent team names for the SAME
# club within one season. Found in K League 1's 2022 season: the military
# rotation club is "Sangju Sangmu FC" in every "Regular Season" fixture but
# "Gimcheon Sangmu FC" (its 2023+ name, after relocating cities) in that
# season's "Relegation Round - N" fixtures — an API-side data artifact, not a
# real name change mid-season. Renamed at parse time so 2022 doesn't split one
# club's record across two identities. Keyed by (af_id, season).
TEAM_RENAME: dict[tuple[int, int], dict[str, str]] = {
    (292, 2022): {"Gimcheon Sangmu FC": "Sangju Sangmu FC"},
}


# ── auth ─────────────────────────────────────────────────────────────────────
def _load_dotenv() -> None:
    """Best-effort load of a gitignored repo-root .env (python-dotenv if present,
    else a tiny manual parser). No-op if the file is absent."""
    if os.environ.get("API_FOOTBALL_KEY"):
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except Exception:  # noqa: BLE001 — fall back to manual parse
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _require_key() -> str:
    _load_dotenv()
    k = os.environ.get("API_FOOTBALL_KEY")
    if not k:
        raise RuntimeError(
            "API_FOOTBALL_KEY not set. Add it to a gitignored repo-root .env "
            "(API_FOOTBALL_KEY=...) or export it. Free key: https://www.api-sports.io/"
        )
    return k


def _get(path: str, params: dict, budget: str = "ops") -> dict:
    from data_pipeline import api_budget
    from data_pipeline.source_health import record_fetch
    # Fails closed BEFORE the request: a refusal makes no request and records
    # no spend. `budget` is "ops" for refresh paths, "backfill" for bulk jobs —
    # separate allowances, so a backfill can never eat the refresh's capacity.
    api_budget.check_budget(budget)
    try:
        r = requests.get(f"{_BASE}/{path}", headers={_HDR_KEY: _require_key()},
                         params=params, timeout=30)
        r.raise_for_status()
        payload = r.json()
        errs = payload.get("errors")
        if errs:  # API-Football returns 200 with an errors object on quota/plan issues
            raise RuntimeError(f"API-Football error for {path} {params}: {errs}")
    except Exception as e:
        # Quota exhaustion arrives as a 200 with an `errors` object, so it is
        # indistinguishable from success at the HTTP layer and would otherwise
        # never appear in source_health. On the free plan that is 100 requests
        # a day, which a single backfill can spend. (2026-08-08)
        record_fetch("api_football", path, ok=False, error=str(e))
        raise
    record_fetch("api_football", path, ok=True,
                 raw=len(payload.get("response") or []))
    # After recording (the request really happened and counts as spend):
    # the silent-lapse guard — headers disagreeing with the configured plan
    # must be an outage, never a quiet regression to Free's 2024-capped data.
    api_budget.assert_plan(getattr(r, "headers", None) or {})
    # Firewall-safe pacing: ≤50% of the plan's per-minute limit, every call.
    time.sleep(api_budget.throttle_delay())
    return payload


def _get_paged(path: str, params: dict, budget: str = "ops") -> dict:
    """Follow `paging {current, total}` and return one payload with the full
    merged `response` list. Built blind per Stage 0 — a 232-fixture season
    measured unpaged, but whether a 552-fixture one pages is a Stage-1
    question, and the handling must exist before it is answered."""
    payload = _get(path, params, budget=budget)
    paging = payload.get("paging") or {}
    total = int(paging.get("total") or 1)
    page = int(paging.get("current") or 1)
    while page < total:
        page += 1
        nxt = _get(path, {**params, "page": page}, budget=budget)
        payload["response"].extend(nxt.get("response") or [])
        total = int((nxt.get("paging") or {}).get("total") or total)
    if "paging" in payload:
        payload["paging"] = {"current": 1, "total": 1}
    return payload


def find_league_id(search: str) -> list[dict]:
    """Look up candidate league ids by name — used once to confirm LEAGUE ids."""
    resp = _get("leagues", {"search": search}).get("response", [])
    return [{"id": r["league"]["id"], "name": r["league"]["name"],
             "country": r["country"]["name"], "type": r["league"]["type"]}
            for r in resp]


# ── parsing ──────────────────────────────────────────────────────────────────
def _parse_fixtures(payload: dict, exclude_rounds: set[str] | None = None,
                     af_id: int | None = None) -> pd.DataFrame:
    """API-Football /fixtures response → canonical _COLS frame.

    `exclude_rounds` drops fixtures whose exact `league.round` string matches
    (see ROUND_EXCLUDE) — used to strip cross-tier playoff fixtures that
    aren't part of the league table. `af_id` (with the row's season) looks up
    TEAM_RENAME to fix same-club naming inconsistencies within one season.
    """
    rows = []
    for f in payload.get("response", []):
        if exclude_rounds and f.get("league", {}).get("round") in exclude_rounds:
            continue
        fx, teams, goals = f["fixture"], f["teams"], f.get("goals", {})
        st = fx.get("status", {}).get("short", "")
        is_result = st in _FINISHED
        season = int(f["league"]["season"])
        dt = pd.to_datetime(fx.get("date"), utc=True, errors="coerce")
        date = dt.tz_localize(None).normalize() if pd.notna(dt) else pd.NaT
        rename = TEAM_RENAME.get((af_id, season), {}) if af_id is not None else {}
        ht = rename.get(teams["home"]["name"], teams["home"]["name"])
        at = rename.get(teams["away"]["name"], teams["away"]["name"])
        hg = goals.get("home") if is_result else None
        ag = goals.get("away") if is_result else None
        label = np.nan
        if is_result and hg is not None and ag is not None:
            label = 0.0 if hg > ag else (1.0 if hg == ag else 2.0)
        rows.append({
            "match_id": f"apif-{season}-{ht}-{at}-{fx.get('id')}".replace(" ", "_"),
            "date": date, "season": season,
            "home_team": ht, "away_team": at,
            "home_goals": float(hg) if hg is not None else np.nan,
            "away_goals": float(ag) if ag is not None else np.nan,
            "home_xg": np.nan, "away_xg": np.nan,
            "label_result": label,
            "is_result": bool(is_result),
            "is_playoff": 0,
        })
    df = pd.DataFrame(rows, columns=_COLS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["season"] = df["season"].astype(int)
        df["is_result"] = df["is_result"].astype(bool)
    return df


def _fetch_league(af_id: int, seasons: list[int]) -> pd.DataFrame:
    _CACHE.mkdir(parents=True, exist_ok=True)
    latest = max(seasons) if seasons else None
    exclude = ROUND_EXCLUDE.get(af_id)
    frames = []
    for s in seasons:
        cache = _CACHE / f"{af_id}_{s}.json"
        if cache.exists() and s != latest:
            payload = json.loads(cache.read_text())
        else:
            # _get paces every request at the plan throttle, so no extra sleep.
            payload = _get_paged("fixtures", {"league": af_id, "season": s})
            cache.write_text(json.dumps(payload))
        frames.append(_parse_fixtures(payload, exclude, af_id))
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=_COLS)
    return (pd.concat(frames, ignore_index=True)
            .sort_values("date").reset_index(drop=True))


# ── public API ───────────────────────────────────────────────────────────────
def results_frame(league_id: str) -> pd.DataFrame:
    """Full canonical frame (played + scheduled) across all configured seasons."""
    af_id, seasons = LEAGUE[league_id]
    return _fetch_league(af_id, seasons)


def upcoming_fixtures(league_id: str) -> pd.DataFrame:
    """Not-yet-played fixtures for the latest configured season."""
    af_id, seasons = LEAGUE[league_id]
    df = _fetch_league(af_id, [max(seasons)]) if seasons else pd.DataFrame(columns=_COLS)
    return df[~df["is_result"]].copy() if not df.empty else df


def team_logos(league_id: str) -> dict[str, dict]:
    """{team_name: {logo, color}} from API-Football's /teams endpoint (crests for
    leagues with no ESPN stub, e.g. Canadian PL). One request for the latest season."""
    af_id, seasons = LEAGUE[league_id]
    if not seasons:
        return {}
    cache = _CACHE / f"teams_{af_id}_{max(seasons)}.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        payload = _get_paged("teams", {"league": af_id, "season": max(seasons)})
        _CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))
    out: dict[str, dict] = {}
    for t in payload.get("response", []):
        team = t.get("team", {})
        name = team.get("name")
        if name:
            out[name] = {"logo": team.get("logo"), "color": None}
    return out
