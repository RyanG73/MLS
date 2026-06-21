# Next Steps — Model / Rankings / Dashboard / Efficiency (2026-06-21)

> **2026-06-21 — Section 1 (Data Contracts) complete.**
> Created `scripts/payload_utils.py` (`write_js_payload` + `health_feature_stats`). Fixed NaN in
> preseason health blocks (epl/ligue-1/serie-a). Added `generated` to continental and power payloads.
> Added explicit placeholder schema to `canadian-pl.js` and `fetch_league_teams.py`.
> Created `scripts/validate_payloads.py` (post-build gate). Wired into `build_all.sh`.
> All 19 payloads pass validator; 199 tests green; zero NaN in any payload file.

> Planning doc. Concrete next steps across four areas, prioritized within each.
> Guardrails carry over: MLS champion parity |Δ|=0.0000; full suite green; in-browser regression-clean.

## Where we are (honest baseline)
- MLS champion at its feature ceiling; continental model validated with honest nulls (coefficient priors
  are strong; Approach C ≈ priors even with as-of-date ELO).
- Known limits: Concacaf small-sample (CC n=51 can't beat naive), no continental odds source, pre-season
  projections concentrated/high-variance, power rankings confederation-relative (no UEFA↔Concacaf bridge).

---

## 1. Model performance

1. **Pre-season prior calibration (high value, near-term).** EPL 2026-27 odds are over-concentrated
   (Arsenal 50% / City 42%). Widen the pre-season prior: blend each team's DC strength toward the league
   mean by a season-gap shrinkage, and/or inflate the per-match draw rate at season start. Validate that
   pre-season title spreads look bookmaker-reasonable (favorite ~25-35%, not 50%).
2. **Promoted-team strength from the 2nd tier (replaces the flat percentile seed).** Seed promoted teams
   from their actual Championship/2.Bundesliga/etc. ELO via a 2nd-tier→top-flight cross-league offset
   (reuses the `league_bridge` framework). More principled than the current 15th-percentile DC seed.
3. **xG-aware continental match model.** Big-5 entrants have rolling xG; use it (not just ELO) for
   continental ties where available — likely the biggest continental accuracy lever, and it sidesteps the
   coefficient-prior ceiling that Approach C hit.
4. **Deeper continental history.** Fetch more seasons of continental results (the adapter + merge support
   it) to give the Concacaf calibration and `league_bridge` more signal — the current n is the binding
   constraint, not the method.
5. **Revisit squad/availability features with 2024+ depth.** The roster-profiles probe was data-limited
   (2024-only); with 3 seasons accumulating, re-run through the promotion gate.
6. **In-season Bayesian updating** of pre-season projections — shrink toward the pre-season prior early,
   let results dominate as the season progresses (a clean Beta/Dirichlet update on the standings sim).

## 2. Ranking individual teams and leagues

1. **League strength index (cross-league offsets you already have).** Rank the *leagues* themselves on
   one scale (mean + top-end team strength), with a "league power" panel. The offsets encode this; it's a
   small aggregation on top of `power.js`.
2. **UEFA↔Concacaf bridge → a true global Top-50.** The one thing blocking a single world ranking is the
   missing anchor between confederations. Options: FIFA Club World Cup results (UEFA vs Concacaf/CONMEBOL
   matches), or a market-value anchor. Even a coarse bridge enables "best clubs in the world."
3. **2nd-tier leagues in the power ranking.** Add Championship/2.Bundesliga/etc. via a 2nd-tier→top-flight
   offset (same machinery as #1.2) — lets a strong Championship side rank against weak top-flight sides.
4. **Biggest movers / momentum.** Rank by ELO change over the last N matches (rising/falling), and a
   "form" rank alongside the strength rank — answers "who's hot right now."
5. **All-time peaks + trajectories.** Best single-season ratings in the dataset; a team's peak vs current.
6. **Uncertainty on ranks.** The strength is a point estimate — add a confidence band (bootstrap over the
   ELO history) so close ranks aren't over-read.

## 3. Improving the dashboard

1. **Model report-card (Model Health tab).** A per-league/comp accuracy panel: hit-rate, Brier vs naive,
   a calibration curve, "model's biggest correct/missed calls." Turns the games retrospective into a
   trust signal. (Was roadmap S9.)
2. **League-power + global-ranking views** (from §2) — natural companions to the team Power Rankings.
3. **Logo coverage + polish.** Fill crests for promoted/new sides (Coventry etc.); consistent sizing;
   higher-res where available. Today they fall back to monograms.
4. **Head-to-head compare tool.** Pick any two teams (cross-league) → strength gap, projected result,
   ELO trajectories overlaid. Showcases the cross-league strength directly.
5. **Promoted/relegated badges** in pre-season tables (deferred from S6) — a small "P"/"R" chip.
6. **Richer match cards** — xG, recent form, H2H on the Match Projections rows.
7. **Mobile polish** — you're viewing on a phone over the LAN; audit responsive breakpoints for the new
   wide table (5 qualification columns) and the bracket/power views.
8. **Value-bets surfacing** once a market source exists (currently scaffolded, dormant).

## 4. Improving efficiency

1. **Vectorize the league Monte-Carlo.** `build_league_data` still loops the season sim in Python (the
   same pattern bracket_sim had before its 8.5× win). Batch the remaining-fixture draws with numpy →
   faster builds, especially the 5000-sim pre-season runs.
2. **Incremental / parallel `build_all.sh`.** It rebuilds every surface sequentially (~40 min). Rebuild
   only what changed (cache-mtime check), and parallelize independent league builds.
3. **Rollover + regression tests (was roadmap S10).** Lock pre-season state, promoted seeding, ESPN
   fixtures parsing, and the new qualification buckets so future seasons don't silently regress them.
4. **Proper static deploy.** Replace the ad-hoc LAN `http.server` with a real static host (GitHub Pages
   or similar) + cache headers, so the dashboard is reachable off-network and stale-cache is controlled
   at the edge (complements the per-file cache-bust already added).
5. **Finish the continental odds scaffold (was roadmap S8)** so value-bets activate cleanly when a key +
   in-season comp exist — small, and removes a dangling thread.
6. **Build-time profiling.** Identify and speed up the slowest steps (continental backtest, league sims)
   now that the engine is vectorized in places but not others.

---

## Suggested execution order
**Quick wins first:** §1.1 pre-season calibration, §4.1 league-sim vectorization, §2.1 league-strength
index (+ panel) — each small, high-visibility. **Then the depth levers:** §1.3 xG continental model,
§2.2 UEFA↔Concacaf bridge (unlocks the global Top-50 + §3.4 head-to-head), §3.1 model report-card.
**Then operational:** §4.2 incremental/parallel builds, §4.3 rollover tests, §4.4 deploy.
