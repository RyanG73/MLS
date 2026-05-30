# Model Architecture Log

> Results from the model-architect agent. Populated by the multi-agent improvement workflow.
> See `docs/experiment-protocol.md` for the protocol.
>
> Open questions (from PLAN.md):
>   - DC drag: stacked ensemble (0.6437) worse than XGB alone (0.6387)
>     → consider XGB-only ensemble (removing DC probs from the meta-learner)
>   - DC as feature only: dc_lam/dc_mu already in +DCParams set (Δ=+0.0002, marginal)
>   - Meta-learner: LogisticRegression over [DC_probs, XGB_probs] — worth testing simple average
>   - Betting-aware loss: betting_logloss() in models/gradient_boost.py — not yet tested in harness

---

<!-- model-architect agent appends entries here -->
