# League Expansion Round 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 14 leagues to the dashboard in three dependency-ordered phases, reusing existing adapters for 12 and adding one new API-Football adapter for the last two.

**Architecture:** `OUTLOOK` in `scripts/build_league_data.py` is a data-driven registry routed by a `source` field. Phase 1 adds config rows on the `footballdata` (mmz4281) and `footballdata_intl` (new-leagues CSV) adapters. Phase 2 generalizes the currently liga-mx-hardcoded `espn` goals-only path and adds config. Phase 3 adds `data_pipeline/api_football.py` (env-keyed) feeding Finland's fixtures and Canadian PL end-to-end.

**Tech Stack:** Python 3, pandas, numpy, xgboost; football-data.co.uk + ESPN site API + API-Football (api-sports.io); pytest; vanilla-JS webapp consuming generated `webapp/data/*.js`.

**Spec:** `docs/superpowers/specs/2026-07-11-league-expansion-round4-design.md`

**Conventions carried from the 2026-07-10 wave:**
- Team name-maps (`FD_ESPN` / `FDI_ESPN` in `build_league_data.py`) are built *empirically*: run the build, read the `[warning] unmapped` lines, add only the entries that differ from the ESPN displayName. Do NOT pre-invent them.
- Continental/relegation buckets are approximate; the `rules` string carries the honest caveat (plain-table, no split-round modeling).
- Per-league verification = build the `.js`, load `webapp/` in the preview browser, confirm table + outlook + drift render with real crests and no console errors.

---

## PHASE 1 — Tier 1 (no API key required)

### Task 1: Register Scottish lower tiers + tier-bridge chain

**Files:**
- Modify: `data_pipeline/football_data.py` (`DIV`, `GOALS_ONLY`)
- Modify: `scripts/build_league_data.py` (`_TIER2_FOR`)
- Test: `tests/test_scottish_tiers.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scottish_tiers.py
"""Scottish Championship / League One / League Two registration + pyramid chain."""
from __future__ import annotations


def test_scottish_tiers_registered():
    from data_pipeline import football_data as fd
    assert fd.DIV["scottish-champ"] == "SC1"
    assert fd.DIV["scottish-league-one"] == "SC2"
    assert fd.DIV["scottish-league-two"] == "SC3"
    for lid in ("scottish-champ", "scottish-league-one", "scottish-league-two"):
        assert lid in fd.GOALS_ONLY
        assert lid not in fd.BIG5


def test_scottish_pyramid_chain():
    from scripts.build_league_data import _TIER2_FOR, _TIER1_FOR_BUILD
    assert _TIER2_FOR["scottish-prem"] == "scottish-champ"
    assert _TIER2_FOR["scottish-champ"] == "scottish-league-one"
    assert _TIER2_FOR["scottish-league-one"] == "scottish-league-two"
    # inverse chain (relegation direction) is derived for free
    assert _TIER1_FOR_BUILD["scottish-league-two"] == "scottish-league-one"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_scottish_tiers.py -v`
Expected: FAIL with `KeyError: 'scottish-champ'`

- [ ] **Step 3: Add DIV + GOALS_ONLY entries**

In `data_pipeline/football_data.py`, extend `DIV` (after the `national-league` entry) and `GOALS_ONLY`:

```python
    # Scottish lower tiers (2026-07-11, expansion round 4). mmz4281 SC1/SC2/SC3,
    # ESPN sco.2/sco.3/sco.4. Chain up to scottish-prem (SC0) for tier-bridge seeding.
    "scottish-champ": "SC1", "scottish-league-one": "SC2", "scottish-league-two": "SC3",
```

Add the three slugs to the `GOALS_ONLY` list.

- [ ] **Step 4: Add the pyramid chain**

In `scripts/build_league_data.py`, extend `_TIER2_FOR`:

```python
    # Scottish pyramid (2026-07-11): SC0→SC1→SC2→SC3. No fitted offsets yet;
    # coefficients.tier2_offset/tier1_offset fall back to the 0.0 default until
    # movers accrue (same posture as the England league-two→national-league hop).
    "scottish-prem":      "scottish-champ",
    "scottish-champ":     "scottish-league-one",
    "scottish-league-one":"scottish-league-two",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_scottish_tiers.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/football_data.py scripts/build_league_data.py tests/test_scottish_tiers.py
git commit -m "feat(expansion): register Scottish Championship/L1/L2 + pyramid chain"
```

---

### Task 2: Scottish OUTLOOK config + build + verify

**Files:**
- Modify: `scripts/build_league_data.py` (`OUTLOOK`)
- Test: `tests/test_scottish_tiers.py` (extend)

