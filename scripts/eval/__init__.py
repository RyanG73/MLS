"""
Decomposed components of the eval_baseline research harness (F4).

This package extracts the pure, self-contained computational core out of the
scripts/eval_baseline.py monolith so it can be unit-tested in isolation and
reused. Extraction is behavior-preserving — verified by `eval_baseline.py
--smoke-test` (2024 Brier within 0.001 of the pinned reference).

Modules:
  dixon_coles      — Dixon-Coles Poisson goal model (fit + predict, pure functions)
  calibration      — probability calibration + calibration-error metrics
  feature_registry — pure constants and helper functions used by the feature
                     building pipeline (FIFA breaks, Pythagorean, haversine,
                     TZ shift, z-score helpers, position predicates)

The large feature-building section of eval_baseline.py is intentionally NOT
fully extracted yet: it is tightly coupled to a module-level `df` and live ASA
fetches, and splitting it is the high-risk part to be done incrementally.
Pure helpers have been extracted; add_rolling_features and section 5* builders
remain inline pending more test coverage.
"""
