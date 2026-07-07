"""Season-outcome evaluation: how well the sim predicts team-level outcomes.

Match-level Brier (the champion gates) never sees whether the SEASON-level
claims — champion, promotion, relegation, top-N — are calibrated; those come
from the Monte-Carlo table sim, whose quality depends on the DC fit, seeding,
temperature, ranking rules, and preseason widening jointly. This module makes
the A10(b) cohort-replay methodology a standing metric (user directive
2026-07-06): replay historical seasons through production-mirrored sims at
several checkpoints and score each league's own OUTLOOK buckets as binary
forecasts against the actual final table.

Per (league, season, checkpoint):
  - DC fit on ALL matches played before the checkpoint date (recent-4 window
    inside fit_dc), temperature fit production-style on the prior season.
  - Teams without DC params take the production 15/85-percentile fallback
    (the tier bridge is not replayed — a documented approximation).
  - Points/GD accrued from actual results up to the checkpoint; the actual
    remaining fixture list is simulated with the production ranking key.
  - Preseason checkpoints (f=0) apply the A10(b) widening (PRESEASON_SIGMA),
    exactly as production does; later checkpoints don't.
  - Outcomes = the league's OUTLOOK buckets (top-N / bottom-N / band), scored
    as P(outcome) vs the actual final classification.

Split/points-transform leagues (Scotland, Belgium, Greece) are EXCLUDED: their
final classification needs format-group simulation that the plain ranking key
does not model. Playoff rows (is_playoff) never count toward tables, matching
the builder.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.research_model import fit_temperature_scalar
from scripts.eval.dixon_coles import dc_predict_batch, fit_dc
from scripts.eval.sim_variance import PRESEASON_SIGMA, perturb_probs

DEFAULT_CHECKPOINTS = (0.0, 0.25, 0.5, 0.75)
DEFAULT_N_SIMS = 3000


def flat_fallback(atk: dict, dfd: dict) -> tuple[float, float]:
    """Production's promoted-team prior: 15th-pct attack / 85th-pct defence."""
    av, dv = sorted(atk.values()), sorted(dfd.values())
    p15 = max(0, int(len(av) * 0.15) - 1)
    p85 = min(len(dv) - 1, int(len(dv) * 0.85))
    return (av[p15] if av else -0.2), (dv[p85] if dv else 0.2)


def bucket_members(bucket: dict, order: np.ndarray, nT: int) -> np.ndarray:
    """Team indices (into `order`, best-first) inside a bucket's rank range."""
    if "top" in bucket:
        return order[:bucket["top"]]
    if "bottom" in bucket:
        return order[nT - bucket["bottom"]:]
    if "band" in bucket:
        return order[bucket["band"][0] - 1:bucket["band"][1]]
    return order[:0]


def _table(rows: pd.DataFrame, idx: dict[str, int]) -> tuple[np.ndarray, np.ndarray]:
    pts = np.zeros(len(idx))
    gd = np.zeros(len(idx))
    for _, r in rows.iterrows():
        hi, ai = idx[r["home_team"]], idx[r["away_team"]]
        hg, ag = int(r["home_goals"]), int(r["away_goals"])
        gd[hi] += hg - ag
        gd[ai] += ag - hg
        if hg > ag:
            pts[hi] += 3
        elif hg < ag:
            pts[ai] += 3
        else:
            pts[hi] += 1
            pts[ai] += 1
    return pts, gd


def simulate_outcomes(P: np.ndarray, RH: np.ndarray, RA: np.ndarray,
                      base_pts: np.ndarray, base_gd: np.ndarray,
                      buckets: list[dict], rng: np.random.Generator,
                      n_sims: int = DEFAULT_N_SIMS,
                      widen_sigma: float = 0.0) -> dict[str, np.ndarray]:
    """{bucket_key: P(outcome) per team} from the production MC ranking rules."""
    nT = len(base_pts)
    F = len(RH)
    LP = np.log(np.clip(P, 1e-12, 1.0)) if widen_sigma > 0 else None
    counts = {b["key"]: np.zeros(nT) for b in buckets}
    for _ in range(n_sims):
        p = base_pts.copy()
        if F:
            Ps = (perturb_probs(LP, RH, RA, rng.standard_normal(nT) * widen_sigma)
                  if widen_sigma > 0 else P)
            u = rng.random(F)
            o = np.where(u < Ps[:, 0], 0, np.where(u < Ps[:, 0] + Ps[:, 1], 1, 2))
            np.add.at(p, RH[o == 0], 3)
            np.add.at(p, RH[o == 1], 1)
            np.add.at(p, RA[o == 1], 1)
            np.add.at(p, RA[o == 2], 3)
        key = p * 10000 + base_gd * 10 + rng.random(nT) * 10
        order = np.argsort(-key)
        for b in buckets:
            counts[b["key"]][bucket_members(b, order, nT)] += 1
    return {k: v / n_sims for k, v in counts.items()}


