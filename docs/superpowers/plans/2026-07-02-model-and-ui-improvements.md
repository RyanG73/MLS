# Model & Webapp Improvement Plan (2026-07-02)

> **VERDICT A5 (2026-07-05): DROP.** `--elo-xg-blend 0.3`, 4-fold walk-forward (2022–2025),
> bag-5 seed 42. Mean ens Brier = 0.6346 vs champion 0.6330 (+0.0016). Consistent regression
> across all four folds; blending xG into ELO updates hurts the ensemble. Flag left as opt-in
> experimental. Champion unchanged.

> **VERDICT A11 (2026-07-05): DROP (both candidates).** Two-stage draw hurdle
> (`--draw-two-stage`) and per-season DC rho re-fit (`--dc-rho-per-season`) both underperform
> champion on the standard aggregate gate — `ens_stacked` avg 0.6347 (hurdle) and 0.6352 (rho)
> vs champion 0.632977 (Δ −0.0017 / −0.0022), both past the ±0.001 noise floor. Per-season:
> hurdle regresses in 2023–2025 (2022 flat); rho regresses hardest in 2024 (+0.0022 fold-specific,
> the exact fold the champion is most sensitive on). Clean double-failure on the task's primary
> gate criterion (ii) — the A1 `draw_reliability` slice and `roi_by_edge_bucket` draw-bet checks
> (criteria i/iii) are skipped per A4 precedent (a regression this far past noise can't be
> rescued by a slice win). B5/B12 continue to suppress draw-side Kelly sizing — no KEEP has
> landed on this track. No second-seed confirmation needed (DROP verdicts are unambiguous per
> `docs/experiment-protocol.md`). Full numbers in `docs/feature-hunt-log.md`.

> **VERDICT A1 (2026-07-03): COMPLETE.** `by_favorite_prob`, `by_season_phase`, `draw_reliability`
> slices added to `_slice_table`; 3 new tests + suite green (403 passed; 1 pre-existing
> browser-smoke mobile-overflow failure, unrelated). Champion report re-run at parity
> (avg 0.6330, cal 0.0182). **Baselines for A4/A5/A6/A8 + B4 data**
> (`experiments/a1-slices-baseline-4f55219c-20260703T154857.report.json`):
> - Favorite deciles: calibrated 0.37–0.58 (prob≈hit); over-confident 0.58–0.65
>   (p̄ 0.604 vs hit 0.554, n=56); under-confident 0.30–0.37 (p̄ 0.360 vs hit 0.405, n=74).
> - Season phase Brier: first_60d **0.6314** (n=497) · mid **0.6379** (n=971) · late **0.6264**
>   (n=604) — mid-season is the worst phase, not first_60d as §1.3d suspected.
> - Draw curve: over-forecast concentrates in high bins (p̄ 0.317→freq 0.270 at 0.30–0.35;
>   p̄ 0.365→freq 0.273 at 0.35+); low bin 0.15–0.20 under (p̄ 0.189→freq 0.082, n=49).

> **VERDICT A7 (2026-07-03): COMPLETE — the Spurs 42% is miscalibration, and the effect is
> monotone.** `scripts/eval/club_prior.py` (`club_prior_gap`, `elo_history_from_matches`) +
> `by_club_prior_gap` tercile slice in `model_report.py`; 6 new tests, suite green.
> Cohort study (big-5 FD history, 2017–2025, 856 team-seasons, K=25/HA=80/REGRESS=0.40):
> - **Relegation rate falls monotonically in gap:** gap≤0 → 23.7% · 0–50 → 9.3% ·
>   50–100 → 1.6% · 100+ → **0.0%** (n=20). Beat-seed margin rises monotonically
>   (−0.40 → +0.42 → +0.44 → +0.60 ranks).
> - **Spurs-shaped subset (gap≥50 AND bottom-half seed, n=18): relegation rate 11.1%**
>   vs 26.6% for all bottom-half seeds; they finish **+4.9 ranks better than seeded**
>   (vs +1.5 baseline). Exact analogues: Chelsea '23 seed 13 → 6th; Man United '25
>   seed 16 → 3rd. **A8's gate number: a high-gap bottom-half team's relegation odds
>   should land near ~11% (Wilson 95% CI ≈ 3–33%), not 42%.**
> - Top gap decile (≥64 pts, n=86, mostly elites — flat-1500 regression mechanically
>   drags every strong club): 0 relegations; ELO home-prob Brier on gap≥100 matches
>   0.2014 vs 0.2463 all (ELO itself recovers in-season; the damage is the SEED).

> **VERDICT B1 (2026-07-03): COMPLETE.** Builders already emitted `status` everywhere except
> power (`build_power_rankings.py` now emits `status: "live"`); the 8 missing payloads were
> stale, not code gaps. Validator now REQUIRES top-level `status` on every payload
> (logos.js excluded, mirroring the contract test) + new contract test
> `test_has_top_level_status`. Rebuilt: ucl/europa/conference/concacaf-champions/leagues-cup
> (all `completed`), mls (`live`), power (`live`), liga-mx (`completed`). All 21 payloads
> valid; suite 433 passed. Note: 2 PRE-EXISTING browser-smoke mobile-overflow failures
> (mls, epl @390px — verified present before any change; flagged as a spin-off task).

> **VERDICT B10 (2026-07-03): COMPLETE — accrual started 2026-07-03 (438 team-rows day one).**
> `scripts/archive_odds_snapshot.py` appends per-(league, team, build-date) rows —
> title/playoff/shield/cup/ucl/europa/releg odds + ELO + proj_pts + next-match model probs
> (market prob columns reserved, populate when B5 ships `mH/mD/mA`) — to
> `data/odds_history.parquet` (gitignore-excepted; committed by CI). Wired after the build
> step in both refresh workflows; 3 tests (dedup, second-date append). **odds_log finding:**
> NOTHING has ever been logged — no `ODDS_API_KEY` anywhere, no CI step, no live launchd job
> (`daily_build.sh` references a plist but the GH-Actions cron replaced it). Added an
> openers+closers step to the daily MLS workflow (clean no-op without the key — user must add
> the `ODDS_API_KEY` repo secret to activate; free-tier quota ≈60 req/mo for MLS both lines).
> The-Odds-API keys for all 14 covered leagues filed in `config/settings.yaml`
> `market.league_sport_keys`, fetch NOT enabled (budget-gated per user decision). Caveat: the
> 7AM-ET daily cron catches closers only for kickoffs within `--minutes 180` of 11:00 UTC —
> real closer coverage needs a near-kickoff schedule; deferred with the paid-key decision.

