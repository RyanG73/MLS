# Promoted Teams and Cross-League Strength — Design Spec

Date: 2026-06-27
Section: Codex review §10

---

## Problem

Promoted teams entering a top-flight league (Championship → EPL, 2.Bundesliga → Bundesliga,
Serie B → Serie A) are currently seeded at a flat 15th-percentile attack / 85th-percentile
defense from the current league's fitted Dixon-Coles parameters. This is better than
league-average seeding, but it ignores how strong the promoted team actually was in their
second-tier season. A team that swept the Championship at 1650 ELO is not the same
preseason prior as a team that scraped through via playoff at 1510 ELO.

Second-tier leagues (Championship, 2.Bundesliga, Serie B) are already built as goals-only
leagues in `build_league_data.py`. Their DC params and ELO exist — they just don't flow
into the top-flight builds or the power rankings.

---

## Goals

1. Replace the flat percentile DC seed with a prior derived from the promoted team's
   actual 2nd-tier ELO, translated to the top-flight scale via a fitted per-pair offset.
2. Add 2nd-tier teams to the power rankings on the same ELO-comparable scale as top-flight teams.
3. Validate using in-season Brier on first-season matches of historically promoted teams.
4. Zero impact on the MLS champion model or its promotion gate.

---

## Architecture

```
[football_data.match_results(tier2_league_id)]
  → re-derive 2nd-tier ELO sequence (same as _build_elo_history in league_bridge)
        ↓
[scripts/eval/tier_bridge.py]  ← NEW
  NLL-minimize one offset δ per league pair from first-season promoted-team matches
  Write experiments/tier2_offsets.json if validation passes
        ↓
[data_pipeline/coefficients.py]  ← EXTEND
  New: tier2_offset(tier2_league_id) → float
  Reads tier2_offsets.json (lazy-loaded, same pattern as _load_fitted)
  Falls back to static priors if file absent or league missing
        ↓
[scripts/build_league_data.py:352–368]  ← EXTEND promoted-team seeding block
  For each promoted team: look up 2nd-tier ELO, apply tier2_offset, map to DC params
  Fall back to existing flat prior if no 2nd-tier data for that team or league pair
        ↓
[scripts/build_power_rankings.py]  ← EXTEND _GROUPS
  Add "UEFA Tier 2" group: championship / bundesliga-2 / serie-b
  strength = 2nd-tier ELO + tier2_offset(league_id)
```

---

## Component Details

### 1. `scripts/eval/tier_bridge.py` (NEW)

**Purpose:** Fit the 2nd-tier → 1st-tier ELO offset for each supported league pair.

**Supported pairs (determined by existing `football_data.DIV` coverage):**

| Tier-2 league ID | Tier-1 league ID | Static prior (fallback) |
|---|---|---|
| `championship` | `epl` | −120 ELO |
| `bundesliga-2` | `bundesliga` | −100 ELO |
| `serie-b` | `serie-a` | −130 ELO |

Static priors are rough starting points estimated from typical ELO level differences
between divisions. They anchor the ridge penalty and serve as the fallback if the
fitted offsets fail validation or if the JSON is absent.

**Algorithm per league pair:**

1. Load full results for both `tier2_league_id` and `tier1_league_id` via
   `football_data.match_results()`.
2. Build 2nd-tier ELO history (reuses `_build_elo_history` pattern from `league_bridge.py`,
   but fed with `football_data` results instead of Understat/MLS).
