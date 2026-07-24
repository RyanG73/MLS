"""ESPN schedule adapter for European leagues — upcoming-season FIXTURES only.

Understat doesn't publish a European season until ~August; ESPN has the official
schedule earlier. This returns the canonical UPCOMING rows (no results/xG) used to
drive pre-season projections; xG-based data resumes from Understat once it publishes.

Schema mirrors data_pipeline.understat._COLS:
    match_id, date, season, home_team, away_team,
    home_goals, away_goals, home_xg, away_xg,
    label_result (0 home / 1 draw / 2 away), is_result, is_playoff

For completed matches: is_result=True, goals filled, label_result set.
For scheduled matches: is_result=False, home_goals/away_goals/label_result=NaN.

Usage:
    python -m data_pipeline.espn_fixtures --league epl --season 2026
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.http import espn_get
from data_pipeline.understat import _COLS, _coerce

logger = logging.getLogger("espn_fixtures")

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_CACHE_DIR = Path("data/espn_fixtures")

# Platform league id → ESPN slug.
SLUGS = {
    "epl":        "eng.1",
    "la-liga":    "esp.1",
    "serie-a":    "ita.1",
    "bundesliga": "ger.1",
    "ligue-1":    "fra.1",
    # C2 (ASA leagues): played rows come from ASA; ESPN supplies the
    # scheduled remainder of the season for the forward sim.
    "nwsl":             "usa.nwsl",
    "usl-championship": "usa.usl.1",
    # football-data leagues: ESPN supplies next-season fixtures for preseason
    # mode (names map ESPN→FD in build_league_data, the inverse of FD_ESPN —
    # NOT via ESPN_TO_UNDERSTAT, which is understat-key specific).
    "championship": "eng.2", "league-one": "eng.3", "league-two": "eng.4",
    "bundesliga-2": "ger.2", "serie-b": "ita.2",
    "segunda": "esp.2", "ligue-2": "fra.2",
    "eredivisie": "ned.1", "primeira": "por.1", "super-lig": "tur.1",
    "scottish-prem": "sco.1", "belgian-pro": "bel.1", "greek-super": "gre.1",
    "national-league": "eng.5",
    # Scottish lower tiers (2026-07-11, round 4): ESPN sco.2/3/4. Aug–May straddle
    # (not calendar-year), so no CALENDAR_YEAR_LEAGUES entry.
    "scottish-champ": "sco.2", "scottish-league-one": "sco.3",
    "scottish-league-two": "sco.4",
    # Tier-1 expansion (2026-07-10, docs/league-expansion-report.md): football-
    # data-intl leagues. poland-ekstraklasa has NO confirmed ESPN slug (probed
    # every plausible guess live) — omitted, ships results-only.
    "brazil-serie-a": "bra.1", "japan-j1": "jpn.1",
    "sweden-allsvenskan": "swe.1", "norway-eliteserien": "nor.1",
    "denmark-superliga": "den.1", "argentina-primera": "arg.1",
    # Round-4 Tier-1 (2026-07-11): footballdata_intl UEFA top flights.
    "austria-bundesliga": "aut.1", "swiss-super-league": "sui.1",
    "romania-liga1": "rou.1", "ireland-premier": "irl.1",
    # Round-4 projection-only, footballdata_intl (odds backbone retained):
    "china-super": "chn.1", "russia-premier": "rus.1",
    # Round-4 projection-only, ESPN goals-only (no football-data source). These
    # route through espn_results_frame; all are Aug/Sep/Oct–May straddles (not
    # calendar-year), so the default Jul–Jun window applies.
    "saudi-pro": "ksa.1", "australia-aleague": "aus.1", "wsl": "eng.w.1",
    # Round 5 (2026-07-14): South America + more Asia + Eerste Divisie. All
    # slugs verified live against the ESPN teams endpoint before use (kor.1 /
    # kor.k1 / k.league.1 tried for South Korea and confirmed to return 0
    # teams — K League 1 has no ESPN slug, see api_football.py instead).
    "chile-primera": "chi.1", "colombia-primera-a": "col.1",
    "uruguay-primera": "uru.1", "peru-liga1": "per.1",
    "thai-league-1": "tha.1", "eerste-divisie": "ned.2",
    # Round 6 (2026-07-24): the remainder of ESPN's soccer catalog that fits the
    # single-table model. Every slug below was diffed out of ESPN's own league
    # index (sports.core.api.espn.com/v2/sports/soccer/leagues?limit=1000, 220
    # entries) rather than guessed, then probed live for a non-zero team count.
    # Season shape per league was classified from a MONTHLY event histogram, not
    # a first/last-date span (round-5 Gotcha #1) — see CALENDAR_YEAR_LEAGUES.
    # CONMEBOL — remaining top flights + second tiers
    "ecuador-ligapro": "ecu.1", "paraguay-primera": "par.1",
    "bolivia-profesional": "bol.1", "venezuela-primera": "ven.1",
    "brazil-serie-b": "bra.2", "argentina-nacional": "arg.2",
    # Concacaf — Mexico/US second tiers + Central America
    "liga-expansion-mx": "mex.2", "usl-league-one": "usa.usl.l1",
    "costa-rica-primera": "crc.1", "honduras-liga": "hon.1",
    "guatemala-liga": "gua.1", "elsalvador-primera": "slv.1",
    # CAF / AFC
    "south-africa-psl": "rsa.1", "india-isl": "ind.1",
    # Women's leagues (projections-only family — the wsl/nwsl precedent)
    "liga-f": "esp.w.1", "france-premiere-ligue": "fra.w.1",
    "vrouwen-eredivisie": "ned.w.1", "australia-aleague-women": "aus.w.1",
    "northern-super-league": "can.w.nsl", "usl-super-league": "usa.w.usl.1",
}

# Leagues whose season is a calendar year (dates window Jan–Dec of `season`)
# rather than the European Jul–Jun straddle. Verified live per league (window
# probe against ESPN's scoreboard, 2026-07-10): Brazil/Japan/Sweden/Norway run
# Jan-Dec; Argentina's Liga Profesional moved to a calendar-year single table
# in recent seasons (matches its football-data "Season" column, which is also
# plain-year for 2024+); Denmark keeps the Aug-May straddle like Europe.
CALENDAR_YEAR_LEAGUES = {"nwsl", "usl-championship",
                         "brazil-serie-a", "japan-j1", "sweden-allsvenskan",
                         "norway-eliteserien", "argentina-primera",
                         # Round-4: Ireland's LOI Premier runs Feb–Nov (calendar
                         # year). Austria/Switzerland/Romania keep the Aug–May straddle.
                         "ireland-premier",
                         # China Super League runs Mar–Nov (calendar year); Russia
                         # keeps the Aug–May straddle.
                         "china-super",
                         # Round 5 (2026-07-14): South American top flights run
                         # calendar-year (Feb/Jan–Dec, verified live via monthly
                         # event-count probes). Thai League 1 and Eerste Divisie
                         # are Aug–May straddles (probe showed a May–Aug gap for
                         # both) — intentionally NOT in this set.
                         "chile-primera", "colombia-primera-a",
                         "uruguay-primera", "peru-liga1",
                         # Round 6 (2026-07-24): classified from a monthly event
                         # histogram over 2025 (round-5 Gotcha #1 — a first/last
                         # date span misclassifies straddles). Continuous through
                         # the year with no Jun–Jul off-season gap:
                         #   ecu Feb–Dec · par Jan–Nov · bol Mar–Dec · ven Jan–Dec
                         #   bra.2 Apr–Nov · arg.2 Feb–Nov · usl-l1 Mar–Nov
                         #   can.w.nsl Apr–Nov
                         "ecuador-ligapro", "paraguay-primera",
                         "bolivia-profesional", "venezuela-primera",
                         "brazil-serie-b", "argentina-nacional",
                         "usl-league-one", "northern-super-league"}
# Deliberately NOT calendar-year (the histogram showed a clear off-season gap, so
# the default Jul–Jun window is correct): liga-expansion-mx (Jul gap — Apertura
# +Clausura, the liga-mx shape), costa-rica-primera / honduras-liga /
# guatemala-liga / elsalvador-primera (Jun gap — Apertura Aug–Dec + Clausura
# Jan–May), south-africa-psl (Jun–Jul), india-isl, liga-f (Jun–Jul),
# france-premiere-ligue / vrouwen-eredivisie (Jun–Aug), australia-aleague-women
# (Jun–Sep, matching the men's A-League), usl-super-league (Aug–May).

# ESPN displayName → Understat team key, per league.
# Only names that DIFFER between the two sources need an entry.
# Promoted teams (no Understat EPL history) are left unmapped — they pass through
# as their ESPN name and pick up an ELO prior from the league mean.
ESPN_TO_UNDERSTAT: dict[str, dict[str, str]] = {
    "epl": {
        "AFC Bournemouth":       "Bournemouth",
        "Brighton & Hove Albion": "Brighton",
        "Hull City":             "Hull",
        "Ipswich Town":          "Ipswich",
        "Leeds United":          "Leeds",
        "Tottenham Hotspur":     "Tottenham",
        "West Ham United":       "West Ham",
    },
    "la-liga": {
        "Alavés":             "Alaves",
        "Atlético Madrid":    "Atletico Madrid",
        "Deportivo Alavés":   "Alaves",
    },
    "serie-a": {
        "AS Roma":           "Roma",
        "Internazionale":    "Inter",
        "Parma":             "Parma Calcio 1913",
        "Hellas Verona":     "Verona",
    },
    "bundesliga": {
        "FC Augsburg":                  "Augsburg",
        "Borussia Mönchengladbach":     "Borussia M.Gladbach",
        "1. FC Heidenheim 1846":        "FC Heidenheim",
        "SC Freiburg":                  "Freiburg",
        "Hamburg SV":                   "Hamburger SV",
        "TSG Hoffenheim":               "Hoffenheim",
        "Mainz":                        "Mainz 05",
        # RB Leipzig: no entry needed — ESPN's name already matches the
        # canonical name (2026-07-12: canonical changed from "RasenBallsport
        # Leipzig" to "RB Leipzig", see data_pipeline/understat.py).
        "1. FC Union Berlin":           "Union Berlin",
        "VfL Wolfsburg":                "Wolfsburg",
    },
    "ligue-1": {
        "AJ Auxerre":          "Auxerre",
        "AS Monaco":           "Monaco",
        "Le Havre AC":         "Le Havre",
        "Paris Saint-Germain": "Paris Saint Germain",
        "Stade Rennais":       "Rennes",
    },
    # ASA leagues: ESPN displayName → ASA team_name (frame keys).
    "nwsl": {
        "Gotham FC":   "NJ/NY Gotham FC",
        "Utah Royals": "Utah Royals FC",
    },
    "usl-championship": {
        "Lexington":              "Lexington SC",
        "Miami FC":               "The Miami FC",
        "Monterey Bay":           "Monterey Bay FC",
        "Oakland Roots":          "Oakland Roots SC",
        "Pittsburgh Riverhounds": "Pittsburgh Riverhounds SC",
        "Sporting JAX":           "Sporting Club Jacksonville",
    },
}


def _to_understat(league_id: str, espn_name: str) -> str:
    """Map an ESPN displayName to the Understat team key for `league_id`.

    If the name is not in the map (either it already matches Understat, or it is
    a newly promoted team with no Understat history), the ESPN name is returned
    unchanged.
    """
    return ESPN_TO_UNDERSTAT.get(league_id, {}).get(espn_name, espn_name)


def _fetch_events(slug: str, season: int, calendar_year: bool = False) -> list[dict]:
    """Fetch all events (played + scheduled) for `slug` in one season.

    European seasons straddle Jul Y – Jun Y+1; calendar-year leagues
    (NWSL, USL) run Jan–Dec of `season`.
    """
    url = f"{_BASE}/{slug}/scoreboard"
    y0, y1 = season, season + 1
    window = f"{y0}0101-{y0}1231" if calendar_year else f"{y0}0701-{y1}0630"
    # limit 1000: the English tiers run 552 fixtures/season — the old 500
    # silently truncated them.
    params = {"dates": window, "limit": 1000}
    try:
        return espn_get(url, params).get("events", [])
    except Exception as e:
        logger.warning("ESPN %s season=%s fetch failed: %s", slug, season, e)
        return []


def _parse_events(events: list[dict], league_id: str, season: int) -> list[dict]:
    """Parse ESPN events into canonical row dicts (played + scheduled)."""
    rows = []
    for e in events:
        comps = e.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        cs = comp.get("competitors", [])
        if len(cs) != 2:
            continue
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        espn_ht = home.get("team", {}).get("displayName", "")
        espn_at = away.get("team", {}).get("displayName", "")
        if not espn_ht or not espn_at:
            continue

        ht = _to_understat(league_id, espn_ht)
        at = _to_understat(league_id, espn_at)

        done = comp.get("status", {}).get("type", {}).get("completed", False)
        dt = pd.to_datetime(e.get("date"), utc=True, errors="coerce")
        date = dt.normalize().tz_localize(None) if pd.notna(dt) else pd.NaT
        venue = comp.get("venue") or {}

        rec: dict = {
            "match_id":    f"espn-{league_id}-{season}-{espn_ht}-{espn_at}".replace(" ", "_"),
            "date":        date,
            "season":      season,
            "home_team":   ht,
            "away_team":   at,
            "home_xg":     np.nan,
            "away_xg":     np.nan,
            "is_playoff":  0,
            # Match metadata (F1, 2026-07-09): kept OUTSIDE the canonical _COLS
            # contract as nullable extras — understat frames don't carry them.
            "ko_utc":      e.get("date") or None,          # full ISO kickoff
            "venue":       venue.get("fullName") or None,
            "venue_city":  (venue.get("address") or {}).get("city") or None,
        }

        if done:
            try:
                hg = int(float(home.get("score") or 0))
                ag = int(float(away.get("score") or 0))
            except (ValueError, TypeError):
                continue
            rec["home_goals"] = float(hg)
            rec["away_goals"] = float(ag)
            rec["label_result"] = 0.0 if hg > ag else (1.0 if hg == ag else 2.0)
            rec["is_result"] = True
        else:
            rec["home_goals"] = np.nan
            rec["away_goals"] = np.nan
            rec["label_result"] = np.nan
            rec["is_result"] = False

        rows.append(rec)
    return rows


def european_fixtures(league_id: str, season: int,
                      use_cache: bool = True) -> pd.DataFrame:
    """Return ALL matches (played + scheduled) for a European league season.

    Parameters
    ----------
    league_id : str
        One of the keys in SLUGS ("epl", "la-liga", "serie-a", "bundesliga",
        "ligue-1").
    season : int
        Start year of the season (e.g. 2026 for the 2026-27 campaign).
    use_cache : bool
        If True (default) and a cached parquet exists, load from disk.
        Pass False to force a live fetch (and refresh the cache).

    Returns
    -------
    pd.DataFrame
        Canonical frame with columns matching understat._COLS.  Team names are
        mapped to Understat keys so ELO history carries over.
    """
    if league_id not in SLUGS:
        raise ValueError(
            f"Unknown league '{league_id}'. Known: {', '.join(SLUGS)}"
        )

    cache = _CACHE_DIR / f"{league_id}-{season}.parquet"
    if use_cache and cache.exists():
        df = pd.read_parquet(cache)
        df["date"] = pd.to_datetime(df["date"])
        return df

    slug = SLUGS[league_id]
    events = _fetch_events(slug, season,
                           calendar_year=league_id in CALENDAR_YEAR_LEAGUES)
    rows = _parse_events(events, league_id, season)

    _META = ["ko_utc", "venue", "venue_city"]
    if rows:
        full = pd.DataFrame(rows)
        df = _coerce(full[_COLS])
        for c in _META:                      # re-attach non-canonical extras
            df[c] = full[c].values
    else:
        df = _coerce(pd.DataFrame(columns=_COLS))
        for c in _META:
            df[c] = pd.Series(dtype=object)

    df = df.sort_values("date").reset_index(drop=True)

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    logger.info(
        "ESPN fixtures %s %s: %d matches (%d scheduled, %d played) cached → %s",
        league_id, season,
        len(df),
        int((~df["is_result"]).sum()),
        int(df["is_result"].sum()),
        cache,
    )
    return df


def espn_results_frame(league_id: str, seasons=None) -> pd.DataFrame:
    """Canonical goals-only frame (played + scheduled) for an ESPN-sourced league.

    The generic analog of `liga_mx_frame` for leagues with no football-data / xG
    source (Saudi Pro League, A-League, WSL): loops `european_fixtures` across
    `seasons` and concatenates. liga-mx keeps its own torneo-specific frame; every
    other `source="espn"` league routes here.

    `seasons` defaults to 2015..current. Empty/failed seasons are skipped, so a
    league with shorter ESPN history (e.g. WSL) simply yields fewer rows. The
    latest season is fetched fresh; earlier seasons use the parquet cache.
    """
    if seasons is None:
        this_year = pd.Timestamp.now().year
        seasons = list(range(2015, this_year + 1))
    else:
        seasons = list(seasons)

    latest = max(seasons) if seasons else None
    frames: list[pd.DataFrame] = []
    for s in seasons:
        try:
            df = european_fixtures(league_id, s, use_cache=(s != latest))
        except Exception as e:  # noqa: BLE001
            logger.warning("espn_results_frame %s season=%s failed: %s", league_id, s, e)
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return _coerce(pd.DataFrame(columns=_COLS))
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", default="epl", choices=list(SLUGS),
                    help="League id (default: epl)")
    ap.add_argument("--season", type=int, default=2026,
                    help="Season start year (default: 2026)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignore parquet cache and re-fetch from ESPN")
    a = ap.parse_args()

    df = european_fixtures(a.league, a.season, use_cache=not a.no_cache)
    teams = sorted(set(df["home_team"]) | set(df["away_team"]))
    played = int(df["is_result"].sum())
    scheduled = int((~df["is_result"]).sum())
    print(f"{a.league} {a.season}: {len(df)} fixtures, {len(teams)} teams "
          f"({played} played, {scheduled} scheduled)")
    print("Teams:", teams)
