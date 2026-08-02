# Codebase Unification Review — ledger

> **Dated evidence, as of 2026-08-02.** Superseded by `docs/STATUS.md`. Figures are as-of;
> re-measure before quoting. Executed against `docs/prompts/codebase-unification-review.md`
> under its §0 rule: nothing the system outputs may change.

**Baseline:** HEAD `1cf82a7`, 4,358 artifacts content-hashed.
`parity-check` ✅ (avg 0.6330 vs target 0.6331, |Δ|=0.0001) · `gate-self-test` ✅ 8/8 ·
`pytest` ✅ 1,681 passed / 14 skipped · `validate` ❌ **red before any change** — see E1.

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

### E2 — `config/settings.yaml` is inert for the model

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

**Owner decision, three options:** wire the call sites to `SETTINGS` (output-neutral today since
values match, but it is model-path surgery); delete the dead sections; or retitle the file so it
stops claiming authority it does not have. §6.4 says report, do not fix inside this pass.

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

## Remaining

§3.3 `legacy/` disposition · §3.4 monoliths · §3.5 tests · §3.6 config/CI drift.
