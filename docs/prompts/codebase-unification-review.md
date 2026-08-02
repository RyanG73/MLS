# Codebase Unification & Reduction Review — Reusable Prompt

> A from-scratch review of the entire repository with one goal: **`main` becomes the single,
> coherent, minimal expression of this project — with identical outputs.**
>
> This is a *subtractive* review. Success is measured in lines removed, branches retired, and
> duplicate paths collapsed — while every number the system produces stays bit-for-bit the same.
> A change that improves the model, adds a feature, or "modernises" style is **out of scope** and
> counts as a failure of this task, not a bonus.
>
> Sibling prompts cover other axes and own their findings: `docs/prompts/site-ux-audit.md`
> (interface quality), `docs/prompts/league-qa-audit.md` (data correctness),
> `docs/prompts/launch-readiness-audit.md` (launch/revenue). If you find a defect in those
> domains, **log it and hand it over — do not fix it here.**

---

## 0. The one rule

> **Nothing this system outputs may change.**

Not the champion Brier score. Not a single forecast, grade, table cell, page, or JSON byte.
Not the paywall boundary. If you cannot prove a deletion is output-neutral, the deletion does not
happen — you file it as a *candidate* with the evidence you'd need, and move on.

"I read it carefully and it looks unused" is **not** proof. §2 defines what proof means.

---

## 1. What you are working with

Measure before you theorise. Counts verified on `main` at `1cf82a7`, 2026-08-02.

| Area | LOC | Files | Notes |
|---|---:|---:|---|
| `scripts/` | 31,301 | 101 | The largest surface and the least governed. Build jobs, eval harness, intelligence pipeline. |
| `tests/` | 13,280 | 100 | Includes a 1,147-line browser smoke suite. |
| `webapp/` (authored) | 8,792 | 7 | Top-level only. `index.html` alone is **6,179**; `intelligence.js` is 1,970. The tree also holds ~155k lines of *generated* pages under `leagues/` — those are build output, not source, and §5 forbids deleting them. |
| `legacy/` | 9,097 | 52 | Archived 2026-06-11 (Postgres + Streamlit). See `legacy/README.md`. |
| `data_pipeline/` | 3,836 | 22 | Active ingest. |
| `server/` | 2,843 | 27 | |
| `api/` | 1,505 | 43 | `api/intel`, `api/admin`, `api/pub`, `api/auth`. |
| `models/` | 949 | 3 | `models/research_model.py` is canonical. |
| `config/` | 319 | 1 | |

Largest single files — each is a unification candidate in its own right:

```
6179  webapp/index.html
3818  scripts/eval_baseline.py
2440  scripts/build_league_data.py
1970  webapp/intelligence.js
1737  scripts/build_static_pages.py
1147  tests/test_browser_smoke.py
 967  scripts/intelligence/builder.py
 947  scripts/build_continental_data.py
 940  scripts/eval/league_bridge.py
 856  scripts/build_dashboard_data.py
```

Read `CLAUDE.md` in full before touching anything. Its "Key decisions" section lists invariants that
are **not open for re-litigation** — training window, test folds, champion config, ELO constants,
calibration method, and the paywall boundary.

---

## 2. The equivalence harness — set this up FIRST

Do not read a single file for cleanup purposes until you have a baseline you can diff against.
This repo already ships its own proof tooling; use it rather than inventing one.

**Step 2a — capture the baseline on untouched `main`:**

```
make validate
make parity-check
make smoke-test
make gate-self-test
pytest -q
```

Capture full logs to files (never pipe a long run through `tail` — you will lose the failure).
Then snapshot every generated artifact the build produces — `webapp/data.js`, `webapp/data/**`,
static pages, reports — by content hash, into a scratch manifest.

**Step 2b — after each batch of deletions, re-run all of it and diff the manifest.**

The pass condition is a **byte-identical artifact set** and a green test suite. If a hash moves,
you either revert the batch or you explain the difference and get it approved before continuing —
a moved hash is the loudest signal in this review and must never be waved through.

**Step 2c — anything the harness cannot exercise is high-risk.** If you're deleting code that no
command above touches, say so explicitly in the ledger and require a second form of evidence
(§4 rubric, evidence level B or better).

**Step 2d — if the baseline is already red, stop and get a decision before proceeding.**
Added 2026-08-02, from the first execution of this prompt. `make validate` failed on untouched
`main` (2024 `ens_stacked_brier=0.6360` vs pinned reference `0.6346`, tolerance 0.001) while
`make parity-check` passed at |Δ|=0.0001. A red gate does not necessarily mean a broken model —
here it was a stale single-season pin — but it does mean you cannot claim "green harness" after a
batch. Record the exact failing value, narrow the gate to what is trustworthy, and say so in the
ledger. Never quietly redefine the pass condition.

---

## 3. Workstreams

Work them in order. Each ends with a full §2 re-run before the next begins.

### 3.1 Branch and worktree unification

`main` should be the only branch that matters, and everything of value must live in it.

