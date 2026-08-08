"""ESPN adapter for continental competitions (results + fixtures).

Mirrors data_pipeline/espn_soccer.py but for a continental slug (e.g.
'uefa.champions'). Parquet-cached under data/espn_continental/<comp>.parquet.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.http import espn_get

logger = logging.getLogger("espn_continental")

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_CACHE_DIR = Path("data/espn_continental")

# Internal comp id -> ESPN slug.
SLUGS = {
    "ucl": "uefa.champions", "europa": "uefa.europa",
    "conference": "uefa.europa.conf", "concacaf-champions": "concacaf.champions",
    "leagues-cup": "concacaf.leagues.cup",
    # Round 6 calibration (2026-07-24). CONMEBOL + AFC continental comps, added
    # alongside the fitted league-offset scales that make their cross-league
    # probabilities meaningful (see scripts/eval/league_bridge.py).
    "libertadores": "conmebol.libertadores",
    "sudamericana": "conmebol.sudamericana",
    "afc-champions": "afc.champions",
    # FIFA Club World Cup (2026-07-26). NOT a league we publish — this is the
    # only competition in the dataset where clubs from different CONFEDERATIONS
    # actually play each other, so it is the evidence that links the four
    # separately-anchored league-offset scales into one comparable ladder.
    # 133 completed matches 2015-2025, 64 of them from the expanded 32-club 2025
    # edition. See scripts/eval/interconf_calibrate.py.
    "club-world-cup": "fifa.cwc",
}

# Comps whose season is a CALENDAR YEAR rather than the Aug–May straddle the
# default window assumes. Verified 2026-07-24 from monthly event histograms:
# both CONMEBOL comps run Feb–Nov of a single year (2024 and 2025 both show
# Feb/Mar–Nov with a hard Dec–Jan gap), so the default Jul–Jun window would cut
# each edition in half and label the two pieces as different seasons — the group
# stage landing in season N-1 and the knockouts in season N. AFC Champions
# League Elite is a genuine Sep–May straddle (Sep–Dec then Feb–May) and stays on
# the default window.
# club-world-cup: every edition sits inside one calendar year — December for the
# old 7-club format, June-July for the expanded 2025 one — so the Aug-May window
# would split an edition across two "seasons".
CALENDAR_YEAR_COMPS = {"libertadores", "sudamericana", "club-world-cup"}

# Earliest season a competition existed, where that is later than the default
# window. Only competitions whose founding date is certain are listed — the
# caches cannot be used to infer this, because a cache holds the seasons ESPN
# happened to ANSWER for, not the seasons that exist (the UCL cache starts at
# 2021 for a competition that is decades old).
_DEFAULT_FIRST_SEASON = 2018
_FIRST_SEASON = {
    "leagues-cup": 2023,   # owner-confirmed 2026-08-08
    "conference": 2021,    # UEFA Conference League's first edition was 2021-22
}


def _fetch(slug: str, y0: int, y1: int, calendar_year: bool = False) -> list[dict]:
    url = f"{_BASE}/{slug}/scoreboard"
    # Date window: season runs ~Aug–May; end at Jun 30 (not Jul 1 — ESPN rejects
    # {y+1}0701 for some seasons with HTTP 400). Calendar-year comps instead take
    # Jan 1–Dec 31 of y0.
    if calendar_year:
        params = {"dates": f"{y0}0101-{y0}1231", "limit": 500}
    else:
        params = {"dates": f"{y0}0701-{y1}0630", "limit": 500}
    try:
        events = espn_get(url, params).get("events", [])
    except Exception as e:
        # None, not []. A caller cannot otherwise tell "this season genuinely had
        # no matches" from "ESPN returned 403", and the cache merge below has to
        # tell them apart — treating a failure as an empty season deletes that
        # season's cached evidence permanently. (2026-08-07)
        logger.warning("ESPN %s %s fetch FAILED (season not refreshed): %s", slug, y0, e)
        _record(slug, y0, ok=False, raw=0, error=str(e))
        return None
    _record(slug, y0, ok=True, raw=len(events))
    return events


def _record(slug: str, season: int, ok: bool, raw: int, error: str | None = None) -> None:
    """Log this fetch to source_health.

    Called from `_fetch` rather than from each caller because that is the single
    choke point for every continental request — one call site covers all
    competitions and all seasons, successes and failures alike.

    Recording the FAILURES is the point. The recorder had only ever been called
    after a successful parse, so a feed going dark left no trace in
    source_health at all: on 2026-08-07 the Leagues Cup lost 9 of 9 seasons to
    403s and the only evidence was a warning line in a workflow log nobody was
    reading. (2026-08-08)
    """
    from data_pipeline.source_health import record_fetch
    record_fetch("espn_continental", f"{slug}/scoreboard?season={season}",
                 ok=ok, raw=raw, error=error)


def _parse(events: list[dict], season: int, completed_only: bool) -> list[dict]:
    rows = []
    for e in events:
        comps = e.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        done = comp.get("status", {}).get("type", {}).get("completed", False)
        if completed_only and not done:
            continue
        cs = comp.get("competitors", [])
        if len(cs) != 2:
            continue
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        ht = home.get("team", {}).get("displayName", "")
        at = away.get("team", {}).get("displayName", "")
        if not ht or not at:
            continue
        dt = pd.to_datetime(e.get("date"), utc=True, errors="coerce")
        rnd = e.get("season", {}).get("slug", "") or (comp.get("notes", [{}]) or [{}])[0].get("headline", "")
        rec = {
            "match_id": f"{season}-{ht}-{at}".replace(" ", "_"),
            "date": dt.normalize().tz_localize(None) if pd.notna(dt) else pd.NaT,
            "season": season, "round": rnd, "home_team": ht, "away_team": at,
            "neutral": bool(comp.get("neutralSite", False)),
            # ESPN team ids (2026-07-24). Names alone cannot resolve a continental
            # club to its domestic league in CONMEBOL: River Plate (Argentina) and
            # River Plate (Uruguay), Guaraní (Paraguay) and Guarani (Brazil Série B),
            # Portuguesa (Brazil) and Portuguesa (Venezuela), Llaneros (Colombia)
            # and Llaneros (Venezuela) are all distinct clubs sharing a normalized
            # name, and several meet in the same competition. The id is drawn from
            # the same ESPN namespace as each league's /teams endpoint, so it
            # resolves club identity exactly. Older caches predate these columns —
            # readers must use .get()/reindex rather than assume they exist.
            "home_id": str(home.get("team", {}).get("id") or "") or None,
            "away_id": str(away.get("team", {}).get("id") or "") or None,
        }
        if done:
            try:
                rec["home_goals"] = int(float(home.get("score") or 0))
                rec["away_goals"] = int(float(away.get("score") or 0))
            except (ValueError, TypeError):
                continue
            # ESPN sets `winner` on the advancing side, including penalty shootouts —
            # the only reliable way to resolve a level (PK-decided) tie/final.
            if home.get("winner"):
                rec["winner"] = ht
            elif away.get("winner"):
                rec["winner"] = at
            elif rec["home_goals"] != rec["away_goals"]:
                rec["winner"] = ht if rec["home_goals"] > rec["away_goals"] else at
            else:
                rec["winner"] = None
        else:
            rec["home_goals"] = np.nan
            rec["away_goals"] = np.nan
            rec["winner"] = None
        rec["is_result"] = bool(done)
        rows.append(rec)
    return rows


def continental_results(comp_id: str, seasons: range | None = None,
                        use_cache: bool = True) -> pd.DataFrame:
    """Completed continental matches for `comp_id`, filtered to `seasons` (start years).

    On a cache hit the full cache is loaded then FILTERED to `seasons` (None = all
    cached seasons). The filter is required: the cache may hold several editions, and
    a caller that wants one edition must not receive a season mix.

    When `use_cache=False`, fetches `seasons` (defaulting to 2018..current) and MERGES
    the fresh rows into any existing cache: old seasons not in the refetch window are
    retained, and the newly-fetched seasons replace their old counterparts (dedup on
    match_id keeping the fresh copy). This allows periodic "refresh current season" runs
    without dropping historical seasons from the cache.
    """
    slug = SLUGS[comp_id]
    cache = _CACHE_DIR / f"{comp_id}.parquet"
    if use_cache and cache.exists():
        df = pd.read_parquet(cache)
    else:
        # Never ask for a season the competition did not exist in. The window
        # starts at 2018 for everything, so the Leagues Cup — founded 2023 —
        # was requesting 2018 through 2022 on every refresh: five requests that
        # can never return a row, against an API that rate-limits by IP and then
        # refuses EVERY endpoint for a while. Run 31234585894 fetched nine
        # seasons for it and lost all nine to 403s. (Owner, 2026-08-08:
        # "leagues cup began in 2023".) Applied to a caller-supplied range too,
        # so `--from-year 2018` is clamped rather than obeyed.
        first = _FIRST_SEASON.get(comp_id, _DEFAULT_FIRST_SEASON)
        fetch_range = (range(max(seasons.start, first), seasons.stop)
                       if seasons is not None else range(first, 2027))
        frames = []
        refreshed: set[int] = set()      # seasons ESPN actually answered for
        failed: list[int] = []
        # A COMPLETED season's results are immutable. Refetching them every run
        # spent most of the request budget re-learning facts that cannot change:
        # eight continental slugs cost 19 requests each in the 2026-08-08
        # rebuild, against ~12 for a typical league. Only the current season and
        # the one before it can still move (a late-finishing edition, a
        # corrected scoreline), so anything older that is already cached is
        # skipped and carried through the merge below untouched. `use_cache`
        # False still means "re-derive from the network" for everything that can
        # actually change. (2026-08-08)
        cached_seasons: set[int] = set()
        if cache.exists():
            try:
                cached_seasons = set(pd.read_parquet(cache)["season"].unique().tolist())
            except Exception as exc:     # corrupt cache → refetch everything
                logger.debug("%s: cache unreadable, refetching all: %s", comp_id, exc)
        newest = max(fetch_range) if len(fetch_range) else 0
        for y in fetch_range:
            if y in cached_seasons and y < newest - 1:
                continue                 # settled history, already held
            events = _fetch(slug, y, y + 1,
                            calendar_year=comp_id in CALENDAR_YEAR_COMPS)
            if events is None:           # transport failure — NOT an empty season
                failed.append(y)
                time.sleep(0.25)
                continue
            refreshed.add(y)
            rows = _parse(events, y, completed_only=True)
            if rows:
                frames.append(pd.DataFrame(rows))
            time.sleep(0.25)
        fresh = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        # Merge with the existing cache. A season is only allowed to be REPLACED
        # if ESPN answered for it; anything else is retained.
        #
        # This used to key on `set(fetch_range)`, which is every season the cache
        # can hold — so "keep all old seasons NOT in the refetch window" kept
        # nothing, and any season whose fetch failed was dropped on the spot.
        # On 2026-08-07 06:32 a refresh hit 403s and all three UEFA competitions
        # silently lost season 2025: the cross-league evidence behind the global
        # ladder fell from 743 matches to 528, with no error and no signal, and
        # the next bridge refit would have re-fitted every league offset on the
        # smaller set as though nothing had happened. Cache erosion from a
        # transient upstream failure is the worst kind of data bug — it is
        # invisible, it is permanent, and it moves published numbers.
        if cache.exists():
            existing = pd.read_parquet(cache)
            old_kept = existing[~existing["season"].isin(refreshed)]
            if not fresh.empty:
                combined = pd.concat([old_kept, fresh], ignore_index=True)
                # Dedup on match_id: keep last occurrence (fresh rows were appended last).
                df = combined.drop_duplicates(subset=["match_id"], keep="last").reset_index(drop=True)
            else:
                df = old_kept.reset_index(drop=True)
            if failed:
                kept = sorted(set(existing["season"]) & set(failed))
                logger.warning(
                    "espn_continental %s: %d season(s) failed to refresh (%s); "
                    "retained cached rows for %s",
                    comp_id, len(failed), failed, kept or "none")
        else:
            df = fresh
            if failed:
                logger.warning(
                    "espn_continental %s: no cache and %d season(s) failed (%s) "
                    "— cache built from a partial fetch", comp_id, len(failed), failed)

        if not df.empty:
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)

    if seasons is not None and not df.empty:
        df = df[df["season"].isin(list(seasons))].reset_index(drop=True)
    return df


def latest_season(comp_id: str) -> int | None:
    """Most recent season (start year) present in the cached results, or None."""
    df = continental_results(comp_id)
    return int(df["season"].max()) if not df.empty else None


def continental_fixtures(comp_id: str, season: int) -> pd.DataFrame:
    """Upcoming (undrawn ties absent) fixtures for the current season."""
    rows = _parse(_fetch(SLUGS[comp_id], season, season + 1,
                         calendar_year=comp_id in CALENDAR_YEAR_COMPS),
                 season, completed_only=False)
    df = pd.DataFrame(rows)
    return df[~df["is_result"]] if not df.empty else df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2025)
    a = ap.parse_args()
    df = continental_results(a.comp, range(a.from_year, a.to_year + 1), use_cache=False)
    print(f"{a.comp}: {len(df)} completed matches, "
          f"{df['season'].nunique() if not df.empty else 0} seasons")
    if not df.empty:
        print("\nColumns:", list(df.columns))
        print("\nSample rows:")
        print(df.head(10).to_string())
        print("\nUnique teams (sample):", sorted(
            set(df["home_team"].tolist() + df["away_team"].tolist())
        )[:20])
