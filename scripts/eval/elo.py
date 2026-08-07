"""
ELO rating model extracted from eval_baseline.py (F4 extraction).

Pure function: takes a sorted DataFrame and returns it with ELO columns added.
No API calls, no module-level state.  eval_baseline.py imports compute_elo from
here; behavior is preserved — verified by eval_baseline.py --smoke-test.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

DEFAULT_INITIAL_ELO: float = 1500.0
DEFAULT_REGRESS:     float = 0.40   # promoted 2026-06-07 (synergistic with whl=6)

# ── home advantage, per competition ──────────────────────────────────────────
# HOME_ADV was a single 80 for every league until 2026-08-07. It was promoted on
# 2026-06-07 against MLS data, and it is right for MLS — it is not right for a
# European domestic league, where the same value overstates the home side in
# every season measured.
#
# Swept end to end (compute_elo re-run at each value, so the ratings themselves
# are refitted, not just re-scored), objective = log-loss of the expected score
# against the realised score, which is what ELO optimises:
#
#   19 European domestic leagues, ~86,000 matches: best mean log-loss at
#   HOME_ADV = 55 (0.64065) against 0.64356 at 80. **80 was optimal in ZERO of
#   the 19.** Mean bias +0.0358 at 80 versus +0.0031 at 55.
#   MLS, 5,746 matches: best 90 (0.65670), 80 gives 0.65692 — a 0.0002
#   difference, so 80 stays and the champion config is untouched.
#   Brazil Série A, 5,524 matches: best 90, 80 within 0.0003 — likewise kept.
#
# The split is mechanical rather than arbitrary: MLS and the Brasileirão are
# continental-scale travel leagues, and that is exactly where a large home
# advantage is expected. Everything measured outside them preferred 40-70
# (Japan 40, Sweden 40, Denmark 40, Austria 40, Switzerland 40, Argentina 55,
# Liga MX 55, Poland 55, Romania 55, Russia 55, Norway 70, China 70), so 55 is
# the default rather than a guess for the leagues not individually swept.
#
# Individual per-league values are deliberately NOT stored: the log-loss curves
# are shallow and a 19-league pooled estimate is far better identified than any
# one of them. Only the two travel leagues, where the effect is mechanical and
# large, get their own entry.
DEFAULT_HOME_ADV: float = 55.0
_HOME_ADV_BY_LEAGUE: dict[str, float] = {
    "mls": 80.0,
    "brazil-serie-a": 80.0,
}


def home_adv_for(league_id: str | None) -> float:
    """Home advantage in ELO points for a competition.

    Falls back to DEFAULT_HOME_ADV, which is the pooled European estimate — a
    much better prior for an unswept league than the old universal 80, which no
    league outside MLS and Brazil preferred.
    """
    return _HOME_ADV_BY_LEAGUE.get(league_id or "", DEFAULT_HOME_ADV)


def compute_elo(
    df: pd.DataFrame,
    K: float,
    home_adv: float,
    regress: float = DEFAULT_REGRESS,
    initial: float = DEFAULT_INITIAL_ELO,
    return_expected: bool = False,
    return_ratings: bool = False,
    club_prior_beta: float = 0.0,
    regress_gap_k: float = 0.0,
    xg_blend: float = 0.0,
    value_beta: float = 0.0,
    season_values: dict | None = None,
) -> pd.DataFrame:
    """Walk-forward ELO ratings with margin-of-victory multiplier and season regression.

    Args:
        df:             Match DataFrame sorted by date ascending.  Must have columns:
                        season, home_team, away_team, home_goals, away_goals.
        K:              ELO K-factor (controls how fast ratings update).
        home_adv:       Home-field advantage in ELO points added to home rating.
        regress:        Fraction of each team's deviation from ``initial`` to remove
                        at the start of each new season (0 = no regression, 1 = full reset).
        initial:        Starting ELO for any team that has not been seen yet.
        return_expected: If True, also writes ``elo_p_home`` (pre-match expected home
                        win probability from the ELO formula).
        return_ratings: If True, returns ``(out_df, ratings)`` where ratings is the
                        post-final-match {team: elo} dict (current ratings — used by
                        the dashboard build; pre-match columns can't provide these).
        club_prior_beta: A8 experiment knob. When > 0, the season-boundary
                        regression target for a team with ≥2 prior seasons is
                        ``(1-β)·initial + β·mean(end-of-season ELO, prior ≤3 seasons)``
                        instead of flat ``initial``. Teams with <2 prior seasons
                        keep the flat target (promoted teams use the tier bridge).
        regress_gap_k:  A8 experiment knob. When > 0, a team whose pre-boundary
                        rating deviates from its club prior regresses HARDER:
                        ``rate = clip(regress + k·|prior − elo|/200, 0.2, 0.6)``.
                        Teams without a prior (< 2 seasons) keep the base rate.
        xg_blend:       A5 experiment knob (λ, 0..1). The ELO update uses an
                        effective score ``s_eff = (1-λ)·s_result + λ·s_xg`` instead
                        of the raw match result, where ``s_xg`` is the outcome
                        implied by match xG totals (win/draw/loss on ``home_xg -
                        away_xg`` with a ±0.25 dead-zone for draws). Matches
                        missing ``home_xg``/``away_xg`` fall back to λ=0.
        value_beta:     A10(a) experiment knob (β₂). When > 0 and ``season_values``
                        is provided, the season-boundary target gains a squad-value
                        term: at each boundary a linear map ``log(value) → ELO`` is
                        fit on the JUST-CLOSED season (end-of-season ratings vs that
                        season's values — walk-forward safe, ≥6 pairs required),
                        then applied to each team's INCOMING-season value. The
                        target becomes ``(1-β₁-β₂)·initial + β₁·prior + β₂·value_elo``
                        where a missing component redistributes its weight to
                        ``initial`` (teams without a new-season value, or boundaries
                        where the fit is not possible, get no value term).
        season_values:  ``{(team_key, season): squad_value_eur}`` with team keys
                        matching ``df``'s home_team/away_team. Only consulted when
                        ``value_beta > 0``.

    Returns:
        Copy of ``df`` with columns added:
        ``home_elo``, ``away_elo``, ``elo_diff`` (home − away *before* the match),
        and optionally ``elo_p_home``.  With ``return_ratings`` a tuple
        ``(df, ratings_dict)`` instead.
    """
    elo: dict[str, float] = {}
    h_elo, a_elo, h_exp = [], [], []
    seen: set[object] = set()
    end_hist: dict[str, list[float]] = {}  # per-team end-of-season ELOs
    has_xg = xg_blend > 0.0 and "home_xg" in df.columns and "away_xg" in df.columns
    use_values = value_beta > 0.0 and bool(season_values)
    prev_season = None

    for _, row in df.iterrows():
        s = row["season"]
        if s not in seen:
            seen.add(s)
            # current values ARE the end-of-season ratings of the season closing
            for t, r in elo.items():
                end_hist.setdefault(t, []).append(r)

            # A10(a): fit log(squad value) → end-of-season ELO on the season just
            # closed, apply to incoming-season values. Walk-forward safe: the fit
            # sees only ratings/values of completed play.
            value_elo: dict[str, float] = {}
            if use_values and prev_season is not None and elo:
                xs, ys = [], []
                for t, r in elo.items():
                    v = season_values.get((t, prev_season))
                    if v is not None and v > 0:
                        xs.append(math.log(v))
                        ys.append(r)
                if len(xs) >= 6 and float(np.std(xs)) > 1e-9:
                    b, a = np.polyfit(np.array(xs), np.array(ys), 1)
                    for t in elo:
                        v_new = season_values.get((t, s))
                        if v_new is not None and v_new > 0:
                            value_elo[t] = a + b * math.log(v_new)

            new_elo = {}
            for t, r in elo.items():
                prior_seasons = end_hist[t][:-1]  # seasons BEFORE the one just closed
                prior = (sum(prior_seasons[-2:] + [r]) / (len(prior_seasons[-2:]) + 1)
                         if len(prior_seasons) >= 1 else None)
                # prior = mean of up to 3 most recent end-of-season ELOs
                # (the just-closed season + up to 2 before it); needs ≥2 seasons
                rate = regress
                b1 = club_prior_beta if (prior is not None and club_prior_beta > 0.0) else 0.0
                b2 = value_beta if t in value_elo else 0.0
                target = ((1.0 - b1 - b2) * initial
                          + (b1 * prior if b1 else 0.0)
                          + (b2 * value_elo[t] if b2 else 0.0))
                if prior is not None and regress_gap_k > 0.0:
                    rate = min(0.6, max(0.2, regress + regress_gap_k * abs(prior - r) / 200.0))
                new_elo[t] = target + (r - target) * (1 - rate)
            elo = new_elo
        prev_season = s
        ht, at = row["home_team"], row["away_team"]
        rh = elo.get(ht, initial)
        ra = elo.get(at, initial)
        e_h = 1.0 / (1.0 + 10.0 ** ((ra - (rh + home_adv)) / 400.0))
        hg, ag = row["home_goals"], row["away_goals"]
        s_h = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        s_eff = s_h
        if has_xg:
            hxg, axg = row["home_xg"], row["away_xg"]
            if pd.notna(hxg) and pd.notna(axg):
                xg_diff = hxg - axg
                s_xg = 1.0 if xg_diff > 0.25 else (0.0 if xg_diff < -0.25 else 0.5)
                s_eff = (1 - xg_blend) * s_h + xg_blend * s_xg
        mov = 1.0 + math.log(abs(hg - ag) + 1) * 0.1
        h_elo.append(rh)
        a_elo.append(ra)
        h_exp.append(e_h)
        elo[ht] = rh + K * mov * (s_eff - e_h)
        elo[at] = ra + K * mov * ((1.0 - s_eff) - (1.0 - e_h))

    out = df.copy()
    out["home_elo"] = h_elo
    out["away_elo"] = a_elo
    out["elo_diff"] = np.array(h_elo) - np.array(a_elo)
    if return_expected:
        out["elo_p_home"] = h_exp
    if return_ratings:
        return out, dict(elo)
    return out
