#!/usr/bin/env python3
"""Validation: compare flat-percentile vs tier-bridge Brier on promoted teams.

For each supported league pair, collects all historically promoted teams' first-
season top-flight matches and computes Brier under (a) the static prior offset
and (b) the fitted tier2 offset.  Also reports naive (uniform) Brier.

Acceptance: tier-bridge Brier should be <= flat prior Brier on this slice.
A meaningful win on the promoted-team slice is the primary success criterion.

Usage:
    python scripts/eval/promoted_team_brier.py
"""
from __future__ import annotations

import logging

from data_pipeline import coefficients as co
from scripts.eval.tier_bridge import (
    _TIER2_PAIRS,
    _collect_tier_matches,
    _brier,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_NAIVE_BRIER = 2 / 3


def evaluate_pair(tier2_lid: str, tier1_lid: str) -> dict:
    """Compare flat vs tier-bridge Brier on promoted-team first-season matches."""
    key = f"{tier2_lid}_to_{tier1_lid}"
    prior = co._TIER2_PRIORS[key]
    fitted_delta = co.tier2_offset(tier2_lid)

    matches_by_season = _collect_tier_matches(tier2_lid, tier1_lid)
    all_matches = [m for ms in matches_by_season.values() for m in ms]

    if not all_matches:
        return {
            "pair": key, "n_matches": 0, "n_seasons": 0,
            "brier_tier_bridge": None, "brier_flat_prior": None,
            "naive_brier": round(_NAIVE_BRIER, 4), "delta_vs_flat": None,
        }

    brier_fitted = _brier(all_matches, fitted_delta)
    brier_flat = _brier(all_matches, prior)

    return {
        "pair": key,
        "n_matches": len(all_matches),
        "n_seasons": len(matches_by_season),
        "fitted_delta": round(fitted_delta, 2),
        "flat_prior": round(prior, 2),
        "brier_tier_bridge": round(brier_fitted, 4),
        "brier_flat_prior": round(brier_flat, 4),
        "naive_brier": round(_NAIVE_BRIER, 4),
        "delta_vs_flat": round(brier_fitted - brier_flat, 4),
        "passes": brier_fitted <= brier_flat,
    }


if __name__ == "__main__":
    print("Promoted-team Brier validation\n" + "=" * 40)
    all_pass = True
    for tier2_lid, tier1_lid in _TIER2_PAIRS:
        result = evaluate_pair(tier2_lid, tier1_lid)
        print(f"\n=== {result['pair']} ===")
        for k, v in result.items():
            if k == "pair":
                continue
            print(f"  {k}: {v}")
        if result.get("passes") is False:
            all_pass = False
            print("  *** REGRESSION: tier-bridge worse than flat prior ***")

    print("\n" + ("ALL PAIRS PASS" if all_pass else "SOME PAIRS FAILED"))
