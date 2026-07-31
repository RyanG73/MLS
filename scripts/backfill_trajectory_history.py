#!/usr/bin/env python3
"""Reconstruct current-season forecast trajectories from point-in-time inputs.

The nightly odds archive is the authoritative record from the day it began.
This script fills only the earlier part of the current season by replaying the
same Dixon-Coles season model at historical matchday cutoffs.  Later results
are used only to recover the fixture list; their scores are never visible to a
replay.  Current-state roster, injury and squad-value inputs are deliberately
excluded because dated snapshots do not exist for every league.

Output is a separate parquet so reconstructed forecasts can never be confused
with, or overwrite, forecasts that were actually published at the time.

Usage:
    python scripts/backfill_trajectory_history.py --sims 2000
    python scripts/backfill_trajectory_history.py --league mls --sims 500
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.research_model import fit_temperature_scalar
from scripts.archive_odds_snapshot import _ODDS_KEYS, _load_payload
from scripts.build_league_data import (
    FDI_ESPN,
    FD_ESPN,
    OUTLOOK,
    _bucket_idx,
    _championship_winner,
    _promo_playoff_winner,
)
from scripts.eval.dixon_coles import dc_predict, dc_predict_batch, fit_dc
from scripts.eval.elo import compute_elo
from scripts.eval.season_format import FORMATS, format_classification, regular_phase_mask
from scripts.eval.sim_variance import perturb_probs, preseason_sigma_for_source


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PAYLOAD_DIR = ROOT / "webapp" / "data"
ARCHIVE = DATA_DIR / "odds_history.parquet"
OUT = DATA_DIR / "reconstructed_trajectory_history.parquet"
COVERAGE = DATA_DIR / "reconstructed_trajectory_coverage.json"
METHOD = "dc-point-in-time-v1"


def _payload(lid: str) -> dict:
    return _load_payload(PAYLOAD_DIR / f"{lid}.js")


def _cached_history(lid: str, source: str) -> pd.DataFrame:
    """Load committed/cached history without refreshing a live provider."""
    if lid == "mls":
        return pd.read_parquet(DATA_DIR / "parity_frame.parquet")
    if source in {"understat", "footballdata", "footballdata_intl"}:
        folder = {"footballdata": "football_data",
                  "footballdata_intl": "football_data_intl"}.get(source, source)
        path = DATA_DIR / folder / f"{lid}.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()
    if source == "espn":
        paths = sorted((DATA_DIR / "espn_fixtures").glob(f"{lid}-*.parquet"))
        frames = [pd.read_parquet(p) for p in paths]
        keep = ["date", "season", "home_team", "away_team", "home_goals",
                "away_goals", "is_playoff"]
        frames = [f[[c for c in keep if c in f.columns]] for f in frames]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if source == "asa":
        from data_pipeline.asa_frame import asa_canonical_frame
        return asa_canonical_frame(OUTLOOK[lid].get("asa_key", lid))
    if source == "api_football":
        from data_pipeline.api_football import LEAGUE, ROUND_EXCLUDE, _parse_fixtures
        af_id, _ = LEAGUE[lid]
        paths = sorted((DATA_DIR / "api_football").glob(f"{af_id}_*.json"))
        frames = [_parse_fixtures(json.loads(p.read_text()), ROUND_EXCLUDE.get(af_id), af_id)
                  for p in paths]
        return pd.concat([f for f in frames if len(f)], ignore_index=True) \
            if any(len(f) for f in frames) else pd.DataFrame()
    return pd.DataFrame()


def _display_to_model(lid: str, source: str) -> dict[str, str]:
    if source in {"footballdata", "asa"}:
        return {display: model for model, display in FD_ESPN.get(lid, {}).items()}
    if source == "footballdata_intl":
        return {display: model for model, display in FDI_ESPN.get(lid, {}).items()}
    return {}


def _schedule_frame(lid: str, payload: dict, source: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """Payload games -> model-name fixture frame and model->display map."""
    d2m = _display_to_model(lid, source)
    display_for: dict[str, str] = {}
    id_for = {s["team"]: s.get("team_id") for s in payload.get("standings") or []}
    rows = []
    for g in payload.get("games") or []:
        if not g.get("date") or not g.get("home") or not g.get("away"):
            continue
        if lid == "mls":
            h = g.get("home_id") or id_for.get(g["home"])
            a = g.get("away_id") or id_for.get(g["away"])
        else:
            h = d2m.get(g["home"], g["home"])
            a = d2m.get(g["away"], g["away"])
        if not h or not a:
            continue
        display_for[h], display_for[a] = g["home"], g["away"]
        rows.append({
            "date": pd.Timestamp(g["date"]), "home_team": h, "away_team": a,
            "home_goals": g.get("hg"), "away_goals": g.get("ag"),
            "is_result": g.get("result") is not None,
            "is_playoff": 0, "season": payload.get("season"),
        })
    for s in payload.get("standings") or []:
        model = id_for.get(s["team"]) if lid == "mls" else d2m.get(s["team"], s["team"])
        if model:
            display_for[model] = s["team"]
    frame = pd.DataFrame(rows)
    if len(frame):
        frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
    return frame, display_for


def _canonical_played(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"])
    if "is_playoff" in out:
        out = out[out["is_playoff"].isna() | (out["is_playoff"] == 0)]
    out["home_goals"] = out["home_goals"].astype(float)
    out["away_goals"] = out["away_goals"].astype(float)
    return out.sort_values("date", kind="stable").reset_index(drop=True)


def _temperature(prefix: pd.DataFrame) -> float:
    """Production-style calibration on the last fully completed season."""
    if len(prefix) < 250 or "season" not in prefix:
        return 1.0
    seasons = (prefix.groupby("season")["date"].max().sort_values().index.tolist())
    if len(seasons) < 2:
        return 1.0
    cal_season = seasons[-1]
    cal = prefix[prefix["season"] == cal_season]
    train = prefix[prefix["season"] != cal_season]
    if len(train) < 200 or len(cal) < 30:
        return 1.0
    atk, dfd, ha, rho = fit_dc(train)
    raw = dc_predict_batch(cal, atk, dfd, ha, rho)
    y = np.where(cal["home_goals"] > cal["away_goals"], 0,
                 np.where(cal["home_goals"] == cal["away_goals"], 1, 2))
    return float(fit_temperature_scalar(raw, y))


def _checkpoints(schedule: pd.DataFrame, stop: pd.Timestamp, step_games: int) -> list[pd.Timestamp]:
    first = schedule["date"].min()
    played = schedule[schedule["is_result"] & (schedule["date"] <= stop)]
    dates = [first - pd.Timedelta(days=1)]
    if played.empty:
        return dates
    teams = sorted(set(schedule["home_team"]) | set(schedule["away_team"]))
    last_level = 0
    for date, _ in played.groupby("date", sort=True):
        through = played[played["date"] <= date]
        counts = pd.concat([through["home_team"], through["away_team"]]).value_counts()
        level = int(round(float(counts.reindex(teams, fill_value=0).mean())))
        if level >= last_level + step_games:
            dates.append(pd.Timestamp(date)); last_level = level
    last = pd.Timestamp(played["date"].max())
    if dates[-1] != last:
        dates.append(last)
    return sorted(set(dates))


def _base_table(played: pd.DataFrame, teams: list[str]) -> tuple[np.ndarray, np.ndarray]:
    idx = {t: i for i, t in enumerate(teams)}
    pts, gd = np.zeros(len(teams)), np.zeros(len(teams))
    for r in played.itertuples():
        hi, ai = idx[r.home_team], idx[r.away_team]
        hg, ag = int(r.home_goals), int(r.away_goals)
        gd[hi] += hg - ag; gd[ai] += ag - hg
        if hg > ag:
            pts[hi] += 3
        elif hg < ag:
            pts[ai] += 3
        else:
            pts[hi] += 1; pts[ai] += 1
    return pts, gd


def _seed_missing(teams: list[str], atk: dict, dfd: dict) -> None:
    av, dv = sorted(atk.values()), sorted(dfd.values())
    ai = max(0, int(len(av) * 0.15) - 1)
    di = min(len(dv) - 1, int(len(dv) * 0.85))
    af, df = (av[ai] if av else -0.2), (dv[di] if dv else 0.2)
    for team in teams:
        if team not in atk:
            atk[team], dfd[team] = af, df


def _prob_matrix(teams: list[str], atk: dict, dfd: dict,
                 ha: float, rho: float, temperature: float) -> np.ndarray:
    n = len(teams)
    out = np.zeros((n, n, 3))
    for hi, home in enumerate(teams):
        for ai, away in enumerate(teams):
            if hi == ai:
                continue
            raw = np.asarray(dc_predict(home, away, atk, dfd, ha, rho))
            lp = np.log(np.clip(raw, 1e-9, 1.0)) / temperature
            lp -= lp.max()
            out[hi, ai] = np.exp(lp) / np.exp(lp).sum()
    return out


def _generic_sim(schedule: pd.DataFrame, played: pd.DataFrame, teams: list[str],
                 buckets: list[dict], pm: np.ndarray, n_sims: int, sigma: float,
                 seed: int, lid: str) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    idx = {t: i for i, t in enumerate(teams)}
    base_pts, base_gd = _base_table(played, teams)
    remaining = schedule[~schedule.index.isin(played.index)]
    rh = remaining["home_team"].map(idx).to_numpy(dtype=int)
    ra = remaining["away_team"].map(idx).to_numpy(dtype=int)
    rp = pm[rh, ra] if len(remaining) else np.zeros((0, 3))
    lrp = np.log(np.clip(rp, 1e-12, 1.0)) if len(remaining) and sigma > 1 else None
    counts = {b["key"]: np.zeros(len(teams)) for b in buckets}
    proj = np.zeros(len(teams))
    rng = np.random.default_rng(seed)
    grp_bonus = np.zeros(len(teams))
    fmt = FORMATS.get(lid)
    if fmt is not None and len(played):
        cls = format_classification(played.sort_values("date"), fmt, teams)
        reg_games = fmt["rr"] * (len(teams) - 1)
        if regular_phase_mask(played.sort_values("date"), reg_games).sum() >= reg_games * len(teams) / 2:
            base_pts = np.array([cls[t]["pts"] for t in teams], dtype=float)
            base_gd = np.array([cls[t]["gd"] for t in teams], dtype=float)
            grp_bonus = np.array([-cls[t]["group"] * 1e7 for t in teams])
    for _ in range(n_sims):
        points = base_pts.copy()
        if len(remaining):
            probs = perturb_probs(lrp, rh, ra, rng.standard_normal(len(teams)) * sigma) \
                if lrp is not None else rp
            u = rng.random(len(remaining))
            outcome = np.where(u < probs[:, 0], 0,
                               np.where(u < probs[:, 0] + probs[:, 1], 1, 2))
            np.add.at(points, rh[outcome == 0], 3)
            np.add.at(points, rh[outcome == 1], 1)
            np.add.at(points, ra[outcome == 1], 1)
            np.add.at(points, ra[outcome == 2], 3)
        proj += points
        key = grp_bonus + points * 10000 + base_gd * 10 + rng.random(len(teams)) * 10
        order = np.argsort(-key)
        for bucket in buckets:
            if "promo_top" in bucket:
                counts[bucket["key"]][order[:bucket["promo_top"]]] += 1
                lo, hi = bucket["playoff_band"]
                seeds = list(order[lo - 1:hi])
                if seeds and rng.random() < bucket.get("barrage_win_rate", 1.0):
                    counts[bucket["key"]][_promo_playoff_winner(seeds, pm, rng)] += 1
            elif "champ_playoff" in bucket:
                winner = _championship_winner(
                    list(order[:min(bucket["champ_playoff"], len(teams))]), pm, rng)
                if winner is not None:
                    counts[bucket["key"]][winner] += 1
            else:
                counts[bucket["key"]][_bucket_idx(bucket, order, len(teams))] += 1
    return proj / n_sims, {k: v / n_sims * 100 for k, v in counts.items()}


def _mls_sim(schedule: pd.DataFrame, played: pd.DataFrame, teams: list[str],
             conferences: dict[str, str], pm: np.ndarray, n_sims: int,
             sigma: float, seed: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    idx = {t: i for i, t in enumerate(teams)}
    base_pts, base_gd = _base_table(played, teams)
    remaining = schedule[~schedule.index.isin(played.index)]
    rh = remaining["home_team"].map(idx).to_numpy(dtype=int)
    ra = remaining["away_team"].map(idx).to_numpy(dtype=int)
    rp = pm[rh, ra] if len(remaining) else np.zeros((0, 3))
    lrp = np.log(np.clip(rp, 1e-12, 1.0)) if len(remaining) and sigma > 1 else None
    conf_idx = [np.array([i for i, t in enumerate(teams) if conferences.get(t) == c])
                for c in ("East", "West")]
    playoff = np.zeros(len(teams)); shield = np.zeros(len(teams)); cup = np.zeros(len(teams))
    proj = np.zeros(len(teams)); rng = np.random.default_rng(seed)

    def pwin(home: int, away: int, extra_time: bool) -> float:
        ph, pd_, pa = pm[home, away]
        return ph + (pd_ * ph / (ph + pa) if extra_time and ph + pa > 1e-9 else 0.5 * pd_)

    def bracket(seeds: list[int]) -> int:
        rank = {t: i for i, t in enumerate(seeds)}
        wc = seeds[7] if rng.random() < pwin(seeds[7], seeds[8], False) else seeds[8]
        winners = []
        for hi, lo in [(seeds[0], wc), (seeds[1], seeds[6]),
                       (seeds[2], seeds[5]), (seeds[3], seeds[4])]:
            wins = {hi: 0, lo: 0}
            for game in range(3):
                home, away = (hi, lo) if game != 1 else (lo, hi)
                winner = home if rng.random() < pwin(home, away, False) else away
                wins[winner] += 1
                if wins[winner] == 2:
                    break
            winners.append(hi if wins[hi] == 2 else lo)
        def single(a: int, b: int) -> int:
            home, away = (a, b) if rank[a] < rank[b] else (b, a)
            return home if rng.random() < pwin(home, away, True) else away
        return single(single(winners[0], winners[3]), single(winners[1], winners[2]))

    for _ in range(n_sims):
        points = base_pts.copy()
        if len(remaining):
            probs = perturb_probs(lrp, rh, ra, rng.standard_normal(len(teams)) * sigma) \
                if lrp is not None else rp
            u = rng.random(len(remaining))
            outcome = np.where(u < probs[:, 0], 0,
                               np.where(u < probs[:, 0] + probs[:, 1], 1, 2))
            np.add.at(points, rh[outcome == 0], 3)
            np.add.at(points, rh[outcome == 1], 1)
            np.add.at(points, ra[outcome == 1], 1)
            np.add.at(points, ra[outcome == 2], 3)
        proj += points
        key = points * 10000 + base_gd * 10 + rng.random(len(teams)) * 10
        finalists = []
        for members in conf_idx:
            order = members[np.argsort(-key[members])]
            playoff[order[:9]] += 1
            finalists.append(bracket(list(order[:9])))
        shield[np.argmax(key)] += 1
        h, a = (finalists[0], finalists[1]) if key[finalists[0]] >= key[finalists[1]] \
            else (finalists[1], finalists[0])
        cup[h if rng.random() < pwin(h, a, True) else a] += 1
    odds = {"playoff": playoff / n_sims * 100, "shield": shield / n_sims * 100,
            "cup": cup / n_sims * 100}
    return proj / n_sims, odds


def reconstruct_league(lid: str, payload: dict, archive: pd.DataFrame | None,
                       n_sims: int, step_games: int) -> tuple[list[dict], dict]:
    source = "asa" if lid == "mls" else OUTLOOK[lid]["source"]
    schedule, display_for = _schedule_frame(lid, payload, source)
    if schedule.empty:
        raise ValueError("current payload has no dated league fixtures")
    first = schedule["date"].min()
    exact = pd.DataFrame()
    if archive is not None and len(archive):
        exact = archive[archive["league"] == lid]
        if "season" in exact and payload.get("season") is not None:
            exact = exact[exact["season"].isna() | (exact["season"] == payload.get("season"))]
    first_archive = pd.Timestamp(exact["snapshot_date"].min()) if len(exact) else None
    if first_archive is not None and first_archive < first:
        return [], {"status": "archive_precedes_season", "points": 0,
                    "season_start": first.strftime("%Y-%m-%d"),
                    "first_archive": first_archive.strftime("%Y-%m-%d")}
    generated = pd.Timestamp(str(payload.get("generated", ""))[:10] or datetime.now().date())
    stop = min(generated, first_archive - pd.Timedelta(days=1)) if first_archive is not None else generated
    checkpoints = _checkpoints(schedule, stop, step_games)
    history = _canonical_played(_cached_history(lid, source))
    prefix = history[history["date"] < first].copy()
    if len(prefix) < 50:
        raise ValueError(f"insufficient prior history ({len(prefix)} played matches)")
    temperature = _temperature(prefix)
    teams = sorted(set(schedule["home_team"]) | set(schedule["away_team"]))
    conferences = {}
    if lid == "mls":
        by_name = {s["team"]: s.get("conf") for s in payload.get("standings") or []}
        conferences = {model: by_name.get(display) for model, display in display_for.items()}
        if any(len([t for t in teams if conferences.get(t) == c]) < 9 for c in ("East", "West")):
            raise ValueError("MLS conference membership incomplete")
    buckets = payload.get("outlook", {}).get("columns") or OUTLOOK.get(lid, {}).get("buckets", [])
    rows: list[dict] = []
    for checkpoint in checkpoints:
        played = schedule[schedule["is_result"] & (schedule["date"] <= checkpoint)].copy()
        fit_current = played.assign(season=payload.get("season"))
        fit_cols = ["date", "season", "home_team", "away_team",
                    "home_goals", "away_goals"]
        fit_rows = pd.concat([prefix[fit_cols], fit_current[fit_cols]], ignore_index=True)
        atk, dfd, ha, rho = fit_dc(fit_rows)
        atk, dfd = dict(atk), dict(dfd)
        _seed_missing(teams, atk, dfd)
        pm = _prob_matrix(teams, atk, dfd, ha, rho, temperature)
        _, elo = compute_elo(fit_rows.sort_values("date"), K=25, home_adv=80,
                             regress=0.40, club_prior_beta=0.0 if lid == "mls" else 0.75,
                             return_ratings=True)
        frac = len(played) / len(schedule) if len(schedule) else 1.0
        sigma = preseason_sigma_for_source(source) * (1.0 - frac)
        seed = zlib.crc32(f"{lid}:{checkpoint.date()}".encode())
        if lid == "mls":
            proj, odds = _mls_sim(schedule, played, teams, conferences, pm,
                                  n_sims, sigma, seed)
        else:
            proj, odds = _generic_sim(schedule, played, teams, buckets, pm,
                                      n_sims, sigma, seed, lid)
        for i, team in enumerate(teams):
            row = {
                "league": lid, "team": display_for.get(team, team),
                "snapshot_date": checkpoint.strftime("%Y-%m-%d"),
                "season": payload.get("season"), "elo": round(float(elo.get(team, 1500))),
                "proj_pts": round(float(proj[i]), 1), "kind": "reconstructed",
                "method": METHOD, "source_cutoff": checkpoint.strftime("%Y-%m-%d"),
                "schedule_basis": "current_full_schedule", "config_id": METHOD,
                "code_rev": None, "n_played": int(len(played)),
            }
            for key in _ODDS_KEYS:
                row[key] = round(float(odds[key][i]), 1) if key in odds else None
            rows.append(row)
    return rows, {
        "status": "reconstructed", "points": len(checkpoints),
        "team_rows": len(rows), "season_start": first.strftime("%Y-%m-%d"),
        "through": checkpoints[-1].strftime("%Y-%m-%d"),
        "first_archive": first_archive.strftime("%Y-%m-%d") if first_archive is not None else None,
        "temperature": round(temperature, 4), "schedule_basis": "current_full_schedule",
        "excluded_inputs": ["current_rosters", "current_injuries", "undated_squad_values"],
        "newcomer_seed": "flat_15_85_prior", "method": METHOD,
    }


def build(leagues: list[str] | None, n_sims: int, step_games: int) -> tuple[pd.DataFrame, dict]:
    wanted = leagues or ["mls", *OUTLOOK.keys()]
    archive = pd.read_parquet(ARCHIVE) if ARCHIVE.exists() else None
    rows, coverage = [], {}
    for lid in wanted:
        if lid != "mls" and lid not in OUTLOOK:
            coverage[lid] = {"status": "not_domestic_race", "points": 0}
            continue
        try:
            league_rows, status = reconstruct_league(
                lid, _payload(lid), archive, n_sims, step_games)
            rows.extend(league_rows); coverage[lid] = status
            print(f"[{lid}] {status['status']} · {status.get('points', 0)} points")
        except Exception as exc:  # one unavailable source must not erase other leagues
            coverage[lid] = {"status": "error", "points": 0, "note": str(exc)}
            print(f"[{lid}] ERROR: {exc}")
    frame = pd.DataFrame(rows)
    return frame, coverage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", action="append", help="repeat for a subset; default all domestic leagues")
    ap.add_argument("--sims", type=int, default=2000)
    ap.add_argument("--step-games", type=int, default=2,
                    help="average team-games between reconstructed points")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    frame, coverage = build(args.league, args.sims, args.step_games)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.out, index=False)
    manifest = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "method": METHOD, "n_sims": args.sims, "step_games": args.step_games,
        "scope": "current-season domestic league race pages",
        "leagues": coverage,
    }
    COVERAGE.write_text(json.dumps(manifest, indent=2) + "\n")
    ok = sum(v.get("status") in {"reconstructed", "archive_precedes_season"}
             for v in coverage.values())
    print(f"Wrote {args.out} · {len(frame):,} rows · {ok}/{len(coverage)} leagues covered")
    return 0 if all(v.get("status") != "error" for v in coverage.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