Scottish lower-tier format (approximate, per spec): champion promoted automatically,
places 2–4 (+ higher-tier's playoff team, not modeled) into a promotion playoff;
bottom club relegated / playoff. Use `_PROMO(1, [2, 4], 1)`. n=10 for all three.

- [ ] **Step 1: Write the failing test**

```python
def test_scottish_outlook():
    from scripts.build_league_data import OUTLOOK
    for lid in ("scottish-champ", "scottish-league-one", "scottish-league-two"):
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "footballdata"
        assert cfg["n"] == 10
        assert cfg["confederation"] == "UEFA" or "confederation" not in cfg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_scottish_tiers.py::test_scottish_outlook -v`
Expected: FAIL with `KeyError`

- [ ] **Step 3: Add OUTLOOK entries**

In `scripts/build_league_data.py`, add to `OUTLOOK` near the other `footballdata` tiers:

```python
    # Scottish lower tiers (2026-07-11, round 4). Plain promotion-playoff shape —
    # the real cross-division playoff (which pulls in the tier above's 11th/9th)
    # is approximated; see rules caveat.
    "scottish-champ": {"name": "Scottish Championship", "source": "footballdata", "n": 10,
                       "buckets": _PROMO(1, [2, 4], 1), "green_line": 4, "red_line": 1,
                       "rules": "Champion promoted to the Premiership · 2nd–4th enter a promotion playoff (the Premiership's 11th also joins — not modeled) · bottom club relegated, 9th plays a playoff"},
    "scottish-league-one": {"name": "Scottish League One", "source": "footballdata", "n": 10,
                            "buckets": _PROMO(1, [2, 4], 1), "green_line": 4, "red_line": 1,
                            "rules": "Champion promoted to the Championship · 2nd–4th promotion playoff · bottom club relegated, 9th plays a playoff"},
    "scottish-league-two": {"name": "Scottish League Two", "source": "footballdata", "n": 10,
                            "buckets": _PROMO(1, [2, 4], 1), "green_line": 4, "red_line": 1,
                            "rules": "Champion promoted to League One · 2nd–4th promotion playoff · bottom club plays the pyramid playoff vs the Highland/Lowland League winners (not modeled)"},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_scottish_tiers.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Build each league + reconcile names**

Run each and read the unmapped-name warnings:
```bash
for L in scottish-champ scottish-league-one scottish-league-two; do
  python3 -m scripts.build_league_data --league $L --sims 20000 2>&1 | tee /tmp/build_$L.log
done
grep -h "unmapped\|no crest\|no ESPN" /tmp/build_scottish-*.log || echo "no name gaps"
```
For any name printed as unmapped, add an entry to `FD_ESPN["scottish-champ"]` (etc.) mapping the football-data short name → ESPN displayName, then rebuild that league. Repeat until clean.

- [ ] **Step 6: Verify in browser**

Start the webapp preview and load each league's page; confirm the table populates with crests, the outlook buckets render, no console errors. (Preview workflow per the harness `preview_start` on `webapp/`.)

- [ ] **Step 7: Commit**

```bash
git add scripts/build_league_data.py tests/test_scottish_tiers.py webapp/data/scottish-*.js webapp/data/drift-traj/scottish-*.js
git commit -m "feat(expansion): Scottish Championship/L1/L2 outlook + data"
```

---

### Task 3: Register Austria / Switzerland / Romania / Ireland (footballdata_intl)

**Files:**
- Modify: `data_pipeline/football_data_intl.py` (`COUNTRY`)
- Test: `tests/test_expansion_intl_tier1.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_expansion_intl_tier1.py
"""Round-4 footballdata_intl Tier-1 top flights: Austria, Switzerland, Romania, Ireland."""
from __future__ import annotations


def test_intl_countries_registered():
    from data_pipeline.football_data_intl import COUNTRY
    assert COUNTRY["austria-bundesliga"] == "AUT"
    assert COUNTRY["swiss-super-league"] == "SWZ"
    assert COUNTRY["romania-liga1"] == "ROU"
    assert COUNTRY["ireland-premier"] == "IRL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_expansion_intl_tier1.py -v`
Expected: FAIL with `KeyError`

- [ ] **Step 3: Add COUNTRY entries**

In `data_pipeline/football_data_intl.py`, extend `COUNTRY`:

```python
    # Round-4 Tier-1 (2026-07-11). football-data "new leagues" CSVs, Pinnacle
    # closings back to ~2012. ESPN aut.1/sui.1/rou.1/irl.1 verified live.
    "austria-bundesliga": "AUT",
    "swiss-super-league": "SWZ",  # NB: football-data code is SWZ, not SUI (report erratum, verified 2026-07-11)
    "romania-liga1": "ROU",
    "ireland-premier": "IRL",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_expansion_intl_tier1.py -v`
Expected: PASS

- [ ] **Step 5: Smoke-check the CSVs actually load**

```bash
python3 -c "
from data_pipeline.football_data_intl import match_results_intl
for lid in ('austria-bundesliga','swiss-super-league','romania-liga1','ireland-premier'):
    df = match_results_intl(lid)
    print(lid, len(df), 'rows,', df['date'].max() if len(df) else 'EMPTY')
"
```
Expected: each prints a non-trivial row count and a recent max date. If a country's CSV lags a season (the Japan-lag lesson), note it — the ESPN backfill path handles it during build.

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/football_data_intl.py tests/test_expansion_intl_tier1.py
git commit -m "feat(expansion): register Austria/Switzerland/Romania/Ireland intl sources"
```

---

### Task 4: Austria / Switzerland / Romania / Ireland OUTLOOK + build + verify

**Files:**
- Modify: `scripts/build_league_data.py` (`OUTLOOK`)
- Test: `tests/test_expansion_intl_tier1.py` (extend)

All UEFA top flights → `_TOP(ucl, rel)` shape. Team counts: Austria 12, Switzerland 12,
Romania 16, Ireland 10. Continental/relegation cut-lines are approximate (caveat in `rules`).

- [ ] **Step 1: Write the failing test**

```python
def test_intl_tier1_outlook():
    from scripts.build_league_data import OUTLOOK
    expect = {"austria-bundesliga": 12, "swiss-super-league": 12,
              "romania-liga1": 16, "ireland-premier": 10}
    for lid, n in expect.items():
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "footballdata_intl"
        assert cfg["n"] == n
        assert cfg["confederation"] == "UEFA"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_expansion_intl_tier1.py::test_intl_tier1_outlook -v`
Expected: FAIL with `KeyError`

- [ ] **Step 3: Add OUTLOOK entries**

```python
    # Round-4 Tier-1 UEFA top flights (2026-07-11). Split-round formats (Austria's
    # points-halving championship/relegation groups, Romania's play-off/play-out)
    # are approximated as a plain table — caveat in each rules string.
    "austria-bundesliga": {"name": "Austrian Bundesliga", "source": "footballdata_intl",
                           "n": 12, "confederation": "UEFA",
                           "buckets": _TOP(2, 2), "green_line": 2, "red_line": 2,
                           "eval_seasons": None,
                           "rules": "Champion → Champions League qualifying (approximate) · bottom club relegated (the real points-halving championship/relegation split is not modeled — plain regular-season table)"},
    "swiss-super-league": {"name": "Swiss Super League", "source": "footballdata_intl",
                           "n": 12, "confederation": "UEFA",
                           "buckets": _TOP(2, 2), "green_line": 2, "red_line": 2,
                           "eval_seasons": None,
                           "rules": "Champion → Champions League qualifying (approximate) · bottom club relegated, 11th plays a barrage (not modeled)"},
    "romania-liga1": {"name": "Liga I (Romania)", "source": "footballdata_intl",
                      "n": 16, "confederation": "UEFA",
                      "buckets": _TOP(2, 3), "green_line": 2, "red_line": 3,
                      "eval_seasons": None,
                      "rules": "Champion → Champions League qualifying (approximate) · bottom relegated (the real championship play-off / relegation play-out split with points-halving is not modeled — plain table)"},
    "ireland-premier": {"name": "League of Ireland Premier", "source": "footballdata_intl",
                        "n": 10, "confederation": "UEFA",
                        "buckets": _TOP(2, 1), "green_line": 2, "red_line": 1,
                        "eval_seasons": None,
                        "rules": "Champion → Champions League qualifying (approximate) · bottom club relegated, 9th plays a promotion/relegation playoff (not modeled) · calendar-year season"},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_expansion_intl_tier1.py -v`
Expected: PASS

- [ ] **Step 5: Build + reconcile names + verify in browser**

```bash
for L in austria-bundesliga swiss-super-league romania-liga1 ireland-premier; do
  python3 -m scripts.build_league_data --league $L --sims 20000 2>&1 | tee /tmp/build_$L.log
done
grep -h "unmapped\|no crest" /tmp/build_*.log || echo "no name gaps"
```
Add `FDI_ESPN[<lid>]` mismatches, rebuild, then load each in the preview browser (table + outlook + drift render, real crests, no console errors).

- [ ] **Step 6: Commit**

```bash
git add scripts/build_league_data.py tests/test_expansion_intl_tier1.py webapp/data/austria-bundesliga.js webapp/data/swiss-super-league.js webapp/data/romania-liga1.js webapp/data/ireland-premier.js webapp/data/drift-traj/*.js
git commit -m "feat(expansion): Austria/Switzerland/Romania/Ireland outlook + data"
```

---

## PHASE 2 — Projection-only (no API key required)

### Task 5: China + Russia (footballdata_intl, odds backbone, projection-only)

**Files:**
- Modify: `data_pipeline/football_data_intl.py` (`COUNTRY`)
- Modify: `scripts/build_league_data.py` (`OUTLOOK`)
- Test: `tests/test_expansion_projection.py` (create)

China/Russia keep their football-data Pinnacle odds columns (backbone for a future
edge layer) but are presented projection-only. ESPN `chn.1`/`rus.1` supply fixtures.
n: China 16, Russia 16.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_expansion_projection.py
"""Round-4 projection-only leagues."""
from __future__ import annotations


def test_china_russia_registered():
    from data_pipeline.football_data_intl import COUNTRY
    assert COUNTRY["china-super"] == "CHN"
    assert COUNTRY["russia-premier"] == "RUS"


def test_china_russia_outlook():
    from scripts.build_league_data import OUTLOOK
    for lid, conf in (("china-super", "AFC"), ("russia-premier", "UEFA")):
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "footballdata_intl"
        assert cfg["n"] == 16
        assert cfg["confederation"] == conf
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_expansion_projection.py -v`
Expected: FAIL with `KeyError`

- [ ] **Step 3: Add COUNTRY + OUTLOOK entries**

`data_pipeline/football_data_intl.py` `COUNTRY`:
```python
    # Round-4 projection-only (2026-07-11). Odds columns retained as a future
    # edge-layer backbone; presented projection-only for now.
    "china-super": "CHN",
    "russia-premier": "RUS",
```

`scripts/build_league_data.py` `OUTLOOK`:
```python
    "china-super": {"name": "Chinese Super League", "source": "footballdata_intl",
                    "n": 16, "confederation": "AFC",
                    "buckets": _CONTINENTAL("AFC Champions League", 3, 2),
                    "green_line": 3, "red_line": 2, "eval_seasons": None,
                    "rules": "Champion + next 2 reach AFC club competitions (approximate) · bottom 2 relegated · calendar-year season"},
    "russia-premier": {"name": "Russian Premier League", "source": "footballdata_intl",
                       "n": 16, "confederation": "UEFA",
                       "buckets": _CONTINENTAL("European qualification (currently suspended)", 3, 2),
                       "green_line": 3, "red_line": 2, "eval_seasons": None,
                       "rules": "Top 3 would qualify for UEFA competitions but Russian clubs are currently suspended from European football (shown for domestic context) · bottom 2 relegated, 13th–14th play relegation playoffs (not modeled)"},
```
(Using `_CONTINENTAL` — the coarse Champion/Continental/Relegation shape, correct for non-UEFA-label leagues and honest for Russia's suspended berths.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_expansion_projection.py -v`
Expected: PASS

- [ ] **Step 5: Build + reconcile + verify**

```bash
for L in china-super russia-premier; do
  python3 -m scripts.build_league_data --league $L --sims 20000 2>&1 | tee /tmp/build_$L.log
done
```
Reconcile `FDI_ESPN` name gaps, rebuild, verify each in the browser.

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/football_data_intl.py scripts/build_league_data.py tests/test_expansion_projection.py webapp/data/china-super.js webapp/data/russia-premier.js webapp/data/drift-traj/*.js
git commit -m "feat(expansion): China + Russia projection-only (odds backbone retained)"
```

---

### Task 6: Generalize the ESPN goals-only frame path

**Files:**
- Modify: `data_pipeline/espn_soccer.py` (or wherever `liga_mx_frame` is defined — confirm with `grep -rn "def liga_mx_frame"`)
- Modify: `scripts/build_league_data.py` (`_load_frame`)
- Test: `tests/test_espn_frame_generic.py` (create)

The current `_load_frame` hardcodes `source == "espn" and league_id == "liga-mx"`. Generalize
to a slug-parameterized `espn_frame(league_id, slug)`; keep `liga_mx_frame()` as a thin
wrapper so existing behavior/tests are unchanged.

- [ ] **Step 1: Confirm the current definition**

Run: `grep -rn "def liga_mx_frame\|liga_mx_frame" data_pipeline/ scripts/`
Read the function; the generic version takes the ESPN slug as a parameter and is otherwise identical.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_espn_frame_generic.py
"""The ESPN goals-only frame builder is slug-generic, not liga-mx-only."""
from __future__ import annotations
import inspect


def test_espn_frame_is_parameterized():
    from data_pipeline import espn_soccer  # adjust import to the confirmed module
    assert hasattr(espn_soccer, "espn_frame")
    sig = inspect.signature(espn_soccer.espn_frame)
    # slug is a required/consumed parameter
    assert "slug" in sig.parameters or "espn_slug" in sig.parameters


def test_liga_mx_wrapper_preserved():
    from data_pipeline import espn_soccer
    assert hasattr(espn_soccer, "liga_mx_frame")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_espn_frame_generic.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'espn_frame'`

- [ ] **Step 4: Extract the generic function**

Rename the body of `liga_mx_frame` to `espn_frame(league_id, slug)` (slug drives the ESPN
scoreboard/teams URLs), and replace `liga_mx_frame`:
```python
def liga_mx_frame():
    return espn_frame("liga-mx", "mex.1")
```
Then in `scripts/build_league_data.py` `_load_frame`, generalize the routing. Add an
`espn_slug` field lookup (from a small `ESPN_SLUG` dict defined in build_league_data):
```python
    if source == "espn":
        from data_pipeline.espn_soccer import espn_frame  # adjust to confirmed module
        return espn_frame(league_id, ESPN_SLUG[league_id])
```
And define near the top of `build_league_data.py`:
```python
# ESPN slugs for the goals-only `espn` source leagues.
ESPN_SLUG = {"liga-mx": "mex.1"}
```

- [ ] **Step 5: Run tests to verify pass (incl. existing liga-mx)**

Run: `python3 -m pytest tests/test_espn_frame_generic.py -v && python3 -m scripts.build_league_data --league liga-mx --sims 5000 2>&1 | tail -5`
Expected: tests PASS; liga-mx build still completes.

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/espn_soccer.py scripts/build_league_data.py tests/test_espn_frame_generic.py
git commit -m "refactor(expansion): slug-generic ESPN goals-only frame (liga-mx wrapper preserved)"
```

---

### Task 7: Saudi / A-League / WSL OUTLOOK (source=espn) + build + verify

**Files:**
- Modify: `scripts/build_league_data.py` (`OUTLOOK`, `ESPN_SLUG`)
- Test: `tests/test_expansion_projection.py` (extend)

Slugs: Saudi `ksa.1` (n=18, AFC), A-League `aus.1` (n=12, AFC, finals series → no relegation),
WSL `eng.w.1` (n=12, UEFA women).

- [ ] **Step 1: Write the failing test**

```python
def test_espn_projection_leagues():
    from scripts.build_league_data import OUTLOOK, ESPN_SLUG
    for lid, slug, n in (("saudi-pro", "ksa.1", 18),
                         ("australia-aleague", "aus.1", 12),
                         ("wsl", "eng.w.1", 12)):
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "espn"
        assert cfg["n"] == n
        assert ESPN_SLUG[lid] == slug
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_expansion_projection.py::test_espn_projection_leagues -v`
Expected: FAIL with `KeyError`

- [ ] **Step 3: Add ESPN_SLUG + OUTLOOK entries**

`ESPN_SLUG`:
```python
ESPN_SLUG = {"liga-mx": "mex.1",
             "saudi-pro": "ksa.1", "australia-aleague": "aus.1", "wsl": "eng.w.1"}
```

`OUTLOOK`:
```python
    # Round-4 projection-only, ESPN goals-only (no football-data odds). Same
    # model family as liga-mx / NWSL. eval_seasons=None → advisory only.
    "saudi-pro": {"name": "Saudi Pro League", "source": "espn", "n": 18,
                  "confederation": "AFC",
                  "buckets": _CONTINENTAL("AFC Champions League", 4, 3),
                  "green_line": 4, "red_line": 3, "eval_seasons": None,
                  "rules": "Champion + top sides reach the AFC Champions League Elite (approximate) · bottom 3 relegated"},
    "australia-aleague": {"name": "A-League Men", "source": "espn", "n": 12,
                          "confederation": "AFC",
                          "buckets": [
                              {"key": "premiers", "label": "Premiers", "col": "Premiers", "top": 1},
                              {"key": "finals", "label": "Finals Series", "col": "Finals", "top": 6}],
                          "green_line": 6, "red_line": None, "eval_seasons": None,
                          "rules": "Premiers Plate = best regular-season record · top 6 reach the finals series (championship decided there — not the table) · no relegation (closed league)"},
    "wsl": {"name": "Women's Super League", "source": "espn", "n": 12,
            "confederation": "UEFA",
            "buckets": _TOP(2, 1), "green_line": 2, "red_line": 1,
            "eval_seasons": None,
            "rules": "Top sides qualify for the UEFA Women's Champions League (approximate) · bottom club relegated · no xG source for this league (goals-only)"},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_expansion_projection.py -v`
Expected: PASS

- [ ] **Step 5: Build + verify**

```bash
for L in saudi-pro australia-aleague wsl; do
  python3 -m scripts.build_league_data --league $L --sims 20000 2>&1 | tee /tmp/build_$L.log
done
```
ESPN supplies crests directly for these (no name-map needed unless a warning appears).
Verify each in the browser — confirm the A-League page shows the finals/no-relegation
shape correctly and WSL renders without a market/edge surface.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_league_data.py tests/test_expansion_projection.py webapp/data/saudi-pro.js webapp/data/australia-aleague.js webapp/data/wsl.js webapp/data/drift-traj/*.js
git commit -m "feat(expansion): Saudi Pro / A-League / WSL projection-only (ESPN goals-only)"
```

---

## PHASE 3 — API-Football adapter (requires `API_FOOTBALL_KEY`)

> Blocked on the user provisioning a free api-sports.io key as env `API_FOOTBALL_KEY`.
> Tasks 8's adapter + unit tests can be written now (against a saved JSON fixture);
> Tasks 9–10 end-to-end builds need the live key. Until the key lands, Finland ships
> results-only (Poland-class) and Canadian PL stays the current placeholder.

### Task 8: `data_pipeline/api_football.py` adapter

**Files:**
- Create: `data_pipeline/api_football.py`
- Create: `tests/fixtures/api_football_sample.json` (a saved real response, captured once the key exists — until then, hand-craft a minimal valid sample matching the API-Football `/fixtures` schema)
- Test: `tests/test_api_football.py` (create)

The adapter mirrors `football_data_intl.py`: `results_frame(league_id, seasons)` and
`upcoming_fixtures(league_id)`, keyed on env `API_FOOTBALL_KEY`, disk-cached, one fetch
per league per build (respects the 100 req/day free ceiling).

- [ ] **Step 1: Write the failing test (parse from fixture, no network)**

```python
# tests/test_api_football.py
"""API-Football adapter: env-keyed, parses fixtures/results frames offline."""
from __future__ import annotations
import json, pathlib, pytest


def _sample():
    return json.loads((pathlib.Path(__file__).parent / "fixtures" / "api_football_sample.json").read_text())


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    from data_pipeline import api_football
    with pytest.raises(RuntimeError, match="API_FOOTBALL_KEY"):
        api_football._require_key()


def test_parse_results_frame():
    from data_pipeline import api_football
    df = api_football._parse_fixtures(_sample())
    # finished matches become result rows with integer goals
    fin = df[df["is_result"]]
    assert {"date", "home_team", "away_team", "home_goals", "away_goals"}.issubset(df.columns)
    assert (fin["home_goals"] >= 0).all()


def test_parse_upcoming():
    from data_pipeline import api_football
    df = api_football._parse_fixtures(_sample())
    upc = df[~df["is_result"]]
    assert upc["home_goals"].isna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_football.py -v`
Expected: FAIL with `ModuleNotFoundError: data_pipeline.api_football`

- [ ] **Step 3: Create the sample fixture**

Hand-craft `tests/fixtures/api_football_sample.json` with the API-Football `/fixtures`
envelope: `{"response": [ {fixture:{date, status:{short:"FT"}}, teams:{home:{name}, away:{name}}, goals:{home:2, away:1}}, {... status short:"NS", goals:{home:null, away:null}} ]}`.
Include at least one finished (`FT`) and one not-started (`NS`) fixture.

- [ ] **Step 4: Implement the adapter**

```python
# data_pipeline/api_football.py
"""API-Football (api-sports.io) adapter — schedule + results for leagues not on
football-data / ESPN (Canadian PL, and the fixture-override for Finland).

Env: API_FOOTBALL_KEY (free tier: 100 req/day). Disk-cached; one fetch per league
per build. Mirrors football_data_intl's frame shape.
"""
from __future__ import annotations
import os, json, time
from pathlib import Path
import pandas as pd
import requests

_BASE = "https://v3.football.api-sports.io"
_CACHE = Path("data/api_football")
_FINISHED = {"FT", "AET", "PEN"}

# our slug → (api-football league id, [seasons])
LEAGUE = {
    "canadian-pl": (466, list(range(2019, 2027))),  # confirm id via /leagues?search=Canadian
    # finland fixture-override registered in build_league_data, id confirmed at wire time
}


def _require_key() -> str:
    k = os.environ.get("API_FOOTBALL_KEY")
    if not k:
        raise RuntimeError("API_FOOTBALL_KEY not set — provision a free api-sports.io key")
    return k


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{_BASE}/{path}", headers={"x-apisports-key": _require_key()},
                     params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _parse_fixtures(payload: dict) -> pd.DataFrame:
    rows = []
    for f in payload.get("response", []):
        st = f["fixture"]["status"]["short"]
        is_result = st in _FINISHED
        g = f.get("goals", {})
        rows.append({
            "date": pd.to_datetime(f["fixture"]["date"], utc=True).tz_localize(None),
            "home_team": f["teams"]["home"]["name"],
            "away_team": f["teams"]["away"]["name"],
            "home_goals": g.get("home") if is_result else None,
            "away_goals": g.get("away") if is_result else None,
            "is_result": is_result,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["home_goals"] = pd.to_numeric(df["home_goals"], errors="coerce")
        df["away_goals"] = pd.to_numeric(df["away_goals"], errors="coerce")
    return df


def _fetch_league(af_id: int, seasons: list[int]) -> pd.DataFrame:
    _CACHE.mkdir(parents=True, exist_ok=True)
    frames = []
    for s in seasons:
        cache = _CACHE / f"{af_id}_{s}.json"
        if cache.exists():
            payload = json.loads(cache.read_text())
        else:
            payload = _get("fixtures", {"league": af_id, "season": s})
            cache.write_text(json.dumps(payload))
            time.sleep(1)  # be gentle on the free tier
        frames.append(_parse_fixtures(payload))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def results_frame(league_id: str) -> pd.DataFrame:
    af_id, seasons = LEAGUE[league_id]
    df = _fetch_league(af_id, seasons)
    return df[df["is_result"]].copy() if not df.empty else df


def upcoming_fixtures(league_id: str) -> pd.DataFrame:
    af_id, seasons = LEAGUE[league_id]
    df = _fetch_league(af_id, [max(seasons)])
    return df[~df["is_result"]].copy() if not df.empty else df
```

- [ ] **Step 5: Run tests to verify pass**

Run: `python3 -m pytest tests/test_api_football.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/api_football.py tests/test_api_football.py tests/fixtures/api_football_sample.json
git commit -m "feat(expansion): API-Football adapter (env-keyed, offline-tested)"
```

---

### Task 9: Wire Canadian Premier League (needs live key)

**Files:**
- Modify: `scripts/build_league_data.py` (`_load_frame`, `OUTLOOK`)
- Test: `tests/test_expansion_projection.py` (extend)

CPL: `source: "api_football"`, Concacaf, projection-only, replaces the `status: soon`
placeholder. CPL runs single-table + playoffs; ~8–9 teams; no relegation.

- [ ] **Step 1: Confirm the API-Football league id**

With the key set: `python3 -c "from data_pipeline.api_football import _get; import json; print(json.dumps(_get('leagues',{'search':'Canadian Premier'})['response'][0]['league'], indent=2))"`
Update `LEAGUE["canadian-pl"]` id in `api_football.py` if it differs from 466. Confirm team count `n` for the current season and set it in the OUTLOOK entry below.

- [ ] **Step 2: Write the failing test**

```python
def test_cpl_outlook():
    from scripts.build_league_data import OUTLOOK
    cfg = OUTLOOK["canadian-pl"]
    assert cfg["source"] == "api_football"
    assert cfg["confederation"] == "Concacaf"
    assert cfg["red_line"] is None  # no relegation
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_expansion_projection.py::test_cpl_outlook -v`
Expected: FAIL

- [ ] **Step 4: Route the source + add OUTLOOK**

In `_load_frame`:
```python
    if source == "api_football":
        from data_pipeline.api_football import results_frame as af_results
        return af_results(league_id)
```

`OUTLOOK`:
```python
    "canadian-pl": {"name": "Canadian Premier League", "source": "api_football",
                    "n": 9, "confederation": "Concacaf",
                    "buckets": [
                        {"key": "premiers", "label": "Best Record", "col": "Premiers", "top": 1},
                        {"key": "playoffs", "label": "Playoffs", "col": "Playoffs", "top": 6}],
                    "green_line": 6, "red_line": None, "eval_seasons": None,
                    "rules": "Best regular-season record earns a bye · top 6 reach the playoffs (championship decided there) · no relegation · projections-only (no odds source)"},
```
Ensure the upcoming-fixtures path also calls `api_football.upcoming_fixtures("canadian-pl")`
where the builder assembles scheduled rows (mirror how footballdata_intl's ESPN fixtures
are attached; wire CPL's fixtures through `upcoming_fixtures`).

- [ ] **Step 5: Build + verify (needs key)**

```bash
API_FOOTBALL_KEY=... python3 -m scripts.build_league_data --league canadian-pl --sims 20000 2>&1 | tee /tmp/build_cpl.log
```
Confirm the placeholder `webapp/data/canadian-pl.js` is replaced with a real payload
(status not "soon", teams populated). Load in the browser: table + outlook + upcoming
fixtures render with crests, no console errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_league_data.py data_pipeline/api_football.py tests/test_expansion_projection.py webapp/data/canadian-pl.js webapp/data/drift-traj/canadian-pl.js
git commit -m "feat(expansion): Canadian Premier League via API-Football (projection-only)"
```

---

### Task 10: Finland Veikkausliiga + fixtures-override hook (needs live key)

**Files:**
- Modify: `data_pipeline/football_data_intl.py` (`COUNTRY`, `NO_ESPN_SCHEDULE`)
- Modify: `data_pipeline/api_football.py` (`LEAGUE` — add finland)
- Modify: `scripts/build_league_data.py` (`OUTLOOK`, fixtures-override hook)
- Test: `tests/test_expansion_projection.py` (extend)

Finland: results+odds from `footballdata_intl` (`FIN`); upcoming fixtures from
API-Football because ESPN `fin.1` is empty. n=12, UEFA, calendar-year.

- [ ] **Step 1: Register the source + declare the fixture override**

`football_data_intl.py`: add `"finland-veikkausliiga": "FIN"` to `COUNTRY`, and add
`"finland-veikkausliiga"` to `NO_ESPN_SCHEDULE` (no ESPN slug). `api_football.py`
`LEAGUE`: add `"finland-veikkausliiga": (244, [<seasons>])` (confirm id via `/leagues?search=Veikkausliiga`).

- [ ] **Step 2: Write the failing test**

```python
def test_finland_registered_with_override():
    from data_pipeline.football_data_intl import COUNTRY, NO_ESPN_SCHEDULE
    from scripts.build_league_data import OUTLOOK, FIXTURE_OVERRIDE
    assert COUNTRY["finland-veikkausliiga"] == "FIN"
    assert "finland-veikkausliiga" in NO_ESPN_SCHEDULE
    assert OUTLOOK["finland-veikkausliiga"]["source"] == "footballdata_intl"
    assert FIXTURE_OVERRIDE["finland-veikkausliiga"] == "api_football"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_expansion_projection.py::test_finland_registered_with_override -v`
Expected: FAIL

- [ ] **Step 4: Add the fixture-override hook + OUTLOOK**

In `build_league_data.py`, define the override registry and consult it where upcoming
fixtures are assembled:
```python
# Leagues whose RESULTS come from `source` but whose UPCOMING FIXTURES come from
# elsewhere (ESPN has no slug). Value = fixtures provider module key.
FIXTURE_OVERRIDE = {"finland-veikkausliiga": "api_football"}
```
Where the builder currently branches on `NO_ESPN_SCHEDULE` to skip fixtures, add: if the
league is in `FIXTURE_OVERRIDE`, fetch upcoming rows via
`api_football.upcoming_fixtures(league_id)` instead of skipping.

`OUTLOOK`:
```python
    "finland-veikkausliiga": {"name": "Veikkausliiga", "source": "footballdata_intl",
                              "n": 12, "confederation": "UEFA",
                              "buckets": _TOP(2, 2), "green_line": 2, "red_line": 2,
                              "eval_seasons": None,
                              "rules": "Champion → Champions League qualifying (approximate) · bottom relegated, 11th plays a playoff (not modeled) · calendar-year season · upcoming fixtures via API-Football (no ESPN coverage)"},
```

- [ ] **Step 5: Run test + build + verify (needs key)**

```bash
python3 -m pytest tests/test_expansion_projection.py::test_finland_registered_with_override -v
API_FOOTBALL_KEY=... python3 -m scripts.build_league_data --league finland-veikkausliiga --sims 20000 2>&1 | tee /tmp/build_fin.log
```
Confirm the payload has both real results (from football-data) AND upcoming fixtures (from
API-Football). Load in the browser: full-featured league (table, outlook, drift, upcoming
fixtures) renders with crests, no console errors.

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/football_data_intl.py data_pipeline/api_football.py scripts/build_league_data.py tests/test_expansion_projection.py webapp/data/finland-veikkausliiga.js webapp/data/drift-traj/finland-veikkausliiga.js
git commit -m "feat(expansion): Finland Veikkausliiga (footballdata results + API-Football fixtures)"
```

---

## FINALIZE

### Task 11: Register leagues in the webapp nav + docs

**Files:**
- Modify: webapp league registry/nav (find with `grep -rn "epl\|championship" webapp/*.js webapp/index.html | grep -iv data/`)
- Modify: `scripts/build_power_rankings.py` (add new leagues to their power-ranking groups: Scottish tiers, UEFA Tier-2, non-UEFA)
- Modify: `docs/CURRENT_STATE.md`, `docs/PLAN.md` (blockquote entry), `docs/PROJECT_HISTORY.md`, `docs/league-expansion-report.md` (round-4 addendum)

- [ ] **Step 1: Add each new league to the webapp navigation/registry**

Locate how leagues appear in the site nav (the same place `national-league` was added in the July wave) and add all built leagues, grouped by confederation/tier. Rebuild any nav-driving data (e.g. `webapp/data/power.js`, coefficients page) that enumerates leagues.

- [ ] **Step 2: Verify the full site**

Load the webapp home and confirm every new league is reachable from the nav and renders. Screenshot the league picker as proof.

- [ ] **Step 3: Run the whole test suite**

Run: `python3 -m pytest tests/ -q`
Expected: all green (no regressions in existing league/tier tests).

- [ ] **Step 4: Update docs**

Per CLAUDE.md doc convention: `docs/PLAN.md` blockquote entry (top), `docs/CURRENT_STATE.md` league list, a dated `docs/PROJECT_HISTORY.md` entry, and a round-4 addendum to `docs/league-expansion-report.md`. Then delete this plan file (completed-plan rule).

- [ ] **Step 5: Commit**

```bash
git add webapp/ scripts/build_power_rankings.py docs/
git rm docs/superpowers/plans/2026-07-11-league-expansion-round4.md
git commit -m "feat(expansion): register round-4 leagues in nav + docs"
```

---

## Self-review notes (author)

- **Spec coverage:** Phase 1 (Tasks 1–4), Phase 2 (Tasks 5–7), Phase 3 (Tasks 8–10), finalize/docs (Task 11) — every spec league maps to a task. ✅
- **Key gate:** Tasks 8 (adapter/tests) is key-free; Tasks 9–10 explicitly marked "needs live key." ✅
- **Unknowns deferred honestly, not placeholdered:** API-Football league ids (466/244) and exact team counts are confirmed via a `/leagues?search=` call at wire time (explicit steps), not guessed into the model. Name-maps are built from build warnings, matching the July-wave workflow. ESPN module path for `liga_mx_frame` is confirmed by grep in Task 6 Step 1 before editing.
- **Type consistency:** `espn_frame(league_id, slug)`, `ESPN_SLUG`, `FIXTURE_OVERRIDE`, `LEAGUE`, `results_frame`/`upcoming_fixtures` used consistently across tasks. ✅
