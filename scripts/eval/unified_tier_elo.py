#!/usr/bin/env python3
"""R2 research: unified two-tier ELO vs seed-on-promotion for the England chain.

Question (docs/superpowers/plans/2026-07-09-ui-feedback-round-3.md, Task R2 step 2):
does ONE ELO rating updated continuously through both tiers predict promoted /
relegated teams' first-season matches better than the current approach (seed the
mover at tier-2 exit ELO + fitted bridge offset)?

Method — FOUR rating systems scored on IDENTICAL match sets:

  bridge   the current `promoted_team_brier` gate metric: mover's exit ELO from
           its source-division replay, FROZEN at the June-30 cutoff, + the fitted
           offset from experiments/tier2_offsets.json; opponent from the
           destination-division replay as-of match date.
  seeded   the production analogue: destination-division replay where each mover
           ENTERS its first season at exit ELO + fitted offset and then updates
           normally (build_league_data's tier-bridge seeding, replayed).
  league   no-bridge reference: destination division's own replay unmodified
           (a newly promoted club starts at ~1500 and updates in-season).
  unified  one merged replay over every division in the chain (epl +
           championship + league-one + league-two), sorted by date — ratings
           carry across promotion/relegation with no offset; the tier gap is
           learned implicitly from the movers' results.

All replays use the champion constants (K=25, HA=80, regress=0.40, init=1500)
via scripts.eval.elo.compute_elo (the seeded replay mirrors its champion path
and is validated to reproduce it exactly when given no seeds), and all
probabilities use the same cross_league.match_probs Poisson map, so the ONLY
difference is where the pre-match ratings come from. Scored on destination
seasons 2017+ (replays run over the full cached history for burn-in).
Sum-form Brier, naive = 2/3.

Usage:
    python -m scripts.eval.unified_tier_elo
    python -m scripts.eval.unified_tier_elo --out experiments/r2-unified-elo.report.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import logging
import math
from typing import NamedTuple

import numpy as np
import pandas as pd

from data_pipeline import coefficients as co
from scripts.eval.cross_league import _ELO_K, _ELO_HA, _ELO_REGRESS, _ELO_INIT, match_probs
from scripts.eval.elo import compute_elo
from scripts.eval.tier_bridge import (
    _TRAIN_FROM,
    _build_fd_elo_history,
    _identify_promotions,
    _identify_relegations,
)

_log = logging.getLogger(__name__)

# The England chain, top tier first. Adjacent entries form the scored pairs.
CHAIN = ["epl", "championship", "league-one", "league-two"]

_NAIVE = 2 / 3

History = dict[str, tuple[list, list]]


class _MoverMatch(NamedTuple):
    mover: str            # the promoted/relegated team
    opp: str              # the other side
    is_home: bool         # is the mover the home side?
    outcome: int          # 0=home win, 1=draw, 2=away win
    season: int           # destination season
    date: pd.Timestamp
    exit_elo: float       # mover's source-division ELO at the June-30 cutoff
    delta: float          # bridge offset for this pair/direction


def _asof(history: History, team: str, date: pd.Timestamp) -> float | None:
    """Most recent pre-match ELO on or before `date` (inclusive: the entry AT
    `date` is the pre-match rating of that day's match). None if no history."""
    dates, elos = history.get(team, ([], []))
    idx = bisect.bisect_right(dates, date)
    return elos[idx - 1] if idx > 0 else None


def _history_from_rated(rated: pd.DataFrame) -> History:
    history: History = {}
    for _, row in rated.iterrows():
        d = pd.Timestamp(row["date"])
        for team, elo in [(row["home_team"], row["home_elo"]),
                          (row["away_team"], row["away_elo"])]:
            history.setdefault(team, ([], []))
            history[team][0].append(d)
            history[team][1].append(float(elo))
    return history


def build_unified() -> tuple[History, pd.DataFrame]:
    """One merged replay over the whole chain → per-team pre-match ELO series."""
    from data_pipeline.football_data import match_results

    frames = [match_results(lid) for lid in CHAIN]
    df = (pd.concat(frames, ignore_index=True)
            .dropna(subset=["home_goals", "away_goals", "date"])
            .sort_values("date", kind="mergesort")
            .reset_index(drop=True))
    rated = compute_elo(df, K=_ELO_K, home_adv=_ELO_HA,
                        regress=_ELO_REGRESS, initial=_ELO_INIT)
    _log.info("unified replay: %d matches", len(rated))
    return _history_from_rated(rated), rated


def replay_league_seeded(league_id: str,
                         seeds: dict[tuple[str, int], float]) -> History:
    """Destination-division replay with per-(team, season) entry seeds.

    Mirrors compute_elo's CHAMPION path exactly (flat regression target, MOV
    multiplier, K/HA/regress/init from cross_league constants); the only
    addition is that at each season boundary, any (team, season) in `seeds`
    has its rating SET to the seed value — the production tier-bridge seeding
    replayed. With seeds={} this must reproduce _build_fd_elo_history.
    """
    from data_pipeline.football_data import match_results

    df = (match_results(league_id).sort_values("date").reset_index(drop=True)
          .dropna(subset=["home_goals", "away_goals"]))
    elo: dict[str, float] = {}
    seen: set = set()
    seeds_by_season: dict[int, dict[str, float]] = {}
    for (t, s), v in seeds.items():
        seeds_by_season.setdefault(int(s), {})[t] = v

    history: History = {}
    for _, row in df.iterrows():
        s = row["season"]
        if s not in seen:
            seen.add(s)
            elo = {t: _ELO_INIT + (r - _ELO_INIT) * (1 - _ELO_REGRESS)
                   for t, r in elo.items()}
            for t, v in seeds_by_season.get(int(s), {}).items():
                elo[t] = v
        d = row["date"]
        if pd.isna(d):
            continue
        d = pd.Timestamp(d)
        ht, at = row["home_team"], row["away_team"]
        rh = elo.get(ht, _ELO_INIT)
        ra = elo.get(at, _ELO_INIT)
        e_h = 1.0 / (1.0 + 10.0 ** ((ra - (rh + _ELO_HA)) / 400.0))
        hg, ag = row["home_goals"], row["away_goals"]
        s_h = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        mov = 1.0 + math.log(abs(hg - ag) + 1) * 0.1
        for team, r in [(ht, rh), (at, ra)]:
            history.setdefault(team, ([], []))
            history[team][0].append(d)
            history[team][1].append(float(r))
        elo[ht] = rh + _ELO_K * mov * (s_h - e_h)
        elo[at] = ra + _ELO_K * mov * ((1.0 - s_h) - (1.0 - e_h))
    return history


def _validate_seeded_replay() -> None:
    """replay_league_seeded(seeds={}) must equal the shared compute_elo history."""
    ref = _build_fd_elo_history(CHAIN[0])
    got = replay_league_seeded(CHAIN[0], {})
    assert set(ref) == set(got), "seeded replay: team set mismatch"
    for t in ref:
        assert ref[t][0] == got[t][0], f"seeded replay: date series mismatch for {t}"
        assert all(abs(a - b) < 1e-9 for a, b in zip(ref[t][1], got[t][1])), \
            f"seeded replay: ELO series mismatch for {t}"
    _log.info("seeded-replay validation vs compute_elo: OK (%s)", CHAIN[0])


def collect_pair(src_lid: str, dst_lid: str, direction: str) -> list[_MoverMatch]:
    """First-destination-season matches for teams moving src→dst.

    direction "promoted": src is the lower tier (movers went UP into dst) —
    the mover set comes from the upper tier's appearance diff, offset from
    tier2_offset. "relegated": src is the upper tier (movers dropped DOWN into
    dst), offset from tier1_offset. Mirrors tier_bridge's collectors; a match
    is kept only when the mover has source history before the cutoff so every
    rating system scores the identical set.
    """
    from data_pipeline.football_data import match_results

    delta = (co.tier2_offset(src_lid) if direction == "promoted"
             else co.tier1_offset(dst_lid))

    dst_df = match_results(dst_lid)
    dst_df = dst_df[dst_df["season"] >= _TRAIN_FROM]
    src_hist = _build_fd_elo_history(src_lid)

    if direction == "promoted":
        upper_df = match_results(dst_lid)
        movers_by_season = _identify_promotions(upper_df[upper_df["season"] >= _TRAIN_FROM])
    else:
        upper_df = match_results(src_lid)
        movers_by_season = _identify_relegations(upper_df[upper_df["season"] >= _TRAIN_FROM])

    out: list[_MoverMatch] = []
    n_skip = 0
    for season, movers in sorted(movers_by_season.items()):
        cutoff = pd.Timestamp(f"{season}-06-30")
        sdf = dst_df[dst_df["season"] == season]
        for _, row in sdf.iterrows():
            if pd.isna(row["date"]):
                continue
            date = pd.Timestamp(row["date"])
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            outcome = 0 if hg > ag else (1 if hg == ag else 2)
            for is_home, mover, opp in [(True, row["home_team"], row["away_team"]),
                                        (False, row["away_team"], row["home_team"])]:
                if mover not in movers:
                    continue
                dates_s, elos_s = src_hist.get(mover, ([], []))
                idx = bisect.bisect_right(dates_s, cutoff)
                if idx == 0:
                    n_skip += 1
                    continue
                out.append(_MoverMatch(mover, opp, is_home, outcome, int(season),
                                       date, elos_s[idx - 1], delta))
    if n_skip:
        _log.info("collect_pair %s→%s (%s): skipped %d unscoreable mover-matches",
                  src_lid, dst_lid, direction, n_skip)
    return out


def _brier_rows(rows: list[_MoverMatch], mover_fn, opp_fn) -> float:
    """Mean sum-form Brier with mover/opponent strengths given by accessors.
    Rows where an accessor returns None are scored at naive (should not happen
    on aligned sets; logged if it does)."""
    if not rows:
        return float("nan")
    total, n_naive = 0.0, 0
    for m in rows:
        me, oe = mover_fn(m), opp_fn(m)
        if me is None or oe is None:
            n_naive += 1
            probs = (1 / 3, 1 / 3, 1 / 3)
        elif m.is_home:
            probs = match_probs(me, oe, conf="UEFA")
        else:
            probs = match_probs(oe, me, conf="UEFA")
        actual = [0.0, 0.0, 0.0]
        actual[m.outcome] = 1.0
        total += sum((probs[i] - actual[i]) ** 2 for i in range(3))
    if n_naive:
        _log.warning("_brier_rows: %d/%d rows lacked a rating (scored naive)",
                     n_naive, len(rows))
    return total / len(rows)


def score_pair(src_lid: str, dst_lid: str, direction: str,
               rows: list[_MoverMatch], unified_hist: History,
               seeded_hist: History) -> dict:
    dst_hist = _build_fd_elo_history(dst_lid)
    res = {
        "pair": f"{src_lid}_to_{dst_lid}",
        "direction": direction,
        "offset_used": rows[0].delta if rows else None,
        "n_matches": len(rows),
        "n_seasons": len({m.season for m in rows}),
        "seasons": sorted({m.season for m in rows}),
        "naive": round(_NAIVE, 4),
        "brier_bridge_frozen": round(_brier_rows(
            rows,
            lambda m: m.exit_elo + m.delta,
            lambda m: _asof(dst_hist, m.opp, m.date)), 4),
        "brier_seeded": round(_brier_rows(
            rows,
            lambda m: _asof(seeded_hist, m.mover, m.date),
            lambda m: _asof(seeded_hist, m.opp, m.date)), 4),
        "brier_per_league": round(_brier_rows(
            rows,
            lambda m: _asof(dst_hist, m.mover, m.date),
            lambda m: _asof(dst_hist, m.opp, m.date)), 4),
        "brier_unified": round(_brier_rows(
            rows,
            lambda m: _asof(unified_hist, m.mover, m.date),
            lambda m: _asof(unified_hist, m.opp, m.date)), 4),
    }
    return res


def tier_gap_diagnostics(rated: pd.DataFrame) -> dict:
    """Mean unified pre-match ELO per division-season — the implied tier gaps."""
    from data_pipeline.football_data import match_results
    gaps = {}
    for lid in CHAIN:
        keys = set(match_results(lid)["match_id"])
        sub = rated[rated["match_id"].isin(keys) & (rated["season"] >= _TRAIN_FROM)]
        gaps[lid] = {int(s): round(float(
            pd.concat([g["home_elo"], g["away_elo"]]).mean()), 1)
            for s, g in sub.groupby("season")}
    return gaps


def main() -> int:
    ap = argparse.ArgumentParser(description="R2: unified two-tier ELO replay (England)")
    ap.add_argument("--out", type=str, default=None, help="write results JSON here")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    _validate_seeded_replay()
    unified_hist, rated = build_unified()

    # Collect every pair first so each destination league's seeded replay can
    # carry ALL of its incoming movers (promoted from below + relegated from above).
    pair_rows: dict[tuple[str, str, str], list[_MoverMatch]] = {}
    for upper, lower in zip(CHAIN, CHAIN[1:]):
        pair_rows[(lower, upper, "promoted")] = collect_pair(lower, upper, "promoted")
        pair_rows[(upper, lower, "relegated")] = collect_pair(upper, lower, "relegated")

    seeds_by_dst: dict[str, dict[tuple[str, int], float]] = {}
    for (src, dst, _dirn), rows in pair_rows.items():
        for m in rows:
            seeds_by_dst.setdefault(dst, {})[(m.mover, m.season)] = m.exit_elo + m.delta
    seeded_hists = {dst: replay_league_seeded(dst, seeds)
                    for dst, seeds in seeds_by_dst.items()}

    results = []
    for (src, dst, dirn), rows in pair_rows.items():
        results.append(score_pair(src, dst, dirn, rows, unified_hist,
                                  seeded_hists[dst]))

    variants = ("brier_bridge_frozen", "brier_seeded", "brier_per_league",
                "brier_unified")
    pooled = {}
    for key in variants:
        w = [(r["n_matches"], r[key]) for r in results
             if r["n_matches"] and not np.isnan(r[key])]
        n = sum(x for x, _ in w)
        pooled[key] = round(sum(x * b for x, b in w) / n, 4) if n else None
    pooled["n_matches"] = int(sum(r["n_matches"] for r in results))

    report = {
        "config": {"K": _ELO_K, "home_adv": _ELO_HA, "regress": _ELO_REGRESS,
                   "initial": _ELO_INIT, "chain": CHAIN, "score_from": _TRAIN_FROM},
        "pooled": pooled,
        "by_pair": results,
        "tier_gap_mean_elo": tier_gap_diagnostics(rated),
    }

    print("\nR2 — unified two-tier ELO vs seed-on-promotion (England chain)")
    print("=" * 88)
    hdr = (f"{'pair':<34}{'n':>5}  {'bridge':>7}  {'seeded':>7}  {'league':>7}  "
           f"{'unified':>8}  {'uni−seed':>8}")
    print(hdr); print("-" * len(hdr))
    for r in results:
        print(f"{r['pair'] + ' (' + r['direction'][:4] + ')':<34}{r['n_matches']:>5}  "
              f"{r['brier_bridge_frozen']:>7.4f}  {r['brier_seeded']:>7.4f}  "
              f"{r['brier_per_league']:>7.4f}  {r['brier_unified']:>8.4f}  "
              f"{r['brier_unified'] - r['brier_seeded']:>+8.4f}")
    print("-" * len(hdr))
    print(f"{'POOLED':<34}{pooled['n_matches']:>5}  {pooled['brier_bridge_frozen']:>7.4f}  "
          f"{pooled['brier_seeded']:>7.4f}  {pooled['brier_per_league']:>7.4f}  "
          f"{pooled['brier_unified']:>8.4f}  "
          f"{pooled['brier_unified'] - pooled['brier_seeded']:>+8.4f}")
    print(f"\nnaive (uniform) = {_NAIVE:.4f}; lower is better; sum-form Brier")
    print("bridge = frozen exit+δ (gate metric) · seeded = exit+δ then updating "
          "(production analogue)\nleague = 1500 start, updating · unified = one "
          "cross-tier rating, updating")

    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nReport → {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
