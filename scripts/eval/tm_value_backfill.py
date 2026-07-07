"""M2 (A10a revival): leakage-clean historical squad-value backfill from TM.

Gate-0 probe (2026-07-07) confirmed transfermarkt.com's `saison_id=<year>`
league pages serve ERA-APPROPRIATE team totals (GB1 2019: Man City €1,050m,
Liverpool €1,000m, Spurs €807m — matches 2019-20 reporting, not 2026 values),
so a historical backfill is walk-forward safe: the season page's values are
start-of-season vintage, exactly the preseason prior the experiment needs.

TEAM-LEVEL totals only (docs/data-sources.md rights register: player values
local-only; aggregates public with attribution). One page per league-season,
politely rate-limited, cached to data/transfermarkt_backfill/values.csv.

Names are TM's own; `map_to_fd()` resolves them to FD frame keys via the
importer's alias table + token-subset matching (unmatched teams drop — the
experiment tolerates missing values).
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/transfermarkt_backfill/values.csv")
_HDR = {"User-Agent": "Mozilla/5.0"}

TM_CODES = {"epl": "GB1", "la-liga": "ES1", "serie-a": "IT1",
            "bundesliga": "L1", "ligue-1": "FR1"}

# TM row pattern in the season-page club table: club title + total value cell.
_ROW = re.compile(r'title="([^"]+)".*?€([\d.]+)(bn|m)')


def fetch_league_season(tm_code: str, season: int) -> dict[str, float]:
    """{tm_team_name: squad_value_eur_m} for one league-season page."""
    url = (f"https://www.transfermarkt.com/x/startseite/wettbewerb/"
           f"{tm_code}/plus/?saison_id={season}")
    html = requests.get(url, headers=_HDR, timeout=30).text
    out: dict[str, float] = {}
    for name, val, unit in _ROW.findall(html[:250000]):
        v = float(val) * (1000.0 if unit == "bn" else 1.0)
        # club rows repeat (crest + name cells); first hit wins. The >20 floor
        # skips player-value cells that share the € pattern.
        if name not in out and v > 20:
            out[name] = v
    return out


def run_backfill(seasons=range(2017, 2026), sleep_s: float = 3.0) -> pd.DataFrame:
    rows = []
    done = set()
    if OUT.exists():
        prev = pd.read_csv(OUT)
        rows = prev.to_dict("records")
        done = {(r["league"], r["season"]) for r in rows}
    for lid, code in TM_CODES.items():
        for s in seasons:
            if (lid, s) in done:
                continue
            vals = fetch_league_season(code, s)
            for name, v in vals.items():
                rows.append({"league": lid, "season": s,
                             "tm_name": name, "value_eur_m": v})
            print(f"[{lid} {s}] {len(vals)} teams", flush=True)
            time.sleep(sleep_s)
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    return df


# TM full names → football-data short names the token matcher can't bridge.
TM_TO_FD = {
    "Manchester City": "Man City", "Manchester United": "Man United",
    "Wolverhampton Wanderers": "Wolves", "Nottingham Forest": "Nott'm Forest",
    "Atlético de Madrid": "Ath Madrid", "Athletic Bilbao": "Ath Bilbao",
    "Deportivo Alavés": "Alaves", "FC Barcelona": "Barcelona",
    "CD Leganés": "Leganes", "Cádiz CF": "Cadiz",
    "Inter Milan": "Inter", "Borussia Mönchengladbach": "M'gladbach",
    "Eintracht Frankfurt": "Ein Frankfurt", "1.FC Köln": "FC Koln",
    "Stade Rennais FC": "Rennes", "Stade Brestois 29": "Brest",
    "AS Saint-Étienne": "St Etienne", "Nîmes Olympique": "Nimes",
}


def _norm(s: str) -> set[str]:
    s = s.lower().replace("-", " ")
    drop = {"fc", "afc", "cf", "ac", "as", "ss", "ssc", "us", "sc", "rc",
            "rcd", "cd", "ca", "sv", "vfb", "vfl", "tsg", "sco", "ogc",
            "losc", "1899", "05", "04", "96", "09"}
    return {t for t in re.split(r"[^a-z0-9]+", s) if t and t not in drop}


def map_to_fd(values: pd.DataFrame, fd_teams_by_league: dict[str, set[str]],
              aliases: dict[str, str] | None = None) -> dict[tuple[str, str, int], float]:
    """{(league, fd_team, season): value_eur_m} via alias then token match."""
    aliases = aliases or {}
    out: dict[tuple[str, str, int], float] = {}
    for _, r in values.iterrows():
        lid, tm = r["league"], r["tm_name"]
        cands = fd_teams_by_league.get(lid, set())
        fd = aliases.get(tm)
        if fd is None:
            toks = _norm(tm)
            hits = [c for c in cands
                    if _norm(c) <= toks or toks <= _norm(c)]
            fd = hits[0] if len(hits) == 1 else None
        if fd and fd in cands:
            out[(lid, fd, int(r["season"]))] = float(r["value_eur_m"])
    return out