- Nine local branches currently contain **zero** commits absent from `main`
  (`agent/intelligence-hub-launch`, `claude/adoring-lehmann-a92938`, `claude/competent-kepler-5e8c7c`,
  `claude/exciting-mendel-2510ea`, `claude/mls-prediction-dashboard-C2mQM`,
  `claude/vigilant-kepler-e2d6de`, and three `worktree-agent-*`). Verify with
  `git rev-list --left-right --count main...<branch>` and propose deletion of the merged ones.
  **Exception:** `claude/mls-prediction-dashboard-C2mQM` is retained for history by explicit decision
  in `CLAUDE.md` — leave it, and confirm the decision still stands rather than assuming.
- Two branches hold **unmerged work**: `claude/clever-meninsky-e0cbc4` (2 commits) and
  `claude/infallible-jennings-948dec` (1 commit), all cross-tier ELO seeding
  (`fdbcfb2`, `eb9abfa`, `d4a0a38` — note `eb9abfa`/`d4a0a38` look like a duplicated commit).
  **Do not merge these as part of a cleanup pass.** Model-affecting code fails §0. Characterise
  each: what it does, whether it's superseded by what's on `main`, and whether it changes Brier.
  Then hand it to the owner as a decision — merge, formally abandon, or schedule as its own gated
  experiment. Record whichever, so this question never has to be asked a third time.
- Do the same for remote branches (`origin/live-data`, `origin/agent/intelligence-hub-launch`).
- Check for stale `git worktree` registrations pointing at directories that no longer exist.

### 3.2 Dead code — with the right definition of "reachable"

**A Python import graph will lie to you in this repo.** Entry points are invoked by:

- `.github/workflows/*.yml` — seven workflows: `deploy.yml`, `deploy-api.yml`,
  `intelligence-delivery.yml`, `refresh-daily.yml`, `refresh-fast.yml`, `refresh-leagues.yml`,
  `refresh-transfermarkt.yml`
- `Makefile` targets (`validate`, `parity-check`, `build-dashboard-data`, `odds-log`,
  `model-report`, `gate-self-test`, `diagnose-2024`, …)
- shell scripts (`scripts/*.sh`), and one script shelling out to another
- `vercel.json` routes → `api/**` handlers
- docs that instruct a human to run a command

Note: the launchd timer that used to invoke `scripts/build_all.sh` was retired 2026-08-02, and
`scripts/daily_build.sh` is not scheduled anywhere. See the pipeline-ownership table in
`docs/CURRENT_STATE.md` before assuming any build script is live.

Before declaring anything unreferenced, grep the **whole tree including YAML, Makefile, shell,
JSON, and Markdown** for the module name, the file stem, and any CLI flag it defines. A file that
only a workflow calls is production code.

Then hunt, in this order:
1. **Orphan scripts** — in `scripts/` (101 files), which are referenced by nothing anywhere.
2. **Superseded siblings** — near-identical builders (`build_league_data` /
   `build_continental_data` / `build_dashboard_data` / `build_static_pages` share a lot of shape).
   Look for copy-paste lineage: identical helper functions, parallel arg parsing, duplicated
   league/season/date handling.
