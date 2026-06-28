# Second-Tier Leagues + Bidirectional Cross-Tier Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Spanish Segunda + French Ligue 2 as full second-tier dashboard leagues, and make the cross-tier promotion/relegation bridge bidirectional and per-league calibrated across all big-5 — so promoted teams seed correctly into the top flight and relegated teams seed correctly into the second tier.

**Architecture:** Extend existing units only. `football_data.py` gains two division codes; `build_league_data.py` gains two `OUTLOOK` entries + a reverse seeding path; `tier_bridge.py` gains a relegation mirror of its promotion fitter; `coefficients.py` gains reverse-offset reads; `leagues.js` gains two sidebar entries. The smooth+floor `_elo_to_dc_params` (added 2026-06-28) is reused unchanged in both directions. No model-config changes.

**Tech Stack:** Python 3.13 (pytest suite via `make test`), football-data.co.uk CSVs (goals-only second-tier source), the static single-file webapp (verified in the browser preview, launch config `webapp`, port 8090).

**Reference:** Spec `docs/superpowers/specs/2026-06-28-second-tier-leagues-bidirectional-bridge-design.md`. Mirror existing patterns: `tests/test_tier_bridge.py`, `tests/test_build_league_data_tier2.py`, the `serie-b` `OUTLOOK` entry, the `FD_ESPN` name map, and `coefficients._TIER2_PRIORS`/`_TIER1_FOR`/`tier2_offset`.

**Standing rules:** Use the project venv (`venv/bin/python`, `venv/bin/pytest`) — system `python3` lacks `understatapi`. Branch before committing. Commit after each task. European builds run one at a time (`venv/bin/python scripts/build_league_data.py --league <id>`).

---

## Task 0: Branch + repair the test the calibration fix broke

The 2026-06-28 calibration fix replaced `_elo_to_dc_params`'s percentile-clamp with a smooth+floor mapping, but `tests/test_build_league_data_tier2.py::test_elo_to_dc_params_clamps_to_5th_95th` still asserts the old clamp. The suite must be green before building on this function.

**Files:**
- Modify: `tests/test_build_league_data_tier2.py`

- [ ] **Step 1: Create the branch**

```bash
cd /Users/ryangerda/Development/MLS
git checkout -b feat/second-tier-bidirectional-bridge
```

- [ ] **Step 2: Run the suite to see the failure**

Run: `venv/bin/python -m pytest tests/test_build_league_data_tier2.py -v`
Expected: `test_elo_to_dc_params_clamps_to_5th_95th` FAILS (the function no longer clamps to a discrete 5th/95th percentile).

- [ ] **Step 3: Replace the stale clamp test with a smooth-mapping + floor test**

Replace `test_elo_to_dc_params_clamps_to_5th_95th` with two tests that assert the new contract — continuity (no cliff) and the soft floor (a far-below-floor ELO seeds no weaker than the floor):

```python
def test_elo_to_dc_params_is_continuous_no_cliff():
    """A tiny ELO change near the floor produces a tiny param change (no snap)."""
    from scripts.build_league_data import _elo_to_dc_params
    atk = {f"t{i}": -0.4 + i * 0.05 for i in range(16)}   # spread of params
    dfd = {f"t{i}": 0.4 - i * 0.05 for i in range(16)}
    elo_now = {f"t{i}": 1400 + i * 20 for i in range(16)}  # 1400..1700
    a1, d1 = _elo_to_dc_params(1452.0, atk, dfd, elo_now)
    a2, d2 = _elo_to_dc_params(1448.0, atk, dfd, elo_now)
    assert abs(a1 - a2) < 0.05 and abs(d1 - d2) < 0.05    # smooth, not a step


def test_elo_to_dc_params_soft_floor_protects_subfloor_team():
    """A team far below the ELO floor seeds no weaker than a near-floor team."""
    from scripts.build_league_data import _elo_to_dc_params
    atk = {f"t{i}": -0.4 + i * 0.05 for i in range(16)}
    dfd = {f"t{i}": 0.4 - i * 0.05 for i in range(16)}
    elo_now = {f"t{i}": 1400 + i * 20 for i in range(16)}
    floor_atk, floor_dfd = _elo_to_dc_params(1450.0, atk, dfd, elo_now)   # ~25th pct
    sub_atk, sub_dfd = _elo_to_dc_params(1200.0, atk, dfd, elo_now)        # far below floor
    assert sub_atk >= floor_atk - 1e-9      # attack not weaker than the floor
    assert sub_dfd <= floor_dfd + 1e-9      # defence not worse than the floor
```

