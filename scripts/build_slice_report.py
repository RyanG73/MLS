#!/usr/bin/env python3
"""Build a public model-slice summary for the webapp.

This is intentionally a presentation artifact, not a replacement for the full
experiment reports. It distills the current champion-family reports into a
small UI payload that can answer: where is the model strong, where is it weak,
and which diagnostics are still missing?
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.payload_utils import write_js_payload

REPO_ROOT = Path(__file__).parent.parent.resolve()
OUT = REPO_ROOT / "webapp" / "data" / "model-slices.js"


FAMILIES = [
    {
        "id": "mls",
        "label": "MLS",
        "champion": "experiments/champion.json",
        "leagues": ["mls"],
        "policy": "MLS-specific champion; parity, travel, playoffs, and roster churn are not imported from Europe.",
    },
    {
        "id": "eur_big5",
        "label": "Big-5 Europe",
        "champion": "experiments/champion_eur_big5.json",
        "leagues": ["epl", "la-liga", "bundesliga", "serie-a", "ligue-1"],
        "policy": "Strongest launch family; market-blind probabilities are useful, but historical markets can still be sharper on aggregate.",
    },
    {
        "id": "eur_tiers",
        "label": "Europe tiers / goals-only",
        "champion": "experiments/champion_eur_tiers.json",
        "leagues": [
            "championship",
            "league-one",
            "league-two",
            "bundesliga-2",
            "serie-b",
            "segunda",
            "ligue-2",
            "eredivisie",
            "primeira",
            "scottish-prem",
            "belgian-pro",
            "greek-super",
            "super-lig",
        ],
        "policy": "Breadth product; promotion/relegation priors and draw behavior need family-specific diagnostics.",
    },
    {
        "id": "nwsl",
        "label": "NWSL",
        "champion": "experiments/champion_nwsl.json",
        "leagues": ["nwsl"],
        "policy": "XGB-only champion; Dixon-Coles leg is treated as a known liability until it clears the NWSL gate.",
    },
    {
        "id": "usl",
        "label": "USL Championship",
        "champion": "experiments/champion_usl.json",
        "leagues": ["usl-championship"],
        "policy": "Match model is useful; season odds should stay cautious until the conference-aware playoff sim is complete.",
    },
]


STATIC_LIMITS = {
    "mls": [
        "Low-confidence favorites and predicted-away rows are weaker than high-confidence home-favorite rows.",
        "Volatile lower-table clubs and roster-reset teams need extra caution.",
        "Draw probabilities remain useful context, but draw-side betting stays suppressed.",
    ],
    "eur_big5": [
        "This is the strongest family versus naive, but it can trail Pinnacle/market history by league and season.",
        "Use market disagreement as a research queue, not as a claim that the model beats the market globally.",
        "Bottom-half preseason value priors are promising; broad match-level value features are not proven.",
    ],
    "eur_tiers": [
        "Promoted/relegated teams need bridge-decay diagnostics before early-season odds are treated as mature.",
        "Goals-only coverage increases uncertainty in style, player, and xG-sensitive leagues.",
        "Draw calibration should be reviewed by league family before draw-side edges are exposed.",
    ],
    "nwsl": [
        "The current champion is only modestly above naive, so confidence language should stay restrained.",
        "Dixon-Coles variants are not production-eligible for this league today.",
        "Show sample size and calibration before any betting-adjacent interpretation.",
    ],
    "usl": [
        "USL shows useful aggregate lift, but playoff approximation is still a product limitation.",
        "Conference and playoff-format handling should clear its own gate before season futures are emphasized.",
        "Treat thin-market odds as informational until CLV history accrues.",
    ],
}


DIAGNOSTIC_QUEUE = [
    "Underdog bins",
    "Draw calibration by total-goals expectation",
    "Market-disagreement buckets",
    "Promoted/relegated bridge decay",
    "Value-rank versus projected-rank gaps",
]


def _team_name_map() -> dict[str, str]:
    """Best-effort ASA opaque team_id -> display name map for legacy reports."""
    src = REPO_ROOT / "data_pipeline" / "team_metadata.py"
    try:
        text = src.read_text()
    except FileNotFoundError:
        return {}
    out = {}
    for team_id, comment in re.findall(r'"([A-Za-z0-9]+)"\s*:\s*\([^#\n]+#\s*([^\n]+)', text):
        name = comment.strip()
        if name and "alt ID" not in name:
            out[team_id] = name
    return out


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _load_js_payload(path: Path) -> dict[str, Any]:
    text = path.read_text()
    match = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JS payload assignment found in {path}")
    return json.loads(match.group(1))


def _resolve_report(champion_path: str) -> tuple[Path | None, dict[str, Any]]:
    pointer = REPO_ROOT / champion_path
    if not pointer.exists():
        return None, {}
    try:
        ptr = _load_json(pointer)
    except json.JSONDecodeError:
        return pointer, {}
    report_name = ptr.get("report")
    if report_name:
        report_path = REPO_ROOT / report_name
        if report_path.exists():
            return report_path, _load_json(report_path)
    return pointer, ptr


def _metric(report: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        val = report.get(key)
        if isinstance(val, (int, float)):
            return round(float(val), 6)
    return None


def _improvement(model: float | None, naive: float | None) -> float | None:
    if model is None or naive in (None, 0):
        return None
    return round((1.0 - model / naive) * 100.0, 2)


def _confidence_rows(slices: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for label, metrics in (slices.get("by_confidence") or {}).items():
        if not isinstance(metrics, dict) or not metrics.get("n"):
            continue
        rows.append(
            {
                "bucket": label,
                "n": int(metrics["n"]),
                "brier": round(float(metrics.get("brier_sum", 0.0)), 4),
                "accuracy": round(float(metrics.get("accuracy", 0.0)) * 100.0, 1),
            }
        )
    return rows


def _worst_home_teams(slices: dict[str, Any], n: int = 6,
                      name_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
    teams = []
    name_map = name_map or {}
    for team, metrics in (slices.get("by_home_team") or {}).items():
        if not isinstance(metrics, dict) or metrics.get("n", 0) < 10:
            continue
        teams.append(
            {
                "team": name_map.get(str(team), str(team)),
                "team_id": str(team) if str(team) in name_map else None,
                "n": int(metrics["n"]),
                "brier": round(float(metrics.get("brier_sum", 0.0)), 4),
                "accuracy": round(float(metrics.get("accuracy", 0.0)) * 100.0, 1),
            }
        )
    teams.sort(key=lambda row: row["brier"], reverse=True)
    return teams[:n]


def _phase_rows(slices: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for label, metrics in (slices.get("by_season_phase") or {}).items():
        if not isinstance(metrics, dict) or not metrics.get("n"):
            continue
        rows.append(
            {
                "phase": label,
                "n": int(metrics["n"]),
                "brier": round(float(metrics.get("brier_sum", 0.0)), 4),
                "accuracy": round(float(metrics.get("accuracy", 0.0)) * 100.0, 1),
            }
        )
    return rows


def _draw_note(slices: dict[str, Any]) -> str | None:
    curve = slices.get("draw_reliability") or []
    if not curve:
        return None
    worst = max(curve, key=lambda row: abs(row.get("p_mean", 0) - row.get("freq", 0)))
    gap = abs(worst.get("p_mean", 0) - worst.get("freq", 0)) * 100.0
    return f"largest measured draw-bin gap is {gap:.1f}pp around {float(worst.get('p_mean', 0))*100:.0f}% predicted draw"


def _result_label(game: dict[str, Any]) -> str | None:
    result = game.get("result")
    if result in {"H", "D", "A"}:
        return result
    hg, ag = game.get("hg"), game.get("ag")
    if hg is None or ag is None:
        return None
    if hg > ag:
        return "H"
    if hg < ag:
        return "A"
    return "D"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(sum(values) / len(values)), 4)


def _bin_rows(rows: list[dict[str, Any]], value_key: str, actual_key: str,
              bins: list[tuple[str, float, float]]) -> list[dict[str, Any]]:
    out = []
    for label, lo, hi in bins:
        group = [r for r in rows if lo <= r[value_key] < hi]
        if not group:
            continue
        played = [r for r in group if r.get(actual_key) is not None]
        hit_rate = _mean([1.0 if r[actual_key] else 0.0 for r in played])
        out.append({
            "bucket": label,
            "n": len(group),
            "played_n": len(played),
            "mean": _mean([float(r[value_key]) for r in group]),
            "hit_rate": hit_rate,
        })
    return out


def _empty_forward_diag(league_id: str, league_name: str) -> dict[str, Any]:
    return {
        "league": league_id,
        "league_name": league_name,
        "matches": {"total": 0, "upcoming": 0, "played": 0, "market": 0},
        "favorite_bins": [],
        "draw_bins": [],
        "total_goals_draw": [],
        "underdogs": {
            "model_count": 0,
            "upcoming_count": 0,
            "played_count": 0,
            "hit_rate": None,
            "market_count": 0,
            "disagreement_count": 0,
        },
        "market_disagreement": {"status": "no_market", "n": 0, "max_edge_pp": None},
        "value_rank_gaps": [],
    }


def _league_current_diagnostics(league_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    league_name = (payload.get("league") or {}).get("name", league_id)
    games = [g for g in payload.get("games") or []
             if all(isinstance(g.get(k), (int, float)) for k in ("pH", "pD", "pA"))]
    if not games:
        return _empty_forward_diag(league_id, league_name)

    favorite_rows = []
    draw_rows = []
    total_goal_rows = []
    underdogs = []
    market_edges = []
    for game in games:
        result = _result_label(game)
        probs = {"H": float(game["pH"]), "D": float(game["pD"]), "A": float(game["pA"])}
        fav_side = max(probs, key=probs.get)
        favorite_rows.append({
            "prob": probs[fav_side],
            "hit": None if result is None else result == fav_side,
        })
        draw_rows.append({
            "prob": probs["D"],
            "hit": None if result is None else result == "D",
        })
        if isinstance(game.get("lam"), (int, float)) and isinstance(game.get("mu"), (int, float)):
            total_goal_rows.append({
                "total": float(game["lam"]) + float(game["mu"]),
                "draw_prob": probs["D"],
                "hit": None if result is None else result == "D",
            })
        for side, team_key, prob_key, mkt_key in (
            ("H", "home", "pH", "mkt_home"),
            ("A", "away", "pA", "mkt_away"),
        ):
            p = float(game[prob_key])
            mkt = game.get(mkt_key)
            if p <= 0.25:
                underdogs.append({
                    "team": game.get(team_key),
                    "side": side,
                    "prob": p,
                    "upcoming": result is None,
                    "hit": None if result is None else result == side,
                    "market_prob": mkt if isinstance(mkt, (int, float)) else None,
                })
            if isinstance(mkt, (int, float)):
                market_edges.append(abs(p - float(mkt)) * 100.0)

    fav_bins = _bin_rows(
        favorite_rows,
        "prob",
        "hit",
        [("<40%", 0.0, 0.4), ("40-50%", 0.4, 0.5), ("50-60%", 0.5, 0.6), (">60%", 0.6, 1.01)],
    )
    draw_bins = _bin_rows(
        draw_rows,
        "prob",
        "hit",
        [("<20%", 0.0, 0.2), ("20-25%", 0.2, 0.25), ("25-30%", 0.25, 0.3), ("30%+", 0.3, 1.01)],
    )
    total_goals_draw = []
    for label, lo, hi in [("low total", 0.0, 2.4), ("middle total", 2.4, 3.0), ("high total", 3.0, 20.0)]:
        group = [r for r in total_goal_rows if lo <= r["total"] < hi]
        if not group:
            continue
        played = [r for r in group if r["hit"] is not None]
        total_goals_draw.append({
            "bucket": label,
            "n": len(group),
            "played_n": len(played),
            "mean_total": _mean([r["total"] for r in group]),
            "mean_draw_prob": _mean([r["draw_prob"] for r in group]),
            "draw_hit_rate": _mean([1.0 if r["hit"] else 0.0 for r in played]),
        })

    played_under = [r for r in underdogs if r["hit"] is not None]
    market_under = [r for r in underdogs if r["market_prob"] is not None and r["market_prob"] <= 0.25]
    disagreement_under = [
        r for r in underdogs
        if r["market_prob"] is not None and r["market_prob"] <= 0.25 and r["prob"] >= r["market_prob"] + 0.08
    ]

    standings = payload.get("standings") or []
    squad_values = payload.get("squad_value") or {}
    value_gaps = []
    for row in standings:
        team = row.get("team")
        sv = squad_values.get(team)
        if not sv or not isinstance(row.get("proj_rank"), (int, float)) or not isinstance(sv.get("league_rank"), (int, float)):
            continue
        gap = float(sv["league_rank"]) - float(row["proj_rank"])
        if abs(gap) < 4:
            continue
        value_gaps.append({
            "team": team,
            "projected_rank": round(float(row["proj_rank"]), 1),
            "value_rank": int(sv["league_rank"]),
            "gap": round(gap, 1),
            "label": "low-value overachiever" if gap > 0 else "high-value underachiever",
        })
    value_gaps.sort(key=lambda r: abs(r["gap"]), reverse=True)

    upcoming = sum(1 for g in games if _result_label(g) is None)
    played = len(games) - upcoming
    market_games = sum(1 for g in games if isinstance(g.get("mkt_home"), (int, float)) and isinstance(g.get("mkt_away"), (int, float)))
    return {
        "league": league_id,
        "league_name": league_name,
        "matches": {"total": len(games), "upcoming": upcoming, "played": played, "market": market_games},
        "favorite_bins": fav_bins,
        "draw_bins": draw_bins,
        "total_goals_draw": total_goals_draw,
        "underdogs": {
            "model_count": len(underdogs),
            "upcoming_count": sum(1 for r in underdogs if r["upcoming"]),
            "played_count": len(played_under),
            "hit_rate": _mean([1.0 if r["hit"] else 0.0 for r in played_under]),
            "market_count": len(market_under),
            "disagreement_count": len(disagreement_under),
        },
        "market_disagreement": {
            "status": "ok" if market_edges else "no_market",
            "n": len(market_edges),
            "max_edge_pp": round(max(market_edges), 1) if market_edges else None,
            "mean_abs_edge_pp": round(float(sum(market_edges) / len(market_edges)), 1) if market_edges else None,
        },
        "value_rank_gaps": value_gaps[:8],
    }


def _aggregate_forward(league_diags: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values = list(league_diags.values())
    matches = {
        "total": sum(d["matches"]["total"] for d in values),
        "upcoming": sum(d["matches"]["upcoming"] for d in values),
        "played": sum(d["matches"]["played"] for d in values),
        "market": sum(d["matches"]["market"] for d in values),
    }
    under = {
        "model_count": sum(d["underdogs"]["model_count"] for d in values),
        "upcoming_count": sum(d["underdogs"]["upcoming_count"] for d in values),
        "market_count": sum(d["underdogs"]["market_count"] for d in values),
        "disagreement_count": sum(d["underdogs"]["disagreement_count"] for d in values),
    }
    value_gaps = []
    for d in values:
        for row in d.get("value_rank_gaps") or []:
            value_gaps.append({"league": d["league"], "league_name": d["league_name"], **row})
    value_gaps.sort(key=lambda r: abs(r["gap"]), reverse=True)
    draw_heavy = sum(
        row["n"]
        for d in values
        for row in d.get("draw_bins") or []
        if row["bucket"] == "30%+"
    )
    return {
        "matches": matches,
        "underdogs": under,
        "draw_heavy_matches": draw_heavy,
        "market_status": "ok" if matches["market"] else "no_market",
        "value_rank_gaps": value_gaps[:10],
    }


def _family_payload(spec: dict[str, Any]) -> dict[str, Any]:
    report_path, report = _resolve_report(spec["champion"])
    slices = report.get("slices") or {}
    model_brier = _metric(report, "avg_brier", "best_brier")
    naive_brier = _metric(report, "naive_brier")
    overall = report.get("overall") or {}
    if model_brier is None and isinstance(overall, dict):
        model_brier = _metric(overall, "brier_sum")

    confidence = _confidence_rows(slices)
    worst_teams = _worst_home_teams(slices, name_map=_team_name_map())
    phase = _phase_rows(slices)
    limits = list(STATIC_LIMITS[spec["id"]])
    draw_note = _draw_note(slices)
    if draw_note:
        limits.append(draw_note + ".")

    missing = []
    if not confidence:
        missing.append("confidence bins")
    if not worst_teams:
        missing.append("club/team weak spots")
    if "by_favorite_prob" not in slices:
        missing.append("favorite probability bins")
    if "draw_reliability" not in slices:
        missing.append("draw reliability curve")
    if "market_disagreement" not in slices:
        missing.append("market disagreement buckets")
    league_diagnostics = {}
    for league_id in spec["leagues"]:
        path = REPO_ROOT / "webapp" / "data" / f"{league_id}.js"
        if not path.exists():
            continue
        try:
            league_diagnostics[league_id] = _league_current_diagnostics(league_id, _load_js_payload(path))
        except Exception:
            continue

    return {
        "id": spec["id"],
        "label": spec["label"],
        "leagues": spec["leagues"],
        "report": str(report_path.relative_to(REPO_ROOT)) if report_path else None,
        "model_brier": model_brier,
        "naive_brier": naive_brier,
        "improvement_pct": _improvement(model_brier, naive_brier),
        "sample_n": int((overall or {}).get("n", 0)) or None,
        "policy": spec["policy"],
        "limits": limits,
        "confidence": confidence,
        "worst_home_teams": worst_teams,
        "season_phase": phase,
        "forward_summary": _aggregate_forward(league_diagnostics),
        "league_diagnostics": league_diagnostics,
        "missing_diagnostics": missing,
    }


def main() -> int:
    families = [_family_payload(spec) for spec in FAMILIES]
    league_map = {}
    for family in families:
        for league_id in family["leagues"]:
            league_map[league_id] = family["id"]

    out = {
        "status": "ok",
        "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "families": families,
        "league_family": league_map,
        "diagnostic_queue": DIAGNOSTIC_QUEUE,
        "note": "Family-level public summary distilled from champion report artifacts; full experiment JSON remains the source of truth.",
    }
    write_js_payload(OUT, "MODEL_SLICES", out)
    try:
        shown = OUT.relative_to(REPO_ROOT)
    except ValueError:
        shown = OUT
    print(f"[slice-report] wrote {shown} ({len(families)} families)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
