# DC Roster Prior Injection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After `fit_dc()`, apply a position-aware roster-value adjustment to `atk`/`dfd` parameters so that a team's DC goal rates reflect recent high-value signings before match history catches up.

**Architecture:** New pure function `apply_roster_dc_prior()` added to `scripts/eval/dixon_coles.py`; activated by a new `--roster-dc-prior` flag in `eval_baseline.py`; α shrinkage coefficient tuned per fold on raw cal-fold DC Brier via a 6-point grid search.

**Tech Stack:** Python 3.13, NumPy, existing Dixon-Coles engine, existing roster-delta z-scores (`_rd_z`) from Section 6c.

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `scripts/eval/dixon_coles.py` | Modify | Add `apply_roster_dc_prior()` at end of file |
| `tests/test_dixon_coles.py` | Modify | Add `TestApplyRosterDcPrior` class |
| `scripts/eval_baseline.py:78–184` | Modify | Add `--roster-dc-prior` flag to `_parse_args()` |
| `scripts/eval_baseline.py:2447–2449` | Modify | Add `apply_roster_dc_prior` to DC import |
| `scripts/eval_baseline.py:2537–2561` | Modify | α tuning + injection inside existing DC `try:` block |
| `scripts/eval_baseline.py:2961–2968` | Modify | Add `dc_prior_alpha` to results dict `r` |
| `scripts/eval_baseline.py:3176–3181` | Modify | Add `dc_prior_alpha` to per-season table |
| `docs/feature-hunt-log.md` | Modify | Add outcome entry after eval |
| `docs/PLAN.md` | Modify | Add blockquote after eval |

---

## Task 1: `apply_roster_dc_prior()` in dixon_coles.py

**Files:**
- Modify: `scripts/eval/dixon_coles.py` (append after line 153)
- Test: `tests/test_dixon_coles.py` (append new class)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dixon_coles.py`:

```python


# ── apply_roster_dc_prior ─────────────────────────────────────────────────────

from scripts.eval.dixon_coles import apply_roster_dc_prior


