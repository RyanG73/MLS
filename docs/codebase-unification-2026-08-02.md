# Codebase Unification Review — ledger

> **Dated evidence, as of 2026-08-02.** Superseded by `docs/STATUS.md`. Figures are as-of;
> re-measure before quoting. Executed against `docs/prompts/codebase-unification-review.md`
> under its §0 rule: nothing the system outputs may change.

**Baseline:** HEAD `1cf82a7`, 4,358 artifacts content-hashed.
`parity-check` ✅ (avg 0.6330 vs target 0.6331, |Δ|=0.0001) · `gate-self-test` ✅ 8/8 ·
`pytest` ✅ 1,681 passed / 14 skipped · `validate` ❌ **red before any change** — see E1.

**Closing state (2026-08-04, HEAD `924e0a3`):** this review removed **0 lines of code** and moved
**0 artifact hashes outside generated output**. 392 payload hashes moved, all of them CI's four
data-refresh commits landing between baseline and close — verified by filtering to non-generated
paths, which returns empty.

`pytest` now reports **2 failed / 1,679 passed**. Neither failure is caused by this review; both
are CI data state, and both are escalations E2/E3 doing their job:
`test_power_payload_agrees_with_the_league_payloads` (E3, the Austria duplication) and
`test_club_pages_are_useful_and_structured` (`team_intelligence` artifacts three days behind their
payloads — `refresh-daily.yml` runs `build_team_intelligence.py` at line 184, after
`build_league_data.py` at 102, so the ordering is right and the step is either failing non-fatally
or being skipped; worth a look, filed under E3's sibling).

---

## Escalations

### E1 — the smoke-test reference is stale, on untouched `main`

`make validate` fails: 2024 `ens_stacked_brier = 0.6360` against a pinned reference of `0.6346`,
tolerance 0.001. **This predates the review.**

What it is not: the UEFA refit. `scripts/eval_baseline.py` contains zero references to
`league_bridge`, `coefficients`, `global_elo` or `league_offset` — it cannot reach that code.

What it probably is: the reference was pinned in `65a4a49`; `2e168ff` (Transfermarkt total value
rather than per-player average) and `7d9d554` (un-gate the preseason value tilt) landed after it
and move features for every season including 2024.

Why it is not alarming: `make parity-check` passes at |Δ|=0.0001 on the 4-fold champion average.
Only the single-season smoke gate, at a tolerance three times tighter, has drifted.

**Owner decision.** Re-pinning is a model change and §5 puts it out of scope for this review.
Until then the gate is narrowed per §2d: manifest + `parity-check` + `gate-self-test` + `pytest`,
with `validate`'s failing value recorded at exactly `0.6360`.

### E2 — `config/settings.yaml` is the *legacy stack's* config

**Revised 2026-08-04 after §3.3.** The original finding stands but the cause was wrong.

Its header states: *"All tunable parameters live here. Scripts import via config.SETTINGS."*

Measured across `scripts/`, `models/`, `features/`, `data_pipeline/`, `server/`, `api/`:

| Section | Production readers |
|---|---|
| `market` | **1** — `data_pipeline/odds_log.py`, and only `sport_key`, `regions`, `odds_format` |
| `elo`, `dixon_coles`, `features`, `gradient_boost`, `ensemble`, `bayesian`, `risk`, `backtest`, `notifications`, `pre_match`, `weather`, `tuning`, `dashboard`, `news`, `data`, `database` | **0** |

**Editing `elo.k_factor`, `dixon_coles.time_decay_half_life_days`, or
`market.default_edge_threshold_pct` changes nothing, silently.** The last is the "Edge threshold:
8%" key decision in `CLAUDE.md`.

The values are currently *correct* — every one matches `CLAUDE.md` and the hardcoded call sites —
so there is no active bug today. There is also no mechanism keeping them in sync: edit either side
and they diverge with nothing to notice.

`models/research_model.py`, the canonical model, references the config only in a comment.
`eval_baseline.py:287` reads `xg_windows` from a CLI arg with a hardcoded `(3, 5, 10, 15)`
fallback, not from the config.

**The cause, found in §3.3:** `legacy/` imports the *active* `config/` package and reads **12 of
the 18 sections** — `elo`, `dixon_coles`, `features`, `gradient_boost`, `bayesian`, `ensemble`,
`dashboard`, `news`, `data`, `database`, `market`, `_repo_root`. The file is not abandoned; it is
the archived Postgres/Streamlit stack's config, and the webapp/harness path that replaced that
stack in June never adopted it. It hardcodes its own values instead.

That makes E2 and the `legacy/` decision **one decision, not two**. Delete `legacy/` and those 12
sections become unambiguously dead, at which point removing them is obvious rather than a judgment
call. Keep `legacy/` and the config keeps a real consumer — just not the one its header claims.

**Owner decision, three options:** wire the active call sites to `SETTINGS` (output-neutral today
since values match, but it is model-path surgery); delete `legacy/` and the sections together; or
retitle the file so it stops claiming authority over a path that does not read it. §6.4 says
report, do not fix inside this pass.

### E3 — duplicated standings rows in `austria-bundesliga`, live on production

Found 2026-08-04 by the regression test written in §3.2
(`test_power_payload_agrees_with_the_league_payloads`), firing on CI's own output. It was written
to catch staleness; it caught duplication instead.

`webapp/data/austria-bundesliga.js` carries **15 standings rows for 13 distinct `team_id`s**. Two
clubs appear twice *with different ratings*:

| Club | `team_id` | `global_elo` (row 1) | `global_elo` (row 2) |
|---|---|---:|---:|
| Rapid Vienna | `v1:ed45f905a49caf9c` | 1355 | 1305 |
| Austria Vienna | `v1:74010312f0ded49c` | 1305 | 1374 |

**User-visible:** `https://entenser.com/leagues/austria-bundesliga/` links `clubs/austria-vienna/`
and `clubs/lask-linz/` four times each. **Ladder-visible:** `power.js` carries four Vienna rows
instead of two, so the global ladder counts two clubs that do not exist.

*Inference:* the Austrian Bundesliga plays a championship/relegation **split** after the regular
phase, and `outlook.mode` is `table` — the format `CURRENT_STATE.md` records as "approximated as a
plain table". The split handling looks like it is emitting a row per phase. A club's ELO is a
property of the club, not of the phase, so two different `global_elo` values for one `team_id` is
wrong under any reading.

**Contained:** exactly one league of 78. Every other payload has zero duplicate `team_id`s.

**Handed to `docs/prompts/league-qa-audit.md`, not fixed here** — the unification prompt's own
header assigns data correctness to that sibling and says to log and hand over.

---

## Ledger

| File / area | Lines | Action | Evidence | Proof | Rationale |
|---|---:|---|---|---|---|
| 8 merged local branches | — | **DELETE** ✅ done | A | 0 hashes moved of 4,358 | `git rev-list --left-right --count` showed 0 commits absent from `main`; removed with `git branch -d`, which refuses anything unmerged |
| `.claude/worktrees/adoring-lehmann-a92938` | — | **DELETE** ✅ done | A | 0 hashes moved | Detached, no uncommitted work, left by a finished background task |
| `config/settings.yaml` model sections | ~40 | **ESCALATE** | A | 17 of 18 sections have 0 production readers | E2 — design decision, not cleanup |
| 2024 smoke reference | 1 | **ESCALATE** | A | `validate` red at baseline | E1 — model decision |
| `claude/infallible-jennings-948dec` | 667 | **DELETE** — proposed | B | `d4a0a38` and `eb9abfa` produce byte-identical `continuous_tier_elo.py` (`42fd7eeded68`); `clever-meninsky` adds 135 lines on top | Superseded duplicate. Unmerged branch, so owner decision |
| `claude/clever-meninsky-e0cbc4` | 846 | **LEAVE** | B | Touches `build_league_data.py` | Cross-tier ELO seeding is model-affecting; merging in a cleanup pass fails §0/§5. Owner decision: merge, abandon, or schedule as its own gated experiment |
| `claude/mls-prediction-dashboard-C2mQM` | 0 ahead | **LEAVE** | B | `CLAUDE.md` retains it for history | Decision still stands. The research-track references that pointed *agents* at it were fixed separately |
| `origin/live-data` | 1 ahead | **LEAVE** | B | Feeds the `workflow_run` deploy chain | §3.6 explicitly warns against simplifying this away |
| `scripts/season_state_report.py` | 205 | **LEAVE** | B | Only orphan of 97 scripts; writes solely to gitignored `output/` | A private diagnostic for exactly the question the 2026-08-21 European season rollover raises — which leagues still show last season's final table versus a projection for the new one. Deleting a working diagnostic 19 days before the scenario it diagnoses is poor timing; it is in no build path so it costs nothing to keep. Revisit after the rollover |
| `_clean` in `build_league_data.py` + `build_dashboard_data.py` | ~2 | **HOIST** — proposed | C | Only byte-identical function across six builders | Net-neutral churn in the model path for one helper. Not worth the regression surface |

---

## Totals

| | |
|---|---|
| Branches retired | **8** (12 local → 4) |
| Worktrees pruned | **1** |
| Orphan scripts found | **1 of 97** |
| Duplicate functions across 6 builders | **1** |
| Diverging constants | **0** |
| Lines removed from the active tree | **0** |
| Artifact hashes moved | **0 of 4,358** |
| Escalations raised | **2** |
| Lines recommended for deletion (owner call) | **9,097** — all in `legacy/` |
| Diverging pins / dead Make targets / dead vercel routes | **0 / 0 / 0** |
| Rotting tests | **0** — all 14 skips deliberate, 0 xfails |

## What this review did *not* find — a real result per §7

- **No orphan scripts worth deleting.** 96 of 97 are referenced by a workflow, Make target, shell
  script, test, or doc. The prompt's warning that "a Python import graph will lie to you" was
  correct, and checking YAML/Make/shell/JSON/Markdown is what kept the count honest.
- **No copy-paste lineage between the builders.** §3.2.2 predicted near-identical siblings across
  `build_league_data` / `build_continental_data` / `build_dashboard_data` / `build_static_pages`.
  They share *shape*, not code: exactly one byte-identical function between any pair.
- **No diverging constants.** Every hardcoded `K=25, home_adv=80, regress=0.40` across nine call
  sites agrees with `CLAUDE.md` and with `config/settings.yaml`. The problem is the opposite of
  the one predicted — see E2.

The subtractive premise did not hold for `scripts/`. The reduction available here is in `legacy/`
(9,097 lines, §3.3) and dated docs, not in the active build surface.

---

## §3.3 — `legacy/` disposition (9,097 lines)

Every isolation check passes. Nothing active imports it (`grep` for `from legacy` / `import legacy`
across `scripts/`, `models/`, `features/`, `data_pipeline/`, `server/`, `api/`, `config/` returns
nothing). Pytest collects **0** legacy tests of 1,695. No CI workflow mentions it.
`requirements-legacy.txt` is installed nowhere.

One coupling runs the other way: **`legacy/` imports the active `config/` package** (see E2).

| Subtree | Lines | Recommendation |
|---|---:|---|
| `dashboard/` | 1,767 | **Delete** — Streamlit UI for the archived stack; the webapp replaced it |
| `models/` | 1,799 | **Delete** — `models/research_model.py` is canonical and shares no code |
| `data_pipeline/` | 1,732 | **Delete** — the active `data_pipeline/` is a separate implementation |
| `features/` | 1,469 | **Delete** — feature building lives in `scripts/eval/feature_builders.py` |
| `scripts/` | 1,454 | **Delete** |
| `market/` | 546 | **Delete — the carve-out is obsolete.** `legacy/README.md` keeps it "for the future CLV/edge workstream". That workstream shipped elsewhere: `scripts/bet_ledger.py:39` sets `KELLY_FRACTION = 0.25` with `_quarter_kelly_units()`, and CLV is computed in `data_pipeline/market.py:clv_pp`. Reserved, then superseded |
| `tests/` | 187 | **Delete** with their subject |
| `r_requirements.R` | — | **Delete** — the Bayesian R path is `enabled: false` and unreferenced |

**Recommendation: delete `legacy/` entirely, as one owner decision.** It is 9,097 lines — the
largest single reduction available in this repo, and larger than everything §3.2 found combined.
Git retains it. Coupled to E2: deleting it resolves the config question at the same time.

**Regardless of that decision — declare the pytest exclusion.** Legacy is currently skipped by
accident, not by configuration. `pytest legacy/` errors on collection today. One `norecursedirs`
or `testpaths` entry in `pyproject.toml` makes the intent explicit and cannot regress.

## §3.4 — monoliths

`webapp/index.html` is now **6,179** lines. The prompt's suggested attack was CSS rules with no
matching selector. A detector over the `<style>` blocks found **59 dead selectors of 678**,
touching ~82 rule lines.

**Not actioned — evidence C.** The detector has a demonstrated false-positive mode, and it hit it:
it flagged `rc-prov-mixed`, a class added on 2026-08-01 and verified rendering on production the
same day. It is built dynamically at `index.html:3768` as `class="rc-prov rc-prov-${prov}"`, which
no static scan can see. Several others are plausibly the same shape or belong to states this pass
could not exercise — signed-in Club Watch (`cc-*`, 11 selectors) and the edge board with live odds
(`eb-*`, 7 selectors, and the odds key is deferred by owner decision).

Per §0, a deletion that cannot be proven output-neutral does not happen. Exercising it properly
needs `./scripts/intel_preview.sh` for the signed-in view plus a payload with `n_bets > 0` — and
§5 explicitly deprioritises restructuring the SPA for taste. **Proposal only.**

## §3.5 — tests (13,280 lines)

**Nothing to reduce.** All 14 skips are deliberate and parametrised: seven knockout competitions
that carry no `league.id`, and the same seven having no domestic standings
(`test_payload_contract.py:133` and `:216`). Zero `xfail` markers anywhere. No dead fixtures
surfaced.

Note for future passes: `test_browser_smoke.py` and `test_intelligence_browser.py` need Playwright,
which is absent locally, so `pytest -q` cannot collect them. That is an environment gap, not dead
code.

## §3.6 — config, CI, and dependency drift

**Essentially clean.**

- **Four requirements files, 0 conflicting pins.** Verified by parsing all four and comparing every
  package pinned in more than one. `requirements-legacy.txt` (7 pins) is installed by nothing and
  dies with `legacy/`.
- **`vercel.json`** — 1 route, 0 destinations missing a handler.
- **`Makefile`** — every target resolves to a script that exists.
- **Workflows** — no `paths:` trigger references a directory that no longer exists.
- **Repeated `checkout` / `setup-python`** across 7 workflows is inherent to GitHub Actions; each
  workflow needs its own. Collapsing it means a composite action, which is *adding* an abstraction
  layer — §5 forbids that.

One item already fixed during this review rather than deferred, because it was a live staleness
bug rather than a cleanup: `build_coefficients_page.py` ran in no workflow at all and the published
page sat a month behind the UEFA refit. Now in `refresh-daily.yml`.
