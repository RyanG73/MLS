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

# Structural parse of the season-page club table.
#
# The original implementation was a single regex over raw HTML:
#     re.compile(r'title="([^"]+)".*?€([\d.]+)(bn|m)')
# with a `v > 20` floor meant to "skip player-value cells". It was wrong, and
# quietly so. A club row looks like this:
#
#   <td class="zentriert no-border-rechts"><a title="Bayern Munich" ...crest...
#   <td class="hauptlink no-border-links"><a title="Bayern Munich" ...name...
#   <td class="zentriert"><a title="Bayern Munich" ...>38</a></td>   squad size
#   <td class="zentriert">24.2</td>                                  ø age
#   <td class="zentriert">21</td>                                    foreigners
#   <td class="rechts">€20.46m</td>                    <-- ø MARKET VALUE
#   <td class="rechts"><a ...>€777.33m</a></td>        <-- TOTAL market value
#
# `title="Bayern Munich"` occurs three times per row, so the non-greedy `.*?`
# resolved to the nearest following €, which is the ø (per-player average)
# column — and for an elite squad that average clears the €20m floor, so the
# guard let it through. Bayern 2019 was stored as €20.46m instead of €777.33m.
# 13.5% of big-5 rows were affected, concentrated on the richest clubs
# (Real Madrid €21.28m, Barcelona €20.41m, PSG €21.35m, Inter €28.37m), which
# is exactly the population a squad-value prior most needs to get right.
#
# Columns are now located by HEADER NAME and rows read cell-by-cell, so a
# column re-order upstream cannot silently shift the meaning of the number.
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_MONEY = re.compile(r"€\s*([\d.,]+)\s*(bn|m|k)?", re.I)
_TAGS = re.compile(r"<[^>]+>")


def _money_to_m(cell_html: str) -> float | None:
    """'€777.33m' / '€1.02bn' → millions of EUR. None when the cell has no €."""
    m = _MONEY.search(cell_html)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "m").lower()
    return num * {"bn": 1000.0, "m": 1.0, "k": 0.001}[unit]


def parse_league_season(html: str) -> dict[str, float]:
    """{tm_team_name: total_squad_value_eur_m} from a season-page's club table.

    Split out from the fetch so it is testable against a saved fixture without
    touching the network.
    """
    start = html.find('<table class="items"')
    if start == -1:
        return {}
    table = html[start:html.find("</table>", start)]

    # Locate the value column by its header text rather than by position.
    head = table[:table.find("</thead>")] if "</thead>" in table else table[:4000]
    headers = [_TAGS.sub("", c).replace("&nbsp;", " ").replace("&oslash;", "ø").strip().lower()
               for c in re.findall(r"<th[^>]*>(.*?)</th>", head, re.S)]
    total_idx = next((i for i, h in enumerate(headers) if "total market value" in h), None)

    out: dict[str, float] = {}
    for row in re.findall(r'<tr class="(?:odd|even)">(.*?)</tr>', table, re.S):
        name_m = re.search(r'<td class="hauptlink[^"]*"[^>]*>\s*<a title="([^"]+)"', row)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        cells = _CELL.findall(row)
        value = None
        if total_idx is not None and total_idx < len(cells):
            value = _money_to_m(cells[total_idx])
        if value is None:
            # Fallback: the LAST money cell in the row is the total (the ø
            # column always precedes it). Never the first — that is the ø.
            monies = [v for v in (_money_to_m(c) for c in cells) if v is not None]
            value = monies[-1] if monies else None
        if value and value > 0:
            out[name] = value
    return out


def fetch_league_season(tm_code: str, season: int) -> dict[str, float]:
    """{tm_team_name: total squad value in EUR millions} for one league-season."""
    url = (f"https://www.transfermarkt.com/x/startseite/wettbewerb/"
           f"{tm_code}/plus/?saison_id={season}")
    return parse_league_season(requests.get(url, headers=_HDR, timeout=30).text)


# A big-5 league-season whose RICHEST club is under this is not a squad-value
# table — it is the ø (per-player) column, which is the exact way this scrape
# failed silently for years. Even the poorest big-5 season has a top club well
# into the hundreds of millions; the corrupt data topped out around €20-45m.
MIN_TOP_CLUB_EUR_M = 200.0


def validate(df: pd.DataFrame) -> list[str]:
    """Structural checks on a scraped value table. Returns a list of problems.

    Deliberately checks the SHAPE of each league-season rather than individual
    values: a plausible-looking number in the wrong column is the failure mode
    that went unnoticed, and only the distribution reveals it.
    """
    problems: list[str] = []
    if df.empty:
        return ["value table is empty"]

    dupes = int(df.duplicated(subset=["league", "season", "tm_name"]).sum())
    if dupes:
        problems.append(f"{dupes} duplicate (league, season, team) rows")

    for (lid, season), g in df.groupby(["league", "season"]):
        if not 16 <= len(g) <= 22:
            problems.append(f"{lid} {season}: {len(g)} clubs (expected 16-22) — "
                            "the row regex is probably matching other tables")
        top = float(g["value_eur_m"].max())
        if top < MIN_TOP_CLUB_EUR_M:
            problems.append(
                f"{lid} {season}: richest club is only €{top:.1f}m — this looks "
                "like the ø market-value column, not the total")
        if (g["value_eur_m"] <= 0).any():
            problems.append(f"{lid} {season}: non-positive values present")
    return problems


def run_backfill(seasons=range(2017, 2027), sleep_s: float = 3.0) -> pd.DataFrame:
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
    problems = validate(df)
    if problems:
        # Loud, but still written: a partial scrape is easier to inspect on disk
        # than to reproduce, and the caller decides whether to promote it.
        print(f"\n!! {len(problems)} VALIDATION PROBLEM(S) — do not promote this "
              f"table into the model until they are resolved:")
        for p in problems:
            print(f"   - {p}")
    else:
        print(f"\nvalidation OK: {len(df)} rows, "
              f"{df.groupby(['league', 'season']).ngroups} league-seasons")
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
