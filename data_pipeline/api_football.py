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

import functools
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
# Per-league canonical name map: {league_slug: {api_football_name: our_name}}.
# Our names are the ESPN spellings the rest of the platform is keyed on
# (crests, team_metadata, payloads). Measured per league during Stage-3
# migration diffs — never typed from memory.
_NAMES_PATH = Path("config/api_football_team_names.json")
_FINISHED = {"FT", "AET", "PEN"}          # completed match statuses
_HDR_KEY = "x-apisports-key"

# Our league slug → (API-Football league id, [seasons]). IDs are confirmed live
# via `find_league_id()` before the first real build (see the plan's Task 9/10).
LEAGUE: dict[str, tuple[int, list[int]]] = {
    # IDs confirmed live via find_league_id (2026-07-11). CPL is the only league
    # that depends on API-Football (not on football-data OR ESPN).
    # Seasons widened 2026-08-08 on the paid plan (Mega): current seasons
    # unlock (2025/2026 — was capped at the free tier's 2024) AND deeper
    # history per the approved map (config/api_football_league_map.json —
    # CPL's catalogue depth starts 2020, K League 1's starts 2016).
    # Finland/Poland are NOT here — their results+odds come from current
    # football-data and they ship results-only.
    "canadian-pl":            (479, [2020, 2021, 2022, 2023, 2024, 2025, 2026]),
    # Round 5 (2026-07-14): K League 1 (South Korea) has NO working ESPN slug
    # (kor.1 / kor.k1 / k.league.1 all confirmed live to return 0 teams) and
    # is not on football-data.co.uk.
    # 2016/2017 deliberately excluded: 2017 is a measured data hole (15
    # fixtures, 6 teams) and 2016 would sit orphaned across the gap. 2018+ is
    # full (228/12 per season) — still four seasons deeper than the free tier.
    "k-league-1":             (292, [2018, 2019, 2020, 2021,
                                     2022, 2023, 2024, 2025, 2026]),
    # ── Stage 3, batch 1 (2026-08-08): smallest Tier A leagues, migrated from
    # ESPN with the spine primary and ESPN as registry fallback. Ids and season
    # depth from the owner-approved map; team names normalized to ESPN spelling
    # via config/api_football_team_names.json.
    "northern-super-league":  (1182, [2025, 2026]),
    "usl-super-league":       (1130, [2024, 2025, 2026]),
    # HELD — not routed (no source_registry entry): spine history is 2016+ vs
    # ESPN's 2015+, and 4/110 diffed scorelines disagreed. Entry retained for
    # the statistics backfill and a future adjudicated migration.
    "costa-rica-primera":     (162, [2016, 2017, 2018, 2019, 2020, 2021,
                                     2022, 2023, 2024, 2025, 2026]),
    # MLS is NOT built by build_league_data (it is not in OUTLOOK) — it comes
    # out of build_dashboard_data off the ASA adapter, with ESPN supplying the
    # schedule. This entry exists so that schedule can fall back to the spine
    # when ESPN is dark (spec §3.1); ASA stays primary for results, ESPN stays
    # primary for the schedule. Id 253 from the owner-approved map
    # (config/api_football_league_map.json), whose catalogue depth for MLS is
    # 2012+; only the current season is ever requested here.
    #
    # The season list is NOT read by the routed schedule path — `schedule_rows`
    # takes the season its caller was invoked with (build_dashboard_data's
    # --season), so a stale entry here cannot make the dashboard fetch the
    # wrong year. It is present for the `fetch_spine_scoreboard` shape and for
    # `results_frame`, neither of which MLS uses today.
    "mls":                    (253, [2026]),
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
    # K League 1: the cross-tier promotion/relegation playoff vs a K League 2
    # side is round "Relegation Round" (bare, 2022–2024) or "Final" (2019,
    # 2025 — measured 2026-08-08: those rounds' only non-league teams are
    # K League 2 sides Busan I Park / Bucheon FC 1995 / Suwon Bluewings).
    # The dash-numbered "Championship/Relegation Round - N" split fixtures are
    # real league games and stay.
    292: {"Relegation Round", "Final"},
}

