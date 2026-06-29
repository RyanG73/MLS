#!/usr/bin/env python3
"""Offline reproduction of the EPL promoted-team seeding bug + smooth-mapping fix.

Loads the cached EPL Understat frame, fits the same Dixon-Coles + ELO the build uses,
then seeds the promoted teams (Coventry, Hull) with the OLD percentile/clamp mapping vs a
NEW smooth (linear ELO→DC) mapping, and reports each team's model strength (avg home-win %
vs the 20 current EPL sides). No network, no commits — diagnostic only.
"""
import numpy as np
import pandas as pd
import models.research_model as rm
from models.research_model import fit_dc
from scripts.eval.elo import compute_elo

EPL = "webapp/data/understat/epl.parquet"
OFFSET = -120.0                       # championship_to_epl (experiments/tier2_offsets.json)
CHAMP_ELO = {"Coventry City": 1647.0, "Hull": 1520.0}   # from championship.js (Hull=Hull City)
CURRENT = ["Arsenal", "Manchester City", "Manchester United", "Liverpool", "Aston Villa",
           "Bournemouth", "Brentford", "Brighton", "Newcastle United", "Nottingham Forest",
           "Chelsea", "Fulham", "Everton", "Crystal Palace", "Tottenham", "Sunderland",
           "Leeds", "Ipswich", "Coventry City", "Hull"]


# ── OLD mapping (current build_league_data._elo_to_dc_params) ──
def old_map(adj_elo, atk, dfd, elo_now):
    elo_vals = sorted(elo_now.values()); n = len(elo_vals)
    if n == 0 or not atk or not dfd:
        return 0.0, 0.0
    rank = sum(1 for e in elo_vals if e <= adj_elo)
    pct = max(0.05, min(0.95, rank / n))
    av, dv = sorted(atk.values()), sorted(dfd.values())
    return av[min(int(pct * len(av)), len(av) - 1)], dv[min(int((1 - pct) * len(dv)), len(dv) - 1)]


# ── NEW mapping: continuous linear regression of DC params on ELO ──
def new_map(adj_elo, atk, dfd, elo_now):
    common = [t for t in atk if t in dfd and t in elo_now]
    if len(common) < 5:
        return 0.0, 0.0
    e = np.array([elo_now[t] for t in common])
    a = np.array([atk[t] for t in common]); d = np.array([dfd[t] for t in common])
    a_s, a_i = np.polyfit(e, a, 1)
    d_s, d_i = np.polyfit(e, d, 1)
    # bound extrapolation modestly so a sub-floor team isn't snapped or sent to infinity
    lo, hi = e.min() - 40, e.max() + 40
    x = max(lo, min(hi, adj_elo))
    return float(a_s * x + a_i), float(d_s * x + d_i)


def strength(team, atk, dfd, ha, rho):
    """avg home-win % vs the 20 current EPL sides (matches the dashboard's pmStr metric)."""
    ps = [rm._dc_predict(team, o, atk, dfd, ha, rho)[0] for o in CURRENT if o != team]
    return 100 * sum(ps) / len(ps)


def main():
    df = pd.read_parquet(EPL)
    played = df.dropna(subset=["home_goals", "away_goals"]).copy()
    atk, dfd, ha, rho = fit_dc(played)
    _, elo_now = compute_elo(played.sort_values("date"), K=25, home_adv=80, regress=0.40,
                             return_ratings=True)
    print(f"EPL elo_now: n={len(elo_now)} range {min(elo_now.values()):.0f}–{max(elo_now.values()):.0f}")
    print(f"DC atk fit n={len(atk)}, dfd n={len(dfd)}\n")

    for off in (OFFSET, -180.0, -220.0):
        print(f"================  tier-2 offset = {off:+.0f}  ================")
        print(f"{'team':16}{'champElo':>9}{'adjElo':>8} | {'OLD str%':>8} | {'NEW str%':>8}")
        a2, d2 = dict(atk), dict(dfd)   # working copies for NEW seeding (for relative context)
        for t, ce in CHAMP_ELO.items():
            adj = ce + off
            oa, od = old_map(adj, atk, dfd, elo_now)
            na, nd = new_map(adj, atk, dfd, elo_now)
            # temporarily install each to measure strength
            atk[t], dfd[t] = oa, od; old_s = strength(t, atk, dfd, ha, rho)
            atk[t], dfd[t] = na, nd; new_s = strength(t, atk, dfd, ha, rho)
            print(f"{t:16}{ce:>9.0f}{adj:>8.0f} | {old_s:>8.1f} | {new_s:>8.1f}")
        # anchor: where do real bottom/mid EPL teams sit (using their fitted params)?
        print("  anchors (fitted EPL params):", end=" ")
        for t in ("Ipswich", "Crystal Palace", "Everton", "Fulham"):
            if t in atk:
                print(f"{t}={strength(t, atk, dfd, ha, rho):.0f}", end="  ")
        print("\n")


if __name__ == "__main__":
    main()