def replay_league(frame: pd.DataFrame, buckets: list[dict],
                  seasons: list[int],
                  checkpoints: tuple[float, ...] = DEFAULT_CHECKPOINTS,
                  n_sims: int = DEFAULT_N_SIMS,
                  preseason_sigma: float = PRESEASON_SIGMA,
                  seed: int = 42,
                  min_season_games: int = 50,
                  min_prior_games: int = 400) -> list[dict]:
    """Rows of {season, checkpoint, outcome, team, pred, actual} for one league.

    `frame` is a canonical played-match frame (goals filled). Playoff rows
    (is_playoff == 1) are dropped up front.
    """
    df = frame.dropna(subset=["home_goals", "away_goals"]).copy()
    if "is_playoff" in df.columns:
        df = df[df["is_playoff"].fillna(0).astype(int) == 0]
    df = df.sort_values("date", kind="stable")

    rows: list[dict] = []
    for S in seasons:
        season_df = df[df["season"] == S]
        prior = df[df["season"] < S]
        cal_df = df[df["season"] == S - 1]
        if (len(season_df) < min_season_games or len(prior) < min_prior_games
                or len(cal_df) < min_season_games // 2):
            continue

        teams = sorted(set(season_df["home_team"]) | set(season_df["away_team"]))
        idx = {t: i for i, t in enumerate(teams)}
        nT = len(teams)

        # actual final classification (regular-phase table)
        pts_f, gd_f = _table(season_df, idx)
        order_f = np.argsort(-(pts_f * 10000 + gd_f))
        actual = {b["key"]: np.zeros(nT, dtype=bool) for b in buckets}
        for b in buckets:
            actual[b["key"]][bucket_members(b, order_f, nT)] = True

        # temperature, production-style: <S-1 params scored on S-1
        a0, d0, h0, r0 = fit_dc(df[df["season"] < S - 1]) \
            if len(df[df["season"] < S - 1]) >= min_prior_games else fit_dc(prior)
        raw_cal = dc_predict_batch(cal_df, a0, d0, h0, r0)
        y_cal = np.where(cal_df["home_goals"] > cal_df["away_goals"], 0,
                         np.where(cal_df["home_goals"] == cal_df["away_goals"], 1, 2))
        T = fit_temperature_scalar(raw_cal, y_cal)

        n_games = len(season_df)
        for f in checkpoints:
            cut = int(round(f * n_games))
            played = season_df.iloc[:cut]
            remaining = season_df.iloc[cut:]

            atk, dfd, ha, rho = fit_dc(pd.concat([prior, played]))
            atk, dfd = dict(atk), dict(dfd)
            afb, dfb = flat_fallback(atk, dfd)
            for t in teams:
                atk.setdefault(t, afb)
                dfd.setdefault(t, dfb)

            P_raw = dc_predict_batch(remaining, atk, dfd, ha, rho)
            lp = np.log(np.clip(P_raw, 1e-9, 1.0)) / T
            lp -= lp.max(axis=1, keepdims=True)
            ep = np.exp(lp)
            P = ep / ep.sum(axis=1, keepdims=True)

            RH = remaining["home_team"].map(idx).values.astype(int)
            RA = remaining["away_team"].map(idx).values.astype(int)
            base_pts, base_gd = _table(played, idx)

            rng = np.random.default_rng(hash((S, f, seed)) % 2**31)
            probs = simulate_outcomes(
                P, RH, RA, base_pts, base_gd, buckets, rng, n_sims,
                widen_sigma=preseason_sigma if f == 0.0 else 0.0)

            for b in buckets:
                k = b["key"]
                for i, t in enumerate(teams):
                    rows.append({"season": S, "checkpoint": f, "outcome": k,
                                 "team": t, "pred": float(probs[k][i]),
                                 "actual": bool(actual[k][i])})
    return rows


def summarize(rows: list[dict], top1_keys: set[str] = frozenset({"title", "shield"})) -> dict:
    """{checkpoint: {outcome: metrics}} pooled across seasons (and leagues if
    the rows carry a `league` column — pooling is per team-season either way).

    brier          binary Brier of P(outcome) vs achieved.
    p_actual_mean  mean probability assigned to teams that ACHIEVED the
                   outcome (for `title` this is the prob on the eventual
                   champion — the headline "did we see it coming" number).
    favorite_hit_rate  for winner-type buckets only: share of league-seasons
                   where the model's pre-checkpoint favorite actually won.
    """
    df = pd.DataFrame(rows)
    grp_cols = ["league", "season"] if "league" in df.columns else ["season"]
    out: dict = {}
    for (f, k), grp in df.groupby(["checkpoint", "outcome"]):
        a = grp["actual"].astype(float)
        m = {
            "n": int(len(grp)),
            "brier": round(float(np.mean((grp["pred"] - a) ** 2)), 5),
            "pred_mean": round(float(grp["pred"].mean()), 4),
            "obs_rate": round(float(a.mean()), 4),
            "p_actual_mean": (round(float(grp.loc[grp["actual"], "pred"].mean()), 4)
                              if grp["actual"].any() else None),
        }
        if k in top1_keys:
            hits = []
            for _, g in grp.groupby(grp_cols):
                fav = g.loc[g["pred"].idxmax()]
                hits.append(bool(fav["actual"]))
            m["favorite_hit_rate"] = round(float(np.mean(hits)), 4)
            m["n_league_seasons"] = len(hits)
        out.setdefault(f"cp{f:g}", {})[k] = m
    return out
