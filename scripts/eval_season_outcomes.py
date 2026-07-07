#!/usr/bin/env python3
"""Season-outcome replay runner — the team-outcome counterpart of eval_baseline.

Replays historical seasons through production-mirrored table sims and scores
each league's OUTLOOK buckets (title / promotion / playoff / relegation / …)
as binary forecasts at four checkpoints (preseason, 25%, 50%, 75% of season).
See scripts/eval/season_outcomes.py for methodology.

Coverage (2026-07-07 measurement upgrade):
  - newcomer seeding replays the production tier bridge (feeder/parent ELO +
    offsets → DC params), not just the flat prior;
  - format leagues (Scotland/Belgium/Greece) are scored against their OFFICIAL
    classification while the sim covers the regular phase — the format gap is
    measured, as it exists in production;
  - ASA leagues (MLS/NWSL/USL) replay 2022+ on ASA frames with their current
    bucket definitions (earlier formats differed; small-n, read as advisory).

Usage:
    python scripts/eval_season_outcomes.py \
        --out experiments/season-outcomes-baseline.report.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

from data_pipeline.asa_frame import asa_canonical_frame
from data_pipeline.football_data import match_results
from scripts.build_league_data import _TIER1_FOR_BUILD, _TIER2_FOR, OUTLOOK
from scripts.eval.season_format import FORMATS
from scripts.eval.season_outcomes import replay_league, summarize

REPO = Path(__file__).parent.parent
DEFAULT_SEASONS = list(range(2018, 2026))
ASA_SEASONS = list(range(2022, 2026))

_FD_SOURCED = [lid for lid, cfg in OUTLOOK.items()
               if cfg["source"] in ("footballdata", "understat")]
_ASA = {"mls": {"asa_key": "mls",
                "buckets": [{"key": "shield", "label": "Shield", "top": 1},
                            {"key": "playoffs", "label": "Playoffs", "top": 18}]},
        "nwsl": OUTLOOK["nwsl"],
        "usl-championship": OUTLOOK["usl-championship"]}

_FD_FRAME_CACHE: dict = {}


def _fd_frame(lid: str):
    if lid not in _FD_FRAME_CACHE:
        _FD_FRAME_CACHE[lid] = match_results(lid, use_cache=True,
                                             refresh_latest=False)
    return _FD_FRAME_CACHE[lid]


def _bridge_for(lid: str) -> dict | None:
    out = {}
    feeder = _TIER2_FOR.get(lid)
    if feeder:
        out["feeder"] = (feeder, _fd_frame(feeder))
    parent = _TIER1_FOR_BUILD.get(lid)
    if parent:
        out["parent"] = (parent, _fd_frame(parent))
    return out or None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+",
                    default=_FD_SOURCED + list(_ASA))
    ap.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    ap.add_argument("--sims", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sigma", type=float, default=None,
                    help="Override preseason widening sigma (default: production "
                         "PRESEASON_SIGMA). Used by the family sigma sweep.")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    all_rows = []
    per_league = {}
    for lid in args.leagues:
        t0 = time.time()
        if lid in _ASA:
            cfg = _ASA[lid]
            frame = asa_canonical_frame(cfg.get("asa_key", lid))
            seasons = [s for s in args.seasons if s in ASA_SEASONS]
            bridge = None
        else:
            cfg = OUTLOOK[lid]
            frame = _fd_frame(lid)
            seasons = args.seasons
            bridge = _bridge_for(lid)
        kw = {}
        if args.sigma is not None:
            kw["preseason_sigma"] = args.sigma
        rows = replay_league(frame, cfg["buckets"], seasons,
                             n_sims=args.sims, seed=args.seed,
                             bridge=bridge, lid=lid,
                             fmt=FORMATS.get(lid), **kw)
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
                       "sigma": args.sigma,
                       "checkpoints": [0.0, 0.25, 0.5, 0.75],
                       "bridge_replayed": True, "formats_replayed": True},
            "pooled": pooled,
            "per_league": per_league,
        }
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
