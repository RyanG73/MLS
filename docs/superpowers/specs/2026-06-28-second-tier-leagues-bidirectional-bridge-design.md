# Second-Tier Completion + Bidirectional Cross-Tier Bridge — Design Spec

**Date:** 2026-06-28
**Scope:** Add Spanish Segunda + French Ligue 2 as full second-tier dashboard leagues, and make the cross-tier promotion/relegation bridge bidirectional and per-league calibrated across all big-5 countries.
**Status:** Design approved; pending spec review.

## 1. Goal & motivation

Bring Spain and France to the same second-tier parity England, Italy, and Germany already have, and fix the cross-tier seeding so that **both** directions are calibrated:
- **Promoted teams** seed correctly into the top flight (exists today for 3 of 5 countries; complete the set).
- **Relegated teams** seed correctly into the second tier (does not exist today — relegated teams hit the harsh flat prior and seed *too weak* when they should be promotion favourites).

Motivating evidence (from the 2026-06-28 calibration test of the promoted-team seeding fix):
- Ligue 1's promoted teams (Le Mans, Troyes) seed at 97.8% relegation via the flat prior, because Ligue 1 has no tracked second tier — a tier-2→tier-1 bridge fixes this.
- Any team relegated into a second-tier preseason projection seeds via the same flat prior — a tier-1→tier-2 bridge fixes that mirror case.

## 2. Constraints & non-goals

- **Reuse existing machinery.** This extends `tier_bridge.py`, `build_league_data.py`, `football_data.py`, `leagues.js`, and `tier2_offsets.json` — no new subsystems, no refactor of validated code. The smooth + soft-floor `_elo_to_dc_params` (added 2026-06-28) is reused unchanged in both directions.
- **Second tiers are goals-only models.** football-data has no xG, so Segunda/Ligue 2 use the goals-only model like the existing second tiers. "Full" = as complete as the data allows. No xG source for second tiers.
- **Scope is the tier-1 ↔ tier-2 boundary only.** Deeper boundaries (Championship↔League One, League One↔League Two) are NOT in scope — teams promoted from a third tier into a second tier keep the flat prior. A future extension could add them.
- **No cross-tier UI navigation.** Per user decision, the experience matches England/Germany today: standalone browsable second-tier leagues with the existing redesigned UI. No links between a top flight and its second tier.
- **No model-config changes.** The champion model, ELO params, and the existing forward offsets' fitting methodology are unchanged; we only add the reverse-direction fit and two new pairs.

## 3. Components

Each is a focused change to an existing unit.

### 3.1 Data source — `data_pipeline/football_data.py`
- `DIV` += `"segunda": "SP2"`, `"ligue-2": "F2"`.
- `GOALS_ONLY` += `"segunda"`, `"ligue-2"` (they are model sources, NOT `BIG5` market sources).
- `_NAME_MAP` += a `"segunda"` and `"ligue-2"` sub-dict mapping football-data short names → display names, for the teams whose names differ from the display/ESPN form. Built by diffing the football-data team list against ESPN `esp.2`/`fra.2` display names during implementation.

### 3.2 League config — `build_league_data.py` `OUTLOOK`
- Add `"segunda"` (n=22) and `"ligue-2"` (n=18), `source: "footballdata"`, with promotion/playoff/relegation buckets mirroring the existing second tiers:
  - **segunda:** promote `top: 2`, playoff `band: [3,6]`, relegate `bottom: 4`.
  - **ligue-2:** promote `top: 2`, playoff `band: [3,5]`, relegate `bottom: 4`.
  - Exact bucket counts confirmed against the current season's format at implementation (the existing entries already note these are approximate and vary by season).

### 3.3 Sidebar — `webapp/leagues.js`
- Add `segunda` and `ligue-2` entries under the UEFA group, each `status: "live"`, with `espn_code` `esp.2`/`fra.2` and the ESPN league logo URL (league-logo id resolved during implementation), positioned adjacent to their top flights (La Liga, Ligue 1).

### 3.4 Bidirectional bridge — `scripts/eval/tier_bridge.py`
- `_TIER2_PAIRS` += `("segunda", "la-liga")`, `("ligue-2", "ligue-1")` (now 5 pairs).
- Add `_identify_relegations(tier1_results)` — mirror of `_identify_promotions`: a team in tier-1 season *Y−1* but absent in season *Y* is relegated for the *Y* second-tier season.
- Add reverse collection — for each relegated team, collect its **first second-tier season** matches (the season after the drop), keyed by tier-2 season, with the team's end-of-tier-1 ELO as the seed-side rating.
- Fit a reverse offset per pair with the existing LOSO fitter (`_fit_offset`, `_loso_validate`), exactly as the forward offset is fit.
- Output `experiments/tier2_offsets.json` with **both** directions per pair:
  `{"championship_to_epl": -120.0, "epl_to_championship": +<fit>, …}` (5 forward + 5 reverse keys).