class TestApplyRosterDcPrior:
    """Unit tests for position-split DC parameter adjustment."""

    def _base(self):
        atk = {"teamA": 0.3, "teamB": -0.1}
        dfd = {"teamA": 0.1, "teamB":  0.2}
        return atk, dfd

    def test_alpha_zero_returns_unchanged_params(self):
        atk, dfd = self._base()
        a2, d2 = apply_roster_dc_prior(atk, dfd, 2024, {}, {}, alpha=0.0)
        assert a2 == atk
        assert d2 == dfd

    def test_new_attacker_increases_atk_only(self):
        atk, dfd = self._base()
        rd_z = {("A", 2024): {"new_att_value_z": 1.0, "new_def_value_z": 0.0, "new_gk_value_z": 0.0}}
        hex_to_short = {"teamA": "A"}
        a2, d2 = apply_roster_dc_prior(atk, dfd, 2024, rd_z, hex_to_short, alpha=0.10)
        assert a2["teamA"] == pytest.approx(atk["teamA"] + 0.10)
        assert d2["teamA"] == pytest.approx(dfd["teamA"])         # dfd unchanged
        assert a2["teamB"] == atk["teamB"]                         # other team unchanged

    def test_new_gk_decreases_dfd_only(self):
        atk, dfd = self._base()
        rd_z = {("A", 2024): {"new_att_value_z": 0.0, "new_def_value_z": 0.0, "new_gk_value_z": 1.0}}
        hex_to_short = {"teamA": "A"}
        a2, d2 = apply_roster_dc_prior(atk, dfd, 2024, rd_z, hex_to_short, alpha=0.10)
        assert d2["teamA"] == pytest.approx(dfd["teamA"] - 0.10)  # dfd decreases
        assert a2["teamA"] == pytest.approx(atk["teamA"])          # atk unchanged

    def test_new_def_decreases_dfd_only(self):
        atk, dfd = self._base()
        rd_z = {("A", 2024): {"new_att_value_z": 0.0, "new_def_value_z": 1.0, "new_gk_value_z": 0.0}}
        hex_to_short = {"teamA": "A"}
        a2, d2 = apply_roster_dc_prior(atk, dfd, 2024, rd_z, hex_to_short, alpha=0.10)
        assert d2["teamA"] == pytest.approx(dfd["teamA"] - 0.10)

    def test_def_and_gk_adjustments_are_additive(self):
        atk, dfd = self._base()
        rd_z = {("A", 2024): {"new_att_value_z": 0.0, "new_def_value_z": 1.0, "new_gk_value_z": 1.0}}
        hex_to_short = {"teamA": "A"}
        a2, d2 = apply_roster_dc_prior(atk, dfd, 2024, rd_z, hex_to_short, alpha=0.10)
        # def_z + gk_z = 2.0 → dfd decreases by alpha * 2.0 = 0.20, capped at 0.25
        assert d2["teamA"] == pytest.approx(dfd["teamA"] - 0.20)

    def test_adjustment_capped_at_max_adj(self):
        atk, dfd = self._base()
        # z=10.0, alpha=0.10 → uncapped = 1.0, capped = 0.25
        rd_z = {("A", 2024): {"new_att_value_z": 10.0, "new_def_value_z": 0.0, "new_gk_value_z": 0.0}}
        hex_to_short = {"teamA": "A"}
        a2, _ = apply_roster_dc_prior(atk, dfd, 2024, rd_z, hex_to_short, alpha=0.10, max_adj=0.25)
        assert a2["teamA"] == pytest.approx(atk["teamA"] + 0.25)

    def test_season_minus1_fallback(self):
        atk, dfd = self._base()
        # Entry only for season 2023, not 2024
        rd_z = {("A", 2023): {"new_att_value_z": 1.0, "new_def_value_z": 0.0, "new_gk_value_z": 0.0}}
        hex_to_short = {"teamA": "A"}
        a2, _ = apply_roster_dc_prior(atk, dfd, 2024, rd_z, hex_to_short, alpha=0.10)
        assert a2["teamA"] == pytest.approx(atk["teamA"] + 0.10)  # used season-1 entry

    def test_missing_entry_leaves_params_unchanged(self):
        atk, dfd = self._base()
        a2, d2 = apply_roster_dc_prior(atk, dfd, 2024, {}, {}, alpha=0.10)
        assert a2 == atk
        assert d2 == dfd

    def test_does_not_mutate_original_dicts(self):
        atk, dfd = self._base()
        atk_copy, dfd_copy = dict(atk), dict(dfd)
        rd_z = {("A", 2024): {"new_att_value_z": 1.0, "new_def_value_z": 1.0, "new_gk_value_z": 0.5}}
        hex_to_short = {"teamA": "A"}
        apply_roster_dc_prior(atk, dfd, 2024, rd_z, hex_to_short, alpha=0.10)
        assert atk == atk_copy
        assert dfd == dfd_copy
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/ryangerda/Development/MLS
python -m pytest tests/test_dixon_coles.py::TestApplyRosterDcPrior -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'apply_roster_dc_prior'`

- [ ] **Step 3: Add `apply_roster_dc_prior()` to `scripts/eval/dixon_coles.py`**

Append after the last line of the file (after `dc_draw_prob_batch`, currently line 153):

```python


def apply_roster_dc_prior(
    atk: dict,
    dfd: dict,
    season: int,
    rd_z: dict,
    hex_to_short: dict,
    alpha: float,
    max_adj: float = 0.25,
) -> tuple:
    """Adjust DC attack/defense parameters using position-split roster value z-scores.

    Called after fit_dc(), before any dc_predict_batch() call:
      atk_adj[team] +=  clip(alpha * new_att_value_z,               -max_adj, +max_adj)
      dfd_adj[team] -=  clip(alpha * (new_def_value_z + new_gk_value_z), -max_adj, +max_adj)

    dfd[team] is defense VULNERABILITY (higher = weaker defense = more goals allowed),
    so a defensive signing DECREASES dfd (fewer goals allowed against the team).

    Returns shallow-copied (atk_adj, dfd_adj). Does not mutate the inputs.
    Lookup falls back to (short, season-1) when current season has no entry.
    """
    atk_adj = dict(atk)
    dfd_adj = dict(dfd)
    for team_id in list(atk.keys()):
        short = hex_to_short.get(team_id, team_id)
        entry = rd_z.get((short, season)) or rd_z.get((short, season - 1))
        if not entry:
            continue
        att_z = entry.get("new_att_value_z", 0.0) or 0.0
        def_z = entry.get("new_def_value_z", 0.0) or 0.0
        gk_z  = entry.get("new_gk_value_z",  0.0) or 0.0
        atk_adj[team_id] += float(np.clip(alpha * att_z,           -max_adj, max_adj))
        dfd_adj[team_id] -= float(np.clip(alpha * (def_z + gk_z),  -max_adj, max_adj))
    return atk_adj, dfd_adj
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_dixon_coles.py::TestApplyRosterDcPrior -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Run full DC test suite to ensure no regressions**