> **VERDICT A8 (2026-07-03): PARTIAL KEEP — Europe only, β=0.75 club-prior target ported to
> production; MLS champion untouched.** `compute_elo` gains `club_prior_beta` (regress toward
> `(1-β)·1500 + β·mean(end-of-season ELO, prior ≤3 seasons)` instead of flat 1500);
> `regress_gap_k` implemented but dropped (adds nothing over β alone). MLS harness A/B
> (`--xgb-bag 5`, 4 folds): β=0.75 seed 42 clears the gate (0.6333, Δ+0.0014) but seed 7 does
> not confirm (0.6351, Δ+0.0005) — **MLS DROP**, champion config unchanged. European proxy
> walk-forward (big-5 FD 2017+, early-60d-of-season Brier, the only window where seed ELO
> matters per A7): monotone in β, β=0.75 beats flat by −0.008 pooled / **−0.023 on A7's
> high-gap slice** (0.21295 → 0.19385, n=646) — ~10× the MLS gate size. **KEEP for European
> production seeding**: `scripts/build_league_data.py`'s two `compute_elo` call sites now pass
> `club_prior_beta=0.75`; `model_card.config["Season regress"]` updated to reflect it. Rebuilt
> all 10 affected European payloads. Production effect: **Spurs preseason relegation odds
> 42.0% → 37.9%** — direction right, size modest (A7's causal link 2, the DC fit on the bad
> season, is untouched by this lever; A10's variance-widening is the remaining piece). Steps
> 2–4 (per-league rate sweep b-i/b-ii) deferred — the β target alone already cleared the gate
> on the primary evidence; rate tuning is lower-leverage and can revisit with C2's per-family
> European champions. Confirmed at second seed (MLS gate); suite green (468 passed, 2
> pre-existing browser-smoke + 1 missing-local-file failure, both unrelated).

> **VERDICT A2 (2026-07-03): GATE FAILED — DC forward path retained (the deep-dive headline
> closes with a validated negative).** Steps 1–5 done; 6–8 correctly NOT executed.
> Feature builder shipped (`scripts/eval/upcoming_features.py`, 4 tests — supports the real
> home_/away_ prefixes AND recomputes derived diff columns; B9 consumes it regardless).
> Backtest (2025 fold, 3 checkpoints, next-30d matches, production-mirrored DC comparator):
> pooled ensemble **0.6439** vs DC **0.6383** (Δ −0.0056, bootstrap CI [−0.0216, +0.0103]).
> Ensemble wins at +60d (0.6299 vs 0.6444) then loses +120/+180 — root cause:
> `predict_upcoming` never sees current-season rows (train<cal<current) while production DC
> re-fits on them; carried features go stale as the season accrues. Full table in
> `docs/feature-hunt-log.md`. Revisit path = rolling-cal `predict_upcoming` variant
> (a new experiment, not this task).

> **VERDICT B9 (2026-07-04): COMPLETE.** `build_team_inputs_full()` (both builders)
> emits every `feat_base` suffix family-grouped (ELO / xG for / xG against / form /
> goalkeeper / availability) via A2's `latest_team_features` carry-forward lookup;
> explicit `null` where a league/team lacks the signal (never hidden, never zero).
> Team profile gets a collapsible "Model inputs — full panel" + a Transfermarkt
> squad-value panel (MLS ships now; other leagues render the null state pending A9).
> **Bug found and fixed before commit**: `config/team_name_to_asa_id.yaml`'s
> `transfermarkt` map is keyed on ASA's 3-letter `team_abbreviation` ("ATL"), not the
> real `team_id` ("KAqBN0Vqbg") the column name implies — `build_squad_value_mls`'s
> membership check against `tids` never matched, so `squad_value` silently built as
> `None` for every MLS team despite real TM data existing on disk. Fixed by resolving
> through an `abbr2id` map built from `get_teams()`. Also fixed: att/def value-split
> displayed as "0.507%" instead of "50.7%" (the `_pct`-named fields are 0–1 fractions,
> confirmed against `eval_baseline.py`'s existing usage); and scraped-but-zero player
> market values rendering as a fake "€0.0m" — the 2026 raw TM snapshot has no
> per-player values yet (a real upstream scrape gap, `data/transfermarkt_squad_values_2026_raw.csv`
> is 100% zero), now shown as "—" like every other null in this panel. **Corrected a
> plan assumption**: the spec expected League Two (goals-only) to show the xG family
> as null — instead `xg_roll_*`/`xga_roll_*` populate via the existing goals-proxy
> fallback (`feature_builders.py`: `float(row["home_xg"]) if notna else float(hg)`);
> only `gk_z`/`avail_share` (genuinely MLS-only signals) are null for European
> leagues. Verified live: MLS (Inter Miami: €85.8m squad value, #2/30, 97th
> percentile) and League Two (goalkeeper/availability rows correctly null, xG rows
> populated from goals). No mobile overflow introduced. Suite green (484 passed, same
> 3 pre-existing unrelated failures). Rebuilt `mls.js` + `league-two.js`; remaining
> league payloads pick up `team_inputs_full` on their next scheduled rebuild (the
> frontend's absence-check already treats older payloads as a no-op fallback to the
> legacy abbreviated panel).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps from the 2026-06-29 unified deep-dive: route forward projections through the full validated ensemble (not raw DC), make conditional calibration measurable, and upgrade the webapp from "presents outputs" to "enables investigation" (uncertainty, why, trust).

**Architecture:** Two workstreams. Part A (model) adds a forward-feature builder so production uses `predict_upcoming`, plus conditional-reliability diagnostics in `model_report.py` that gate two structural experiments (time-varying HFA, xG-ELO). Part B (webapp) is additive rendering on data mostly already shipped or newly exported by Part A — no simulation-math changes.

**Tech Stack:** Existing stack only — Python 3.13 (`models/research_model.py`, `scripts/build_*.py`, pytest), vanilla-JS single-file webapp (`webapp/index.html`), static `webapp/data/*.js` payloads.

**Status of the 2026-06-29 deep-dive "Now" tier (verified in git log, do NOT redo):**
- ✅ DC forward temperature (2dbd5bc, 7701289) — the *cheap* half of §1.6 #1
- ✅ seasonCard outcome-set bug (2b6af09, 43c23d6)
- ✅ Matchup explorer (990294c) + top-3 scorelines (3ae30a3, a7e825e)
- ✅ logos.js contract exclusion (281c384); CI deploy + daily/weekly refresh
- ❌ Full-ensemble forward path (Task A2 — the headline item, still DC-only)
- ❌ Conditional reliability diagnostics (Task A1)
- ❌ `status` on continental/power payloads (Task B1 — ucl/power verified still missing it)

**Product goal (user decision 2026-07-03): betting edge.** The model stays market-blind
(CLAUDE.md constraint), but the UI leads with model-vs-market, edge filters, and CLV honesty;
the 8% edge threshold becomes a first-class UI concept. This promotes B5/B10 and makes
`data_pipeline/odds_log.py` coverage (openers + closers, more leagues) a priority — an edge
product is only as credible as its market-comparison data.

**Ordering:** A1 → A7 → B1 → B10 → A2 → A8 → B5 → B11 → B12 → B13 → A3 → B2 → B3 → B9 → B4 →
A4 → A11 → A5 → A6 → A9 → A12 → A10 → C1 → C2 → B6 (B7/B8 = follow-up plan). A11 directly
after A4 (they share the draw thesis: if HFA fixes the draw curve, A11's bar rises).
**Continental competitions (user decision 2026-07-03): projection-only this cycle** — excluded
from the edge board and ledger (no odds source until the Odds API spend); brackets stay as-is. A1 first because it is zero-risk and its
slices are the judging criteria for A4/A5/A6/A8 and the data source for B4. A7/A8 promoted
early (2026-07-03): the Spurs case study showed the preseason-prior problem is live and
user-visible on the current EPL payload. B10 early because time-series data only exists from
the day we start archiving it — every build without it is lost history.

**Compute venue (user decision 2026-07-03): local, sequential.** One eval run at a time on
this machine (16GB; the improve-model skill's crash-safety rule). The A8 multi-league sweep is
a few evenings of wall time — schedule accordingly; never fan out locally.

**Experiment-protocol note (Part A experiments):** A4/A5/A6/A8 follow `docs/experiment-protocol.md`, not TDD — the "test" is the harness A/B with the KEEP/DROP gate (Δ ≥ 0.001 aggregate Brier on the single bagged run `--xgb-bag 5 --seed 42`, confirmed at a second base seed, 2024-fold robustness). New for this plan: verdicts must ALSO report the A1 conditional slices (draw cal-err, favorite-decile reliability), because the whole point is that aggregate Brier alone mis-judged these levers before.

---

## Part A — Model

### Task A1: Conditional reliability slices in model_report.py

The champion report pools all class-probs into one marginal reliability number. Add slices that turn "too aggressive on some teams" into a measured quantity.

**Files:**
- Modify: `scripts/model_report.py` (extend `_slice_table`, ~line 171)
- Test: `tests/test_model_report_slices.py` (new)

- [x] **Step 1: Write the failing test**

```python
# tests/test_model_report_slices.py
import numpy as np
import pandas as pd
from scripts.model_report import _slice_table

def _fake_preds(n=400, seed=0):
    rng = np.random.default_rng(seed)
    p = rng.dirichlet([4, 2, 3], size=n)
    y = np.array([rng.choice(3, p=row) for row in p])
    dates = pd.date_range("2024-02-20", periods=n, freq="D")
    return pd.DataFrame({
        "prob_home": p[:, 0], "prob_draw": p[:, 1], "prob_away": p[:, 2],
        "label_result": y, "season": 2024, "date": dates,
        "home_team": "h", "away_team": "a",
    })

def test_favorite_decile_slice_present():
    out = _slice_table(_fake_preds())
    fav = out["by_favorite_prob"]
    assert len(fav) >= 3                      # deciles with enough support
    for k, m in fav.items():
        assert {"n", "brier", "fav_prob_mean", "fav_hit_rate"} <= set(m)

def test_season_phase_slice_present():
    out = _slice_table(_fake_preds())
    assert {"first_60d", "mid", "late"} <= set(out["by_season_phase"])

def test_draw_reliability_curve_present():
    out = _slice_table(_fake_preds())
    curve = out["draw_reliability"]           # list of {bin, n, p_mean, freq}
    assert all({"n", "p_mean", "freq"} <= set(b) for b in curve)
```

- [x] **Step 2: Run it to verify failure**

Run: `venv/bin/pytest tests/test_model_report_slices.py -v`
Expected: FAIL — `KeyError: 'by_favorite_prob'`

- [x] **Step 3: Implement the slices in `_slice_table`**

Append inside `_slice_table(preds)` before `return out` (reuse the existing `_by` helper for the first two; the reliability curve is direct):

```python
    P = preds[["prob_home", "prob_draw", "prob_away"]].values
    y = preds["label_result"].values.astype(int)

    # (i) favorite-probability decile — conditional calibration by confidence
    fav_p = P.max(axis=1)
    fav_cls = P.argmax(axis=1)
    dec = pd.cut(fav_p, bins=np.arange(0.3, 1.0001, 0.07), include_lowest=True)
    by_fav = {}
    for b, idx in pd.Series(range(len(preds))).groupby(dec, observed=True):
        ii = idx.values
        if len(ii) < 25:
            continue
        yoh = np.eye(3)[y[ii]]
        by_fav[str(b)] = {
            "n": int(len(ii)),
            "brier": round(float(np.mean(np.sum((P[ii] - yoh) ** 2, axis=1))), 4),
            "fav_prob_mean": round(float(fav_p[ii].mean()), 4),
            "fav_hit_rate": round(float((fav_cls[ii] == y[ii]).mean()), 4),
        }
    out["by_favorite_prob"] = by_fav

    # (ii) season phase — early-season staleness is a known suspect (§1.3d)
    doy = pd.to_datetime(preds["date"])
    start = doy.groupby(preds["season"]).transform("min")
    days_in = (doy - start).dt.days
    phase = pd.Series(np.select(
        [days_in <= 60, days_in <= 180], ["first_60d", "mid"], default="late"))
    _by(phase, "by_season_phase")

    # (iii) draw reliability curve — the worst class (max-decile err 0.108)
    curve = []
    for lo in np.arange(0.0, 0.5, 0.05):
        m = (P[:, 1] >= lo) & (P[:, 1] < lo + 0.05)
        if m.sum() < 25:
            continue
        curve.append({"bin": f"{lo:.2f}", "n": int(m.sum()),
                      "p_mean": round(float(P[m, 1].mean()), 4),
                      "freq": round(float((y[m] == 1).mean()), 4)})
    out["draw_reliability"] = curve
```

- [x] **Step 4: Run tests**

Run: `venv/bin/pytest tests/test_model_report_slices.py tests/ -x -q`
Expected: new tests PASS, full suite green.

- [x] **Step 5: Regenerate the champion report view and eyeball the slices**

Run: `venv/bin/python scripts/model_report.py --frame data/parity_frame.parquet`
Expected: report prints `by_favorite_prob`, `by_season_phase`, `draw_reliability`. Record the numbers in the verdict — they are the baseline for A4/A5/A6 and the data for B4.

- [x] **Step 6: Commit**

```bash
git add scripts/model_report.py tests/test_model_report_slices.py
git commit -m "feat(report): conditional reliability slices (favorite decile, season phase, draw curve)"
```

---

### Task A2: Full-ensemble forward path (the headline fix)

`predict_upcoming` (models/research_model.py:330) is production-ready but has zero callers: every forward number (upcoming cards, 30×30 pmatrix, season sim) is temperature-scaled DC only. The missing piece is an upcoming-feature matrix. Rolling features are team-level (xG/form windows, GK z, availability, ELO), so each team's *latest observed values* in the parity frame carry forward to any hypothetical fixture.

**Files:**
- Create: `scripts/eval/upcoming_features.py`
- Modify: `scripts/build_dashboard_data.py` (dc_probs fork, ~lines 214–290) — MLS first
- Modify: `scripts/build_league_data.py` (mirror fork, ~lines 520–576) — after MLS validates
- Test: `tests/test_upcoming_features.py` (new)

- [x] **Step 1: Write the failing test for the feature builder**

```python
# tests/test_upcoming_features.py
import pandas as pd
from scripts.eval.upcoming_features import latest_team_features, build_upcoming_row

FEAT = ["h_elo", "a_elo", "h_xg_form_5", "a_xg_form_5"]

def _frame():
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-03-01", "2026-03-08", "2026-03-15"]),
        "season": 2026,
        "home_team": ["A", "B", "A"], "away_team": ["B", "C", "C"],
        "home_goals": [1, 0, 2], "away_goals": [0, 0, 1],
        "h_elo": [1500.0, 1480.0, 1512.0], "a_elo": [1490.0, 1505.0, 1470.0],
        "h_xg_form_5": [1.1, 0.9, 1.3], "a_xg_form_5": [1.0, 1.2, 0.8],
    })

def test_latest_values_prefer_most_recent_match_and_side():
    tf = latest_team_features(_frame(), FEAT)
    # A last appeared 03-15 as HOME → take h_* values
    assert tf["A"]["elo"] == 1512.0 and tf["A"]["xg_form_5"] == 1.3
    # B last appeared 03-08 as HOME
    assert tf["B"]["elo"] == 1480.0
    # C last appeared 03-15 as AWAY → take a_* values
    assert tf["C"]["elo"] == 1470.0 and tf["C"]["xg_form_5"] == 0.8

def test_build_upcoming_row_maps_sides():
    tf = latest_team_features(_frame(), FEAT)
    row = build_upcoming_row("B", "C", tf, FEAT)
    assert row["h_elo"] == 1480.0 and row["a_elo"] == 1470.0

def test_unseen_team_returns_none_values():
    tf = latest_team_features(_frame(), FEAT)
    row = build_upcoming_row("B", "ZZZ", tf, FEAT)
    assert row["a_elo"] is None   # caller decides DC-fallback
```

- [x] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_upcoming_features.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 3: Implement `scripts/eval/upcoming_features.py`**

```python
"""Carry-forward feature matrix for unplayed fixtures.

Rolling features in the parity frame are team-level snapshots stamped onto each
match row as h_*/a_* pairs. For an unplayed fixture we take each team's values
from its most recent PLAYED row (home or away side, whichever is later) and
re-stamp them under the correct side prefix. Matchup-symmetric columns with no
h_/a_ prefix (e.g. referee rates) are not knowable pre-assignment → left None
(imputed to 0 by predict_upcoming's fillna, same as training-time missing).
"""
import pandas as pd


def _side_key(col: str) -> str | None:
    if col.startswith("h_"):
        return col[2:]
    if col.startswith("a_"):
        return col[2:]
    return None


def latest_team_features(frame: pd.DataFrame, feat_cols: list[str]) -> dict:
    """{team: {suffix: latest value}} from played rows, most recent date wins."""
    played = frame.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    out: dict[str, dict] = {}
    suffixes = sorted({s for c in feat_cols if (s := _side_key(c))})
    for _, r in played.iterrows():
        out[r["home_team"]] = {s: r.get(f"h_{s}") for s in suffixes}
        out[r["away_team"]] = {s: r.get(f"a_{s}") for s in suffixes}
    return out


def build_upcoming_row(home: str, away: str, team_feats: dict,
                       feat_cols: list[str]) -> dict:
    hf, af = team_feats.get(home), team_feats.get(away)
    row: dict = {"home_team": home, "away_team": away}
    for c in feat_cols:
        s = _side_key(c)
        if s is None:
            row[c] = None
        elif c.startswith("h_"):
            row[c] = None if hf is None else hf.get(s)
        else:
            row[c] = None if af is None else af.get(s)
    return row


def build_upcoming_features(frame: pd.DataFrame, pairs: list[tuple[str, str]],
                            feat_cols: list[str], season: int) -> pd.DataFrame:
    tf = latest_team_features(frame, feat_cols)
    rows = []
    for i, (h, a) in enumerate(pairs):
        r = build_upcoming_row(h, a, tf, feat_cols)
        r.update({"match_id": f"up_{i}", "season": season})
        rows.append(r)
    return pd.DataFrame(rows)
```

- [x] **Step 4: Run tests**

Run: `venv/bin/pytest tests/test_upcoming_features.py -v` → PASS.

- [x] **Step 5: MEASURE before wiring (deep-dive Part 3 item 1 — the gate for this task)**

Backtest the forward-ensemble vs forward-DC on known outcomes: for the 2025 MLS fold, at 3 checkpoints (after 60d / 120d / 180d of season), build carry-forward features for the *next 30 days* of then-future matches, score both paths against actuals. Write this as a throwaway script in the scratchpad (not the repo), reusing `walk_forward`-style fitting from `models/research_model.py`.

Expected decision rule: ensemble forward Brier < DC forward Brier by more than the σ≈0.001 noise. If it is NOT better (possible — carried-forward features are stale by construction), stop here, keep DC+temperature forward path, and record the negative result in `docs/feature-hunt-log.md`. Everything below is conditional on the gate passing.

- [ ] **Step 6: Wire the MLS builder**

In `scripts/build_dashboard_data.py`, after the existing DC fit (~line 216): build `up_feat = build_upcoming_features(df, pairs, feat, ts)` for (a) the UPCOMING fixture list and (b) all 30×30 team pairs; call `rm.predict_upcoming(df, up_feat, ts)` once; replace `dc_probs(h, a)` lookups for match cards and `PM[hi, ai]` with the ensemble probabilities (keep `dc_probs` as fallback for teams with no played rows, and keep `dc_lam_mu` for scorelines — λ/μ stay DC by design). Update `model_card.arch` to be accurate for the forward path.

- [ ] **Step 7: Verify end-to-end**

```bash
venv/bin/python scripts/build_dashboard_data.py
venv/bin/python scripts/validate_payloads.py
venv/bin/pytest tests/ -q
```
Expected: payload valid; upcoming-match top-2 season-odds concentration should *drop* vs the previous build (record before/after — MLS Shield top-2 was 82%). Spot-check 3 upcoming cards in the browser (`make build-dashboard-data`, open webapp).

- [ ] **Step 8: Commit, then mirror in `build_league_data.py` as a separate commit** (same pattern; European leagues have the additional wrinkle that promoted teams may have no frame rows → they hit the DC-fallback path, which is correct — the tier bridge already seeds them).

```bash
git add scripts/eval/upcoming_features.py tests/test_upcoming_features.py scripts/build_dashboard_data.py
git commit -m "feat(forward): route upcoming projections through the full ensemble (predict_upcoming)"
```

---

> **VERDICT A3 (2026-07-03): COMPLETE.** `scripts/eval/promoted_team_brier.py` gains
> `pooled_summary()` — match-count-weighted Brier across all 5 tier2→tier1 pairs, flagged
> against naive (2/3) independent of each pair's own flat-prior comparison. Wired into
> `scripts/model_report.py` as `promoted_team_brier` (best-effort, try/except, mirrors
> `_source_health_snapshot` — attached to every report as an independent diagnostic since MLS
> itself has no promotion) and into `scripts/promotion_gate.py` as a non-blocking advisory
> (self-test case 8: pooled Brier above naive → gate still PASSES, advisory string fires). 6 new
> tests (3 pooling/threshold unit tests + gate self-test case), suite green (480 passed, same 3
> pre-existing unrelated failures). Current real number: pooled **0.6304** vs naive 0.6667
> (n=3984 across 5 pairs) — comfortably clear, advisory does not fire today; this is
> infrastructure for catching future regressions, not evidence of a current problem. Runtime
> cost ~12s (live football-data.co.uk history processing per pair) — acceptable overhead on a
> report-generation step that already takes much longer end-to-end; no new flag added to skip it.

### Task A3: Promoted/relegated calibration gate (advisory)

`scripts/eval/promoted_team_brier.py` exists but isn't wired as a check. Make it an advisory line in the promotion gate + champion report, like `feature_completeness`.

**Files:**
- Modify: `scripts/model_report.py` (add `promoted_team_brier` block to report payload)
- Modify: `scripts/promotion_gate.py` (advisory, non-blocking check: flag if promoted-team-match Brier > naive 0.6667)
- Test: extend `tests/test_promotion_gate.py` (or the gate's self-test) with one case: promoted-cohort Brier above naive → gate passes but emits the advisory warning string.

Steps follow the same pattern as Task A1 (failing test → implement → suite green → commit). Keep it advisory: the cohort is small; a blocking gate would be noise-driven.

---

> **VERDICT A4 (2026-07-04): DROP.** `fit_dc_dynamic_ha` (season-level HFA shrunk toward the
> pooled estimate, atk/dfd/rho fixed, `k` tuned per fold over {50, 100, 200} on cal-fold DC
> Brier) — `scripts/eval/dixon_coles.py` + `--hfa-dynamic` flag. MLS harness A/B
> (`--xgb-bag 5 --seed 42 --test-seasons 2022 2023 2024 2025`, ens_stacked avg): champion
> 0.632977 vs hfa-dynamic 0.635075 (**Δ −0.0021**, aggregate); 2024 fold (the primary evidence
> for this lever) champion 0.634913 vs hfa-dynamic 0.6397 (**Δ −0.0048**, worse than the
> aggregate) — both of the task's own judging criteria fail decisively, past the noise floor, in
> the wrong direction. Per-fold `k` bounced between grid extremes (50/200/200/50) rather than
> converging, consistent with fitting cal-fold noise rather than a real seasonal HFA drift. The
> A1 `draw_reliability` re-check was skipped: it exists to catch a hidden calibration win behind
> a small aggregate loss, which cannot apply to a result that already loses on both criteria. No
> second-seed confirmation (reserved for gate-bound KEEP claims, not DROPs). Champion config
> unchanged; code kept as an opt-in, off-by-default flag (A8/A2 precedent for documented
> negative results). Full numbers in `docs/feature-hunt-log.md`.

### Task A4: Experiment — time-varying home-field advantage

Static DC `home_adv` can't track the documented 2024/25 home-win collapse, and mass mis-priced out of "home win" lands on "draw" (draw cal-err 0.108). Both reviews converged here.

**Files:**
- Modify: `scripts/eval_baseline.py` (new flag `--hfa-dynamic`, DC-fit section only)

- [x] **Step 1:** Implement `--hfa-dynamic`: replace the single fitted `ha` with a season-level HFA shrunk toward the pooled estimate — `ha_s = (n_s * ha_hat_s + k * ha_pool) / (n_s + k)`, k tuned on the cal fold over {50, 100, 200}. Forward prediction uses the latest season's `ha_s`.
- [x] **Step 2:** A/B: `venv/bin/python scripts/eval_baseline.py --xgb-bag 5 --seed 42 --hfa-dynamic` vs champion baseline (no flag), 4 folds.
- [x] **Step 3:** Judge on (a) the standard KEEP/DROP Brier gate AND (b) A1's `draw_reliability` + 2024-fold Brier specifically — this lever exists for the regime shift, so the 2024 fold is the primary evidence.
- [x] **Step 4:** Confirm at second base seed if gate-bound; append verdict to `docs/feature-hunt-log.md` and this plan; blockquote in `docs/PLAN.md`.

### Task A5: Experiment — xG-blended ELO update

ELO banks finishing luck (`s_h` from goals with MoV multiplier, scripts/eval/elo.py:64-71); it is a top feature and seeds the sim. Untried lever — the campaign never touched the ELO update rule.

**Files:**
- Modify: `scripts/eval/elo.py` + `scripts/eval_baseline.py` (flag `--elo-xg-blend LAMBDA`)

- [x] **Step 1:** Implement: effective score `s_eff = (1-λ)*s_result + λ*s_xg` where `s_xg` is the result implied by the match xG totals (win/draw/loss on xG difference with a ±0.25 dead-zone for draws). λ grid {0.25, 0.5, 0.75} on the cal fold. Matches without xG (older/second-tier rows) fall back to λ=0.
- [x] **Step 2–4:** Same A/B, gate, and dual-judging (aggregate + A1 slices, esp. `by_season_phase.first_60d` — where banked luck from last season should hurt most) as A4. Verdict + logs.

### Task A6: Re-judge `pythag_luck` on conditional calibration

Dropped at Δ=+0.0008 on the aggregate bar, directionally right 2 of 3 seasons. With A1 in place, rerun `--ab-only "+PythagLuck"` (existing section in `eval_baseline.py`) and judge on favorite-decile calibration + per-team Brier spread, not just aggregate Brier. One eval run + verdict; no new code. If it narrows the 0.52–0.70 per-team spread without regressing aggregate beyond noise, promote via the standard gate flow.

---

### The "fallen giant" cluster (A7–A10) — added 2026-07-03

**Case study that motivates it (verified in the live 2026-27 preseason EPL payload):** Tottenham
seed at ELO **1442** → projected rank 15.9 → **42.0% relegation** — 2nd-highest in the league,
above three promoted sides. Their ELO trajectory bottomed at 1396 (2026-04-18) and finished
~1436. The causal chain, each link verified in code:

1. `compute_elo` regresses every team 40% toward a **flat 1500** at the season boundary
   ([scripts/eval/elo.py:59](../../../scripts/eval/elo.py)) — a fallen giant and a perennial
   straggler get the same target. Spurs: ~1436 → ~1462-lands-at-1442, still bottom-quartile.
2. DC attack/defence fit on match history with a 120-day half-life — dominated by the bad season.
3. **Zero forward-looking inputs exist for European teams**: `data/transfermarkt_squad_values_*.csv`
   is MLS-only (30 rows, `asa_team_id` keys). Summer spending, returning stars, and coaching
   changes are invisible.
4. The 42% is a **point estimate** — no variance widening when identity signals conflict.

The model may be *directionally* right that risk is elevated; the question is conditional
calibration, so A7 measures before A8/A10 fix.

### Task A7: "Fallen giant" cohort study + club-prior-gap reliability slice

Zero model risk; extends A1's slice framework. Defines the signal the later tasks consume:
`club_prior_gap_t = mean(end-of-season ELO, prior 3 seasons) − seed ELO_t`.

**Files:**
- Create: `scripts/eval/club_prior.py` (`club_prior_gap(elo_history) -> dict[team, float]`; pure function over ELO series we already compute)
- Modify: `scripts/model_report.py` — add `by_club_prior_gap` slice (terciles: high-gap "fallen", neutral, negative-gap "overachiever") reusing A1's `_by` helper
- Test: `tests/test_club_prior.py`

- [x] **Step 1:** Failing test: a synthetic ELO history where team X averaged 1600 over 3 seasons then seeds at 1440 → `club_prior_gap == 160`; a team with <2 prior seasons → gap 0 (promoted teams stay with the tier bridge, not this mechanism).
- [x] **Step 2:** Implement; suite green; commit.
- [x] **Step 3 (the cohort study — scratchpad script, findings into the verdict):** across all leagues/seasons in the frame (2017+), collect team-seasons in the top gap decile; measure (a) their actual next-season finish/relegation rate vs the model's preseason odds, (b) walk-forward Brier on their matches vs the cohort-neutral baseline. This answers empirically whether 42% for Spurs-shaped teams is miscalibration or reality — the number A8's gate is judged against.

### Task A8: Experiment — variable season-to-season ELO regression (target AND rate)

**(Scope widened 2026-07-03 by user directive.)** Two orthogonal knobs on the season-boundary
regression, tested separately then jointly:

- **(a) Club-prior target** (data-free; uses only ELO history): regress toward
  `target_t = (1-β)·1500 + β·mean(end-of-season ELO, prior 3 seasons)` instead of flat 1500;
  teams with <2 prior seasons fall back to 1500 (promoted teams keep the tier bridge).
- **(b) Variable rate** — the 40% is itself a single global constant, promoted on MLS folds
  only. Test: (i) **per-league** regress fitted on each league's own history (MLS parity churn
  plausibly needs MORE regression than Serie A's stable hierarchy — one constant can't serve
  both); (ii) **per-team** rate modulated by identity stability,
  `regress_i = clip(base + k·|club_prior_gap_i|/200, 0.2, 0.6)` — teams whose current rating
  disagrees with their own history regress harder toward their prior.

**Files:**
- Modify: `scripts/eval/elo.py` (`compute_elo` gains `club_prior_beta=0.0`, `regress_map=None` (per-league override), `regress_gap_k=0.0`)
- Modify: `scripts/eval_baseline.py` (flags `--elo-club-prior-beta` grid {0.25, 0.5, 0.75}; `--elo-regress` grid {0.25, 0.40, 0.55}; `--elo-regress-gap-k`)
- Modify: `scripts/eval/league_features.py` / European fold harness for the per-league sweep (European folds judge the per-league rates; MLS folds guard the champion)

- [x] **Step 1:** Implement flags; A/B (a) alone per protocol (`--xgb-bag 5 --seed 42`, 4 folds) vs champion.
- [x] **Step 2 (partial):** (a) swept and gated on both MLS and Europe. (b) `regress_gap_k` implemented and tested — dropped, no gain over β alone. Per-league rate sweep (b-i/b-ii) deferred (see verdict).
- [x] **Step 3:** Judged on standard aggregate gate (MLS: DROP) + A7's `by_club_prior_gap` high-gap slice (Europe: KEEP, primary evidence).
- [x] **Step 4:** Ported β=0.75 to production seeding in `build_league_data.py` (both `compute_elo` call sites); rebuilt affected European payloads; Spurs before/after recorded in verdict. Confirmed at second seed (MLS gate); doc updates: this file + `docs/PLAN.md` (`docs/CURRENT_STATE.md` — European seeding now diverges from the MLS champion config; noted inline, full per-family champion docs deferred to C2).

### Task A9: Data — Transfermarkt squad values for ALL covered leagues

**(Scope widened 2026-07-03 by user directive: not just big-5 — every league and team the
dashboard covers.)** Extends the MLS-only TM import to: EPL, Championship, League One, League
Two, La Liga, Segunda, Serie A, Serie B, Bundesliga, 2.Bundesliga, Ligue 1, Ligue 2, Liga MX,
Canadian PL (TM codes GB1/GB2/GB3/GB4, ES1/ES2, IT1/IT2, L1/L2, FR1/FR2, MEX1, KAN1). Where TM
coverage is thin (lower English tiers, CanPL), rows are imported with whatever players TM has
and the payload marks the value as low-confidence rather than dropping the team. Import
**player-level rows** (name, position, age, value), not just team aggregates — B9's squad-value
panel needs the top-players table and new-signing flags (the MLS import already works this way). This is the
*only* source in reach that quantifies "spending massively this summer" and "stars returning"
(injured players still count in squad value — TM value says Champions-League-quality squad even
while results said relegation). Also unblocks the deep-dive's roster-continuity regression (old
item 6) and dated-snapshot roadmap (old item 8) for Europe.

**Files:**
- Modify: `scripts/import_transfermarkt.py` — league-parameterized fetch (TM league codes GB1, L1, ES1, IT1, FR1), output keyed on the FD/ESPN-normalized names used by `build_league_data.py` (reuse the alias machinery from the logo map), `observed_at`-stamped per the existing validation gates
- Create: `data/transfermarkt_squad_values_eur_<season>.csv`
- Test: mapping coverage test — every current EPL payload team resolves to a TM row

**Phasing (user decision 2026-07-03 — annual now, weekly later):**
- **Phase 1 (this plan):** one annual preseason snapshot per league per season — enough for
  A8/A10 priors and the Spurs fix.
- **Phase 2 (background, starts as soon as Phase 1's fetcher works):** a weekly GitHub Actions
  cron re-running the same fetcher with `observed_at` stamping into
  `data/transfermarkt_snapshots/` — dated data accrues passively so the roster-timing
  experiments (the ones that failed on season-static data) become testable in a few months.
  No experiment consumes it in this plan; accrual is the deliverable.

- [ ] Steps: fetch one league (EPL) → mapping test green → extend to all covered leagues → commit → add the weekly cron workflow. **Rights check first** per `codex suggestions.md` (TM scrape terms) before committing scraped data.

### Task A10: Experiment — squad-value-informed prior + preseason variance widening

Two consumers of A9, gated separately:
- **(a) Value-informed regression target:** extend A8's target to
  `target = (1-β)·1500 + β₁·club_elo_mean + β₂·value_implied_elo` where `value_implied_elo` is a
  per-league linear map of log squad value → ELO fit on history. A/B per protocol.
- **(b) Variance widening:** in the preseason sim only, scale DC parameter noise per team by
  `1 + γ·|club_prior_gap|/200` (γ tuned so a Spurs-gap team's finish distribution widens
  visibly; capped at 1.5×). Judged on A7's cohort calibration, not aggregate Brier (preseason
  odds have no per-match Brier). Renders in the UI via B2's uncertainty machinery.

Coach-change and individual injury-return signals were considered and **deliberately excluded**:
no structured data source in reach, weak effect sizes in the literature, and squad value already
proxies the injury-return component. Revisit only if A9's dated snapshots mature.

### Task A11: Experiment — draw-aware structure (dedicated track, user decision 2026-07-03)

The worst class: draw named modal in 12 of 2,072 matches (draws occur ~25%), decile cal-err
0.108 — and draws are where 1X2 markets misprice most, so this is directly edge-relevant.
Two candidates, tested separately in the harness:
- **(a) Two-stage head:** `P(draw)` binary model × win-direction model conditional on
  non-draw, recombined (`--draw-two-stage`). The failed per-class-vector calibration
  (−0.0135 on 2024) is NOT this — that rescaled probs post-hoc; this restructures the estimator.
- **(b) DC rho re-fit:** the Dixon-Coles low-score correction `rho` directly governs draw mass —
  sweep fitting it per-season vs pooled, and check it survives the temperature pass
  (`--dc-rho-per-season`).

Judged on (i) A1's `draw_reliability` curve — primary, (ii) the aggregate gate — must not
regress beyond noise, (iii) draw-side edge quality in the market backtest
(`roi_by_edge_bucket` filtered to draw bets). Until a KEEP lands here, **B5/B12 suppress
draw-side Kelly recommendations** (show the probs, no unit sizing on draws) — don't recommend
bets from the model's known-worst class.

### Task A12: Data — FBref/Opta match xG for goals-only leagues (user decision 2026-07-03)

FBref publishes Opta xG for many leagues Understat lacks (Championship + lower English tiers,
Eredivisie, Primeira, Scotland, Belgium, Süper Lig, Liga MX). New `data_pipeline/fbref_xg.py`
match-xG adapter (the worldfootballR referee path is precedent; respect FBref's scrape-rate
limits — one league-season per request window, cached like `asa_cache`). Wired as an optional
xG source in `build_league_data.py` feature construction: goals-only leagues gain the xG
window features + become eligible for A5's xG-ELO. Gate per league family (see governance):
xG features must beat that family's goals-only baseline on its own walk-forward before
shipping. Source-health entry + rights check (FBref ToS) required, per the codex review.

---

## Part B — Webapp

### Task B1: `status` on continental + power payloads

`webapp/data/ucl.js` and `power.js` (and the other continental payloads) verified missing top-level `status`; the validator can't enforce what builders don't emit.

**Files:**
- Modify: `scripts/build_continental_data.py` (emit `status: "knockout_live" | "completed"` — the taxonomy already defines these; verify whether the code path was added 2026-06-27 but the payloads are stale → if so this is just a rebuild)
- Modify: `scripts/fetch_league_teams.py` / power builder (power gets `status: "live"`)
- Modify: `scripts/validate_payloads.py` — make top-level `status` REQUIRED for every payload except `logos.js`
- Test: extend the payload-contract test to assert `status` present on all league keys

- [x] Step 1: check builders first — `grep -n '"status"' scripts/build_continental_data.py`. If present, rebuild payloads; if absent, add the field.
- [x] Step 2: tighten `validate_payloads.py`, run it, rebuild whatever fails, commit.

> **VERDICT B2 (2026-07-03): PARTIAL — standings p10–p90 tooltip shipped; match-card bag-spread
> chip BLOCKED on A2.** Standings odds cells (`tableLadder()`'s `hc()`) now carry a
> `title="Projected finish: p10–p90 (median …)"` tooltip, reusing the *existing* `finishVals`/
> `ensureFinish()` base sim that already backs the "Projected finish" plot panel — no new sim
> call, no duplicate logic. Verified live (EPL preseason): Arsenal 1–3, mid-table teams widen to
> 3–13, correctly tracking table position. **The match-card `±x.x` bag-spread chip could not be
> built as scoped**: it requires `max−min home-win prob across the 5 bag members` for upcoming
> matches, but A2's verdict (same day) confirms the production forward path for upcoming/unplayed
> matches is DC+temperature ONLY — `build_dashboard_data.py` line ~466 literally comments "Game
> cards: played (ensemble) + upcoming (DC)". There is no bagged XGB prediction for any upcoming
> match in production today, so a "bag spread" chip would have to be fabricated from something
> that isn't actually 5-seed disagreement — declined rather than ship a fake uncertainty number.
> Revisit if/when a rolling-cal `predict_upcoming` variant (A2's own suggested revisit path)
> lands. **Bug caught before commit**: my first draft duplicated `finishVals`/`ensureFinish()`
> with a second `baseFin`/lazy-`runSimTable()` call — found by reading the "Projected finish"
> panel's existing code before assuming none existed; removed in favor of reuse.

### Task B2: Uncertainty cues on odds

The 5-seed bag and 20k-sim distributions exist but render as point estimates.

**Files:**
- Modify: `scripts/build_dashboard_data.py` + `scripts/build_league_data.py` — for upcoming matches emit `spread`: max−min home-win prob across the 5 bag members (one extra line where `bag_proba` averages; A2 makes this available on the forward path)
- Modify: `webapp/index.html` — match cards get a small `±x.x` chip next to the headline prob when `spread` present; standings odds cells get a `title` tooltip with p10–p90 finishing positions (already computed in `runSimTable`'s histogram, ~line 901 — currently discarded beyond p10/p50/p90)

Verification: rebuild MLS + EPL, open both in browser, zero console errors, chips render only where data exists (older payloads without `spread` must not break — guard with `g.spread!=null`).

> **VERDICT B3 (2026-07-03): COMPLETE.** `whyStrip(home,away)` — pure render over
> `D.team_inputs`, no model math — computes 4 home-minus-away deltas (ELO, xG form, GK z,
> availability pp), color-coded by sign (`var(--qualify)` favors home, `#e25f4f` favors away),
> hides any row where either team lacks that input. Match rows (`renderGames()`'s `.grow`) are
> now clickable to expand a `.gr-why` strip (CSS-toggled via `.grow.open`, mirrors B12's
> `.eb-row` pattern — no framework, no re-render). Verified live: MLS (full inputs) shows all 4
> rows, e.g. `ELO −36 · xG form +0.4 · GK z −1.3 · Availability ±0pp`; Championship (no
> `gk_z`/`avail` keys in that league's `team_inputs`) correctly shows only `ELO`/`xG form`, no
> `undefined`. Mobile: clean, no overflow. No new tests (pure presentational JS matching the
> existing untested render-function convention in this file — `cbar`/`edgePick`/`bestBet` etc.
> aren't unit tested either); verification was live in-browser per the task's own instruction.

### Task B3: "Why this pick" attribution on match cards

`D.team_inputs` (elo, xg_for, xg_against, form, gk_z, avail) is already client-side (used on team profile ~line 1404).

**Files:**
- Modify: `webapp/index.html` — expanding a match card shows a 4-row delta strip: `ELO +160 · xG form +0.4 · GK z −0.9 · availability −1`. Pure render function `whyStrip(home, away)` computing input deltas; no model math. Color by sign with the existing accent palette; hide rows where either team lacks the input.

Verification: browser check MLS (full inputs) and a goals-only league like Championship (sparse inputs → rows hidden, no `undefined`).

> **VERDICT B4 (2026-07-04): COMPLETE.** Health tab now renders A1's reliability
> scatter (favorite-probability deciles + draw curve vs observed frequency, dashed
> diagonal), a Brier-by-season-phase table, a Brier-by-favorite-decile table, and A3's
> pooled promoted-team advisory banner. Numbers match A1's original verdict exactly
> (first_60d 0.6314 n=497 · mid 0.6379 n=971 · late 0.6264 n=604) and A3's (pooled
> 0.6304 vs naive 0.6667, n=3984). **Data-source problem found and solved**: neither
> existing report file had both A1's slices and A3's `promoted_team_brier` — those
> fields were added to `model_report.py` at different points in the campaign, after
> the reports that would need them were already generated. Rather than touch the
> pinned `experiments/challenger-bag5.report.json` (CLAUDE.md names it as the
> promotion-time artifact), regenerated the identical champion config into a new
> `experiments/b4-trust-baseline.report.json` (avg_brier 0.6330, cal_err 0.0182 —
> reproduced at parity) and added a documented gitignore exception (matching the
> existing `league_offsets.json`/`tier2_offsets.json` precedent) so it ships with the
> repo instead of silently regenerating empty on every fresh checkout. European
> leagues get an explicit `trust: None` and render the honest "not available" empty
> state — no per-league-family champion report exists yet (C2). **Bug found and
> fixed before commit**: `const _PHASE_LABEL` was declared textually after the page's
> own eager `renderHealth()` pre-render call — a TDZ violation that threw
> synchronously and left literally every function in the 84KB main script block
> undefined (not just the new B4 ones), since the throw happened before the script's
> later statements ran. `typeof renderHealth` etc. all read "undefined" in the
> console until traced to this one line; moved the const earlier. Verified live: MLS
> shows the full panel, EPL shows the empty state, no mobile overflow. Suite green
> (484 passed, same 3 pre-existing unrelated failures).

### Task B4: "Model Trust" upgrade of the Health tab

Render A1's conditional slices publicly: reliability curve, Brier by favorite decile / season phase, draw curve, promoted-team advisory (A3).

**Files:**
- Modify: `scripts/build_dashboard_data.py` + `build_league_data.py` — attach a `trust` block to payloads, copied from the champion report's new slice fields (same pattern as `model_card`; empty-safe if report unreadable)
- Modify: `webapp/index.html` `renderHealth()` (~line 1213) — add a reliability chart (predicted vs observed per bin, diagonal reference) and two small slice tables; reuse the existing panel/heat-cell components

Depends on: A1 (and A3 for the promoted line). Verification: browser, both a `live` and a `preseason` league (preseason must show the no-rows empty state, not NaN).

### Task B5: Model-vs-market view (PROMOTED — the betting-edge centerpiece)

`scripts/market_eval.py` already computes `brier_vs_market` and `roi_by_edge_bucket`; European payloads carry historical market odds. With the product goal set to betting edge (2026-07-03), this stops being a diagnostic footnote: upcoming match cards show **(a) model prob vs market prob side-by-side, (b) edge %, and (c) a Kelly-criterion unit size** (user decision 2026-07-03) — `kelly = (p·(b+1) − 1)/b` per outcome on de-vigged decimal odds, **quarter-Kelly** (user decision 2026-07-03: defensive sizing while the model trails the closing line), displayed in units, shown only when edge ≥ the 8% threshold. The honest ROI history is the trust anchor (EPL backtest: −4.6% ROI at 8% — show it; credibility comes from not hiding it).

**Odds API spend (user decision 2026-07-03): deferred.** Everything ships against data we
already have — football-data historical closing odds for Europe, the existing free-tier MLS
odds log. Revisit trigger: B5+B10 live in the UI and the Part C leagues built; then a paid key
buys forward European openers/closers and real CLV.

**Files:**
- Modify: `scripts/build_league_data.py` — for leagues with market history, emit per-match `{model_p, market_p}` pairs (played games) + the ROI-by-edge-bucket table into a `market_view` block
- Modify: `webapp/index.html` — Matches tab gains a "vs market" panel: scatter of model home-prob vs market home-prob (off-diagonal = disagreement, dot color = outcome) + the ROI bucket bar. Frame honestly: trailing Pinnacle ~2% is strong for a market-blind model.

> **VERDICT B6 (2026-07-04): COMPLETE.** Four new `#resultFilter` buttons — Model
> miss, High-conf miss, Biggest edge, High leverage — all computed client-side from
> `D.games`, no new payload fields. Model miss / high-conf miss are plain predicates
> (played matches only, ≥60% favorite that lost for the latter). Biggest edge and
> high leverage are ranked top-20 views (not boolean predicates) — sorted by
> `edgeMag()`/`leverageScore()` and sliced, since "top N by magnitude" doesn't fit the
> existing chronological day-grouped render loop as a filter predicate. Leverage
> approximates stakes as `(1 − |pH−pA|) × 1/(1+|rank gap|)` — a toss-up between
> table-adjacent teams — per the plan's own scoping (a full playoff/title-swing
> simulation was explicitly out of scope). Verified live: MLS (edge=0 — correctly
> matches B10's finding that MLS market odds have never been logged, not a bug;
> leverage=20); La Liga (edge=20, real non-null `mkt_home` data, spot-checked sort
> order 0.269→0.194 descending); leverage=0 on leagues with zero upcoming fixtures
> (season concluded) is the honest empty state, not a bug. Suite green (484 passed,
> same 3 pre-existing unrelated failures), no mobile overflow.

### Task B6: Richer match filters

**Files:**
- Modify: `webapp/index.html` `#resultFilter` handling (~line 1281) + `renderGames()`

Add filters (all computable client-side from `D.games`): **model miss** (modal class ≠ result), **high-confidence miss** (fav ≥ 60% and missed), **biggest edge** (|model−market| where market exists, top 20), **high leverage** (upcoming games with max playoff/title odds swing — approximate via pmatrix win-prob closeness × opponent proximity in table). Keep the existing all/upcoming/played/hit set.

### Task B9: Full model-input panel on the team profile (added 2026-07-03, user directive)

The team profile currently surfaces only the abbreviated `team_inputs` (elo, xg_for,
xg_against, form, gk_z, avail — [index.html:1404](../../../webapp/index.html)). Requirement:
show **every** model input for the team, and where a variable isn't available for that
league/team, render it explicitly as `null` — absence is information (it tells the user which
features the model actually had for this league).

**Files:**
- Modify: `scripts/build_dashboard_data.py` + `scripts/build_league_data.py` — emit `team_inputs_full`: the team's complete latest feature snapshot. **Reuse A2's `latest_team_features(frame, feat_base)`** — the carry-forward builder already computes exactly this dict; missing/never-populated features emit as JSON `null` (ensure `allow_nan=False` holds — NaN → None before dump). Group keys by feature family for display (elo / xg windows / form windows / gk / availability / referee / squad value once A9 lands).
- Modify: `webapp/index.html` team profile — new collapsible "Model inputs" panel: one row per input, family-grouped, monospace values, `null` rendered as a muted `—` with a "not available for this league" tooltip (NOT hidden, NOT zero). Falls back to the legacy `team_inputs` when `team_inputs_full` absent (older payloads must not break).
- Test: payload contract — `team_inputs_full` values are numbers or null, never NaN strings; browser smoke: goals-only league (League Two) shows the xG family as null rows, MLS shows them populated.

**Transfer-market value section (user directive 2026-07-03).** Below the model-input rows, a
dedicated squad-value panel per team (data from A9; MLS renders today from the existing csvs):
- **Headline:** total squad value, league rank + percentile bar, value-weighted age vs league.
- **Composition:** ATT/DEF/GK value split (the `att_value_pct`/`def_value_pct`/`tilt` fields
  the import already computes), value-concentration (`dp_value_share` for MLS; top-3-player
  share elsewhere), squad size.
- **Player table:** top ~10 players by TM value with position and age — requires A9 to import
  **player-level** rows for all leagues, not just team aggregates (the MLS import already has
  player-level raw CSVs; make that the norm). New signings this season flagged.
- **Trend (unlocks with A9 Phase 2):** value sparkline across weekly snapshots + summer net
  spend once ≥2 dated snapshots exist; hidden until then.
- Leagues without TM rows render the panel's null state (consistent with the input rows above).

Dependency note: shares `latest_team_features` with A2 — build A2's Step 3 module first even
if the A2 ensemble gate later fails; the module stands alone and B9 consumes it. The TM panel
additionally depends on A9 Phase 1 (except MLS, which can ship immediately).

> **VERDICT B12 (2026-07-03): COMPLETE.** `scripts/build_edge_board.py` aggregates every
> upcoming match (next 48h, day-granularity — no kickoff time-of-day exists in any payload,
> documented rather than faked) across all `status:"live"` non-knockout payloads into
> `webapp/data/edge-board.js`; rows with a market line and ≥8% edge are separated from
> priced-no-edge and no-line rows, sorted by edge desc; empty state falls back to a
> `next_kickoffs` list (verified live — currently ALL leagues are edge-empty since no payload
> anywhere carries forward `mkt_home` yet, matching B10's finding that the odds log has never
> fired; the empty state is real, not hypothetical). Reuses `bet_ledger.py`'s
> `_quarter_kelly_units` and `scripts/payload_utils.write_js_payload` (no third Kelly
> implementation). 7 new tests (edge/threshold/draw-suppression/window/knockout-exclusion/
> sort/next-kickoffs), suite green (475 passed, same 3 pre-existing failures unrelated to
> this change). Webapp: no-`?league=` is now the landing route (`?league=X` deep links
> unchanged); new pinned "Today's Edge" sidebar entry; ledger strip (B11) reused verbatim.
> **Bug found and fixed along the way:** `ledgerStripHTML`/`BET_DISCLAIMER` were declared
> *inside* the per-league render branch that the edge board deliberately skips — a block-scoped
> `function` there only gets hoisted into the callable outer binding if that block executes
> (Annex B semantics), so calling them from the edge-board's separate script tag silently threw
> `ReferenceError`. Moved both to shared top-level scope (visible in webapp/index.html around
> `american()`) so both call sites work; regression-checked MLS/EPL/Championship/Power routes
> in-browser after the fix, zero console errors. **Scoped down from the full B12 spec**: inline
> row expansion currently shows only scorelines (already-available data); B2's bag-spread and
> B3's why-attribution are NOT wired into `.eb-expand` yet since those tasks haven't shipped —
> `ebRow()` has a comment marking where they extend it. CI: `build_edge_board.py` added to both
> `refresh-daily.yml` (finalize job, after `bet_ledger.py`) and `refresh-leagues.yml`.
> `edge-board.js` excluded from the strict LEAGUE_DATA/POWER_DATA payload contract (mirrors
> `ledger.js`'s existing treatment — a cross-league aggregate, not a per-league payload).
> League badges link to `?league=<id>` (stops click propagation so it doesn't also toggle row
> expansion). Not built this pass: a ledger P/L sparkline on the strip (text summary only) and
> a JS↔Python Kelly parity test (skipped because the edge board doesn't run JS Kelly math at
> all — Python precomputes `bet.units`/`bet.edge_pct` server-side; the existing JS
> `kellyUnits`/`bestBet` remain used only by the per-league match list, unchanged by this task).

### Task B12: "Today's edge board" — the new landing view (user decision 2026-07-03)

The site's front door becomes a cross-league edge board instead of a single league dashboard.

**Files:**
- Create: `scripts/build_edge_board.py` — after all league builds, aggregate every upcoming
  match in the next 48h across all `live` payloads into `webapp/data/edge-board.js`: league,
  match, kickoff (UTC + local render), model probs, de-vigged market probs (where available),
  edge %, quarter-Kelly units, sorted by edge desc; matches without market odds listed below a
  divider ("no line yet") rather than hidden. Runs last in the CI build chain.
- Modify: `webapp/index.html` — no `?league=` param → render the edge board as home (replacing
  the current default-league behavior); `?league=X` deep links unchanged; each row links to its
  league's match view. ≥8% rows highlighted with the accent-per-role palette; the disclaimer
  (see Success criteria) lives here and on B5's market view.
- Validate: edge board regenerates even when zero edges qualify (empty state: "no qualifying
  edges today · next kickoffs: …").

**Interaction & presentation decisions (user, 2026-07-03):**
- **Aggressive staleness guards.** Build timestamp on every view; each edge row shows
  "priced Xh ago"; if kickoff is <2h away OR the build is >24h old, the edge/Kelly cells grey
  out with a "reprice before betting" warning. Errs toward costing bets, never money. (The
  payload carries `built_at` ISO timestamps; the guard is client-side against `Date.now()`.)
- **Rows expand inline**: why-attribution (B3), scorelines, bag-spread (B2) render in place —
  the full bet-evaluation picture without leaving the board; league deep link secondary.
- **Ledger strip on the board** (B11's summary block): running units P/L, CLV mean, hit rate,
  n bets, sparkline at the top of the landing view — the track record confronts every visitor
  before every bet.
- **Dark only.** The quant-terminal identity stays single-theme; no light-mode audit.

Depends on: B5's edge/Kelly math (share one JS helper — devig + kelly live in ONE place,
mirroring `data_pipeline/market.py` semantics; add a JS↔Python parity test like the sim's).

> **VERDICT B13 (2026-07-03): COMPLETE.** `scripts/fetch_league_teams.py`'s `REGISTRY` gains a
> `group` field (Americas/England/Spain/Italy/Germany/France/Cups — "Other Europe" reserved for
> C1); sidebar groups by it (plan order) instead of the coarser confederation, collapsible per
> group with a chevron, state persisted in `localStorage`. Star-to-pin favorites section renders
> above the groups, also `localStorage`-persisted. Mobile drawer needed zero extra work — same
> DOM/JS, existing responsive CSS handles it (verified: favorites + a collapsed group both
> carried over correctly into the mobile drawer). **Found and fixed a real drift bug along the
> way**: `REGISTRY` was missing `ligue-2` and `segunda` — both are live leagues with real
> payloads and were already present in the committed `webapp/leagues.js`, but not in the Python
> source that generates it. Running `fetch_league_teams.py` (as this task required, to add the
> `group` field) would have silently dropped both from the sidebar on the next regen. Added
> both entries with their real ESPN codes; new `tests/test_fetch_league_teams.py` guards this
> class of bug going forward (asserts every on-disk payload has a `REGISTRY` entry). Regenerated
> `webapp/leagues.js` (18 → 20 leagues). 2 new tests; suite green (477 passed, same 3
> pre-existing unrelated failures). **Bug in my own first draft, caught before commit**: a
> template-literal typo produced a stray `"` in the group-body `<div>` attribute — caught by
> reading the generated HTML in-browser rather than trusting the diff.

### Task B13: Sidebar — country/region groups + favorites (user decision 2026-07-03)

**Files:** `scripts/fetch_league_teams.py` (registry gains `group` field: England / Spain /
Italy / Germany / France / Americas / Other Europe / Cups / Rankings), `webapp/leagues.js`
(regenerated), `webapp/index.html` (collapsible groups, persisted open/closed state +
star-to-pin favorites section on top, both localStorage; mobile drawer gets the same treatment).
Ship with C1 leagues or before — the flat list breaks past ~20 entries.

**Also decided 2026-07-03:** no alert infrastructure (site-only; the edge board is the single
surface) — do not build email/issue notifications. Bet sizes display as **abstract units**
(1u = 1% bankroll convention, quarter-Kelly % shown alongside); no bankroll/currency input
this plan.

### Task B10: Start archiving the odds/projection time series NOW (added 2026-07-03)

Every CI build overwrites the payloads; odds history only exists from the day we start keeping
it. This task is deliberately tiny — accrual infrastructure only, no UI (the movers strip and
sparklines consume it in the follow-up plan).

**Files:**
- Create: `scripts/archive_odds_snapshot.py` — after each build, append one row per (league, team, date): title/playoff/UCL/relegation odds + seed ELO + (where present) upcoming-match model & market probs, to `data/odds_history.parquet` (append-only, deduped on league+team+build-date)
- Modify: `.github/workflows/` daily-MLS + weekly-European refresh jobs — run the archiver after the build step and commit the parquet
- Test: `tests/test_archive_odds_snapshot.py` — same build run twice appends once; a second date appends new rows.

Also extend `data_pipeline/odds_log.py` coverage per the betting-edge goal: verify the daily
cron logs openers AND closers for MLS, and file The-Odds-API league keys for the covered
European leagues (soccer_epl, soccer_spain_la_liga, …) so forward CLV accrues beyond MLS —
budget-gated (free tier is 500 req/mo; check quota math in the task before enabling; paid key
deferred per user decision until B5/B10/Part C are live).

### Task B11: Build cadence + virtual bet ledger (user decisions 2026-07-03)

**(a) Daily in-season builds.** Extend the daily 7AM workflow from MLS-only to every league
whose payload `status` is `live` (skip preseason/completed — a status check in the workflow
script, not new YAML per league). Weekly Monday full rebuild stays as the catch-all. Keeps the
30-min timeout honest: leagues build in parallel CI jobs, one league per matrix entry.

**(b) Build-time paper-bet ledger.** New `scripts/bet_ledger.py`, run after each build:
- **Log:** for every upcoming match with market odds where edge ≥ 8%: league, match_id, date,
  side, model p, de-vigged market p, decimal odds, edge %, quarter-Kelly units →
  `data/bet_ledger.parquet` (append-only, deduped on league+match_id+side; a bet is logged at
  the FIRST build that recommends it — no repricing on later builds, that's what CLV measures).
- **Settle:** on later builds, fill result + units P/L for decided matches; compute CLV pp
  where closers exist (`data_pipeline/market.py:clv_pp`).
- **Surface:** emit `ledger` summary block into payloads (running units P/L, hit rate, CLV
  mean, max drawdown, n bets, by-league split); UI renders a P/L curve + ledger table in the
  market view (B5). This is the live validation of the entire edge product — it must accrue
  before real money moves.
- Test: log-once dedup; settlement math on a synthetic decided match; drawdown calc.

### B7/B8 follow-up plan (out of scope here — spine confirmed 2026-07-03)

User selected ALL four later-tier features; the follow-up plan's order (edge-product lens):
**odds history + movers** (consumes B10's accrued data) → **is-this-team-for-real panel**
(the Spurs story as product; consumes A7's gap signal + xG-implied points) → **projection lab**
(scenario deltas, share links) → **mobile polish** (continuous, one pass per shipped feature).
Do not start them from this plan.

---

## Part C — League expansion (added 2026-07-03, user decision)

User selected all three easy tracks; Brazil/Argentina/Japan explicitly deferred (format +
calendar-year season work, no adapter reuse).

### Task C1: football-data.co.uk batch — Eredivisie, Primeira Liga, Scottish Premiership, Belgian Pro League, Süper Lig, Greek Super League

Same source/format as Championship (goals + market odds — odds matter double under the
betting-edge goal). Per league: FD code (N1, P1, SC0, B1, T1, G1) + sidebar/registry entry +
FD→ESPN name map + logos + OUTLOOK buckets (title/UCL-spots/relegation per league rules) +
season_state wiring. No tier bridges (no covered second tiers) — promoted teams use the static
prior path, which already exists. Süper Lig/Greek carry the heaviest diacritic/name-mapping
load — reuse the fuzzy-alias machinery from `scripts/build_logo_map.py`.

**Format warning — two of these are NOT plain round-robins, and a naive table sim ships wrong
odds (unacceptable for a betting-edge product):**
- **Scottish Premiership:** 33 rounds, then the table SPLITS top-6/bottom-6 for 5 more rounds
  (teams only play within their half; positions can't cross the split line).
- **Belgian Pro League:** regular season, then Champions' Play-offs with **points halved**
  (rounded up) — title odds are meaningless without modeling the halving.
- **Greek Super League** also has a championship playoff round (points carried, top-6).
The sim needs a per-league `format` config (rounds, split rule, points transform) in the
season simulator; Eredivisie/Primeira/Süper Lig are plain round-robins and ship first. Ship
order within C1: Eredivisie → Primeira → Süper Lig → Scotland → Greece → Belgium (ascending
format complexity), each behind a payload-validation + odds-sanity check before the sidebar
entry goes live.

- [ ] One league end-to-end first (Eredivisie: cleanest names) → validate payload + browser check → then the remaining five as config-driven repeats → `scripts/validate_payloads.py` green → weekly CI refresh list updated.
- Verification per league: payload validates; standings/odds render; power rankings gain the league group; ~18 min/league build budget (see memory: run serially).

### Task C2: ASA track — NWSL + USL Championship

The richest expansion: `itscalledsoccer` serves both leagues with the same xG/possession/GK
endpoints as MLS, so the full MLS feature pipeline (and `build_dashboard_data.py`-style
ensemble path) applies — not the goals-only European path. Needs: ASA league parameter
threading through `data_pipeline/asa_cache.py`, ESPN fixture/logo mapping for both leagues,
playoff-format sim config (NWSL shield+playoffs; USL Eastern/Western conferences), and a
walk-forward eval on each league's history before shipping odds (champion config may not
transfer — treat each as a new eval, gate vs its own naive baseline).

**Governance (user decisions 2026-07-03): champions per LEAGUE FAMILY — five gates total.**
Championed configs are governed per data family, not per league and not one-global:

| Family | Leagues | Champion pointer |
|---|---|---|
| MLS | MLS | `experiments/champion.json` (existing, untouched) |
| xG-rich Europe | big-5 top flights | `experiments/champion_eur_big5.json` (new) |
| Goals-only tiers | second/lower tiers + C1 leagues (graduate to xG-rich as A12 lands) | `experiments/champion_eur_tiers.json` (new) |
| NWSL | NWSL | `experiments/champion_nwsl.json` (new) |
| USL | USL Championship | `experiments/champion_usl.json` (new) |

Each family gets its own walk-forward report, naive baseline, and promotion gate; experiments
(A4/A5/A8/A11…) are judged per family — a KEEP in one family doesn't auto-apply to another.
`model_card` in each payload reads its family's champion. `scripts/promotion_gate.py` gains a
`--champion <path>` parameter rather than being duplicated.

- [ ] NWSL first (cleaner playoff structure, better ASA coverage) → eval → build → browser check → USL second.

---

---

## Success criteria (proposed defaults — user may override)

The campaign is a success when, in priority order:
1. **Conditional calibration:** the A7 fallen-giant cohort's projected relegation/finish odds
   sit within the cohort's historical base-rate confidence interval (the Spurs test), with no
   MLS champion aggregate regression beyond seed noise.
2. **Edge validation:** the B11 paper ledger accrues ≥50 settled bets with **CLV ≥ 0** (beating
   the close is the leading indicator; short-run P/L is noise at n=50 — judge on CLV, report both).
3. **Coverage:** all six C1 leagues + NWSL live with validated payloads and per-league gates.
4. **Trust surface:** reliability slices public in the UI (B4), forward path honestly labeled.

**Public-site note:** the dashboard is publicly hosted (GitHub Pages) and B5/B11 add betting
recommendations. B5 ships with a short fixed disclaimer on the market view (informational, not
betting advice; 18+/21+; links to problem-gambling resources) — one-line task, non-negotiable
for a public edge product.

## Documentation obligations (per CLAUDE.md, every task)

- Append a verdict to THIS file after each task.
- A2/A4/A5/A6 outcomes → blockquote in `docs/PLAN.md`; experiments also logged in `docs/feature-hunt-log.md`.
- If A2 changes the production forward path: update `docs/CURRENT_STATE.md` (Production Path + Model Card sections).
- On completion: 2–3 sentence summary in `docs/PROJECT_HISTORY.md`, then delete this file.
- Housekeeping (first commit of this plan): `docs/superpowers/plans/` currently holds 7 files; CLAUDE.md says 1–2. Verify the 5 pre-2026-06-30 plans are complete (verdicts at top), fold their summaries into `PROJECT_HISTORY.md`, delete them.

## Risks

- **A2 gate may fail** — carried-forward features are stale by construction; DC-identity may genuinely be the better forward model. That's why Step 5 measures before wiring. A negative result is still valuable (it validates the current path and closes the deep-dive headline).
- **Payload size** — B2/B4/B5 add data to `webapp/data/*.js`; check gzipped size stays reasonable (< ~1MB/league) since GitHub Pages serves them statically.
- **Concurrency** — one eval run at a time (16GB machine, ~90 XGB models per run; see memory note "European build timing").