### 3.5 Seeding — `build_league_data.py`
- Generalise `_get_tier2_elo_map(tier2_lid)` → a league-agnostic `_get_tier_elo_map(lid)` (or keep both as thin wrappers) so either tier's ELO map can be loaded.
- Add `_TIER1_FOR: dict[str, str]` (tier2 → tier1), the inverse of `_TIER2_FOR`.
- In the preseason seeding block: when the league being built is a **second tier** (`lid in _TIER1_FOR`), detect relegated teams (in `_upcoming_teams` but not `_prior_teams`, AND present in the tier-1 ELO map) and seed them via `_elo_to_dc_params(tier1_elo + reverse_offset, …)` using the same smooth+floor mapping. Teams new from a third tier (not in the tier-1 map) keep the flat prior.
- The existing tier-1 build path (promoted teams via `_TIER2_FOR`) is unchanged.
- `co.tier2_offset(...)` reads forward offsets; add `co.tier1_offset(tier2_lid)` (or generalise to a single `co.tier_offset(src, dst)`) to read the reverse key.

### 3.6 Logos — `scripts/fetch_foreign_logos.py` + `build_logo_map.py`
- Ensure `esp.2` and `fra.2` are in the fetch list (fra.2 already present; add esp.2), regenerate `webapp/data/logos.js`. Segunda/Ligue 2 teams (no football-data logos) resolve through the global map.

## 4. Data flow

Build-time, offline/deterministic where possible:
1. `tier_bridge.fit_all()` → fits 5 pairs × 2 directions from football-data history (LOSO-validated) → `tier2_offsets.json`.
2. `build_league_data.py --league <id>` → reads offsets, seeds cross-tier teams (promoted in a top flight, relegated in a second tier), writes `webapp/data/<id>.js`.
3. `build_logo_map.py` → `logos.js`. The webapp renders the new leagues with the existing UI.

## 5. Calibration plan

- Fit all offsets via the extended `tier_bridge.fit_all()`; record LOSO Brier per pair/direction (the module already validates the forward direction this way).
- Rebuild the affected leagues: la-liga, ligue-1 (forward offsets now exist), serie-a/epl/bundesliga (re-fit may shift forward offsets slightly), and segunda/ligue-2/championship/serie-b/bundesliga-2 (reverse seeding).
- Verify in the dashboard, in preseason mode where applicable: promoted teams cluster in the relegation third of the top flight; relegated teams cluster in the promotion third of the second tier; no team snapped to an extreme (the smooth+floor mapping holds in both directions).

## 6. Testing

- **Offline reproduction (reverse):** a mirror of `scripts/validate_promoted_seeding.py` — load a second-tier cached frame, fit DC + ELO, seed a known relegated team via the reverse offset, confirm sane strength (promotion-favourite band, not flat-prior weak).
- **LOSO Brier** on each new offset (forward Spain/France + all five reverse), reported by `tier_bridge` — must beat the naive baseline as the existing forward offsets do.
- **Dashboard verification:** rebuild Segunda, Ligue 2, and re-fit/rebuild the big-5 + their second tiers; screenshot-confirm the tables and the projected-finish plots render and that cross-tier-seeded teams are sane. Console clean.

## 7. Risks & mitigations

- **Team-name mismatches** (football-data ↔ ESPN/display ↔ tier-1 names) — handled by `_NAME_MAP` additions and the existing `_FD_TEAM_ALIASES`; verified by checking the seeding log names against the ELO map.
- **Preseason vs completed** — if football-data has no current-season data, the new second tiers display the completed prior season (no seeding visible). Same behaviour as the top flights today; not a defect.
- **Bucket exactness** — promotion/playoff/relegation counts vary by season; entries use the documented "approximate" convention and are confirmed at implementation.
- **Reverse-offset data sparsity** — fewer relegated-team-seasons than promoted; the LOSO fitter's ridge penalty (already present) shrinks toward the static prior when data is thin, as it does for the forward direction.

## 8. File touch list

- Modify: `data_pipeline/football_data.py` (DIV, GOALS_ONLY, _NAME_MAP)
- Modify: `scripts/build_league_data.py` (OUTLOOK +2 entries; `_TIER1_FOR`; reverse seeding path; tier ELO map generalisation)
- Modify: `scripts/eval/tier_bridge.py` (+2 pairs; `_identify_relegations`; reverse collection + fit; both-direction output)
- Modify: `data_pipeline/coefficients.py` (read reverse offset key)
- Modify: `webapp/leagues.js` (+segunda, +ligue-2)
- Modify: `scripts/fetch_foreign_logos.py` (+esp.2) → regenerate `webapp/data/logos.js`
- New (generated): `webapp/data/segunda.js`, `webapp/data/ligue-2.js`; updated `experiments/tier2_offsets.json`
- New (test): a reverse-direction reproduction script alongside `scripts/validate_promoted_seeding.py`
- Docs per CLAUDE.md convention (PLAN blockquote, CURRENT_STATE tier-bridge section, PROJECT_HISTORY entry, plan-file lifecycle).

## 9. Open questions

None blocking. Defaults taken: tier-1↔tier-2 boundary only (no deeper tiers); goals-only second-tier models; standalone (no cross-tier UI nav); symmetric per-pair independently-fitted offsets.