```bash
python -m pytest tests/test_dixon_coles.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/eval/dixon_coles.py tests/test_dixon_coles.py
git commit -m "feat(dc): add apply_roster_dc_prior — position-split atk/dfd adjustment

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: `--roster-dc-prior` flag + import

**Files:**
- Modify: `scripts/eval_baseline.py:78–184` (argparse section)
- Modify: `scripts/eval_baseline.py:2447–2449` (DC import block)

- [ ] **Step 1: Add the CLI flag**

In `scripts/eval_baseline.py`, find:
```python
    p.add_argument("--smoke-test",   action="store_true",
                   help="Run 2024-only eval and assert Brier within 0.001 of pinned "
                        "reference (0.6346). Gate before refactoring eval_baseline.py.")
    return p.parse_args()
```

Replace with:
```python
    p.add_argument("--smoke-test",   action="store_true",
                   help="Run 2024-only eval and assert Brier within 0.001 of pinned "
                        "reference (0.6346). Gate before refactoring eval_baseline.py.")
    p.add_argument("--roster-dc-prior", action="store_true",
                   help="P4 experiment: after fit_dc(), adjust atk/dfd parameters using "
                        "position-split roster-value z-scores (new_att_value_z, "
                        "new_def_value_z, new_gk_value_z). Requires --transfermarkt "
                        "data. α shrinkage tuned per fold on cal-fold raw DC Brier "
                        "from grid {0.0, 0.02, 0.05, 0.08, 0.12, 0.18}.")
    return p.parse_args()
```

- [ ] **Step 2: Add `apply_roster_dc_prior` to the DC import**

Find:
```python
from scripts.eval.dixon_coles import (        # noqa: E402
    dc_tau, dc_nll, fit_dc, dc_predict, dc_predict_batch, dc_lam_mu_batch,
    dc_draw_prob_batch,
)
```

Replace with:
```python
from scripts.eval.dixon_coles import (        # noqa: E402
    dc_tau, dc_nll, fit_dc, dc_predict, dc_predict_batch, dc_lam_mu_batch,
    dc_draw_prob_batch, apply_roster_dc_prior,
)
```

- [ ] **Step 3: Verify the import resolves and smoke test still passes**

```bash
python -c "from scripts.eval.dixon_coles import apply_roster_dc_prior; print('import OK')"
python scripts/eval_baseline.py --smoke-test 2>&1 | tail -5
```

Expected: `import OK` and `SMOKE TEST PASSED` (or the pinned Brier assertion passes). The flag is default-off so parity is unchanged.

- [ ] **Step 4: Commit**

```bash
git add scripts/eval_baseline.py
git commit -m "feat(harness): add --roster-dc-prior flag and import apply_roster_dc_prior

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: α calibration + DC injection in the fold loop

**Files:**
- Modify: `scripts/eval_baseline.py:2537–2561` (Dixon-Coles section of the walk-forward loop)

- [ ] **Step 1: Inject α tuning and adjusted atk/dfd**

Find the entire Dixon-Coles section in the fold loop:
```python
    # ── Dixon-Coles ──────────────────────────────────────────────────────────
    dc_ok = False
    try:
        atk, dfd, ha, rho = fit_dc(train_raw, decay_hl=DC_DECAY_HL)
        dc_pred_cal = dc_predict_batch(cal_raw, atk, dfd, ha, rho)
        dc_pred_te  = dc_predict_batch(test_raw, atk, dfd, ha, rho)
        dc_cal_te3  = calibrate_multiclass(dc_pred_cal, y_cal_r, dc_pred_te)
        dc_cal_cal3 = calibrate_multiclass(dc_pred_cal, y_cal_r, dc_pred_cal)
        dc_ok = True
        print(" | DC✓", end="", flush=True)
    except Exception as e:
        dc_pred_cal = dc_pred_te = dc_cal_te3 = dc_cal_cal3 = None
        print(f" | DC✗({e})", end="", flush=True)
```

