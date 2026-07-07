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

from data_pipeline import coefficients as co
from models.research_model import fit_temperature_scalar
from scripts.eval.dixon_coles import dc_predict_batch, fit_dc
from scripts.eval.elo import compute_elo
from scripts.eval.season_format import format_classification, regular_phase_mask
from scripts.eval.sim_variance import PRESEASON_SIGMA, perturb_probs

DEFAULT_CHECKPOINTS = (0.0, 0.25, 0.5, 0.75)
DEFAULT_N_SIMS = 3000


def flat_fallback(atk: dict, dfd: dict) -> tuple[float, float]:
    """Production's promoted-team prior: 15th-pct attack / 85th-pct defence."""
    av, dv = sorted(atk.values()), sorted(dfd.values())
    p15 = max(0, int(len(av) * 0.15) - 1)
    p85 = min(len(dv) - 1, int(len(dv) * 0.85))
    return (av[p15] if av else -0.2), (dv[p85] if dv else 0.2)


def _seed_newcomers(newcomers: list[str], atk: dict, dfd: dict,
                    elo_now: dict[str, float],
                    bridge: dict | None, cutoff: pd.Timestamp,
                    lid: str) -> None:
    """Production's tier-bridge seeding for teams absent from the DC fit.

    Mirrors build_league_data's preseason block: promoted teams take their
    feeder-league ELO + tier2 offset, relegated ones their parent-league ELO
    + tier1 offset, mapped to DC params via the same ELO→param linear fit
    (`_elo_to_dc_params`). Teams unseen in either bridge fall back to the
    flat prior. Feeder/parent ELO is computed walk-forward (matches strictly
    before `cutoff`).
    """
    from scripts.build_league_data import _elo_to_dc_params  # shared mapping

    def _elo_map(frame: pd.DataFrame) -> dict[str, float]:
        hist = frame.dropna(subset=["home_goals", "away_goals"])
        hist = hist[hist["date"] < cutoff].sort_values("date")
        if len(hist) < 200:
            return {}
        _, ratings = compute_elo(hist, K=25, home_adv=80, regress=0.40,
                                 club_prior_beta=0.75, return_ratings=True)
        return dict(ratings)

    feeder_map = _elo_map(bridge["feeder"][1]) if bridge and "feeder" in bridge else {}
    parent_map = _elo_map(bridge["parent"][1]) if bridge and "parent" in bridge else {}
    afb, dfb = flat_fallback(atk, dfd)
    for t in newcomers:
        if t in feeder_map:
            adj = feeder_map[t] + co.tier2_offset(bridge["feeder"][0])
            atk[t], dfd[t] = _elo_to_dc_params(adj, atk, dfd, elo_now)
        elif t in parent_map:
            adj = parent_map[t] + co.tier1_offset(lid)
            atk[t], dfd[t] = _elo_to_dc_params(adj, atk, dfd, elo_now)
        else:
            atk[t], dfd[t] = afb, dfb


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
                  min_prior_games: int = 400,
                  bridge: dict | None = None,
                  lid: str = "",
                  fmt: dict | None = None,
                  sigma_decay: bool = False,
                  value_map: dict | None = None,
                  value_beta: float = 0.0) -> list[dict]:
    """Rows of {season, checkpoint, outcome, team, pred, actual} for one league.

    `frame` is a canonical played-match frame (goals filled). Playoff rows
    (is_playoff == 1) are dropped up front.

    bridge: optional {"feeder": (lid, frame), "parent": (lid, frame)} —
        newcomers seed from cross-tier ELO exactly as production does.
    fmt: optional FORMATS entry (split/playoff leagues). The sim covers the
        REGULAR phase only (what production simulates preseason) and is
        scored against the OFFICIAL classification from format_classification
        — the format gap is part of the measured error, as it is in prod.
    """
    df = frame.dropna(subset=["home_goals", "away_goals"]).copy()
    if "is_playoff" in df.columns:
        df = df[df["is_playoff"].fillna(0).astype(int) == 0]
    df = df.sort_values("date", kind="stable")

    rows: list[dict] = []
    for S in seasons:
        season_full = df[df["season"] == S]
        prior = df[df["season"] < S]
        cal_df = df[df["season"] == S - 1]
        if (len(season_full) < min_season_games or len(prior) < min_prior_games
                or len(cal_df) < min_season_games // 2):
            continue

        teams = sorted(set(season_full["home_team"]) | set(season_full["away_team"]))
        idx = {t: i for i, t in enumerate(teams)}
        nT = len(teams)

        # actual final classification; format leagues use the OFFICIAL one
        # (groups + carry transform), everyone else the plain table.
        if fmt is not None:
            cls = format_classification(season_full, fmt, teams)
            order_f = np.array([idx[t] for t in sorted(
                teams, key=lambda t: (cls[t]["group"], -cls[t]["pts"], -cls[t]["gd"]))])
            season_df = season_full[regular_phase_mask(
                season_full, fmt["rr"] * (nT - 1))]
        else:
            season_df = season_full
            pts_f, gd_f = _table(season_full, idx)
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

            fit_rows = pd.concat([prior, played])
            atk, dfd, ha, rho = fit_dc(fit_rows)
            atk, dfd = dict(atk), dict(dfd)
            newcomers = [t for t in teams if t not in atk]
            elo_now = None
            if newcomers or (value_beta > 0 and f == 0.0):
                _, elo_now = compute_elo(
                    fit_rows.sort_values("date"), K=25, home_adv=80,
                    regress=0.40, club_prior_beta=0.75, return_ratings=True)
            if newcomers:
                cutoff = (played["date"].min() if len(played)
                          else season_df["date"].min())
                _seed_newcomers(newcomers, atk, dfd, elo_now,
                                bridge, cutoff, lid)

            # M2 (A10a revival): value-informed preseason strength correction.
            # Fit log(squad value) → ELO on the JUST-CLOSED season (values of
            # S-1 vs end-of-S-1 ratings — walk-forward safe), apply to the
            # incoming season's start-of-season values, and tilt each team's
            # fixture log-odds by β·(value_elo − elo) — a LOCATION fix the
            # symmetric widening cannot provide (Spurs: value says top-6).
            value_delta = np.zeros(nT)
            if value_beta > 0 and f == 0.0 and value_map and elo_now:
                import math as _math
                xs, ys = [], []
                for t, r_elo in elo_now.items():
                    v = value_map.get((t, S - 1))
                    if v and v > 0:
                        xs.append(_math.log(v))
                        ys.append(r_elo)
                if len(xs) >= 6 and float(np.std(xs)) > 1e-9:
                    b_, a_ = np.polyfit(np.array(xs), np.array(ys), 1)
                    # Bottom-half targeting: the measured location error lives
                    # in bottom-table outcomes (fallen giants seeded too low);
                    # the top of the table already carries strong skill and an
                    # untargeted tilt drags title odds toward the richest club
                    # (title Brier +0.005 at β=0.5 in the untargeted A/B).
                    _med = float(np.median([elo_now.get(t, 1500.0) for t in teams]))
                    for i, t in enumerate(teams):
                        v_new = value_map.get((t, S))
                        if (v_new and v_new > 0 and t in elo_now
                                and elo_now[t] <= _med):
                            value_delta[i] = value_beta * (
                                (a_ + b_ * _math.log(v_new)) - elo_now[t])

            P_raw = dc_predict_batch(remaining, atk, dfd, ha, rho)
            lp = np.log(np.clip(P_raw, 1e-9, 1.0)) / T
            lp -= lp.max(axis=1, keepdims=True)
            ep = np.exp(lp)
            P = ep / ep.sum(axis=1, keepdims=True)

            RH = remaining["home_team"].map(idx).values.astype(int)
            RA = remaining["away_team"].map(idx).values.astype(int)
            if value_delta.any():
                # deterministic tilt: same ELO-scale log-odds math as the
                # stochastic widening, applied once to the baseline probs.
                P = perturb_probs(np.log(np.clip(P, 1e-12, 1.0)),
                                  RH, RA, value_delta)
            base_pts, base_gd = _table(played, idx)

            rng = np.random.default_rng(hash((S, f, seed)) % 2**31)
            # production: widening at preseason only. sigma_decay experiment:
            # σ·(1−f) at every checkpoint (uncertainty shrinks with evidence).
            _sig = (preseason_sigma * (1.0 - f) if sigma_decay
                    else (preseason_sigma if f == 0.0 else 0.0))
            probs = simulate_outcomes(
                P, RH, RA, base_pts, base_gd, buckets, rng, n_sims,
                widen_sigma=_sig)

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