3. Identify promoted teams per season: teams present in tier1 season Y+1 but absent from
   tier1 season Y. Seasons 2017–present (matching the model's training window).
4. For each promoted team and their tier-1 first-season matches:
   - `home_elo_promoted` = team's end-of-2nd-tier-season ELO (last match in season Y)
   - `away_elo_opponent` = opponent's tier-1 ELO as-of match date (from tier-1 ELO history)
   - Record outcome (0/1/2) as a `_Match` namedtuple (same structure as `league_bridge._Match`)
5. NLL-minimize single scalar offset δ over **all collected matches** using `scipy.optimize.minimize`
   (L-BFGS-B, same as `league_bridge._fit_group`):
   ```
   loss(δ) = -sum(log(match_probs(elo_2nd + δ, elo_opponent)[outcome]))
             + λ * n * (δ - prior)²
   ```
   λ = 0.01 (same default as league_bridge); n = match count. This produces the final offset.
6. Leave-one-season-out validation (separate from step 5): for each promotion cohort year
   (e.g. 2018, 2019, ...), fit on all *other* cohorts, evaluate Brier on the held-out cohort.
   Aggregate mean held-out Brier across folds. This is LOSO rather than random 70/30
   because the data is small (~24 events across 8 seasons) and structured by season.
7. Accept the step-5 offset if LOSO held-out Brier < naive AND |δ − prior| < 200 ELO.
   Otherwise fall back to static prior.
8. Write `experiments/tier2_offsets.json`:
   ```json
   {
     "championship_to_epl": -118.3,
     "bundesliga-2_to_bundesliga": -95.1,
     "serie-b_to_serie-a": -134.7
   }
   ```

**Name resolution:** Football-data uses consistent short names within its own files.
Teams appearing in both E1 (Championship) and E0 (EPL) use the same football-data
name. An `_ALIAS` dict in `tier_bridge.py` handles any known discrepancies (same
pattern as `_NAME_MAP` in `football_data.py`). Any unresolvable name logs a WARNING
and is skipped; the fit continues on the remaining data.

**CLI:**
```bash
python -m scripts.eval.tier_bridge              # fit all pairs, write JSON if valid
python -m scripts.eval.tier_bridge --dry-run    # fit and report, do not write
python -m scripts.eval.tier_bridge --lam 0.05   # ridge penalty override
```

---

### 2. `data_pipeline/coefficients.py` (EXTEND)

Add a `tier2_offset(tier2_league_id: str) -> float` function alongside the existing
`league_offset()`. Same lazy-load pattern as `_load_fitted()`:

- Reads `experiments/tier2_offsets.json` once on first call.
- Key format: `f"{tier2_league_id}_to_{tier1_league_id}"` — caller constructs the key.
- Convenience aliases: `tier2_offset("championship")` → looks up `championship_to_epl`.
- Returns the static prior constant if JSON absent or key missing.

Add a new `_TIER2_PRIORS` dict constant (static priors from the table above) and a
`_TIER1_FOR: dict[str, str]` mapping (e.g. `"championship" → "epl"`), both used by
`tier2_offset()` and by `build_league_data.py` to know which pair to look up.

---

### 3. `scripts/build_league_data.py` — promoted-team seeding (EXTEND)

Replace the body of the existing promoted-team seeding block (lines 352–368) with:

```python
for _pt in _promoted_teams:
    _tier2_lid = _TIER2_FOR.get(lid)          # e.g. "epl" → "championship"
    _tier2_elo = _get_tier2_elo(_pt, _tier2_lid) if _tier2_lid else None
    if _tier2_elo is not None:
        # Translate 2nd-tier ELO to 1st-tier scale and map to DC params.
        _adj_elo = _tier2_elo + co.tier2_offset(_tier2_lid)
        atk[_pt], dfd[_pt] = _elo_to_dc_params(_adj_elo, atk, dfd, elo_now)
    else:
        # Fall back to existing flat percentile prior.
        atk[_pt] = _atk_prior
        dfd[_pt] = _dfd_prior
```

**New helpers added to `build_league_data.py`:**

- `_TIER2_FOR: dict[str, str]` — maps top-flight league ID to its 2nd-tier ID (e.g.
  `"epl" → "championship"`). Only covers the three supported pairs; other leagues fall
  through to the existing flat prior.

- `_get_tier2_elo(team, tier2_league_id) -> float | None` — loads 2nd-tier results via
  `football_data.match_results(tier2_league_id)`, runs `compute_elo`, returns the team's
  most recent ELO. Returns `None` if the team isn't found (e.g. promoted from a league
  not in the supported pairs, or name mismatch).

- `_elo_to_dc_params(adj_elo, atk_map, dfd_map, elo_map) -> tuple[float, float]` — maps
  the translated ELO to a DC attack/defense prior by interpolating the percentile of
  `adj_elo` in `elo_map.values()`, then returning the corresponding percentile of
  `sorted(atk_map.values())` for attack and `sorted(dfd_map.values(), reverse=True)` for
  defense (stronger attack = higher atk value; weaker defense = higher dfd value in DC
  log-space). Clamps to [5th, 95th] percentile to avoid extreme seeds.

**Logging:** Promoted teams seeded via tier-bridge log at `[epl] promoted team X:
championship_elo=1583, adjusted=1463, DC_seed=(atk=-0.11, dfd=0.09)`. Fallback to
flat prior logs at WARNING level with the reason.

---

### 4. `scripts/build_power_rankings.py` (EXTEND)

Add a `"UEFA Tier 2"` confederation group using the same `_rank_group()` function. Each
2nd-tier team's strength = their built ELO + `co.tier2_offset(lid)`. This places them on
the EPL-anchored ELO scale, so strong Championship sides appear just below the EPL
relegation zone — which is the correct interpretation.

