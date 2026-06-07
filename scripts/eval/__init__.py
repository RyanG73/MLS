"""
Decomposed components of the eval_baseline research harness (F4).

This package extracts the pure, self-contained computational core out of the
scripts/eval_baseline.py monolith so it can be unit-tested in isolation and
reused. Extraction is behavior-preserving — verified by `eval_baseline.py
--smoke-test` (2024 Brier within 0.001 of the pinned reference).

Modules:
  dixon_coles      — Dixon-Coles Poisson goal model (fit + predict, pure functions)
  calibration      — probability calibration + calibration-error metrics
  elo              — ELO rating model (walk-forward, margin-of-victory, regression)
  feature_registry — pure constants and helpers (FIFA breaks, Pythagorean,
                     haversine, TZ shift, z-score, position predicates)
  feature_builders — rolling feature computation (add_rolling_features,
                     add_h2h_draw_features) with explicit parameter signatures

The section 5a–5n builders in eval_baseline.py that depend on live ASA fetches
or complex multi-season lookups remain inline; these are extracted incrementally
as test coverage grows.
"""
