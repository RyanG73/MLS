# Continental Competitions — Expansion to Europa / Conference / Concacaf (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` tracking.

**Goal:** Extend the UCL vertical slice to the four remaining active continental competitions, accounting for their genuinely different current formats, and remove the defunct Concacaf League from the sidebar.

**Architecture:** Reuse the `cross_league` strength seam and `bracket_sim` engine. Two comps (Europa, Conference) are config-only on the existing league-phase engine. Two (Concacaf Champions Cup, Leagues Cup) require new `bracket_sim` paths. The MLS champion and existing leagues stay untouched (parity |Δ|=0.0000).

**Current formats (researched 2026-06-17):**
| Comp | Format |
|---|---|
| Europa (`uefa.europa`) | 36-team league phase, **8** games each → top-8 auto + 9–24 playoff → R16/QF/SF/Final (single-leg final). Identical to UCL. |
| Conference (`uefa.europa.conf`) | 36-team league phase, **6** games each → same knockout. |
| Concacaf Champions Cup (`concacaf.champions`) | **27 teams, pure knockout.** Round One (22 teams → 11 two-leg ties → 16 with 5 byes), R16, QF, SF two-legged, **single-leg Final**. No league phase. |
| Leagues Cup (`usa.league_cup` — verify) | 36 teams (18 MLS + 18 Liga MX). **Two parallel league tables** (MLS-only, Liga MX-only); each club plays 3 cross-league games, **no draws (PK決)**; top-4 per table → 8-team single-elim (QF/SF/Final). |
| Concacaf League | **Defunct** (last 2023). REMOVE from registry. |

**Strength note:** UEFA comps use the existing UEFA coefficient anchor. Concacaf comps need Concacaf-internal league offsets (MLS, Liga MX, Central-American/Caribbean leagues) — these only need correct RELATIVE spacing within a Concacaf comp (match_lambdas uses strength *differences*, and Concacaf teams never meet UEFA teams). MLS ELO loads from `data/parity_frame.parquet`; Liga MX from `espn_soccer.liga_mx_frame()`; big-5 from Understat.

**Spec:** `docs/superpowers/specs/2026-06-16-continental-competitions-design.md` (Approach A).

---

## Task E1: Coefficient + strength extensions

**Files:** Modify `data_pipeline/coefficients.py`; Test `tests/test_coefficients.py`.

Add Concacaf-internal league offsets and Concacaf club strengths; extend UEFA club strengths for common Europa/Conference entrants.

- [ ] **Step 1 — tests** (append to `tests/test_coefficients.py`):
```python
def test_concacaf_offsets_are_relative_not_uefa_scale():
    # MLS is the Concacaf reference (offset 0); Liga MX slightly above; CA leagues below.
    assert co.league_offset("mls") == 0.0
    assert co.league_offset("liga-mx") > co.league_offset("mls")
    assert co.league_offset("liga-mx") <= 60  # modest, not a UEFA-sized gap

def test_concacaf_club_strength_below_modeled_top():
    # An unmodeled Central-American club sits well below MLS/Liga MX modeled range.
    assert co.club_strength("Alajuelense") < 1550
```

- [ ] **Step 2 — implement.** In `coefficients.py`:
  - Add to `_LEAGUE_COEFF` handling: Concacaf offsets are NOT UEFA coefficients. Introduce a separate `_CONCACAF_OFFSET` dict `{"mls":0.0, "liga-mx":30.0}` and make `league_offset` check it: if `league_id` in `_CONCACAF_OFFSET`, return that value directly (bypassing the UEFA `_K_COEFF` formula). Document that Concacaf offsets are internally-relative (MLS=0 ref) and the +30 Liga MX prior reflects recent near-parity with a slight Liga MX edge.
  - Extend `_CLUB_STRENGTH` with common Europa/Conference non-big-5 entrants (e.g. Roma, Lazio, Tottenham→modeled; but add Rangers, Galatasaray, Fenerbahce, Lyon, Real Sociedad→ many are modeled; add the genuinely-unmodeled: Olympiacos, Ferencvaros, Slavia Prague, Braga, Real Betis, Villarreal[modeled], etc.) on the ELO scale (~1450–1620). AND common Concacaf unmodeled clubs (Alajuelense, Saprissa, Herediano, Motagua, Olimpia, Cavalier, Forge FC, etc.) at ~1380–1500.
  - Keep all existing UEFA values and functions unchanged.

