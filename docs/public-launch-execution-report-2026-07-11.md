# Public Launch Execution Report

Date: 2026-07-11

## Summary

- Refreshed MLS champion report Brier: 0.6331. Previous checkpoint was 0.632977, so this is flat/slightly worse by +0.000106 and not a model improvement.
- MLS significant underdogs: 24.2% predicted vs 24.8% observed, n=1358.
- Edge-board 7-day slate: 135 matches across 12 leagues.
- Current risk flags: away_model_underdog=6, draw_heavy=8, low_total_draw_setup=9, no_line=13.
- Tier-family row-level market buckets: 0 buckets; market status no_market.

## 18-Step Execution Status

1. European Market-Disagreement Buckets — Completed for available row-level market payload rows. Family-level buckets now flow through `model-slices.js`; broader historical depth still depends on row-level odds history beyond aggregate `perf_by_year`.
2. Promoted/Relegated Early-Window Slice — Completed in `scripts/eval/unified_tier_elo.py` with pooled windows `0-5`, `6-15`, and `16+`.
   - 0-5: seeded 0.6440, league 0.6436, decay8 0.6445.
   - 6-15: seeded 0.6414, league 0.6408, decay8 0.6409.
   - 16+: seeded 0.6276, league 0.6277, decay8 0.6277.
3. Historical Draw Calibration by Goal Total — Completed for played rows carrying `lam`/`mu`; surfaced by family in `model-slices.js`.
   - low total: draw 30.2% predicted vs pending observed, played_n=0.
   - middle total: draw 25.9% predicted vs pending observed, played_n=0.
   - high total: draw 21.0% predicted vs pending observed, played_n=0.
4. Trust UI: Market Disagreement Card — Completed as a conditional evidence tape. It appears only when row-level market buckets exist.
5. Trust UI: Promoted/Relegated Caution Card — Completed for the Europe tiers family using early-window replay results.
6. Draw-Side Policy Gate — Completed as policy: draw recommendations remain suppressed; draw rows are diagnostics only until a future gate explicitly promotes them.
7. Current Slate Risk Scoring — Completed in `scripts/build_edge_board.py` with no-line, draw-heavy, low-total draw setup, model-underdog, and qualifying-edge flags.
8. Command Center Risk Tape — Completed in the landing Command Center and match rows.
9. Paper Ledger + CLV Upgrade — Build chain now runs `scripts/bet_ledger.py`; real CLV still depends on opener/closer odds files accumulating.
10. Odds Coverage Expansion — Repo-side decision artifact remains: current implementation is ready for broader odds, but provider selection/payment is external and unresolved.
11. European Launch QA Pass — Payload validation and static syntax checks are wired; visual QA should still be repeated before deploy on the target host.
12. SEO / Share Pages — Completed basic title, description, Open Graph, and Twitter metadata in `webapp/index.html`.
13. Email Capture / Weekly Digest — Static UI scaffold completed. Real capture requires selecting an email backend or form endpoint.
14. Weekly Content Workflow — This report is the first generated content artifact; recurring weekly generation can reuse the same source payloads.
15. Post-Launch Calibration Review — Not due until 2026-27 matches accrue; report surfaces the fields needed for review.
16. Model Feature Hunt Resumption — Deferred by design; diagnostics showed no Brier improvement yet and no production model change.
17. Promotion Gate Extensions — Completed as advisory `trust_diagnostics` output in `scripts/promotion_gate.py`.
18. Production Build Discipline — `build_all.sh` now includes model slices, paper ledger, edge board, and this public-launch report after payload validation.

## Findings

- Brier did not improve. The work improved auditability and launch readiness, not model accuracy.
- MLS underdog calibration is strong enough to show publicly: significant underdogs are close to calibrated.
- Promoted/relegated bridge-decay remains a no-change result. The early-window replay did not reveal a hidden first-five-match win.
- Market-disagreement evidence is now structurally available, but current row-level market depth is thin and concentrated in leagues with played market rows.
- Draw-side betting should remain suppressed. Draw-by-total diagnostics are visible, but there is no promotion gate result that justifies draw recommendations.

## Remaining External Dependencies

- Paid/live odds coverage for broader row-level model-vs-market and CLV history.
- Email collection backend or static form provider.
- Final hosted-domain URL for canonical/share metadata.
- Manual visual QA on production deployment after build.
