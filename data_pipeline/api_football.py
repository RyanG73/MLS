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
    # CPL: everything comes from API-Football → full history (launched 2019).
    "canadian-pl":            (468, list(range(2019, 2027))),
    # Finland: results+odds come from football-data; API-Football supplies only
    # UPCOMING fixtures, so we fetch just the current season (1 request/day).
    "finland-veikkausliiga":  (244, [2026]),
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


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{_BASE}/{path}", headers={_HDR_KEY: _require_key()},
                     params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()
    errs = payload.get("errors")
    if errs:  # API-Football returns 200 with an errors object on quota/plan issues
        raise RuntimeError(f"API-Football error for {path} {params}: {errs}")
    return payload


def find_league_id(search: str) -> list[dict]:
    """Look up candidate league ids by name — used once to confirm LEAGUE ids."""
    resp = _get("leagues", {"search": search}).get("response", [])
    return [{"id": r["league"]["id"], "name": r["league"]["name"],
             "country": r["country"]["name"], "type": r["league"]["type"]}
            for r in resp]


# ── parsing ──────────────────────────────────────────────────────────────────
def _parse_fixtures(payload: dict) -> pd.DataFrame:
    """API-Football /fixtures response → canonical _COLS frame."""
    rows = []
    for f in payload.get("response", []):
        fx, teams, goals = f["fixture"], f["teams"], f.get("goals", {})
        st = fx.get("status", {}).get("short", "")
        is_result = st in _FINISHED
        season = int(f["league"]["season"])
        dt = pd.to_datetime(fx.get("date"), utc=True, errors="coerce")
        date = dt.tz_localize(None).normalize() if pd.notna(dt) else pd.NaT
        ht, at = teams["home"]["name"], teams["away"]["name"]
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
    frames = []
    for s in seasons:
        cache = _CACHE / f"{af_id}_{s}.json"
        if cache.exists() and s != latest:
            payload = json.loads(cache.read_text())
        else:
            payload = _get("fixtures", {"league": af_id, "season": s})
            cache.write_text(json.dumps(payload))
            time.sleep(1)                      # gentle on the free tier
        frames.append(_parse_fixtures(payload))
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
        payload = _get("teams", {"league": af_id, "season": max(seasons)})
        _CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))
    out: dict[str, dict] = {}
    for t in payload.get("response", []):
        team = t.get("team", {})
        name = team.get("name")
        if name:
            out[name] = {"logo": team.get("logo"), "color": None}
    return out