- [ ] **Step 3** — `venv/bin/python -m pytest tests/test_coefficients.py -v` (all pass).
- [ ] **Step 4** — commit `Continental: Concacaf offsets + expanded club strengths`.

---

## Task E2: Europa + Conference format specs (config only)

**Files:** Modify `scripts/eval/bracket_sim.py`; Test `tests/test_bracket_sim.py`.

- [ ] **Step 1 — test** (append):
```python
def test_europa_conference_formats():
    assert bs.FORMATS["europa"]["phase"]["matches_each"] == 8
    assert bs.FORMATS["conference"]["phase"]["matches_each"] == 6
    for c in ("europa","conference"):
        assert bs.FORMATS[c]["phase"]["auto_advance"] == 8
        assert bs.FORMATS[c]["phase"]["playoff"] == (9,24)
        assert [r["round"] for r in bs.FORMATS[c]["ko"]] == ["R16","QF","SF","Final"]
```

- [ ] **Step 2 — implement.** Add `"europa"` (clone of `"ucl"`) and `"conference"` (same but `matches_each: 6`) entries to `FORMATS`. No engine change.
- [ ] **Step 3** — pytest the file (all pass).
- [ ] **Step 4** — commit `Continental: Europa + Conference format specs`.

---

## Task E3: Pure-knockout engine path (Concacaf Champions Cup)

**Files:** Modify `scripts/eval/bracket_sim.py`; Test `tests/test_bracket_sim.py`.

The Champions Cup has no league phase: 27 teams, top-5 (by strength/seed) bye to R16, the other 22 play Round One (11 two-leg ties), winners join the 5 byes = 16 → R16/QF/SF (two-leg) → single-leg Final.

- [ ] **Step 1 — test** (append):
```python
class TestPureKnockout:
    def test_concacaf_cc_format(self):
        f = bs.FORMATS["concacaf-champions"]
        assert f["phase"]["type"] == "bracket"
        assert f["phase"]["teams"] == 27
        assert f["phase"]["byes"] == 5

    def test_pure_knockout_simulate_champion_odds_sum_to_one(self):
        field=[{"team":f"T{i}","strength":1700-i*8} for i in range(27)]
        out=bs.simulate("concacaf-champions", field, N=300, seed=1)
        assert abs(sum(t["odds"]["win"] for t in out["field"])-1.0)<1e-6
        # top seed should out-favor the weakest
        byt={t["team"]:t for t in out["field"]}
        assert byt["T0"]["odds"]["win"] > byt["T26"]["odds"]["win"]
        # pure-knockout has no league standings
        assert out["standings"] == []
```

- [ ] **Step 2 — implement.** Add `FORMATS["concacaf-champions"]`:
```python
"concacaf-champions": {
    "phase": {"type": "bracket", "teams": 27, "byes": 5, "round_one": "RoundOne"},
    "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
           {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
    "away_goals": False, "extra_time": True, "pens": True,
},
```
Then branch `simulate()` on `fmt["phase"]["type"]`:
- For `"league"` (existing UCL/Europa/Conference): unchanged.
- For `"bracket"`: NEW path `_simulate_bracket(comp_id, field, N, seed)`:
  - Seed teams by strength descending. Top `byes` go straight to R16; the remaining `teams-byes` play Round One as two-leg ties (pair strongest-vs-weakest by seed, standard bracket seeding). Round One winners + byes = the R16 field (pad/truncate to power of two = 16).
  - Then run the `ko` rounds exactly like the league path's bracket loop (two-leg / single-leg final, reach[] accounting, champion).
  - Return `{"standings": [], "field": [...with odds incl. a "RoundOne" reach for non-bye teams...]}`. Field entries get `odds` with the ko rounds + `"win"`, plus `"bye": bool`. No auto_advance/playoff/eliminated keys (pure knockout).
  - Normalize champion odds to sum to 1 (same as the league path).

Keep the existing league-path `simulate` logic intact; factor the shared KO-rounds loop into a helper `_run_ko(alive, fmt, strengths, rng, reach, win)` used by both paths if clean, else duplicate carefully.

- [ ] **Step 3** — pytest the file (all pass, incl. prior tests).
- [ ] **Step 4** — commit `Continental: pure-knockout bracket path (Concacaf Champions Cup)`.

---

## Task E4: Two-table group-phase engine path (Leagues Cup)

**Files:** Modify `scripts/eval/bracket_sim.py`; Test `tests/test_bracket_sim.py`.

