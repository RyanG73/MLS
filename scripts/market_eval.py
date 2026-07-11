#!/usr/bin/env python3
"""
Market evaluation report — model vs market Brier, CLV, ROI by edge bucket.

Reads pre-computed per-season model vs market Brier from webapp payloads
(European Big-5) and from odds_log/odds_closers parquet files (MLS, forward-
only). Outputs experiments/market_eval.json.

Market odds are EVALUATION-ONLY — never added to the training feature set
or the parity frame. This is a read-only report artifact.

Usage:
    python scripts/market_eval.py
    python scripts/market_eval.py --out experiments/market_eval_2025.json
    python scripts/market_eval.py --leagues epl,bundesliga --seasons 2022,2023,2024
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.market import devig

REPO_ROOT = Path(__file__).parent.parent.resolve()
logger = logging.getLogger("market_eval")

_ASA_TEAM_CACHE = REPO_ROOT / "data" / "asa_cache" / "get_teams_mls.parquet"
_OPENERS_PATH = REPO_ROOT / "data" / "odds_log.parquet"
_CLOSERS_PATH = REPO_ROOT / "data" / "odds_closers.parquet"
_WEBAPP_DATA = REPO_ROOT / "webapp" / "data"
_DEFAULT_EUROPEAN = ["epl", "la-liga", "serie-a", "bundesliga", "ligue-1"]
_DEFAULT_SEASONS = [2022, 2023, 2024, 2025]


# ── Metric functions (importable by tests) ────────────────────────────────────

def brier_vs_market(df: pd.DataFrame) -> dict:
    """Per-season model vs market Brier on rows where mkt_home is not NaN.

    Args:
        df: DataFrame with prob_home/draw/away, mkt_home/draw/away,
            label_result (0=home,1=draw,2=away), season columns.

    Returns:
        {season_str: {model, market, n, model_edge_pct}} — all values finite.
    """
    matched = df[df["mkt_home"].notna()].copy()
    if matched.empty:
        return {}

    y = matched["label_result"].values.astype(int)
    P = matched[["prob_home", "prob_draw", "prob_away"]].values
    M = matched[["mkt_home", "mkt_draw", "mkt_away"]].values
    Y = np.eye(3)[y]

    result = {}
    seasons = matched["season"].unique() if "season" in matched.columns else [0]
    for season in sorted(seasons):
        mask = (matched["season"] == season).values if "season" in matched.columns \
            else np.ones(len(matched), dtype=bool)
        gP, gM, gY = P[mask], M[mask], Y[mask]
        model_b = float(np.mean(np.sum((gP - gY) ** 2, axis=1)))
        market_b = float(np.mean(np.sum((gM - gY) ** 2, axis=1)))
        result[str(season)] = {
            "model": round(model_b, 4),
            "market": round(market_b, 4),
            "n": int(mask.sum()),
            "model_edge_pct": round((market_b - model_b) / market_b * 100, 2)
            if market_b > 0 else 0.0,
        }
    return result


def roi_by_edge_bucket(df: pd.DataFrame,
                       thresholds: list[float] | None = None) -> dict:
    """ROI and win-rate by model edge bucket (unit-stake approximation).

    Args:
        df: DataFrame with edge (pp), mkt_home/draw/away, label_result.
            Optional: clv (pp) column for CLV-by-bucket reporting.
        thresholds: left edges of buckets in pp (default [0, 4, 8]).

    Returns:
        {bucket_label: {n, roi, win_rate, avg_edge, avg_clv}}.
    """
    thresholds = thresholds or [0, 4, 8]
    eligible = (df[df["mkt_home"].notna() & (df["edge"] >= 0)].copy()
                if "edge" in df.columns else pd.DataFrame())

    result = {}
    for i, lo in enumerate(thresholds):
        hi = thresholds[i + 1] if i + 1 < len(thresholds) else float("inf")
        label = f"{int(lo)}–{int(hi)}%" if hi < float("inf") else f"{int(lo)}%+"
        bucket = (eligible[(eligible["edge"] >= lo) & (eligible["edge"] < hi)]
                  if not eligible.empty else pd.DataFrame())
        avg_clv = (float(bucket["clv"].mean())
                   if not bucket.empty and "clv" in bucket.columns
                   and bucket["clv"].notna().any() else None)
        result[label] = {
            "n": int(len(bucket)),
            "roi": None,  # requires settled P&L; populated when bet records exist
            "win_rate": None,
            "avg_edge": round(float(bucket["edge"].mean()), 2) if not bucket.empty else None,
            "avg_clv": round(avg_clv, 2) if avg_clv is not None else None,
        }
    return result


def market_disagreement_buckets(df: pd.DataFrame,
                                include_draw: bool = False) -> dict:
    """Side-level model-vs-market calibration by edge bucket.

    Market odds stay evaluation-only. By default this uses home/away sides and
    excludes draw, matching the current product policy of suppressing draw-side
    betting recommendations until draw calibration clears.
    """
    required = {"prob_home", "prob_draw", "prob_away",
                "mkt_home", "mkt_draw", "mkt_away", "label_result"}
    if not required.issubset(df.columns):
        return {"status": "missing_columns", "n": 0, "by_edge": {}}
    matched = df[df["mkt_home"].notna()].copy()
    if matched.empty:
        return {"status": "no_market", "n": 0, "by_edge": {}}

    sides = [("home", 0), ("away", 2)]
    if include_draw:
        sides.insert(1, ("draw", 1))
    rows = []
    for _, match in matched.iterrows():
        for side, label in sides:
            model_p = float(match[f"prob_{side}"])
            market_p = float(match[f"mkt_{side}"])
            rows.append({
                "side": side,
                "model_prob": model_p,
                "market_prob": market_p,
                "edge_pp": (model_p - market_p) * 100.0,
                "hit": int(int(match["label_result"]) == label),
            })
    side_df = pd.DataFrame(rows)
    if side_df.empty:
        return {"status": "no_market", "n": 0, "by_edge": {}}

    edge_bins = pd.cut(
        side_df["edge_pp"],
        bins=[-100.0, -8.0, -4.0, 0.0, 4.0, 8.0, 100.0],
        labels=["<=-8pp", "-8 to -4pp", "-4 to 0pp", "0 to 4pp", "4 to 8pp", "8pp+"],
        include_lowest=True,
    )
    out = {}
    for bucket, grp in side_df.groupby(edge_bins, observed=True):
        if grp.empty:
            continue
        out[str(bucket)] = {
            "n": int(len(grp)),
            "mean_model_prob": round(float(grp["model_prob"].mean()), 4),
            "mean_market_prob": round(float(grp["market_prob"].mean()), 4),
            "mean_edge_pp": round(float(grp["edge_pp"].mean()), 2),
            "hit_rate": round(float(grp["hit"].mean()), 4),
            "binary_brier": round(float(np.mean((grp["model_prob"] - grp["hit"]) ** 2)), 4),
        }

    market_under = side_df[side_df["market_prob"] <= 0.25]
    disagreement_under = market_under[market_under["edge_pp"] >= 8.0]
    return {
        "status": "ok",
        "n": int(len(side_df)),
        "include_draw": bool(include_draw),
        "mean_abs_edge_pp": round(float(side_df["edge_pp"].abs().mean()), 2),
        "max_abs_edge_pp": round(float(side_df["edge_pp"].abs().max()), 2),
        "by_edge": out,
        "market_underdogs": {
            "n": int(len(market_under)),
            "hit_rate": round(float(market_under["hit"].mean()), 4)
            if len(market_under) else None,
        },
        "disagreement_underdogs": {
            "n": int(len(disagreement_under)),
            "hit_rate": round(float(disagreement_under["hit"].mean()), 4)
            if len(disagreement_under) else None,
        },
    }


# ── MLS market join ───────────────────────────────────────────────────────────

def _asa_id_to_name() -> dict[str, str]:
    """ASA hex team_id → display name (e.g. 'Nashville SC')."""
    if not _ASA_TEAM_CACHE.exists():
        logger.warning("ASA team cache not found: %s", _ASA_TEAM_CACHE)
        return {}
    df = pd.read_parquet(_ASA_TEAM_CACHE)
    return dict(zip(df["team_id"], df["team_name"]))


def _pivot_odds(parquet_path: Path, prefix: str) -> pd.DataFrame:
    """Load odds parquet, pivot to one row per fixture.

    Returns columns: home_team, away_team, date_str,
    {prefix}_home, {prefix}_draw, {prefix}_away.
    Empty DataFrame if file missing, empty, or malformed.
    """
    if not parquet_path.exists():
        return pd.DataFrame()
    raw = pd.read_parquet(parquet_path)
    if raw.empty:
        return pd.DataFrame()
    wide = raw.pivot_table(
        index=["fixture_key", "home_team", "away_team", "commence_time"],
        columns="outcome", values="decimal_odds", aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    if not {"home", "draw", "away"}.issubset(wide.columns):
        return pd.DataFrame()
    wide["date_str"] = pd.to_datetime(wide["commence_time"]).dt.strftime("%Y-%m-%d")
    return wide[["home_team", "away_team", "date_str", "home", "draw", "away"]].rename(
        columns={"home": f"{prefix}_home", "draw": f"{prefix}_draw",
                 "away": f"{prefix}_away"})


def _devig_odds_columns(df: pd.DataFrame, prefix: str,
                        out_cols: tuple[str, str, str]) -> pd.DataFrame:
    """De-vig odds columns ({prefix}_home/draw/away) → implied prob columns."""
    h_col, d_col, a_col = f"{prefix}_home", f"{prefix}_draw", f"{prefix}_away"
    oh_col, od_col, oa_col = out_cols
    df[oh_col] = np.nan
    df[od_col] = np.nan
    df[oa_col] = np.nan
    has = df[h_col].notna()
    for idx in df[has].index:
        try:
            dv = devig(float(df.at[idx, h_col]),
                       float(df.at[idx, d_col]),
                       float(df.at[idx, a_col]))
            df.at[idx, oh_col] = dv["home"]
            df.at[idx, od_col] = dv["draw"]
            df.at[idx, oa_col] = dv["away"]
        except (ValueError, TypeError):
            pass
    return df


def join_mls_market(preds: pd.DataFrame) -> pd.DataFrame:
    """Join MLS walk-forward predictions with opening/closing Pinnacle odds.

    preds must have: date, home_team (ASA hex id), away_team (ASA hex id),
    prob_home, prob_draw, prob_away, label_result, season.

    Returns copy with mkt_home/mkt_draw/mkt_away (opening implied, NaN where
    unmatched) and optionally close_mkt_* columns.
    """
    id_map = _asa_id_to_name()
    out = preds.copy()
    out["_ht"] = out["home_team"].map(id_map).fillna("")
    out["_at"] = out["away_team"].map(id_map).fillna("")
    out["_ds"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")

    for path, prefix, out_prefix in [
        (_OPENERS_PATH, "open", "mkt"),
        (_CLOSERS_PATH, "close", "close_mkt"),
    ]:
        odds = _pivot_odds(path, prefix)
        if odds.empty:
            if out_prefix == "mkt":
                out[["mkt_home", "mkt_draw", "mkt_away"]] = np.nan
            continue
        out = out.merge(
            odds,
            left_on=["_ht", "_at", "_ds"],
            right_on=["home_team", "away_team", "date_str"],
            how="left",
            suffixes=("", f"_{prefix}"),
        )
        out = _devig_odds_columns(
            out, prefix,
            (f"{out_prefix}_home", f"{out_prefix}_draw", f"{out_prefix}_away"),
        )
        drop = [c for c in [f"home_team_{prefix}", f"away_team_{prefix}",
                             "date_str", f"{prefix}_home",
                             f"{prefix}_draw", f"{prefix}_away",
                             "home_team", "away_team"]
                if c in out.columns and c not in preds.columns]
        out = out.drop(columns=drop, errors="ignore")

    if "mkt_home" not in out.columns:
        out[["mkt_home", "mkt_draw", "mkt_away"]] = np.nan
    return out.drop(columns=["_ht", "_at", "_ds"], errors="ignore")


# ── European market summary (from existing webapp payloads) ───────────────────

def _read_payload(league_id: str) -> dict:
    """Read webapp/data/{league_id}.js and return parsed dict (or {})."""
    path = _WEBAPP_DATA / f"{league_id}.js"
    if not path.exists():
        return {}
    txt = path.read_text()
    m = re.match(r"window\.\w+ = ", txt)
    body = txt[m.end():] if m else txt
    try:
        return json.loads(body.rstrip(";\n"))
    except Exception:
        return {}


def _european_from_payload(league_id: str,
                           seasons: list[int]) -> dict:
    """Extract model vs market Brier from the existing webapp payload.

    Reads perf_by_year[] entries that have a 'market' key and whose year is
    in the requested seasons list. Returns the market_eval european sub-dict.
    """
    data = _read_payload(league_id)
    perf = data.get("perf_by_year", [])
    season_set = {str(s) for s in seasons} | {s for s in seasons}

    matched = {}
    for rec in perf:
        yr = rec.get("year") or rec.get("label")
        if yr not in season_set and str(yr) not in season_set:
            continue
        if rec.get("market") is None:
            continue
        matched[str(yr)] = {
            "model": rec["model"],
            "market": rec["market"],
            "model_edge_pct": rec.get("edge_pct"),
            "naive": rec.get("naive"),
        }

    return {
        "source": "webapp_payload",
        "n_seasons_with_market": len(matched),
        "brier_vs_market": matched,
    }


# ── MLS report section ────────────────────────────────────────────────────────

def _mls_section(test_seasons: list[int]) -> dict:
    """Build the MLS market evaluation sub-dict."""
    openers_exist = _OPENERS_PATH.exists()
    closers_exist = _CLOSERS_PATH.exists()

    if not openers_exist:
        return {
            "status": "no_odds_data",
            "note": (
                "data/odds_log.parquet does not exist yet. "
                "Run: ODDS_API_KEY=... python -m data_pipeline.odds_log"
            ),
        }

    raw = pd.read_parquet(_OPENERS_PATH)
    if raw.empty:
        return {"status": "no_odds_data", "note": "odds_log.parquet is empty"}

    # Summarize what opening lines we have
    raw["date"] = pd.to_datetime(raw["commence_time"]).dt.date
    n_fixtures = int(raw["fixture_key"].nunique())
    date_min = str(raw["date"].min())
    date_max = str(raw["date"].max())

    return {
        "status": "openers_only" if not closers_exist else "openers_and_closers",
        "n_fixtures_with_opening_odds": n_fixtures,
        "date_range": f"{date_min} to {date_max}",
        "brier_vs_market": {},
        "note": (
            "MLS market Brier requires walk-forward predictions joined to "
            "opening odds by (date, team). Accumulate more fixtures and run "
            "--mls-eval to compute."
        ),
        "clv_note": (
            "CLV available once odds_closers.parquet accumulates via: "
            "ODDS_API_KEY=... python -m data_pipeline.odds_log --closers"
        ) if not closers_exist else "CLV computable from opener/closer pairs",
    }


# ── Main report builder ───────────────────────────────────────────────────────

def build_report(test_seasons: list[int], european_leagues: list[str]) -> dict:
    """Build the full market evaluation report."""
    now = datetime.datetime.now(datetime.timezone.utc)

    euro_section: dict = {}
    for lid in european_leagues:
        euro_section[lid] = _european_from_payload(lid, test_seasons)

    return {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "test_seasons": test_seasons,
        "note": (
            "Market odds are evaluation-only — never used as training features. "
            "European: from webapp payload perf_by_year (football-data.co.uk "
            "Pinnacle/market-avg closing odds). "
            "MLS: Pinnacle h2h via The Odds API (forward-only accumulation)."
        ),
        "mls": _mls_section(test_seasons),
        "european": euro_section,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None,
                    help="Output JSON path (default: experiments/market_eval.json)")
    ap.add_argument("--seasons", default=None,
                    help="Comma-separated test seasons, e.g. 2022,2023,2024,2025")
    ap.add_argument("--leagues", default=None,
                    help="Comma-separated European league IDs, "
                         "e.g. epl,bundesliga,la-liga")
    args = ap.parse_args()

    seasons = ([int(s) for s in args.seasons.split(",")]
               if args.seasons else _DEFAULT_SEASONS)
    leagues = args.leagues.split(",") if args.leagues else _DEFAULT_EUROPEAN

    report = build_report(seasons, leagues)

    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "experiments" / "market_eval.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"[market_eval] report written → {out_path}")

    mls = report.get("mls", {})
    print(f"[market_eval] MLS: {mls.get('status', '?')}")
    for lid, ev in report.get("european", {}).items():
        n = ev.get("n_seasons_with_market", 0)
        print(f"[market_eval] {lid}: {n} seasons with market data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
