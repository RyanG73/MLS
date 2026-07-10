#!/usr/bin/env python3
"""Append per-build odds/projection snapshots (B10 + drift-tracking step 1).

Every CI build overwrites the webapp payloads in place; the time series of the
model's own odds only exists from the day we start keeping it. This runs after
each build and writes two append-only parquet files:

data/odds_history.parquet — one row per (league, team, snapshot_date):
    league, team, snapshot_date, elo, proj_pts,
    title, playoff, shield, cup, ucl, europa, conf, releg, promo, promoted,
    liguilla, playoffs,                                    (whichever exist)
    nm_id, nm_date, nm_opp, nm_is_home, nm_ph, nm_pd, nm_pa,   (next match, model)
    nm_mh, nm_md, nm_ma,                                   (next match, market — None
                                                            until a line posts)
    n_played, config_id, code_rev                          (provenance, added 2026-07-10)

data/match_prob_history.parquet — one row per (league, home, away, date,
snapshot_date), for EVERY upcoming match (not just each team's next one):
    pH, pD, pA, mkt_home, mkt_draw, mkt_away, days_to_kickoff, config_id

Both are deduped on their natural key, so re-running the archiver on the same
build is a no-op (the test contract). This is the raw material for
scripts/build_drift_report.py — see docs/projection-drift-tracking.md and
docs/drift-playbook.md for how the numbers are interpreted.

Usage:
    python scripts/archive_odds_snapshot.py            # all webapp/data/*.js
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.resolve()
_DATA = REPO_ROOT / "webapp" / "data"
_OUT = REPO_ROOT / "data" / "odds_history.parquet"
_MATCH_OUT = REPO_ROOT / "data" / "match_prob_history.parquet"
_CHAMPION = REPO_ROOT / "experiments" / "champion.json"

# Same exclusion as validate_payloads / test_payload_contract.
_NON_PAYLOAD = {"logos.js", "ledger.js", "edge-board.js", "movers.js",
                "coefficients.js"}

# promoted/promo/conf/liguilla/playoffs added 2026-07-09 (round-3 promotion
# playoffs + drift-tracking step 1a — history not captured never exists).
_ODDS_KEYS = ["title", "playoff", "shield", "cup", "ucl", "europa", "conf",
              "releg", "promo", "promoted", "liguilla", "playoffs"]
_DEDUP_KEYS = ["league", "team", "snapshot_date"]


def _load_payload(path: Path) -> dict:
    txt = path.read_text(encoding="utf-8")
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", txt, re.DOTALL)
    if not m:
        raise ValueError(f"{path.name}: no JS assignment pattern")
    return json.loads(m.group(1))


def _next_match(team: str, games: list[dict]) -> dict | None:
    """The team's earliest upcoming (no-result) game, by date."""
    ups = [g for g in games
           if not g.get("result") and team in (g.get("home"), g.get("away"))]
    return min(ups, key=lambda g: g.get("date") or "") if ups else None


_config_id_cache: str | None = None
_code_rev_cache: str | None = None


def config_id() -> str | None:
    """The promoted champion's run_id — the provenance tag for 'which model
    produced this snapshot'. Drift after a config_id change is expected;
    drift without one is a bug (see docs/drift-playbook.md)."""
    global _config_id_cache
    if _config_id_cache is None:
        try:
            _config_id_cache = json.loads(_CHAMPION.read_text()).get("run_id")
        except (FileNotFoundError, json.JSONDecodeError):
            _config_id_cache = "unknown"
    return _config_id_cache


def code_rev() -> str | None:
    """Short git SHA at archive time — secondary provenance (config_id can be
    unchanged while a non-model code path, e.g. this archiver, changes)."""
    global _code_rev_cache
    if _code_rev_cache is None:
        try:
            _code_rev_cache = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.strip() or None
        except Exception:
            _code_rev_cache = None
    return _code_rev_cache