Leagues Cup: 18 MLS + 18 Liga MX; each club plays 3 cross-league games (no draws → PK decides level games for table points: win=3, PK-win=... use 3 for a win, 0 for a loss; simplest: simulate goals, if level decide by PK and award 3/0). Two separate tables (by `league`), top-4 per table → 8 teams → single-elim QF/SF/Final (single-leg, neutral=False for QF/SF, neutral final).

- [ ] **Step 1 — test** (append):
```python
class TestTwoTableGroup:
    def test_leagues_cup_format(self):
        f=bs.FORMATS["leagues-cup"]
        assert f["phase"]["type"]=="two_table"
        assert f["phase"]["advance_per_table"]==4

    def test_leagues_cup_simulate(self):
        field=([{"team":f"MLS{i}","league":"mls","strength":1600-i*5} for i in range(18)]+
               [{"team":f"MX{i}","league":"liga-mx","strength":1620-i*5} for i in range(18)])
        out=bs.simulate("leagues-cup", field, N=300, seed=2)
        assert abs(sum(t["odds"]["win"] for t in out["field"])-1.0)<1e-6
        # two tables of 18 each in standings
        assert len(out["standings"])==36
        assert {s.get("table") for s in out["standings"]} == {"mls","liga-mx"}
```

- [ ] **Step 2 — implement.** Add `FORMATS["leagues-cup"]`:
```python
"leagues-cup": {
    "phase": {"type": "two_table", "teams": 36, "games_each": 3,
              "advance_per_table": 4, "no_draws": True},
    "ko": [{"round": "QF", "legs": 1}, {"round": "SF", "legs": 1},
           {"round": "Final", "legs": 1, "neutral": True}],
    "extra_time": True, "pens": True,
},
```
NEW path `_simulate_two_table(comp_id, field, N, seed)`:
- Split field by `t["league"]` into two groups. For each Monte-Carlo run: schedule each club `games_each` cross-league matches (pair MLS vs Liga MX randomly, balanced); simulate goals; if level, PK coin-flip (logistic on strength) decides the winner → 3/0 (no draw points). Accumulate per-table points+GD; rank each table; mark top-`advance_per_table` per table.
- The 8 advancers (4+4) seed a single-elim bracket (cross-seed: MLS1 v MX4, etc.); run single-leg QF/SF + neutral Final via `sim_single_leg`.
- Standings: 36 rows, each with `team`, `league`, `table` (=league), `advance` (P(top-4 in its table)), `strength`. Field: each with `odds` {QF,SF,Final,win} + advance.
- Champion odds normalized to 1.

- [ ] **Step 3** — pytest the file (all pass).
- [ ] **Step 4** — commit `Continental: two-table group path (Leagues Cup)`.

---

## Task E5: ESPN adapter — new slugs + Leagues Cup resolution

**Files:** Modify `data_pipeline/espn_continental.py`.

- [ ] **Step 1 — add slugs** to `SLUGS`: `"europa":"uefa.europa"`, `"conference":"uefa.europa.conf"`, `"concacaf-champions":"concacaf.champions"` (already present — verify), and resolve Leagues Cup: try `"usa.league_cup"`, `"concacaf.leagues_cup"`, `"mex.league_cup"` via a smoke fetch and keep whichever returns matches. Add the working one as `"leagues-cup"`.
- [ ] **Step 2 — smoke-run** each new slug:
```bash
for c in europa conference concacaf-champions leagues-cup; do
  venv/bin/python -m data_pipeline.espn_continental --comp $c --from-year 2023 --to-year 2025
done
```
Expect non-zero matches for each. If Leagues Cup has no working ESPN slug, report BLOCKED for that comp only and proceed with the other 3 (note it for the user).
- [ ] **Step 3** — commit `Continental: ESPN slugs for europa/conference/concacaf-champions/leagues-cup`.

---

## Task E6: Build script — META, frame routing, name maps, build all

**Files:** Modify `scripts/build_continental_data.py`.

