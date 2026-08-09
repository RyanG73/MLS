"""xG feature campaign — does backfilled API-Football xG improve league Brier?

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md
(Stage 4 / invariant 4). The Stage-4 backfill gave six competitions usable xG
for the first time. Invariant 4 forbids that reaching the model as a
consequence of a plumbing change, so this is the gate: a per-league A/B on the
same walk-forward the champion uses, judged on Brier.

Design:
  A (control)   — the frame exactly as production builds it today. For these
                  leagues home_xg/away_xg are entirely NaN, so the 18 xG
                  feature columns are present but empty.
  B (treatment) — the same frame with xg_store.attach_xg applied.

Everything else is held fixed: same features (LEAGUE_FEAT_BASE), same config,
same test seasons, same seed, same bag count. The only difference is whether
xG has values, which is precisely the question.

Judged per CLAUDE.md's verification protocol: a single bagged run
(n_bags=5, seed 42, sigma ~0.0002), with any gate-bound claim confirmed at a
second base seed. Brier here is sum-form (range 0-2; random ~0.64), so LOWER
is better and a delta of -0.001 or better is the bar worth acting on.

Run:
    python -m scripts.xg_feature_campaign --league championship
    python -m scripts.xg_feature_campaign --all --seed 42
    python -m scripts.xg_feature_campaign --all --seed 7 --confirm
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from data_pipeline import xg_store
from models.research_model import DEFAULT_N_BAGS, walk_forward
from scripts.build_league_data import OUTLOOK, _load_frame
from scripts.eval.league_features import LEAGUE_FEAT_BASE, build_league_features

# The six competitions whose backfilled xG cleared the >=90% usable bar
# (measured 2026-08-08 over the whole store; segunda was excluded after its
# league-id defect was corrected and its true coverage measured at 12%).
CAMPAIGN_LEAGUES = ["championship", "brazil-serie-a", "super-lig",
                    "belgian-pro", "primeira", "eredivisie"]

OUT = Path("experiments/xg_campaign")
DEFAULT_TEST_SEASONS = [2022, 2023, 2024, 2025]


def _played(frame):
    df = frame[frame["is_result"]].copy()
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)
    df["label_result"] = df["label_result"].astype(int)
    return df


def run_league(league_id: str, seasons, n_bags: int, seed: int) -> dict:
    raw = _load_frame(league_id, OUTLOOK[league_id]["source"])
    control = _played(raw)
    treatment = _played(xg_store.attach_xg(raw, league_id))

    covered = int(treatment["home_xg"].notna().sum())
    in_test = int(treatment[treatment["season"].isin(seasons)]["home_xg"].notna().sum())
    n_test = int(treatment["season"].isin(seasons).sum())

    t0 = time.time()
    a = walk_forward(build_league_features(control), LEAGUE_FEAT_BASE,
                     seasons, n_bags=n_bags, seed=seed)
    b = walk_forward(build_league_features(treatment), LEAGUE_FEAT_BASE,
                     seasons, n_bags=n_bags, seed=seed)
    return {
        "league": league_id, "seed": seed, "n_bags": n_bags,
        "matches": int(len(control)),
        "xg_rows": covered,
        "xg_in_test_seasons": in_test, "test_matches": n_test,
        "xg_test_share": round(in_test / n_test, 3) if n_test else 0.0,
        "control_brier": round(a["avg_brier"], 4),
        "treatment_brier": round(b["avg_brier"], 4),
        "delta": round(b["avg_brier"] - a["avg_brier"], 4),
        "control_per_season": {int(k): round(v, 4) for k, v in a["per_season"].items()},
        "treatment_per_season": {int(k): round(v, 4) for k, v in b["per_season"].items()},
        "secs": round(time.time() - t0, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", choices=CAMPAIGN_LEAGUES)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--bags", type=int, default=DEFAULT_N_BAGS)
    ap.add_argument("--seasons", default=None,
                    help="comma-separated test seasons (default 2022-2025)")
    ap.add_argument("--confirm", action="store_true",
                    help="label this run as the second-seed confirmation")
    args = ap.parse_args()

    seasons = ([int(s) for s in args.seasons.split(",")] if args.seasons
               else DEFAULT_TEST_SEASONS)
    leagues = CAMPAIGN_LEAGUES if args.all else [args.league]
    if not leagues or leagues == [None]:
        ap.error("pass --league <id> or --all")

    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for lid in leagues:
        r = run_league(lid, seasons, args.bags, args.seed)
        results.append(r)
        verdict = ("IMPROVES" if r["delta"] <= -0.001 else
                   "regresses" if r["delta"] >= 0.001 else "noise")
        print(f"{r['league']:16s} xG on {r['xg_test_share']:5.0%} of test matches · "
              f"control {r['control_brier']:.4f} -> treatment {r['treatment_brier']:.4f} · "
              f"delta {r['delta']:+.4f}  {verdict}  [{r['secs']}s]")

    tag = "confirm" if args.confirm else "run"
    path = OUT / f"seed{args.seed}_{tag}.json"
    path.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
