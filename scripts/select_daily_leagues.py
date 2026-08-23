#!/usr/bin/env python3
"""Leagues the daily refresh should rebuild, printed as a JSON array.

Extracted from `.github/workflows/refresh-daily.yml`, which carried this as an
inline heredoc that nothing could test.

Why it is not simply `status == "live"`
---------------------------------------
That filter was a LATCH. `refresh-daily.yml` is the only job that rebuilds a
payload, and it skipped any league whose payload said the season was over — so
a league wrongly published as complete could never be recomputed by it. The
only escape was the Monday rebuild in `refresh-leagues.yml`, and on 2026-08-17
that rebuild ran while ESPN was refusing our User-Agent and reproduced the same
wrong verdict. Eight leagues were still showing a final table mid-season six
days later, Allsvenskan among them at 16 of 30 rounds.

The builder now cross-examines its own CONCLUDED verdict
(`scripts.eval.season_state.looks_unfinished`), so the wrong answer should not
be written in the first place. This is the second layer: a league that PLAYED
recently is a league that might still be playing, whatever its payload claims,
and rebuilding it costs one matrix job and fixes itself.

The idle window is imported rather than typed, so this filter and the builder's
guard cannot drift into disagreeing about what "recently played" means.

Usage:
    python3 scripts/select_daily_leagues.py                 # JSON array
    python3 scripts/select_daily_leagues.py --payload-dir X
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.eval.season_state import MAX_IDLE_DAYS      # noqa: E402
from scripts.payload_utils import read_js_payload        # noqa: E402

PAYLOAD_DIR = Path("webapp/data")

# Cross-league data files carry their own `status` but are NOT leagues —
# excluding them stops bogus matrix jobs like "build (edge-board)". Kept as the
# literal list the workflow used, deliberately: swapping it for a registry
# lookup would change which leagues are selected for reasons unrelated to the
# latch this module exists to fix.
NOT_A_LEAGUE = {"logos", "ledger", "power", "edge-board", "movers", "drift",
                "model-slices", "coefficients", "match-leverage"}


def _last_result_date(payload: dict) -> date | None:
    """Newest date among matches that actually have a result."""
    best = None
    for game in payload.get("games") or []:
        if not isinstance(game, dict):
            continue
        if game.get("result") is None and game.get("hg") is None:
            continue
        raw = game.get("date")
        if not raw:
            continue
        try:
            parsed = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if best is None or parsed > best:
            best = parsed
    return best


def select_leagues(payload_dir: Path = PAYLOAD_DIR,
                   today: date | None = None,
                   max_idle_days: int = MAX_IDLE_DAYS) -> list[str]:
    """League ids to rebuild: every live one, plus any claiming to be finished
    that has played within `max_idle_days`."""
    now = today or date.today()
    picked = []
    for path in sorted(Path(payload_dir).glob("*.js")):
        if path.stem in NOT_A_LEAGUE:
            continue
        try:
            data = read_js_payload(path)
        except Exception:
            continue
        # Durable guard: any data file that isn't a payload dict (search-index.js
        # is a JSON array) is not a league — skip rather than crash on .get().
        if not isinstance(data, dict):
            continue
        status = data.get("status")
        if status == "live":
            picked.append(path.stem)
            continue
        if status != "completed":
            continue
        last = _last_result_date(data)
        if last is not None and (now - last).days <= max_idle_days:
            picked.append(path.stem)
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload-dir", default=str(PAYLOAD_DIR))
    args = ap.parse_args()
    print(json.dumps(select_leagues(Path(args.payload_dir))))


if __name__ == "__main__":
    main()
