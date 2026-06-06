#!/usr/bin/env python3
"""Print overall prediction and market performance from PostgreSQL."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from data_pipeline import db_utils


def _prediction_rows(season: int | None, model: str | None) -> pd.DataFrame:
    params: list[object] = []
    clauses = [
        "m.status = 'completed'",
        "m.home_goals IS NOT NULL",
        "m.away_goals IS NOT NULL",
    ]
    if season is not None:
        clauses.append("m.season = %s")
        params.append(season)
    if model is not None:
        clauses.append("p.model = %s")
        params.append(model)

    where = " AND ".join(clauses)
    return db_utils.query(
        f"""
        WITH latest_predictions AS (
            SELECT DISTINCT ON (match_id, model) *
            FROM predictions
            ORDER BY match_id, model, predicted_at DESC
        )
        SELECT
            p.match_id,
            p.model,
            p.prob_home,
            p.prob_draw,
            p.prob_away,
            p.prob_over,
            p.prob_under,
            p.predicted_at,
            m.date,
            m.season,
            m.home_team,
            m.away_team,
            m.home_goals,
            m.away_goals
        FROM latest_predictions p
        JOIN matches m ON m.match_id = p.match_id
        WHERE {where}
        ORDER BY m.date, p.model
        """,
        params,
    )


def _prediction_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    rows = []
    for model, group in df.groupby("model", sort=True):
        probs = group[["prob_home", "prob_draw", "prob_away"]].astype(float).to_numpy()
        probs = np.clip(probs, 1e-6, 1 - 1e-6)
        probs = probs / probs.sum(axis=1, keepdims=True)

        actual = np.select(
            [
                group["home_goals"] > group["away_goals"],
                group["home_goals"] == group["away_goals"],
                group["home_goals"] < group["away_goals"],
            ],
            [0, 1, 2],
        )
        y = np.eye(3)[actual]

        # brier_half = sum_form / 2 (display convention; canonical is sum-form ~0.6375)
        brier = np.sum((probs - y) ** 2, axis=1) / 2.0
        logloss = -np.log(probs[np.arange(len(group)), actual])
        accuracy = np.argmax(probs, axis=1) == actual

        over_mask = group["prob_over"].notna()
        if over_mask.any():
            over_probs = group.loc[over_mask, "prob_over"].astype(float).clip(1e-6, 1 - 1e-6)
            actual_over = (
                group.loc[over_mask, "home_goals"] + group.loc[over_mask, "away_goals"] > 2.5
            ).astype(int)
            brier_ou = ((over_probs - actual_over) ** 2).mean()
            acc_ou = ((over_probs >= 0.5).astype(int) == actual_over).mean()
        else:
            brier_ou = math.nan
            acc_ou = math.nan

        rows.append(
            {
                "model": model,
                "matches": int(len(group)),
                "brier_1x2": float(np.mean(brier)),
                "log_loss_1x2": float(np.mean(logloss)),
                "accuracy_1x2": float(np.mean(accuracy)),
                "brier_over25": float(brier_ou) if not pd.isna(brier_ou) else None,
                "accuracy_over25": float(acc_ou) if not pd.isna(acc_ou) else None,
                "first_match": str(pd.to_datetime(group["date"]).min().date()),
                "last_match": str(pd.to_datetime(group["date"]).max().date()),
            }
        )

    return pd.DataFrame(rows).sort_values(["model"]).reset_index(drop=True)


def _bet_rows(season: int | None, edge_threshold: float) -> pd.DataFrame:
    params: list[object] = [edge_threshold]
    season_clause = ""
    if season is not None:
        season_clause = "AND m.season = %s"
        params.append(season)

    return db_utils.query(
        f"""
        SELECT sb.*, m.date, m.season, m.home_team, m.away_team
        FROM simulated_bets sb
        JOIN matches m ON m.match_id = sb.match_id
        WHERE sb.result IS NOT NULL
          AND sb.edge_pct >= %s
          {season_clause}
        ORDER BY m.date, sb.placed_at
        """,
        params,
    )


def _bet_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}

    stake25 = float(df["stake_kelly25"].fillna(0).sum())
    stake50 = float(df["stake_kelly50"].fillna(0).sum())
    pnl25 = float(df["pnl_kelly25"].fillna(0).sum())
    pnl50 = float(df["pnl_kelly50"].fillna(0).sum())
    clv = df["clv"].dropna() if "clv" in df.columns else pd.Series(dtype=float)

    return {
        "settled_bets": int(len(df)),
        "win_rate": float((df["result"] == "won").mean()),
        "roi_kelly25": pnl25 / stake25 if stake25 > 0 else None,
        "roi_kelly50": pnl50 / stake50 if stake50 > 0 else None,
        "pnl_kelly25": pnl25,
        "pnl_kelly50": pnl50,
        "avg_clv_pct": float(clv.mean()) if not clv.empty else None,
        "positive_clv_rate": float((clv > 0).mean()) if not clv.empty else None,
        "avg_edge_pct": float(df["edge_pct"].mean()),
    }


def _latest_pipeline_run() -> dict:
    runs = db_utils.query(
        """
        SELECT run_type, status, started_at, finished_at, step_name, message, stats
        FROM pipeline_runs
        ORDER BY started_at DESC
        LIMIT 1
        """
    )
    if runs.empty:
        return {}
    row = runs.iloc[0].to_dict()
    stats = row.get("stats")
    if isinstance(stats, str) and stats:
        try:
            row["stats"] = json.loads(stats)
        except json.JSONDecodeError:
            pass
    return row


def _print_markdown(pred_metrics: pd.DataFrame, bet_metrics: dict, latest_run: dict) -> None:
    print("# MLS Performance Report")
    print()
    print("Baselines: uniform 1X2 Brier is 0.3333; uniform log loss is 1.0986.")
    print()

    if pred_metrics.empty:
        print("No completed-match prediction rows found.")
    else:
        display = pred_metrics.copy()
        for col in ["brier_1x2", "log_loss_1x2", "accuracy_1x2", "brier_over25", "accuracy_over25"]:
            if col in display.columns:
                display[col] = display[col].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")
        columns = list(display.columns)
        rows = [[str(value) for value in row] for row in display.to_numpy()]
        widths = [
            max(len(str(col)), *(len(row[idx]) for row in rows)) if rows else len(str(col))
            for idx, col in enumerate(columns)
        ]
        header = "| " + " | ".join(str(col).ljust(widths[idx]) for idx, col in enumerate(columns)) + " |"
        divider = "| " + " | ".join("-" * widths[idx] for idx in range(len(columns))) + " |"
        print(header)
        print(divider)
        for row in rows:
            print("| " + " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(columns))) + " |")

    print()
    print("## Betting")
    if not bet_metrics:
        print("No settled simulated bets found for the selected filters.")
    else:
        for key, value in bet_metrics.items():
            if isinstance(value, float):
                print(f"- {key}: {value:.4f}")
            else:
                print(f"- {key}: {value}")

    print()
    print("## Latest Pipeline Run")
    if not latest_run:
        print("No pipeline run metadata found.")
    else:
        for key in ["run_type", "status", "started_at", "finished_at", "step_name", "message"]:
            print(f"- {key}: {latest_run.get(key)}")
        if latest_run.get("stats"):
            print("- stats:")
            for key, value in latest_run["stats"].items():
                print(f"  - {key}: {value}")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, help="Limit metrics to one season.")
    parser.add_argument("--model", help="Limit prediction metrics to one model.")
    parser.add_argument("--edge-threshold", type=float, default=0.0, help="Minimum simulated bet edge.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    args = parser.parse_args()

    try:
        pred_df = _prediction_rows(args.season, args.model)
        pred_metrics = _prediction_metrics(pred_df)
        bets_df = _bet_rows(args.season, args.edge_threshold)
        bet_metrics = _bet_metrics(bets_df)
        latest_run = _latest_pipeline_run()
    except Exception as exc:
        print(f"Could not read performance metrics from PostgreSQL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "prediction_metrics": pred_metrics.to_dict(orient="records"),
            "betting_metrics": bet_metrics,
            "latest_pipeline_run": latest_run,
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_markdown(pred_metrics, bet_metrics, latest_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