3. **Dead flags and branches** — CLI options no caller passes; `if` branches gated on config that
   is now a constant; experiment toggles left from settled A/Bs (`CLAUDE.md` records which
   experiments concluded — a settled experiment's switch is deletable, its *winning* path is not).
4. **Unused imports, unreferenced helpers, commented-out blocks, TODOs already done.**
5. **Duplicate constants** — ELO K/HOME_ADV/REGRESS, half-lives, xG windows, edge threshold. These
   have canonical values in `CLAUDE.md`/`config/`. Every hardcoded second copy is a latent
   result-changing bug. Collapsing them to one source is the highest-value fix in this review —
   but verify the values are *currently identical* before collapsing, and if they are not, **stop
   and report**: you have found a real bug, not a cleanup.

### 3.3 `legacy/` disposition — 9,097 lines

`legacy/README.md` says the tree was archived 2026-06-11 and is not in the active path, with one
carve-out: `legacy/market/` (`clv_tracker`, `kelly`, `implied`, `risk_rules`) is "kept for the
future CLV/edge workstream", which the betting-edge goal still wants.

Produce a per-subtree recommendation (`dashboard/`, `models/`, `data_pipeline/`, `features/`,
`market/`, `scripts/`, `tests/`, `r_requirements.R`):

- **Delete** — git history preserves it; nothing imports it; no planned work needs it.
- **Promote** — something active already depends on it, so it isn't legacy and should move out.
- **Keep, with an expiry** — like `market/`; name the workstream and the date it gets revisited.

Also confirm `legacy/` is excluded from test collection, linting, coverage, packaging, and CI. If
it isn't, that's dead weight in every run and a fix worth making. Check whether
`requirements-legacy.txt` is still installed anywhere.

### 3.4 The monoliths

For each of the largest files, answer the same three questions and **only then** propose a change:

1. How much of this is duplication of something elsewhere in the repo?
2. How much is dead — unreachable, or serving a removed feature?
3. What is the smallest edit that removes that, with zero behavioral delta?

Specific to `webapp/index.html` (6,179 lines): look for repeated inline `<style>`/`<script>`
blocks, duplicated markup across sections that could be one template, and CSS rules with no
matching selector in the DOM. Beware: content that looks unused may be rendered by a build step
(`build_static_pages.py`) or hydrated by `intelligence.js`. Verify in a running preview, not by
reading.

**Do not restructure for taste.** Splitting a 6,000-line file into twelve modules is a
*net-neutral* line change with a real regression risk; it is not this task unless removing genuine
duplication happens to produce it.

### 3.5 Tests — 13,280 lines

Reduce test code only where it doesn't reduce coverage:
- Duplicate fixtures and setup repeated across files → shared conftest.
- Multiple tests asserting the identical property through the identical path.
- Tests for deleted code (these must go with their subject).
- Skipped/xfailed tests that have been dead for months — resolve or delete, don't leave rotting.

**Never** delete a test because it is slow, awkward, or currently failing. A failing test is a
finding to report, not a line to remove. Coverage before and after must not drop.

Note: `tests/test_browser_smoke.py` and `tests/test_intelligence_browser.py` require Playwright,
which is not installed in every environment. `pytest -q` cannot collect them locally — that is an
environment gap, not dead code, and they must not be deleted on that basis.

### 3.6 Config, CI, and dependency drift

- Four requirements files (`requirements.txt`, `-dev`, `-api`, `-legacy`) plus `pyproject.toml`:
  find pins that conflict, packages nothing imports, and duplicate declarations.
- Seven workflows: find copy-pasted setup steps, workflows that trigger on paths that no longer
  exist, and any that duplicate another's job. Note the `workflow_run` deploy chain — data pushed
  by token needs it, so do not "simplify" that trigger away.
- `Makefile`: targets that no longer run, or that duplicate a script's own CLI.
- `vercel.json` routes pointing at handlers that were removed.

---

## 4. How to classify and evidence every finding

Each candidate gets exactly one action and one evidence level. Anything below level B stays a
proposal — you don't execute it.

| Action | Meaning |
|---|---|
| **DELETE** | Remove entirely. Nothing references it; no planned work needs it. |
| **MERGE** | Two or more implementations of one thing collapse into the surviving one. |
| **HOIST** | Duplicated logic/constant moves to a single home; call sites updated. |
| **LEAVE** | Looks redundant, is not. **Record why** — this is what stops the next reviewer redoing the analysis. |

| Evidence | Standard |
|---|---|
| **A** | Full §2 harness re-run, artifact hashes identical, tests green. |
| **B** | Tree-wide grep (code + YAML + Make + shell + JSON + Markdown) shows zero references, **and** the change is covered by at least one harness command. |
| **C** | Reasoning only. Proposal only — never executed in this pass. |

`LEAVE` entries are a first-class deliverable, not filler. Half the value of this review is a
durable record of what *looked* removable and survived.

---

## 5. Explicitly out of scope

Doing any of these means the review failed:

- Changing the model, features, hyperparameters, calibration, or anything that moves Brier.
- Merging the unmerged cross-tier ELO branches (§3.1) as part of cleanup.
- Adding features, dependencies, frameworks, or abstraction layers.
- Renaming or reformatting for style; reorganising directories for elegance.
- Touching the paywall boundary in `CLAUDE.md` — no figure the public site publishes today may
  become locked.
- Deleting generated data artifacts under `webapp/data/` or `webapp/leagues/`, or committed parity
  frames, because they "look like build output". CI depends on them.
- Rewriting docs beyond the update rules in §6.
- **Re-pinning a failing model reference to make the harness green.** If §2d fires, that is an
  owner decision and its own gated change.

---

## 6. Deliverables

1. **The ledger** — one table, every candidate, most impactful first:

   | File / area | Lines | Action | Evidence | Proof | Rationale |
   |---|---:|---|---|---|---|

   Include executed and proposed items, plus every `LEAVE`.

2. **Branch disposition** — for all local and remote branches: delete / retain-with-reason /
   needs-owner-decision, with the ELO commits characterised (§3.1).

3. **Totals** — lines removed, files removed, duplicate implementations collapsed, branches
   retired; and the artifact-hash diff showing **zero** output change.

4. **Escalations** — every real bug found (diverging duplicate constants, failing tests, dead CI
   paths). Report; do not opportunistically fix inside this pass.

5. **Doc updates**, per the convention in `CLAUDE.md`:
   - `docs/STATUS.md` — any production-state change.
   - The active `docs/superpowers/plans/` file — a concise verdict appended.
   - `docs/CURRENT_STATE.md` — only if run commands moved (config/metrics must not have).
   - `docs/PROJECT_HISTORY.md` — 2–3 sentences under a dated entry if this completes a plan.
   Commit docs together with the code changes.

---

## 7. Working method

- **Batch, verify, commit.** Small thematic batches, each with a full §2 run before the next.
  A 40-file batch that breaks one hash costs you the whole batch's bisect.
- **Never delete and refactor in the same commit.** Deletions must be trivially revertable.
- **When the harness disagrees with your reading, the harness is right.**
- **Report honestly.** If a workstream turns out to have nothing in it, say so — a section that
  finds nothing is a real result. Never pad the ledger to look productive, and never claim a
  verification you didn't run.