```python
_GROUPS = {
    "UEFA": [...],   # unchanged
    "UEFA Tier 2": [("championship", "Championship"), ("bundesliga-2", "2. Bundesliga"),
                    ("serie-b", "Serie B")],
    "Concacaf": [...],   # unchanged
}
```

In `_rank_group()`, use `co.tier2_offset(lid)` instead of `co.league_offset(lid)` for
tier-2 leagues. Add a `"tier": 2` field to each ranked row so the dashboard can render
them in a visually distinct band. The anchor display for this group is `"EPL = 0"` (same
as UEFA, because the tier2 offset is relative to EPL).

The `power.js` payload gains a third group. No schema changes needed — the existing
`groups[].teams[]` structure accommodates the new `"tier"` field transparently.

---

## Data Flow Example

```
Championship 2024–25 results → compute_elo
  → Ipswich Town end-of-season ELO: 1618

tier_bridge fit: championship_to_epl offset = −118.3
  → experiments/tier2_offsets.json

build_league_data.py (epl, preseason 2025–26):
  _promoted_teams = {Ipswich Town, Burnley, Sheffield United}  (example)
  Ipswich Town:
    _tier2_elo = 1618
    _adj_elo = 1618 + (−118.3) = 1499.7  ← just below EPL average (1500)
    percentile in EPL ELO dist ≈ 48th
    DC seed: atk ≈ median, dfd ≈ median  (near-average EPL team, not relegation fodder)
  vs. current flat prior: always 15th-pct attack / 85th-pct defense regardless of 2nd-tier form
```

---

## Validation

**Metric:** In-season Brier on first-season top-flight matches of promoted teams, sliced
from completed seasons 2018–2025 (first cohort is 2017-promotions playing in 2018 tier1).

**New script:** `scripts/eval/promoted_team_brier.py` — loads historical results, runs
both priors (flat vs tier-bridge) on promoted-team first-season matches, reports Brier
and naive baseline per league pair and combined.

**Acceptance criteria for the tier-bridge offset:**
- Held-out Brier ≤ naive baseline.
- Held-out Brier ≤ flat-percentile prior Brier (no regression on the target slice).
- |fitted offset − static prior| < 200 ELO (sanity bound).

**No change to MLS champion gate.** The MLS model is unaffected by this feature —
MLS teams don't get promoted from a tracked lower division.

---

## Error Handling and Fallbacks

| Failure mode | Behavior |
|---|---|
| `tier2_offsets.json` absent | `tier2_offset()` returns static prior; build continues |
| Promoted team not found in 2nd-tier ELO map | Falls back to existing flat-percentile seed; logs WARNING |
| League pair not in supported set | Falls back to existing flat-percentile seed; no error |
| Fit validation fails (Brier worse or offset out of bounds) | Static prior written to JSON; fit reports reason |
| `football_data.match_results()` fetch fails | `_get_tier2_elo()` returns None; flat-prior fallback |

---

## Testing

| Test | File | Type |
|---|---|---|
| `tier2_offset()` returns static prior when JSON absent | `tests/test_coefficients.py` | unit |
| `tier2_offset()` reads fitted offset from JSON | `tests/test_coefficients.py` | unit |
| `_elo_to_dc_params()` returns correct percentile params | `tests/test_build_league_data.py` | unit |
| `tier_bridge --dry-run` runs end-to-end with real data | `tests/test_tier_bridge.py` | integration |
| Promoted-team Brier no worse than flat prior | `scripts/eval/promoted_team_brier.py` | validation |
| 2nd-tier teams appear in power.js with correct tier field | `tests/test_build_power_rankings.py` | integration |
| Existing `test_cross_league.py` still passes | `tests/test_cross_league.py` | regression |

---

## Scope

**In scope:**
- Championship → EPL
- 2. Bundesliga → Bundesliga
- Serie B → Serie A
- Power rankings: all three 2nd-tier leagues

**Out of scope (deferred):**
- La Liga 2 → La Liga (no football-data coverage in current `DIV` map)
- Ligue 2 → Ligue 1 (same)
- League One → Championship / lower-tier-to-second-tier seeding (same mechanism but lower
  priority; can be added later by extending `_TIER2_FOR` and `_TIER1_FOR` with one more pair)
- Playoff vs automatic promotion distinction (sparse data per promotion path; deferred)
- UEFA ↔ Concacaf global bridge (separate initiative per next-steps plan §2.3)
- MLS champion model or MLS Brier gate changes