Replace with:
```python
    # ── Dixon-Coles ──────────────────────────────────────────────────────────
    dc_ok = False
    _dc_prior_alpha = 0.0
    try:
        atk, dfd, ha, rho = fit_dc(train_raw, decay_hl=DC_DECAY_HL)
        if _ARGS.roster_dc_prior and _HAS_ROSTER_DELTA:
            _best_pr_b, _dc_prior_alpha = float("inf"), 0.0
            for _a in (0.0, 0.02, 0.05, 0.08, 0.12, 0.18):
                _a_atk, _a_dfd = apply_roster_dc_prior(
                    atk, dfd, test_season, _rd_z, _hex_to_short, _a)
                _pr_b = multiclass_brier(
                    y_cal_oh, dc_predict_batch(cal_raw, _a_atk, _a_dfd, ha, rho))
                if _pr_b < _best_pr_b:
                    _best_pr_b, _dc_prior_alpha = _pr_b, _a
            atk, dfd = apply_roster_dc_prior(
                atk, dfd, test_season, _rd_z, _hex_to_short, _dc_prior_alpha)
            print(f" | α={_dc_prior_alpha:.2f}", end="", flush=True)
        dc_pred_cal = dc_predict_batch(cal_raw, atk, dfd, ha, rho)
        dc_pred_te  = dc_predict_batch(test_raw, atk, dfd, ha, rho)
        dc_cal_te3  = calibrate_multiclass(dc_pred_cal, y_cal_r, dc_pred_te)
        dc_cal_cal3 = calibrate_multiclass(dc_pred_cal, y_cal_r, dc_pred_cal)
        dc_ok = True
        print(" | DC✓", end="", flush=True)
    except Exception as e:
        dc_pred_cal = dc_pred_te = dc_cal_te3 = dc_cal_cal3 = None
        print(f" | DC✗({e})", end="", flush=True)
```

- [ ] **Step 2: Verify syntax with a quick parse check**

```bash
python -c "import ast; ast.parse(open('scripts/eval_baseline.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/eval_baseline.py
git commit -m "feat(harness): inject roster DC prior into fold loop with per-fold α tuning

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Reporting — `dc_prior_alpha` in results dict and per-season table

**Files:**
- Modify: `scripts/eval_baseline.py:2961–2968` (results dict `r` population)
- Modify: `scripts/eval_baseline.py:3176–3181` (per-season table print)

- [ ] **Step 1: Store `dc_prior_alpha` in the results dict**

Find:
```python
    if dc_ok:
        r["dc_brier_raw"] = multiclass_brier(y_te_oh, dc_pred_te)
        r["dc_brier_cal"] = multiclass_brier(y_te_oh, dc_cal_te3)
        r["dc_ll_raw"]    = log_loss(y_te_r, dc_pred_te)
        r["dc_ll_cal"]    = log_loss(y_te_r, dc_cal_te3)
        h, d, a = per_class_brier(y_te_oh, dc_cal_te3)
        r["dc_cal_h"], r["dc_cal_d"], r["dc_cal_a"] = h, d, a
        r["dc_cal_err_max"], _ = decile_cal_error(dc_cal_te3[:, 0], (y_te_r == 0))
```

Replace with:
```python
    if dc_ok:
        r["dc_brier_raw"] = multiclass_brier(y_te_oh, dc_pred_te)
        r["dc_brier_cal"] = multiclass_brier(y_te_oh, dc_cal_te3)
        r["dc_ll_raw"]    = log_loss(y_te_r, dc_pred_te)
        r["dc_ll_cal"]    = log_loss(y_te_r, dc_cal_te3)
        h, d, a = per_class_brier(y_te_oh, dc_cal_te3)
        r["dc_cal_h"], r["dc_cal_d"], r["dc_cal_a"] = h, d, a
        r["dc_cal_err_max"], _ = decile_cal_error(dc_cal_te3[:, 0], (y_te_r == 0))
        r["dc_prior_alpha"] = _dc_prior_alpha
```

- [ ] **Step 2: Add `dc_prior_alpha` to the per-season table**

Find:
```python
# Per-season detail
print(f"\nPer-season Brier:")
dcols = ["season", "n", "naive_brier"]
for c in ["dc_brier_cal", "xgb_brier_cal", "ens_stacked_brier"]:
    if c in rd.columns:
        dcols.append(c)
print(rd[dcols].to_string(index=False, float_format="{:.4f}".format))
```

Replace with:
```python
# Per-season detail
print(f"\nPer-season Brier:")
dcols = ["season", "n", "naive_brier"]
for c in ["dc_brier_cal", "xgb_brier_cal", "ens_stacked_brier"]:
    if c in rd.columns:
        dcols.append(c)
