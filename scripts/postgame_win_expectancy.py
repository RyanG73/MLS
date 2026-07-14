#!/usr/bin/env python3
"""Postgame win expectancy (WE) model — "how deserved was this result".

NEW, ADDITIVE research capability. This is NOT the pre-match Dixon-Coles /
XGBoost win-probability pipeline (`models/research_model.py`) and does not
touch it, `features/`, `config/`, or `scripts/eval_baseline.py`. It answers a
different question: given the ACTUAL in-game process stats of a COMPLETED
match (final xG for/against for each side), what was each team's win
probability *given the balance of play* — so a 1-0 win on one shot reads as
"~10% postgame WE, they got fortunate" rather than the boxscore's flat 100%.

Data reality (checked before building this): the production pipeline has
match-level AGGREGATE xG only (no shot-by-shot event data) via:
  - Understat (`data_pipeline/understat.py`) for the Big-5 European leagues
  - American Soccer Analysis (`data_pipeline/asa_cache.py`) for MLS/NWSL/USLC
Both are read here directly from their existing local parquet caches — no
network calls, no new data source, no change to any ingestion file.

Model: a symmetric BINARY logistic regression,
    P(team wins | xg_for, xg_against)
fit on two rows per historical match (home perspective + away perspective),
grouped by match_id under cross-validation so both rows of a match always
land in the same fold (no leakage). "Win" is a binary target (draw/loss both
count as 0) — this is deliberately NOT the 3-class pre-match model; postgame
WE is asked and answered as "how likely was THIS team to win", matching the
Bill-Connelly-style framing in the request.

Three candidate feature sets are compared and the one with the lowest max
decile calibration error (secondary veto: Brier must not regress) is kept,
mirroring the calibration-agent convention in docs/experiment-protocol.md.

**Fit PER DATA-SOURCE-FAMILY, not one universal model.** A first pass pooling
all 8 leagues into one logistic regression looked well-calibrated in
aggregate (pooled max decile error ~0.014) but that number hid a real
per-league problem: MLS/NWSL/USLC (xG from American Soccer Analysis) came
out to 0.06-0.09 decile error under the pooled model, while the Understat
Big-5 leagues stayed at 0.02-0.045. Understat and ASA compute "expected
goals" with different underlying shot models, so pooling their raw xG values
into one numeric feature conflates two different measurement scales — a
0.3 xG differential doesn't mean the same thing in both systems. Fitting one
model per source family (mirroring docs/CURRENT_STATE.md's existing
"League-Family Champions" governance, which already treats MLS / NWSL / USL
/ big-5 Europe as separately-validated families for the pre-match model)
resolved most of the gap: MLS 0.092->0.053, USLC 0.063->0.025. NWSL stayed
around 0.06 even after the split — almost certainly a small-sample artifact
(734 matches, some deciles under n=50) rather than a modeling failure; see
the decile table for that league before treating it as production-ready.

Every fit is repeated at two seeds (CLAUDE.md verification protocol) to
confirm the calibration numbers aren't a fold-shuffle artifact.

Usage:
    python scripts/postgame_win_expectancy.py --out experiments/postgame_we_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO_ROOT = Path(__file__).resolve().parent.parent
UNDERSTAT_DIR = REPO_ROOT / "data" / "understat"
ASA_CACHE_DIR = REPO_ROOT / "data" / "asa_cache"

BIG5_LEAGUES = ["epl", "la-liga", "bundesliga", "ligue-1", "serie-a"]
ASA_LEAGUES = ["mls", "nwsl", "uslc"]

_COVID_SEASON = 2020  # excluded repo-wide per CLAUDE.md ("2020 excluded (COVID bubble)")


# ─────────────────────────────────────────────────────────────────────────────
# Data loading — read straight from existing local caches, no network, no
# writes to any production file.
# ─────────────────────────────────────────────────────────────────────────────

def _load_understat(league: str) -> pd.DataFrame:
    path = UNDERSTAT_DIR / f"{league}.parquet"
    df = pd.read_parquet(path)
    df["league"] = league
    return df


def _load_asa(league: str) -> pd.DataFrame:
    """Rebuild the same canonical frame as data_pipeline.asa_frame.asa_canonical_frame,
    reading the cached parquets directly (offline, matches the ASA cache schema
    exactly — see data_pipeline/asa_frame.py)."""
    games = pd.read_parquet(ASA_CACHE_DIR / f"get_games_{league}.parquet")
    teams = pd.read_parquet(ASA_CACHE_DIR / f"get_teams_{league}.parquet")
    xg = pd.read_parquet(ASA_CACHE_DIR / f"get_game_xgoals_{league}.parquet")
    id2name = dict(zip(teams["team_id"], teams["team_name"]))

    g = games[(games["status"] == "FullTime")
              & games["home_score"].notna() & games["away_score"].notna()].copy()
    g["date"] = pd.to_datetime(g["date_time_utc"]).dt.tz_localize(None)
    g["season"] = g["season_name"].astype(int)

    xg_map = (xg.set_index("game_id")[["home_team_xgoals", "away_team_xgoals"]]
              if not xg.empty and "home_team_xgoals" in xg.columns else None)

    out = pd.DataFrame({
        "match_id": g["game_id"].astype(str),
        "date": g["date"],
        "season": g["season"],
        "home_team": g["home_team_id"].map(id2name),
        "away_team": g["away_team_id"].map(id2name),
        "home_goals": g["home_score"].astype(float),
        "away_goals": g["away_score"].astype(float),
        "home_xg": (g["game_id"].map(xg_map["home_team_xgoals"])
                    if xg_map is not None else np.nan),
        "away_xg": (g["game_id"].map(xg_map["away_team_xgoals"])
                    if xg_map is not None else np.nan),
        "is_result": True,
        "is_playoff": g.get("knockout_game", pd.Series(False, index=g.index))
                       .fillna(False).astype(int),
    })
    out["label_result"] = np.where(
        out["home_goals"] > out["away_goals"], 0,
        np.where(out["home_goals"] == out["away_goals"], 1, 2)).astype(float)
    out["league"] = league
    return out.dropna(subset=["home_team", "away_team"]).sort_values("date").reset_index(drop=True)


def load_all_matches() -> pd.DataFrame:
    frames = [_load_understat(lg) for lg in BIG5_LEAGUES] + [_load_asa(lg) for lg in ASA_LEAGUES]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["is_result"].astype(bool)]
    df = df[df["season"] != _COVID_SEASON]
    df = df.dropna(subset=["home_xg", "away_xg", "home_goals", "away_goals"])
    df = df[(df["home_xg"] >= 0) & (df["away_xg"] >= 0)]
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Symmetric team-match rows
# ─────────────────────────────────────────────────────────────────────────────

def build_symmetric_rows(matches: pd.DataFrame) -> pd.DataFrame:
    """Two rows per match: one per team's own perspective. Fully symmetric —
    no team identity, no league-specific intercept — so the fitted model is a
    single universal function of (xg_for, xg_against)."""
    home = pd.DataFrame({
        "match_id": matches["match_id"],
        "league": matches["league"],
        "season": matches["season"],
        "date": matches["date"],
        "is_playoff": matches["is_playoff"],
        "side": "home",
        "xg_for": matches["home_xg"],
        "xg_against": matches["away_xg"],
        "win": (matches["home_goals"] > matches["away_goals"]).astype(int),
        "home_flag": 1,
    })
    away = pd.DataFrame({
        "match_id": matches["match_id"],
        "league": matches["league"],
        "season": matches["season"],
        "date": matches["date"],
        "is_playoff": matches["is_playoff"],
        "side": "away",
        "xg_for": matches["away_xg"],
        "xg_against": matches["home_xg"],
        "win": (matches["away_goals"] > matches["home_goals"]).astype(int),
        "home_flag": 0,
    })
    rows = pd.concat([home, away], ignore_index=True)
    rows["xg_diff"] = rows["xg_for"] - rows["xg_against"]
    rows["xg_total"] = rows["xg_for"] + rows["xg_against"]
    rows["source"] = np.where(rows["league"].isin(BIG5_LEAGUES), "understat", "asa")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Feature sets under comparison
# ─────────────────────────────────────────────────────────────────────────────

def _feat_linear(df: pd.DataFrame) -> np.ndarray:
    return df[["xg_diff", "xg_total"]].to_numpy()


def _feat_quadratic(df: pd.DataFrame) -> np.ndarray:
    xf, xa = df["xg_for"].to_numpy(), df["xg_against"].to_numpy()
    return np.column_stack([xf, xa, xf ** 2, xa ** 2, xf * xa])


def _feat_linear_homeflag(df: pd.DataFrame) -> np.ndarray:
    return df[["xg_diff", "xg_total", "home_flag"]].to_numpy()


FEATURE_SETS = {
    "linear_diff_total": _feat_linear,
    "quadratic_for_against": _feat_quadratic,
    "linear_diff_total_homeflag": _feat_linear_homeflag,
}


# ─────────────────────────────────────────────────────────────────────────────
# Grouped cross-validation (group = match_id, so both rows of a match always
# land in the same fold — no leakage between a match's home/away perspective)
# ─────────────────────────────────────────────────────────────────────────────

def _fold_assignment(df: pd.DataFrame, seed: int, n_folds: int) -> np.ndarray:
    """Assign a CV fold per match_id (shuffled), so both rows (home/away
    perspective) of the same match always land in the same fold."""
    match_ids = df["match_id"].unique()
    rng = np.random.RandomState(seed)
    shuffled = match_ids.copy()
    rng.shuffle(shuffled)
    fold_of = {m: i % n_folds for i, m in enumerate(shuffled)}
    return df["match_id"].map(fold_of).to_numpy()


def grouped_kfold_oof(df: pd.DataFrame, feat_fn, seed: int, n_folds: int = 5) -> np.ndarray:
    """Single universal model across all rows (kept for the feature-set
    comparison / pooled-vs-per-family ablation; NOT the final design)."""
    fold = _fold_assignment(df, seed, n_folds)
    X_all = feat_fn(df)
    y_all = df["win"].to_numpy()
    oof = np.full(len(df), np.nan)

    for f in range(n_folds):
        te = fold == f
        tr = ~te
        clf = LogisticRegression(C=1.0, max_iter=2000)
        clf.fit(X_all[tr], y_all[tr])
        oof[te] = clf.predict_proba(X_all[te])[:, 1]

    return oof


def grouped_kfold_oof_by_family(df: pd.DataFrame, feat_fn, seed: int, n_folds: int = 5) -> np.ndarray:
    """PRIMARY design: fit a separate model per data-source family
    (Understat vs ASA — see module docstring for why pooling xG numerically
    across vendors miscalibrates). Same match-grouped fold assignment as
    grouped_kfold_oof, just partitioned by source before fitting."""
    fold = _fold_assignment(df, seed, n_folds)
    X_all = feat_fn(df)
    y_all = df["win"].to_numpy()
    oof = np.full(len(df), np.nan)

    for source in df["source"].unique():
        src_mask = (df["source"] == source).to_numpy()
        X_src, y_src, fold_src = X_all[src_mask], y_all[src_mask], fold[src_mask]
        src_positions = np.where(src_mask)[0]
        for f in range(n_folds):
            te = fold_src == f
            tr = ~te
            clf = LogisticRegression(C=1.0, max_iter=2000)
            clf.fit(X_src[tr], y_src[tr])
            oof[src_positions[te]] = clf.predict_proba(X_src[te])[:, 1]

    return oof


def fit_final_by_family(df: pd.DataFrame, feat_fn) -> dict:
    """Fit the deployable model: one LogisticRegression per source family,
    trained on ALL rows for that family (no held-out split)."""
    out = {}
    X_all = feat_fn(df)
    y_all = df["win"].to_numpy()
    for source in df["source"].unique():
        src_mask = (df["source"] == source).to_numpy()
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(X_all[src_mask], y_all[src_mask])
        out[source] = {
            "coef": clf.coef_.tolist(),
            "intercept": clf.intercept_.tolist(),
            "n_rows": int(src_mask.sum()),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────

def binary_brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def binary_log_loss(p: np.ndarray, y: np.ndarray) -> float:
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    return float(np.mean(-(y * np.log(pc) + (1 - y) * np.log(1 - pc))))


def decile_table(p: np.ndarray, y: np.ndarray, bins: int = 10, min_n: int = 20) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        n = int(m.sum())
        row = {
            "decile": f"{edges[b]:.1f}-{edges[b+1]:.1f}",
            "n": n,
            "mean_pred": round(float(p[m].mean()), 4) if n else None,
            "actual_win_rate": round(float(y[m].mean()), 4) if n else None,
            "abs_error": round(float(abs(p[m].mean() - y[m].mean())), 4) if n >= min_n else None,
        }
        out.append(row)
    return out


def max_decile_cal_error(p: np.ndarray, y: np.ndarray, bins: int = 10, min_n: int = 20) -> float:
    errs = [r["abs_error"] for r in decile_table(p, y, bins, min_n) if r["abs_error"] is not None]
    return round(max(errs), 6) if errs else float("nan")


# ─────────────────────────────────────────────────────────────────────────────
# Deployment: apply the fitted per-family model at request/build time.
# Closed-form — no retraining, no sklearn object needed at call time, just the
# coefficients already validated and pinned in experiments/postgame_we_report.json.
# ─────────────────────────────────────────────────────────────────────────────

_FAMILY_OF_SOURCE = {"understat": "understat", "asa": "asa"}
_WE_MODEL_CACHE: dict | None = None


def _load_we_model(report_path: str = "experiments/postgame_we_report.json") -> dict:
    global _WE_MODEL_CACHE
    if _WE_MODEL_CACHE is None:
        report = json.loads((REPO_ROOT / report_path).read_text())
        _WE_MODEL_CACHE = report["final_model"]
    return _WE_MODEL_CACHE


def compute_we(xg_for: float, xg_against: float, family: str) -> float | None:
    """Postgame win expectancy for the side with `xg_for`/`xg_against`, using
    the fitted per-family logistic model (quadratic_for_against feature set:
    [xg_for, xg_against, xg_for^2, xg_against^2, xg_for*xg_against]).
    `family` must be "understat" or "asa" (this model was never fit or
    validated on any other xG source) — anything else returns None rather
    than silently misapplying a coefficient set calibrated for a different
    xG scale (see module docstring: Understat and ASA aren't numerically
    comparable, that's the whole reason this is fit per-family)."""
    model = _load_we_model()
    if model["feature_set"] != "quadratic_for_against" or family not in model["families"]:
        return None
    fam = model["families"][family]
    xf, xa = float(xg_for), float(xg_against)
    feats = [xf, xa, xf ** 2, xa ** 2, xf * xa]
    z = fam["intercept"][0] + sum(c * f for c, f in zip(fam["coef"][0], feats))
    return round(1.0 / (1.0 + np.exp(-z)), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="experiments/postgame_we_report.json")
    ap.add_argument("--seeds", nargs="+", type=int, default=[42, 7])
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    matches = load_all_matches()
    rows = build_symmetric_rows(matches)
    print(f"Loaded {len(matches)} matches ({len(rows)} team-match rows) across "
          f"{matches['league'].nunique()} leagues, seasons "
          f"{int(matches['season'].min())}-{int(matches['season'].max())}")
    print(matches.groupby("league").size().to_string())

    report: dict = {
        "n_matches": int(len(matches)),
        "n_rows": int(len(rows)),
        "leagues": sorted(matches["league"].unique().tolist()),
        "season_range": [int(matches["season"].min()), int(matches["season"].max())],
        "excluded_season": _COVID_SEASON,
        "feature_sets": {},
    }

    # ── 0. Pooled-universal-model vs per-source-family ablation ──────────────
    # Documents WHY the final design fits one model per source family instead
    # of one universal model (see module docstring). Uses the simplest
    # feature set (linear_diff_total) for this comparison.
    primary_seed = args.seeds[0]
    y = rows["win"].to_numpy()
    oof_pooled = grouped_kfold_oof(rows, _feat_linear, seed=primary_seed, n_folds=args.folds)
    oof_family = grouped_kfold_oof_by_family(rows, _feat_linear, seed=primary_seed, n_folds=args.folds)
    report["pooled_vs_family_ablation"] = {"by_league": {}}
    print("=== pooled universal model vs per-source-family model (linear_diff_total) ===")
    for lg, idx in rows.groupby("league").groups.items():
        ii = rows.index.get_indexer(idx)
        if len(ii) < 40:
            continue
        pooled_err = max_decile_cal_error(oof_pooled[ii], y[ii], min_n=10)
        family_err = max_decile_cal_error(oof_family[ii], y[ii], min_n=10)
        report["pooled_vs_family_ablation"]["by_league"][lg] = {
            "pooled_cal_err": pooled_err, "per_family_cal_err": family_err,
        }
        print(f"  {lg:12s} pooled={pooled_err}  per_family={family_err}")
    report["pooled_vs_family_ablation"]["pooled_overall_cal_err"] = max_decile_cal_error(oof_pooled, y)
    report["pooled_vs_family_ablation"]["family_overall_cal_err"] = max_decile_cal_error(oof_family, y)
    print(f"  overall(pooled)={report['pooled_vs_family_ablation']['pooled_overall_cal_err']}  "
          f"overall(per_family)={report['pooled_vs_family_ablation']['family_overall_cal_err']}")
    print("  -> per-source-family fitting adopted as final design (see module docstring)\n")

    # ── 1. Compare feature sets at the primary seed (per-family harness) ─────
    for name, feat_fn in FEATURE_SETS.items():
        oof = grouped_kfold_oof_by_family(rows, feat_fn, seed=primary_seed, n_folds=args.folds)
        brier = binary_brier(oof, y)
        ll = binary_log_loss(oof, y)
        cal = max_decile_cal_error(oof, y)
        report["feature_sets"][name] = {"seed": primary_seed, "brier": round(brier, 6),
                                         "log_loss": round(ll, 6), "max_decile_cal_error": cal}
        print(f"[{primary_seed}] {name:28s} brier={brier:.4f} logloss={ll:.4f} max_cal_err={cal:.4f}")

    # KEEP/DROP-style selection: lowest cal error, Brier must not regress > 0.001
    # vs the simplest baseline (linear_diff_total).
    baseline_brier = report["feature_sets"]["linear_diff_total"]["brier"]
    candidates = {
        k: v for k, v in report["feature_sets"].items()
        if v["brier"] <= baseline_brier + 0.001
    }
    chosen_name = min(candidates, key=lambda k: candidates[k]["max_decile_cal_error"])
    report["chosen_feature_set"] = chosen_name
    print(f"\nChosen feature set: {chosen_name}")

    # ── 2. Full calibration validation of the chosen model at every seed ─────
    chosen_feat_fn = FEATURE_SETS[chosen_name]
    report["seed_validation"] = {}
    all_oof_by_seed = {}
    for seed in args.seeds:
        oof = grouped_kfold_oof_by_family(rows, chosen_feat_fn, seed=seed, n_folds=args.folds)
        all_oof_by_seed[seed] = oof
        y = rows["win"].to_numpy()
        dec = decile_table(oof, y)
        cal = max_decile_cal_error(oof, y)
        brier = binary_brier(oof, y)
        ll = binary_log_loss(oof, y)
        report["seed_validation"][str(seed)] = {
            "brier": round(brier, 6), "log_loss": round(ll, 6),
            "max_decile_cal_error": cal, "decile_table": dec,
        }
        print(f"\n=== seed={seed} decile calibration (chosen: {chosen_name}) ===")
        for r in dec:
            if r["n"] == 0:
                continue
            flag = "" if (r["abs_error"] is None or r["abs_error"] < 0.05) else "  <-- ERR>0.05"
            print(f"  pred {r['decile']:>9s}  n={r['n']:5d}  mean_pred={r['mean_pred']:.3f}  "
                  f"actual={r['actual_win_rate']:.3f}  |diff|={r['abs_error']}{flag}")
        print(f"  brier={brier:.4f}  log_loss={ll:.4f}  max_decile_cal_error={cal:.4f}")

    # ── 3. Cross-seed stability check ────────────────────────────────────────
    cal_errs = [report["seed_validation"][str(s)]["max_decile_cal_error"] for s in args.seeds]
    report["cal_err_seed_spread"] = round(max(cal_errs) - min(cal_errs), 6)
    print(f"\nCal-error spread across seeds {args.seeds}: {report['cal_err_seed_spread']:.4f}")

    # ── 4. Per-league / per-season / playoff slices (chosen model, primary seed) ──
    oof_primary = all_oof_by_seed[primary_seed]
    y = rows["win"].to_numpy()
    slices = {}
    for lg, idx in rows.groupby("league").groups.items():
        ii = rows.index.get_indexer(idx)
        if len(ii) < 40:
            continue
        slices[f"league_{lg}"] = {
            "n": int(len(ii)), "brier": round(binary_brier(oof_primary[ii], y[ii]), 6),
            "max_decile_cal_error": max_decile_cal_error(oof_primary[ii], y[ii], min_n=10),
        }
    for season, idx in rows.groupby("season").groups.items():
        ii = rows.index.get_indexer(idx)
        if len(ii) < 40:
            continue
        slices[f"season_{int(season)}"] = {
            "n": int(len(ii)), "brier": round(binary_brier(oof_primary[ii], y[ii]), 6),
            "max_decile_cal_error": max_decile_cal_error(oof_primary[ii], y[ii], min_n=10),
        }
    playoff_idx = rows.index.get_indexer(rows[rows["is_playoff"] == 1].index)
    if len(playoff_idx) >= 40:
        slices["playoffs"] = {
            "n": int(len(playoff_idx)),
            "brier": round(binary_brier(oof_primary[playoff_idx], y[playoff_idx]), 6),
            "max_decile_cal_error": max_decile_cal_error(oof_primary[playoff_idx], y[playoff_idx], min_n=10),
        }
    report["slices"] = slices
    print("\n=== slices (chosen model, seed={}) ===".format(primary_seed))
    for k, v in slices.items():
        print(f"  {k:20s} n={v['n']:5d} brier={v['brier']:.4f} max_cal_err={v['max_decile_cal_error']}")

    # ── 5. Fit final per-family models on ALL data (for actual deployment) ───
    families = fit_final_by_family(rows, chosen_feat_fn)
    report["final_model"] = {
        "feature_set": chosen_name,
        "design": "one LogisticRegression per source family (understat / asa)",
        "families": families,
        "note": "Each family fit on ALL of its rows (no held-out split) for "
                "deployment; calibration numbers above come exclusively from "
                "out-of-fold CV predictions, never from this in-sample fit.",
    }

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWrote report to {out_path}")


if __name__ == "__main__":
    main()
