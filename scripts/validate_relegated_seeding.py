#!/usr/bin/env python3
"""Offline reproduction of the REVERSE cross-tier seeding (bidirectional bridge).

A team relegated from the top flight should seed as a promotion FAVOURITE in the second
tier, not the harsh flat prior. This loads the cached football-data Championship + EPL
results, fits the same DC + ELO the build uses, seeds a few recently-relegated EPL sides
via _elo_to_dc_params(tier1_elo + tier1_offset), and reports their strength vs the
Championship field. Mirror of scripts/validate_promoted_seeding.py. No commits.

    PYTHONPATH=. venv/bin/python scripts/validate_relegated_seeding.py
"""
import models.research_model as rm
from models.research_model import fit_dc
from scripts.eval.elo import compute_elo
from data_pipeline.football_data import match_results
from data_pipeline import coefficients as co
from scripts.build_league_data import _elo_to_dc_params, _get_tier_elo_map

TIER2, TIER1 = "championship", "epl"
# Recently relegated from the EPL into the Championship (football-data short names).
RELEGATED = ["Leicester", "Southampton", "Ipswich", "Leeds"]


def main():
    df = match_results(TIER2).dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    latest = sorted(df["season"].unique())[-1]
    season_df = df[df["season"] == latest]
    field = sorted(set(season_df["home_team"]) | set(season_df["away_team"]))

    atk, dfd, ha, rho = fit_dc(df)
    _, elo_now = compute_elo(df, K=25, home_adv=80, regress=0.40, return_ratings=True)
    tier1_elo_map = _get_tier_elo_map(TIER1)

    def strength(team):
        ps = [rm._dc_predict(team, o, atk, dfd, ha, rho)[0] for o in field if o != team]
        return 100 * sum(ps) / len(ps)

    fs = sorted(strength(t) for t in field if t in atk)
    print(f"{TIER2} field strength (avg home-win%): "
          f"min={fs[0]:.0f}  median={fs[len(fs) // 2]:.0f}  max={fs[-1]:.0f}")
    print(f"reverse offset tier1_offset('{TIER2}') = {co.tier1_offset(TIER2):+.1f} ELO\n")

    for team in RELEGATED:
        t1_elo = tier1_elo_map.get(team)
        if t1_elo is None:
            print(f"  {team:14} not in {TIER1} ELO map — skip")
            continue
        adj = t1_elo + co.tier1_offset(TIER2)
        a, d = _elo_to_dc_params(adj, atk, dfd, elo_now)
        atk[team], dfd[team] = a, d
        print(f"  {team:14} tier1_elo={t1_elo:.0f}  adj={adj:.0f}  "
              f"strength={strength(team):.1f}%  (DC atk={a:.3f} dfd={d:.3f})")

    print("\nExpected: relegated sides land in the UPPER field band (promotion favourites),"
          "\nnot near the bottom where the flat prior would put them.")


if __name__ == "__main__":
    main()