- [ ] **Step 1 — extend `META`** with europa, conference (phases `["league","knockout"]`), concacaf-champions (phases `["knockout"]`), leagues-cup (phases `["group","knockout"]`), each with name/confederation/format_label.
- [ ] **Step 2 — frame routing.** Generalize `_league_elos(league_id)` to route by source: big-5 → `canonical_frame`; `liga-mx` → `espn_soccer.liga_mx_frame()`; `mls` → load `data/parity_frame.parquet` (ASA names). Cache per league. Add an MLS ESPN→ASA name map and a Liga-MX ESPN→key map as needed (verify by running and checking for `team_strength` WARNINGs).
- [ ] **Step 3 — extend `_ESPN_TO_MODELED`** for Europa/Conference big-5 entrants, and for Concacaf comps map MLS + Liga MX teams (league ids `mls` / `liga-mx`). Unmodeled clubs fall through to coefficients.
- [ ] **Step 4 — build all 4:**
```bash
for c in europa conference concacaf-champions; do
  venv/bin/python scripts/build_continental_data.py --comp $c --season 2024 --sims 5000
done
venv/bin/python scripts/build_continental_data.py --comp leagues-cup --season 2025 --sims 5000
```
Confirm each writes `webapp/data/<c>.js`; champion favorites are sensible modeled clubs; champion odds sum ~1.0; for Concacaf comps verify MLS/Liga MX teams resolve as modeled (no baseline mis-rating) and the strongest are near the top.
- [ ] **Step 5** — commit `Continental: build europa/conference/concacaf-champions/leagues-cup data`.

---

## Task E7: Webapp — pure-knockout + group views; verify

**Files:** Modify `webapp/index.html`.

`renderKnockout()` currently assumes `phases:["league","knockout"]`. Generalize:
- [ ] **Step 1** — pure-knockout (`phases:["knockout"]`, Concacaf CC): show ONLY the Knockout sub-tab (no League Phase table); the champion-odds leaderboard columns come from `D.outlook.rounds` (include RoundOne if present). Already partially handled (the `phases.includes('league')` guard) — verify and fix the leaderboard for a `byes`/RoundOne column.
- [ ] **Step 2** — two-table group (`phases:["group","knockout"]`, Leagues Cup): the "Group" sub-tab renders TWO tables side by side (MLS table, Liga MX table) from `D.standings` split by `table`, with the top-4 cut-line each; the Knockout sub-tab shows the 8-team bracket + champion odds. Add a `phases.includes('group')` branch in `renderKnockout`.
- [ ] **Step 3 — verify in-browser** (preview server): load `?league=europa`, `?league=conference`, `?league=concacaf-champions`, `?league=leagues-cup`. Confirm each renders the right sub-tabs, no console errors, sensible favorites; MLS + UCL + a table league regression-clean. Capture a screenshot of Leagues Cup (two tables) and Concacaf CC (bracket).
- [ ] **Step 4** — commit `Continental: webapp pure-knockout + two-table group views`.

---

## Task E8: Integration — remove Concacaf League, go-live, docs

**Files:** Modify `scripts/fetch_league_teams.py`, `webapp/leagues.js`, `docs/*`.

- [ ] **Step 1** — in `fetch_league_teams.py` REGISTRY: **delete** the `concacaf-league` row; flip `europa`, `conference`, `concacaf-champions`, `leagues-cup` `soon`→`live`. Delete `webapp/data/concacaf-league.js` if present.
- [ ] **Step 2 — gates:** `venv/bin/python -m pytest tests/ -q` (all pass) and `venv/bin/python scripts/parity_check.py` (|Δ|=0.0000).
- [ ] **Step 3** — `venv/bin/python scripts/fetch_league_teams.py` (regenerate leagues.js; expect 17 live / 1–2 soon, no concacaf-league).
- [ ] **Step 4 — in-browser final check:** all 4 new comps live in sidebar + render; MLS/UCL/table leagues clean.
- [ ] **Step 5 — docs:** update PLAN.md (Phase 7 block), HANDOFF.md, CODE_WALKTHROUGH.md §12 (the 4 formats + the two new engine paths + the Concacaf strength offsets + Concacaf League removal).
- [ ] **Step 6** — commit `Continental: 4 comps live (Europa/Conference/Concacaf CC/Leagues Cup), Concacaf League removed + docs`.

---

## Notes / risks
- **Leagues Cup ESPN slug is the main unknown** (Task E5). If unresolved, ship the other 3 and flag it.
- The pure-knockout and two-table paths should factor the shared KO-rounds loop where clean, but correctness > DRY — duplicate if factoring is risky.
- Concacaf offsets are internally-relative; do not attempt to make them comparable to the UEFA scale (the two confederations never meet).
- Keep champion-odds normalization and the `reach[]`-sums-per-round invariant in both new paths (the UCL review verified R16=16, QF=8, SF=4, Final=2 — the new paths have different round sizes but each round's reach should equal that round's entrant count).
