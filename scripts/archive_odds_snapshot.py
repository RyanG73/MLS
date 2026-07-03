#!/usr/bin/env python3
"""Append per-build odds/projection snapshots to data/odds_history.parquet (B10).

Every CI build overwrites the webapp payloads in place; the time series of the
model's own odds only exists from the day we start keeping it. This runs after
each build and appends one row per (league, team, snapshot_date):

    league, team, snapshot_date, elo, proj_pts,
    title, playoff, shield, cup, ucl, europa, releg,      (whichever exist)
    nm_id, nm_date, nm_opp, nm_is_home, nm_ph, nm_pd, nm_pa,   (next match, model)
    nm_mh, nm_md, nm_ma                                    (next match, market — None
                                                            until B5 ships market fields)

Append-only, deduped on league+team+snapshot_date (snapshot_date comes from the
payload's `generated` stamp, so re-running the archiver on the same build is a
no-op — the test contract).

Usage:
    python scripts/archive_odds_snapshot.py            # all webapp/data/*.js
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.resolve()
_DATA = REPO_ROOT / "webapp" / "data"
_OUT = REPO_ROOT / "data" / "odds_history.parquet"

# Same exclusion as validate_payloads / test_payload_contract.
_NON_PAYLOAD = {"logos.js"}

_ODDS_KEYS = ["title", "playoff", "shield", "cup", "ucl", "europa", "releg"]
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


def snapshot_rows(league_id: str, payload: dict) -> list[dict]:
    """One archive row per standings team; [] for payloads without standings."""
    generated = payload.get("generated") or ""
    snapshot_date = generated[:10] if generated else None
    games = payload.get("games") or []
    rows = []
    for s in payload.get("standings") or []:
        team = s.get("team")
        if not team or not snapshot_date:
            continue
        row = {
            "league": league_id, "team": team, "snapshot_date": snapshot_date,
            "elo": s.get("elo"), "proj_pts": s.get("proj_pts"),
        }
        for k in _ODDS_KEYS:
            row[k] = s.get(k)
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


def append_snapshot(rows: list[dict], path: Path) -> int:
    """Append rows, dedupe on league+team+snapshot_date. Returns rows added."""
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    n_old = 0
    if path.exists():
        old = pd.read_parquet(path)
        n_old = len(old)
        new = pd.concat([old, new], ignore_index=True)
    combined = new.drop_duplicates(subset=_DEDUP_KEYS, keep="first")
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    return len(combined) - n_old


def main() -> int:
    total_before = len(pd.read_parquet(_OUT)) if _OUT.exists() else 0
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
        rows = snapshot_rows(p.stem, payload)
        append_snapshot(rows, _OUT)
    total_after = len(pd.read_parquet(_OUT)) if _OUT.exists() else 0
    print(f"[archive] odds_history.parquet: {total_before} → {total_after} rows "
          f"(+{total_after - total_before})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