- [ ] **Step 4: Run to verify green**

Run: `venv/bin/python -m pytest tests/test_build_league_data_tier2.py -v`
Expected: all PASS (the two new tests + the unchanged high/low and empty-map tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_build_league_data_tier2.py
git commit -m "test: update _elo_to_dc_params tests for smooth+floor mapping"
```

---

## PHASE A — Add Segunda + Ligue 2 as standalone leagues

### Task A1: Register the two divisions in the football-data source

**Files:**
- Modify: `data_pipeline/football_data.py` (`DIV`, `GOALS_ONLY`)
- Test: `tests/test_second_tier_leagues.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_second_tier_leagues.py
from data_pipeline import football_data as fd


def test_segunda_and_ligue2_registered():
    assert fd.DIV["segunda"] == "SP2"
    assert fd.DIV["ligue-2"] == "F2"
    assert "segunda" in fd.GOALS_ONLY
    assert "ligue-2" in fd.GOALS_ONLY
    # they are model sources, not big-5 market sources
    assert "segunda" not in fd.BIG5 and "ligue-2" not in fd.BIG5
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_second_tier_leagues.py -v`
Expected: FAIL with `KeyError: 'segunda'`.

- [ ] **Step 3: Add the codes**

In `data_pipeline/football_data.py`, extend `DIV` and `GOALS_ONLY`:

```python
DIV = {
    "epl": "E0", "la-liga": "SP1", "serie-a": "I1", "bundesliga": "D1", "ligue-1": "F1",
    "championship": "E1", "league-one": "E2", "league-two": "E3",
    "bundesliga-2": "D2", "serie-b": "I2",
    "segunda": "SP2", "ligue-2": "F2",
}
...
GOALS_ONLY = ["championship", "league-one", "league-two", "bundesliga-2", "serie-b",
              "segunda", "ligue-2"]
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_second_tier_leagues.py -v`
Expected: PASS.

- [ ] **Step 5: Smoke-test the live fetch (network)**

Run: `venv/bin/python -c "from data_pipeline.football_data import match_results; d=match_results('segunda'); print('segunda rows', len(d), 'teams', d['home_team'].nunique())"`
Expected: prints a non-zero row count and ~22 teams (current/most-recent season). Repeat for `ligue-2` (~18 teams). If it errors, stop and inspect — do not proceed.

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/football_data.py tests/test_second_tier_leagues.py
git commit -m "feat(data): register Segunda (SP2) + Ligue 2 (F2) as goals-only sources"
```

### Task A2: Add OUTLOOK config + FD→ESPN name map

**Files:**
- Modify: `scripts/build_league_data.py` (`OUTLOOK` dict; `FD_ESPN` dict)
- Test: `tests/test_second_tier_leagues.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_second_tier_leagues.py`:

```python
def test_segunda_ligue2_in_outlook():
    from scripts.build_league_data import OUTLOOK
    assert OUTLOOK["segunda"]["source"] == "footballdata"
    assert OUTLOOK["segunda"]["n"] == 22
    assert OUTLOOK["ligue-2"]["source"] == "footballdata"
    assert OUTLOOK["ligue-2"]["n"] == 18
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_second_tier_leagues.py::test_segunda_ligue2_in_outlook -v`
Expected: FAIL with `KeyError: 'segunda'`.

- [ ] **Step 3: Add OUTLOOK entries** (mirror the `serie-b` entry: `_PROMO(auto, [playoff_lo, playoff_hi], relegate)`, `green_line`, `red_line`). Confirm the exact promotion/relegation counts against the current season format; defaults below match the standard Segunda (2 up, 3–6 playoff, 4 down) and Ligue 2 (2 up, 3–5 playoff, 4 down):

```python
    "segunda":      {"name": "LaLiga 2", "source": "footballdata", "n": 22,
                     "buckets": _PROMO(2, [3, 6], 4), "green_line": 6, "red_line": 4},
    "ligue-2":      {"name": "Ligue 2", "source": "footballdata", "n": 18,
                     "buckets": _PROMO(2, [3, 5], 4), "green_line": 5, "red_line": 4},
```

- [ ] **Step 4: Add FD→ESPN name-map entries.** Generate the diffs first:

```bash
venv/bin/python - <<'PY'
from data_pipeline.football_data import match_results
import urllib.request, json
for lid, slug in (("segunda","esp.2"),("ligue-2","fra.2")):
    fd = set(match_results(lid)["home_team"].unique())
    j = json.load(urllib.request.urlopen(
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/teams?limit=50"))
    espn = {t["team"]["displayName"] for t in j["sports"][0]["leagues"][0]["teams"]}
    print(f"\n== {lid}: football-data names NOT matching an ESPN displayName ==")
    for n in sorted(fd - espn): print("   ", n)
PY
```

For each football-data name that has no exact ESPN match, add a `"<fd name>": "<espn displayName>"` entry under new `"segunda"` and `"ligue-2"` sub-dicts of `FD_ESPN` in `scripts/build_league_data.py` (mirror the `championship` sub-dict). Teams that already match need no entry.

- [ ] **Step 5: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_second_tier_leagues.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_league_data.py tests/test_second_tier_leagues.py
git commit -m "feat(config): OUTLOOK + FD-ESPN name map for Segunda + Ligue 2"
```

### Task A3: Sidebar entries + logos

**Files:**
- Modify: `webapp/leagues.js`
- Modify: `scripts/fetch_foreign_logos.py` (add `esp.2`); regenerate `webapp/data/logos.js`

- [ ] **Step 1: Resolve ESPN league-logo URLs**

```bash
for slug in esp.2 fra.2; do
  curl -s "https://site.api.espn.com/apis/site/v2/sports/soccer/$slug/scoreboard" \
   | python3 -c "import json,sys;d=json.load(sys.stdin);print('$slug', d['leagues'][0].get('logos',[{}])[0].get('href','?'))" 2>/dev/null
done
```
Record the two league-logo URLs (fallback to the `leaguelogos/soccer/500/<id>.png` pattern if the scoreboard omits them).

- [ ] **Step 2: Add `leagues.js` entries** next to La Liga / Ligue 1 (mirror the `serie-b` entry shape). Insert into the array in `webapp/leagues.js`:

```js
{"id":"segunda","name":"LaLiga 2","confederation":"UEFA","status":"live","logo":"<esp.2 logo url>","espn_code":"esp.2"},
{"id":"ligue-2","name":"Ligue 2","confederation":"UEFA","status":"live","logo":"<fra.2 logo url>","espn_code":"fra.2"},
```

- [ ] **Step 3: Add `esp.2` to the logo fetcher.** In `scripts/fetch_foreign_logos.py`, ensure both `esp.2` and `fra.2` are in the `LEAGUES` list (fra.2 is already present; add `esp.2`). Then:

```bash
venv/bin/python scripts/fetch_foreign_logos.py && python3 scripts/build_logo_map.py
```
Expected: both run clean; `logos.js` team count grows.

- [ ] **Step 4: Commit**

```bash
git add webapp/leagues.js scripts/fetch_foreign_logos.py scripts/foreign_logos.json webapp/data/logos.js
git commit -m "feat(webapp): sidebar entries + logos for Segunda + Ligue 2"
```

### Task A4: Build the two leagues + verify rendering

**Files:**
- Generated: `webapp/data/segunda.js`, `webapp/data/ligue-2.js`

- [ ] **Step 1: Build both** (one at a time)

```bash
venv/bin/python scripts/build_league_data.py --league segunda
venv/bin/python scripts/build_league_data.py --league ligue-2
```
Expected: each prints `[<id>] wrote webapp/data/<id>.js … N teams`, exit 0. (If football-data has no current-season data, they render the completed prior season — expected.)

- [ ] **Step 2: Verify in the preview**

Start preview (config `webapp`). For `?league=segunda` and `?league=ligue-2`: `preview_console_logs` level error → none; `preview_screenshot` → the league table, race strip, and projected-finish plot render; crests resolve (via the logo map). Assert via `preview_eval` that `window.LEAGUE_DATA.standings.length` equals 22 / 18 respectively.

- [ ] **Step 3: Commit**

```bash
git add webapp/data/segunda.js webapp/data/ligue-2.js
git commit -m "feat(webapp): build Segunda + Ligue 2 league data"
```

---

## PHASE B — Forward bridge for Spain + France

### Task B1: Register the two new pairs (forward seeding)

**Files:**
- Modify: `scripts/eval/tier_bridge.py` (`_TIER2_PAIRS`)
- Modify: `scripts/build_league_data.py` (`_TIER2_FOR`)
- Modify: `data_pipeline/coefficients.py` (`_TIER1_FOR`, `_TIER2_PRIORS`)
- Test: `tests/test_second_tier_leagues.py`

- [ ] **Step 1: Add the failing test**

```python
def test_forward_pairs_cover_all_big5():
    from scripts.eval.tier_bridge import _TIER2_PAIRS
    from scripts.build_league_data import _TIER2_FOR
    from data_pipeline import coefficients as co
    pairs = set(_TIER2_PAIRS)
    assert ("segunda", "la-liga") in pairs and ("ligue-2", "ligue-1") in pairs
    assert _TIER2_FOR["la-liga"] == "segunda" and _TIER2_FOR["ligue-1"] == "ligue-2"
    # offset readable (falls back to static prior until fitted)
    assert co.tier2_offset("segunda") < 0 and co.tier2_offset("ligue-2") < 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_second_tier_leagues.py::test_forward_pairs_cover_all_big5 -v`
Expected: FAIL (`("segunda","la-liga")` not in pairs).

- [ ] **Step 3: Wire the pairs and static priors**

`scripts/eval/tier_bridge.py` — `_TIER2_PAIRS`:
```python
_TIER2_PAIRS: list[tuple[str, str]] = [
    ("championship", "epl"),
    ("bundesliga-2", "bundesliga"),
    ("serie-b", "serie-a"),
    ("segunda", "la-liga"),
    ("ligue-2", "ligue-1"),
]
```
`scripts/build_league_data.py` — `_TIER2_FOR`:
```python
_TIER2_FOR: dict[str, str] = {
    "epl": "championship",
    "bundesliga": "bundesliga-2",
    "serie-a": "serie-b",
    "la-liga": "segunda",
    "ligue-1": "ligue-2",
}
```
`data_pipeline/coefficients.py` — `_TIER1_FOR` and `_TIER2_PRIORS`:
```python
_TIER2_PRIORS: dict[str, float] = {
    "championship_to_epl": -120.0,
    "bundesliga-2_to_bundesliga": -100.0,
    "serie-b_to_serie-a": -130.0,
    "segunda_to_la-liga": -120.0,
    "ligue-2_to_ligue-1": -120.0,
}
_TIER1_FOR: dict[str, str] = {
    "championship": "epl",
    "bundesliga-2": "bundesliga",
    "serie-b": "serie-a",
    "segunda": "la-liga",
    "ligue-2": "ligue-1",
}
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_second_tier_leagues.py::test_forward_pairs_cover_all_big5 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/tier_bridge.py scripts/build_league_data.py data_pipeline/coefficients.py tests/test_second_tier_leagues.py
git commit -m "feat(bridge): forward tier-2 pairs for Spain (segunda) + France (ligue-2)"
```

---

## PHASE C — Reverse bridge (bidirectional)

### Task C1: `_identify_relegations` (mirror of `_identify_promotions`)

**Files:**
- Modify: `scripts/eval/tier_bridge.py`
- Test: `tests/test_tier_bridge.py`

- [ ] **Step 1: Write the failing test** (mirror `test_identify_promotions_detects_new_teams`)

```python
def test_identify_relegations_detects_dropped_teams():
    import pandas as pd
    # tier-1 results: season 2023 has {A,B,C}; 2024 has {A,B,D} → C relegated in 2024
    df = pd.DataFrame({
        "season": [2023, 2023, 2024, 2024],
        "home_team": ["A", "B", "A", "B"],
        "away_team": ["B", "C", "B", "D"],
    })
    from scripts.eval import tier_bridge as tb
    rel = tb._identify_relegations(df)
    assert rel[2024] == {"C"}            # in 2023, gone in 2024
    assert 2023 not in rel or rel[2023] == set()   # first season → no relegations
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_tier_bridge.py::test_identify_relegations_detects_dropped_teams -v`
Expected: FAIL (`AttributeError: module has no attribute '_identify_relegations'`).

- [ ] **Step 3: Implement** (in `scripts/eval/tier_bridge.py`, next to `_identify_promotions`)

```python
def _identify_relegations(tier1_results: pd.DataFrame) -> dict[int, set[str]]:
    """Return {tier1_season: set_of_teams_relegated_OUT_after_that_season}.

    A team is relegated for season Y's *second tier* if it appears in tier-1
    season Y-1 but NOT in tier-1 season Y. Keyed by the tier-1 season it left
    (Y), which is also the tier-2 season it drops into.
    """
    seasons = sorted(tier1_results["season"].unique())
    out: dict[int, set[str]] = {}
    for s in seasons:
        prev = s - 1
        if prev not in seasons:
            out[s] = set()
            continue
        cur_teams = set(tier1_results.loc[tier1_results["season"] == s, "home_team"]) | \
                    set(tier1_results.loc[tier1_results["season"] == s, "away_team"])
        prev_teams = set(tier1_results.loc[tier1_results["season"] == prev, "home_team"]) | \
                     set(tier1_results.loc[tier1_results["season"] == prev, "away_team"])
        out[s] = prev_teams - cur_teams
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_tier_bridge.py::test_identify_relegations_detects_dropped_teams -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/tier_bridge.py tests/test_tier_bridge.py
git commit -m "feat(bridge): _identify_relegations (relegation mirror of promotion detect)"
```

### Task C2: Reverse-offset collection + fit, written to both directions

**Files:**
- Modify: `scripts/eval/tier_bridge.py` (`_collect_relegated_matches`, extend `fit_all`)
- Test: `tests/test_tier_bridge.py`

- [ ] **Step 1: Write the failing test** for reverse collection (mirror `test_collect_tier_matches_returns_matches_for_promoted_team`, using `mock` for the football-data history; reuse that test's mock fixtures)

```python
def test_collect_relegated_matches_returns_first_tier2_season(monkeypatch):
    import pandas as pd
    from scripts.eval import tier_bridge as tb
    # tier-1: team R present in 2023, gone 2024 (relegated). tier-2: R plays in 2024.
    tier1 = pd.DataFrame({"season":[2023,2024], "home_team":["R","X"], "away_team":["Y","Z"],
                          "home_goals":[1,1], "away_goals":[0,0], "date":["2023-08-01","2024-08-01"]})
    tier2 = pd.DataFrame({"season":[2024], "home_team":["R"], "away_team":["W"],
                          "home_goals":[2], "away_goals":[0], "date":["2024-09-01"]})
    monkeypatch.setattr(tb, "match_results",
                        lambda lid: tier1 if lid == "epl" else tier2)
    monkeypatch.setattr(tb, "_build_fd_elo_history",
                        lambda lid: {"R": ([pd.Timestamp("2023-05-01")], [1600.0]),
                                     "W": ([pd.Timestamp("2024-08-01")], [1480.0])})
    by_season = tb._collect_relegated_matches("championship", "epl")
    assert 2024 in by_season and any(m.promoted_team == "R" for m in by_season[2024])
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_tier_bridge.py::test_collect_relegated_matches_returns_first_tier2_season -v`
Expected: FAIL (`_collect_relegated_matches` undefined).

- [ ] **Step 3: Implement `_collect_relegated_matches`** as the mirror of `_collect_tier_matches`: identify relegations from the tier-1 results, then collect each relegated team's **first tier-2 season** matches (the season it dropped into), with the team's end-of-tier-1 ELO as `promoted_elo` (reuse the `_TierMatch` NamedTuple and the same date-cutoff/ELO-as-of logic, swapping the team source from tier-2-promotions to tier-1-relegations and the match source from tier-1 to tier-2). Show the full function body mirroring `_collect_tier_matches` lines 141–200 with: `promotions = _identify_promotions(...)` → `relegations = _identify_relegations(tier1_df)`; iterate `relegations.items()`; pull matches from `match_results(tier2_lid)` for those teams in that tier-2 season; seed ELO from `tier1_history`.

- [ ] **Step 4: Extend `fit_all`** to fit and emit BOTH directions per pair. For each `(tier2, tier1)` in `_TIER2_PAIRS`: fit forward (existing) → key `f"{tier2}_to_{tier1}"`; fit reverse via `_collect_relegated_matches` + `_fit_offset` → key `f"{tier1}_to_{tier2}"`. Write all keys to `experiments/tier2_offsets.json`. Reverse offset sign is POSITIVE (relegated team is stronger than the tier-2 field).

- [ ] **Step 5: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_tier_bridge.py -v`
Expected: all PASS (new reverse test + existing forward tests unchanged).

- [ ] **Step 6: Commit**

```bash
git add scripts/eval/tier_bridge.py tests/test_tier_bridge.py
git commit -m "feat(bridge): fit reverse (relegation) offsets; emit both directions"
```

### Task C3: `coefficients.tier1_offset` (read the reverse key)

**Files:**
- Modify: `data_pipeline/coefficients.py` (`_TIER1_PRIORS`, `tier1_offset`)
- Test: `tests/test_coefficients.py`

- [ ] **Step 1: Write the failing test**

```python
def test_tier1_offset_is_positive_for_relegated_seeding():
    from data_pipeline import coefficients as co
    # a team relegated INTO the championship seeds ABOVE the championship field
    assert co.tier1_offset("championship") > 0
    assert co.tier1_offset("segunda") > 0
    assert co.tier1_offset("nonexistent") == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_coefficients.py::test_tier1_offset_is_positive_for_relegated_seeding -v`
Expected: FAIL (`tier1_offset` undefined).

- [ ] **Step 3: Implement** (mirror `tier2_offset`, reversed key + positive priors)

```python
_TIER1_PRIORS: dict[str, float] = {
    "epl_to_championship": 120.0,
    "bundesliga_to_bundesliga-2": 100.0,
    "serie-a_to_serie-b": 130.0,
    "la-liga_to_segunda": 120.0,
    "ligue-1_to_ligue-2": 120.0,
}

def tier1_offset(tier2_league_id: str) -> float:
    """ELO offset translating a RELEGATED team's tier-1 ELO down to the tier-2 scale.
    Positive: a dropped top-flight side is strong in the second tier. Fitted value
    from experiments/tier2_offsets.json when available, else the static prior."""
    tier1_lid = _TIER1_FOR.get(tier2_league_id)
    if tier1_lid is None:
        return 0.0
    key = f"{tier1_lid}_to_{tier2_league_id}"
    fitted = _load_tier2()
    if fitted is not None and key in fitted:
        return float(fitted[key])
    return _TIER1_PRIORS.get(key, 0.0)
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_coefficients.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add data_pipeline/coefficients.py tests/test_coefficients.py
git commit -m "feat(coefficients): tier1_offset for reverse (relegated-team) seeding"
```

### Task C4: Reverse seeding path in `build_league_data.py`

**Files:**
- Modify: `scripts/build_league_data.py` (`_get_tier_elo_map`, reverse seeding block)
- Test: `tests/test_build_league_data_tier2.py`

- [ ] **Step 1: Write the failing test** (the build module exposes a `_TIER1_FOR` map = inverse of `_TIER2_FOR`, driving reverse seeding)

```python
def test_build_exposes_tier1_for_inverse_map():
    from scripts.build_league_data import _TIER1_FOR_BUILD, _TIER2_FOR
    # every tier-1 → tier-2 mapping has an inverse tier-2 → tier-1 entry
    for t1, t2 in _TIER2_FOR.items():
        assert _TIER1_FOR_BUILD[t2] == t1
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_build_league_data_tier2.py::test_build_exposes_tier1_for_inverse_map -v`
Expected: FAIL (`_TIER1_FOR_BUILD` undefined).

- [ ] **Step 3: Implement**

In `scripts/build_league_data.py`:
1. Add `_TIER1_FOR_BUILD = {t2: t1 for t1, t2 in _TIER2_FOR.items()}` (named distinctly from coefficients' `_TIER1_FOR` to avoid confusion).
2. Generalise `_get_tier2_elo_map(tier2_lid)` to `_get_tier_elo_map(lid)` (same body, any league id); keep `_get_tier2_elo_map` as a thin alias so existing callers/tests don't break.
3. In the preseason seeding block (currently only the `_TIER2_FOR` promotion path), add a reverse branch: when `lid in _TIER1_FOR_BUILD` (the league being built is a second tier), the tier-1 league is `_TIER1_FOR_BUILD[lid]`; load its ELO map via `_get_tier_elo_map(tier1_lid)`; for each `_pt` in `_promoted_teams` (new to this tier) whose name resolves in the tier-1 ELO map (i.e. relegated, not promoted-from-tier-3), seed `atk[_pt], dfd[_pt] = _elo_to_dc_params(tier1_elo + co.tier1_offset(lid), atk, dfd, elo_now)` and print `[{lid}] relegated {_pt}: tier1_elo=… adj=… DC=(…)`. Teams not in the tier-1 map keep the existing flat prior.

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_build_league_data_tier2.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_league_data.py tests/test_build_league_data_tier2.py
git commit -m "feat(build): reverse seeding path — relegated teams seed from tier-1 ELO"
```

---

## PHASE D — Calibrate, rebuild, verify

### Task D1: Fit all offsets (both directions)

**Files:**
- Generated: `experiments/tier2_offsets.json`

- [ ] **Step 1: Run the fitter**

```bash
venv/bin/python -m scripts.eval.tier_bridge   # or the module's fit_all entry point
```
Expected: prints per-pair, per-direction fitted offsets + LOSO Brier; writes `experiments/tier2_offsets.json` with 5 forward + 5 reverse keys. Forward keys negative, reverse keys positive.

- [ ] **Step 2: Sanity-check the JSON**

```bash
python3 -c "import json; d=json.load(open('experiments/tier2_offsets.json')); print(len(d),'keys'); [print(k,v) for k,v in sorted(d.items())]"
```
Expected: 10 keys; every `*_to_<tier1>` negative, every `<tier1>_to_*` positive; magnitudes in the ~80–200 ELO range. Investigate any sign flip or |offset| > 300 before continuing.

- [ ] **Step 3: Commit**

```bash
git add experiments/tier2_offsets.json
git commit -m "feat(calibration): fit bidirectional tier offsets for all big-5 pairs"
```

### Task D2: Offline reverse-seeding validation

**Files:**
- Create: `scripts/validate_relegated_seeding.py` (mirror `scripts/validate_promoted_seeding.py`)

- [ ] **Step 1: Write the reproduction** — mirror `validate_promoted_seeding.py` but for the reverse case: load a cached second-tier frame (e.g. `data/football_data` Championship results), fit DC + ELO, seed a known relegated team (e.g. a side dropped from the EPL) via `_elo_to_dc_params(tier1_elo + co.tier1_offset("championship"), …)`, and print its strength vs the tier-2 field.

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=. venv/bin/python scripts/validate_relegated_seeding.py`
Expected: the relegated team seeds in the **promotion-favourite band** (top third of the second tier), NOT flat-prior weak. Record the numbers.

- [ ] **Step 3: Commit**

```bash
git add scripts/validate_relegated_seeding.py
git commit -m "test: offline reproduction for reverse (relegated) seeding"
```

### Task D3: Rebuild affected leagues + dashboard verification

**Files:**
- Generated: `webapp/data/{la-liga,ligue-1,epl,serie-a,bundesliga,segunda,ligue-2,championship,serie-b,bundesliga-2}.js`

- [ ] **Step 1: Rebuild, one at a time**

```bash
for lg in la-liga ligue-1 epl serie-a bundesliga segunda ligue-2 championship serie-b bundesliga-2; do
  venv/bin/python scripts/build_league_data.py --league "$lg" || echo "FAILED $lg"
done
```
Expected: each exits 0. Capture the `promoted`/`relegated` seeding log lines.

- [ ] **Step 2: Calibration check** — for each preseason league, confirm via a small script (mirror the Task-14 check): promoted teams cluster in the relegation third of the top flight; relegated teams cluster in the promotion third of the second tier; no team at >97% relegation or seeded mid-table when it shouldn't be. Specifically confirm Ligue 1's Le Mans/Troyes are now seeded from Ligue 2 (not the flat prior 97.8%).

- [ ] **Step 3: Dashboard verification** — preview `?league=segunda`, `?league=ligue-2`, `?league=ligue-1`, plus one second tier showing a relegated team. `preview_console_logs` error → none on each; `preview_screenshot` of each. Run `make test` (full suite) → all green.

- [ ] **Step 4: Commit**

```bash
git add webapp/data/*.js
git commit -m "feat(webapp): rebuild leagues with bidirectional cross-tier seeding"
```

---

## PHASE E — Docs + finish

### Task E1: Documentation

**Files:** `docs/PLAN.md`, `docs/CURRENT_STATE.md`, `docs/PROJECT_HISTORY.md`, delete the plan file

- [ ] **Step 1:** Blockquote entry at the top of `docs/PLAN.md` (date 2026-06-28: Segunda + Ligue 2 added; bidirectional tier bridge; per-league offsets).
- [ ] **Step 2:** Update `docs/CURRENT_STATE.md` — the tier-bridge / promoted-team section gains the reverse direction + the two new pairs; add `segunda`/`ligue-2` to any league inventory.
- [ ] **Step 3:** Dated entry in `docs/PROJECT_HISTORY.md`; **delete** `docs/superpowers/plans/2026-06-28-second-tier-bidirectional-bridge.md`.
- [ ] **Step 4: Commit** `git commit -am "docs: record second-tier completion + bidirectional bridge"`

### Task E2: Finish the branch

- [ ] Use superpowers:finishing-a-development-branch — run `make test` (must be green), present options, and present before/after of the calibration (Le Mans/Troyes, a relegated team) + the new Segunda/Ligue 2 pages.

---

## Self-review (coverage map)

- Spec §3.1 (data source) → A1. §3.2 (OUTLOOK) → A2. §3.3 (sidebar) → A3 + A4. §3.4 (bidirectional bridge) → C1 (relegation detect), C2 (reverse fit + both-direction output), D1 (fit). §3.5 (reverse seeding) → C4; `tier1_offset` → C3; forward pairs → B1. §3.6 (logos) → A3. §5 (calibration) → D1–D3. §6 (testing) → D2 + per-task pytest + D3 `make test`. §8 (docs) → E1.
- Pre-req not in spec but required: Task 0 (repair the test the 2026-06-28 calibration fix broke) — without it `make test` is red before we start.
- Naming: build-module inverse map is `_TIER1_FOR_BUILD` (distinct from coefficients' `_TIER1_FOR`); reverse-read is `co.tier1_offset`; relegation detector is `_identify_relegations`; reverse collector is `_collect_relegated_matches`. Consistent across all tasks.
- No placeholders in load-bearing code (`_identify_relegations`, `tier1_offset`, the DIV/OUTLOOK/leagues.js/coefficients entries, the test bodies are concrete). C2/C4 reference the exact existing functions to mirror with the precise transformation, rather than restating ~60 lines verbatim.