# Some leagues' /fixtures response uses inconsistent team names for the SAME
# club within one season, or a club renames across seasons and would split its
# record into two identities. Keyed by (af_id, season); unification is FORWARD,
# to the club's current name, matching how the platform keys crests/metadata.
#
# K League 1's military rotation club: "Sangju Sangmu FC" through 2022 (the
# 2022 season mixes both spellings — regular season Sangju, relegation round
# Gimcheon), "Gimcheon Sangmu FC" from 2024 (city relocation; 2021/2023 spent
# in K League 2). One franchise, one identity: Gimcheon. The original
# 2026-07-14 fix unified 2022 toward Sangju, which was right for a 2022-2024
# window; with 2018+ history (2026-08-08) the current name wins.
TEAM_RENAME: dict[tuple[int, int], dict[str, str]] = {
    (292, 2018): {"Sangju Sangmu FC": "Gimcheon Sangmu FC"},
    (292, 2019): {"Sangju Sangmu FC": "Gimcheon Sangmu FC"},
    (292, 2020): {"Sangju Sangmu FC": "Gimcheon Sangmu FC"},
    (292, 2022): {"Sangju Sangmu FC": "Gimcheon Sangmu FC"},
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
        # Endpoint carries the budget kind so spend can be counted PER
        # ALLOWANCE — without it a backfill's spend also exhausts the ops
        # budget, which is the coupling the two allowances exist to prevent.
        record_fetch("api_football", f"{budget}:{path}", ok=False, error=str(e))
        raise
    record_fetch("api_football", f"{budget}:{path}", ok=True,
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


# ── identity validation (spec §2 R1) ─────────────────────────────────────────
class IdentityMismatch(RuntimeError):
    """A response (or a cache hit) declares a different league/season than the
    one requested. Raised rather than filtered: a provider that answers with
    the wrong competition is not a source we can silently repair, and defect #4
    (`segunda` → La Liga's id) shipped 1,140 sheets of the wrong division while
    reporting 100% coverage."""


def assert_fixture_identity(payload: dict, af_id: int,
                            season: int | None = None) -> None:
    """Assert every fixture in a /fixtures payload declares the requested
    league id (and season, when one was requested).

    Validated on cache READ as well as on fetch: the poisoned football-data
    `SP2` file was already on disk when it was found, so write-time validation
    alone leaves a wrong artifact serving forever.
    """
    bad_league: set[int | None] = set()
    bad_season: set[int | None] = set()
    for f in payload.get("response") or []:
        league = f.get("league") or {}
        got_id = league.get("id")
        try:
            got_id = int(got_id) if got_id is not None else None
        except (TypeError, ValueError):
            got_id = None
        if got_id != int(af_id):
            bad_league.add(got_id)
        if season is not None:
            got_season = league.get("season")
            try:
                got_season = int(got_season) if got_season is not None else None
            except (TypeError, ValueError):
                got_season = None
            if got_season != int(season):
                bad_season.add(got_season)
    problems = []
    if bad_league:
        problems.append(f"league id {sorted(map(str, bad_league))} != {af_id}")
    if bad_season:
        problems.append(f"season {sorted(map(str, bad_season))} != {season}")
    if problems:
        raise IdentityMismatch(
            "API-Football /fixtures identity mismatch: " + "; ".join(problems))


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
            assert_fixture_identity(payload, af_id, s)      # R1: validate on read
        else:
            # _get paces every request at the plan throttle, so no extra sleep.
            payload = _get_paged("fixtures", {"league": af_id, "season": s})
            assert_fixture_identity(payload, af_id, s)      # before it is cached
            cache.write_text(json.dumps(payload))
        frames.append(_parse_fixtures(payload, exclude, af_id))
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=_COLS)
    return (pd.concat(frames, ignore_index=True)
            .sort_values("date").reset_index(drop=True))


# ── public API ───────────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=1)
def _team_names() -> dict[str, dict[str, str]]:
    """Load the per-league canonical name map (empty when absent)."""
    try:
        return json.loads(_NAMES_PATH.read_text())
    except FileNotFoundError:
        return {}


def _apply_names(df: pd.DataFrame, league_id: str) -> pd.DataFrame:
    names = _team_names().get(league_id)
    if not names or df.empty:
        return df
    for col in ("home_team", "away_team"):
        df[col] = df[col].map(lambda n: names.get(n, n))
    return df


def results_frame(league_id: str) -> pd.DataFrame:
    """Full canonical frame (played + scheduled) across all configured seasons,
    with team names normalized to our canonical (ESPN) spellings."""
    af_id, seasons = LEAGUE[league_id]
    return _apply_names(_fetch_league(af_id, seasons), league_id)


def upcoming_fixtures(league_id: str) -> pd.DataFrame:
    """Not-yet-played fixtures for the latest configured season."""
    af_id, seasons = LEAGUE[league_id]
    df = _fetch_league(af_id, [max(seasons)]) if seasons else pd.DataFrame(columns=_COLS)
    df = _apply_names(df, league_id)
    return df[~df["is_result"]].copy() if not df.empty else df


# Provider status → the three-state ESPN `status.type.state` the dashboard
# builder branches on. Anything not finished and not in play is "pre", which is
# the state that makes a fixture count as remaining.
_STATE_POST = _FINISHED
_STATE_IN = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}