def snapshot_rows(league_id: str, payload: dict) -> list[dict]:
    """One archive row per standings team; [] for payloads without standings."""
    generated = payload.get("generated") or ""
    snapshot_date = generated[:10] if generated else None
    games = payload.get("games") or []
    n_played = sum(1 for g in games if g.get("result") is not None)
    cid, rev = config_id(), code_rev()
    rows = []
    for s in payload.get("standings") or []:
        team = s.get("team")
        if not team or not snapshot_date:
            continue
        row = {
            "league": league_id, "team": team, "snapshot_date": snapshot_date,
            "elo": s.get("elo"), "proj_pts": s.get("proj_pts"),
            "n_played": n_played, "config_id": cid, "code_rev": rev,
        }
        for k in _ODDS_KEYS:
            v = s.get(k)
            # "conf" collides across payload shapes: MLS uses it for the
            # conference NAME ("East"/"West"), some UEFA leagues for the
            # Conference-League qualification PERCENTAGE (float) — only the
            # latter belongs in an odds column, so non-numeric values are
            # dropped here rather than polluting the column's dtype (found
            # 2026-07-10: crashed to_parquet the first time this ran).
            row[k] = v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        nm = _next_match(team, games)
        is_home = bool(nm and nm.get("home") == team)
        row.update({
            "nm_id": nm.get("id") if nm else None,
            "nm_date": nm.get("date") if nm else None,
            "nm_opp": (nm.get("away") if is_home else nm.get("home")) if nm else None,
            "nm_is_home": is_home if nm else None,
            "nm_ph": nm.get("pH") if nm else None,
            "nm_pd": nm.get("pD") if nm else None,
            "nm_pa": nm.get("pA") if nm else None,
            # market probs — payloads gain these on upcoming cards when forward
            # odds land (same mkt_* keys the builder uses on played games)
            "nm_mh": nm.get("mkt_home") if nm else None,
            "nm_md": nm.get("mkt_draw") if nm else None,
            "nm_ma": nm.get("mkt_away") if nm else None,
        })
        rows.append(row)
    return rows


# match_prob_history dedup key: a fixture is identified by (league, home,
# away, date) — the game card's "id" is only an index into that build's
# remaining-fixtures array (per the SIM PORTING CONTRACT) and is NOT stable
# across builds, so it must never be used as a join/dedup key here.
_MATCH_DEDUP_KEYS = ["league", "home", "away", "date", "snapshot_date"]


def match_prob_rows(league_id: str, payload: dict) -> list[dict]:
    """One row per upcoming match per build — the full pre-match probability
    log that odds_history.parquet's next-match-only capture can't provide.
    Powers the drift report's kickoff funnel (how the quote moves as kickoff
    approaches) and any post-hoc calibration study."""
    generated = payload.get("generated") or ""
    snapshot_date = generated[:10] if generated else None
    if not snapshot_date:
        return []
    cid = config_id()
    rows = []
    for g in payload.get("games") or []:
        if g.get("result") is not None or not g.get("date"):
            continue
        try:
            dtk = (pd.Timestamp(g["date"]) - pd.Timestamp(snapshot_date)).days
        except (ValueError, TypeError):
            dtk = None
        rows.append({
            "league": league_id, "home": g.get("home"), "away": g.get("away"),
            "date": g["date"], "snapshot_date": snapshot_date,
            "pH": g.get("pH"), "pD": g.get("pD"), "pA": g.get("pA"),
            "mkt_home": g.get("mkt_home"), "mkt_draw": g.get("mkt_draw"),
            "mkt_away": g.get("mkt_away"),
            "days_to_kickoff": dtk, "config_id": cid,
        })
    return rows


def append_snapshot(rows: list[dict], path: Path,
                    dedup_keys: list[str] | None = None) -> int:
    """Append rows, dedupe on `dedup_keys` (default _DEDUP_KEYS). Returns rows added."""
    if not rows:
        return 0
    keys = dedup_keys or _DEDUP_KEYS
    new = pd.DataFrame(rows)
    n_old = 0
    if path.exists():
        old = pd.read_parquet(path)
        n_old = len(old)
        new = pd.concat([old, new], ignore_index=True)
    combined = new.drop_duplicates(subset=keys, keep="first")
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    return len(combined) - n_old


def main() -> int:
    total_before = len(pd.read_parquet(_OUT)) if _OUT.exists() else 0
    match_before = len(pd.read_parquet(_MATCH_OUT)) if _MATCH_OUT.exists() else 0
    for p in sorted(_DATA.glob("*.js")):
        if p.name in _NON_PAYLOAD:
            continue
        try:
            payload = _load_payload(p)
        except Exception as e:
            print(f"[archive] skip {p.name}: {e}", file=sys.stderr)
            continue
        if payload.get("status") == "placeholder":
            continue
        append_snapshot(snapshot_rows(p.stem, payload), _OUT)
        append_snapshot(match_prob_rows(p.stem, payload), _MATCH_OUT, _MATCH_DEDUP_KEYS)
    total_after = len(pd.read_parquet(_OUT)) if _OUT.exists() else 0
    match_after = len(pd.read_parquet(_MATCH_OUT)) if _MATCH_OUT.exists() else 0
    print(f"[archive] odds_history.parquet: {total_before} → {total_after} rows "
          f"(+{total_after - total_before})")
    print(f"[archive] match_prob_history.parquet: {match_before} → {match_after} rows "
          f"(+{match_after - match_before})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