if "dc_prior_alpha" in rd.columns and _ARGS.roster_dc_prior:
    dcols.append("dc_prior_alpha")
print(rd[dcols].to_string(index=False, float_format="{:.4f}".format))
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "import ast; ast.parse(open('scripts/eval_baseline.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/eval_baseline.py
git commit -m "feat(reporting): add dc_prior_alpha to results dict and per-season table

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Full eval run + parity check + docs update

**Files:**
- Run: `scripts/eval_baseline.py`
- Modify: `docs/feature-hunt-log.md` (add outcome entry)
- Modify: `docs/PLAN.md` (add blockquote)

- [ ] **Step 1: Parity check — confirm champion unchanged with flag off**

```bash
python scripts/eval_baseline.py --xgb-bag 5 --seed 42 --out /tmp/parity.json 2>&1 | grep -E "avg.*Brier|ens_stacked"
```

Expected: avg Brier matches champion `0.6330` (|Δ| = 0.0000 rounded to 4 decimal places).

- [ ] **Step 2: Run with `--roster-dc-prior` flag**

```bash
python scripts/eval_baseline.py --xgb-bag 5 --seed 42 --roster-dc-prior --out /tmp/dc_prior.json 2>&1 | tee /tmp/dc_prior_run.txt
```

Let it complete (≈ same runtime as champion run, ~2–4 min). Check for `α=` inline prints per season showing which α was selected.

- [ ] **Step 3: Check results**

```bash
grep -E "dc_prior_alpha|dc_brier_cal|ens_stacked|Per-season|α=" /tmp/dc_prior_run.txt | head -30
```

Note the per-season `dc_prior_alpha` values and the 4-fold avg `ens_stacked_brier`. Compare to champion `0.6330`.

- [ ] **Step 4: Update `docs/feature-hunt-log.md`**

Prepend a new entry at the top of `docs/feature-hunt-log.md`:

```markdown
## 2026-06-26 — DC Roster Prior Injection — [KEPT / NOT KEPT]

**Experiment:** Position-split roster-value z-scores (new_att, new_def, new_gk) injected
into Dixon-Coles atk/dfd parameters after fit_dc(). α shrinkage tuned per fold on cal-fold
raw DC Brier. Flag: `--roster-dc-prior --xgb-bag 5 --seed 42`.

| Season | α* | DC Brier (cal) | Ens Brier |
|--------|----|----------------|-----------|
| 2022   |    |                |           |
| 2023   |    |                |           |
| 2024   |    |                |           |
| 2025   |    |                |           |
| **Avg**|    |                |           |

Champion (no flag): avg `0.6330`  
With flag: avg `____`  Δ = `____`

**Verdict:** [KEPT — improves by X / NOT KEPT — regresses by X]

**Root cause:** [explanation]

**Next:** [next step]
```

Fill in the table from `/tmp/dc_prior_run.txt` output.

- [ ] **Step 5: Add blockquote to `docs/PLAN.md`**

Prepend at the very top of `docs/PLAN.md` (above existing blockquotes):

```markdown
> **2026-06-26 — Section 4 DC Prior Injection ▶ [DONE — KEPT / NOT KEPT]**
> α* per fold: [values]. 4-fold avg Brier: [X] vs champion 0.6330 (Δ=[Y]).
> [One sentence conclusion and next step.]
```

- [ ] **Step 6: Commit everything**

```bash
git add docs/feature-hunt-log.md docs/PLAN.md
git commit -m "eval: DC roster prior injection results + docs update

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 1 (core injection formula with signs) → Task 1 function body
- ✅ Section 2 (α calibration on cal-fold raw Brier, 6-point grid) → Task 3
- ✅ Section 3 (`apply_roster_dc_prior` in dixon_coles.py, `--roster-dc-prior` flag, `dc_prior_alpha` reporting) → Tasks 1–4
- ✅ Success criterion (KEEP if Brier improves) → Task 5

**Placeholder scan:** No TBDs. Task 5 Step 4 has blank table cells intentionally — they must be filled from actual run output (they are not TBDs, they are result slots).

**Type consistency:** `apply_roster_dc_prior` called in Task 3 with `(atk, dfd, test_season, _rd_z, _hex_to_short, _a)` matches the signature defined in Task 1 `(atk, dfd, season, rd_z, hex_to_short, alpha, max_adj=0.25)` ✅. Tests import with the same name ✅.

**Scope:** Five tasks, one plan, one flag, one eval run. Well-bounded.