def schedule_rows(league_id: str, season: int) -> list[dict]:
    """One season's fixtures with the fields a *schedule* needs — kickoff,
    venue and venue city — which the canonical `_COLS` frame does not carry.

    Exists for MLS (spec §3.1): `build_dashboard_data` takes its schedule from
    ESPN, and when ESPN 403s the flagship league stops rebuilding entirely.
    The row shape mirrors `build_dashboard_data.espn_schedule` so either source
    can answer, and team names are mapped through the same per-league canonical
    map the rest of the spine uses.

    Not cached: a schedule is only ever wanted for the live season, where
    `_fetch_league`'s cache would be bypassed anyway.
    """
    af_id, _ = LEAGUE[league_id]
    payload = _get_paged("fixtures", {"league": af_id, "season": int(season)})
    assert_fixture_identity(payload, af_id, int(season))
    names = _team_names().get(league_id, {})
    exclude = ROUND_EXCLUDE.get(af_id) or set()
    rows = []
    for f in payload.get("response") or []:
        league, fx = f.get("league") or {}, f.get("fixture") or {}
        if league.get("round") in exclude:
            continue
        teams = f.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        if not home or not away:
            continue
        short = (fx.get("status") or {}).get("short") or ""
        state = ("post" if short in _STATE_POST
                 else "in" if short in _STATE_IN else "pre")
        goals = f.get("goals") or {}
        hg = ag = None
        if state == "post":
            try:
                hg, ag = int(goals.get("home")), int(goals.get("away"))
            except (TypeError, ValueError):
                hg = ag = None
        venue = fx.get("venue") or {}
        ko = fx.get("date")
        rows.append({
            "date": str(ko)[:10] if ko else None,
            "home": names.get(home, home),
            "away": names.get(away, away),
            "state": state,
            "home_goals": hg,
            "away_goals": ag,
            "ko_utc": ko or None,
            "venue": venue.get("name") or None,
            "venue_city": venue.get("city") or None,
        })
    return rows


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
    names = _team_names().get(league_id, {})
    out: dict[str, dict] = {}
    for t in payload.get("response", []):
        team = t.get("team", {})
        name = team.get("name")
        if name:
            # Keyed by our canonical spelling so crest lookups match the frame.
            out[names.get(name, name)] = {"logo": team.get("logo"), "color": None}
    return out
