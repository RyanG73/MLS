#!/usr/bin/env python3
"""Season-outcome replay runner — the team-outcome counterpart of eval_baseline.

Replays historical seasons through production-mirrored table sims and scores
each league's OUTLOOK buckets (title / promotion / playoff / relegation / …)
as binary forecasts at four checkpoints (preseason, 25%, 50%, 75% of season).
See scripts/eval/season_outcomes.py for methodology and approximations.

Usage:
    python scripts/eval_season_outcomes.py \
        --out experiments/season-outcomes-baseline.report.json

Format leagues (Scotland/Belgium/Greece) are excluded — their classification
needs format-group sims. ASA leagues are excluded in V1 (short history).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

from data_pipeline.football_data import match_results
from data_pipeline.understat import canonical_frame
from scripts.build_league_data import OUTLOOK
from scripts.eval.season_format import FORMATS
from scripts.eval.season_outcomes import replay_league, summarize

REPO = Path(__file__).parent.parent
DEFAULT_SEASONS = list(range(2018, 2026))

# Understat leagues replay on their FD frames (identical fixtures, FD names
# keep one name-space per league; xG plays no role in the DC-only table sim).
_FD_SOURCED = [lid for lid, cfg in OUTLOOK.items()
               if cfg["source"] in ("footballdata", "understat")
               and lid not in FORMATS]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+", default=_FD_SOURCED)
    ap.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    ap.add_argument("--sims", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    all_rows = []
    per_league = {}
    for lid in args.leagues:
        t0 = time.time()
        cfg = OUTLOOK[lid]
        frame = (match_results(lid, use_cache=True, refresh_latest=False)
                 if cfg["source"] in ("footballdata", "understat")
                 else canonical_frame(lid))
        rows = replay_league(frame, cfg["buckets"], args.seasons,
                             n_sims=args.sims, seed=args.seed)
        for r in rows:
            r["league"] = lid
        all_rows.extend(rows)
        per_league[lid] = summarize(rows)
        print(f"[{lid}] {len(rows)} outcome rows ({time.time()-t0:.0f}s)", flush=True)

    pooled = summarize(all_rows)
    print("\n── pooled by checkpoint/outcome ──")
    for cp, outs in pooled.items():
        for k, m in outs.items():
            fav = (f"  fav_hit {m['favorite_hit_rate']:.0%} of {m['n_league_seasons']}"
                   if "favorite_hit_rate" in m else "")
            print(f"  {cp:7s} {k:10s} brier {m['brier']:.4f} · "
                  f"p_on_achievers {m['p_actual_mean']} · "
                  f"pred {m['pred_mean']:.3f} vs obs {m['obs_rate']:.3f}{fav}")

    if args.out:
        report = {
            "experiment_id": Path(args.out).stem,
            "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "config": {"leagues": args.leagues, "seasons": args.seasons,
                       "sims": args.sims, "seed": args.seed,
                       "checkpoints": [0.0, 0.25, 0.5, 0.75]},
            "pooled": pooled,
            "per_league": per_league,
        }
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
