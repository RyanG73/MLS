# Documentation System Review — 2026-08-02 · ONE-TIME DOCUMENT

> **This is not a project document.** It is a one-time meta-review of the project's
> documentation system, written 2026-08-02 at the owner's request. It is deliberately
> named and located outside `docs/` so it cannot be mistaken for canonical truth.
>
> - It does **not** override `docs/STATUS.md`, `docs/PLAN.md`, `CLAUDE.md`, or any contract.
> - It contains **no** production claims. Every factual statement about the product comes
>   from the canonical docs and is cited as such.
> - **Delete this file once its recommendations are accepted or rejected.** Anything worth
>   keeping moves into `docs/PLAN.md`, `CLAUDE.md`, or a skill. Git retains the full text.
>
> Verification basis: full sweep of `docs/`, `.claude/`, `CLAUDE.md`, `README.md`, and the
> session memory directory; git first/last commit dates per file; cross-reference resolution
> for every `docs/*.md` path mentioned in any doc.

---

## 0. Executive summary

The documentation is **in better shape than its size suggests**. A consolidation pass on
2026-08-01 gave `docs/PLAN.md` a real filing system, and `docs/STATUS.md` is an unusually
disciplined document — every production claim carries a workflow run ID or a live HTTP check.
That machinery should be preserved, not replaced.

The problem is narrower and more specific than "too many docs":

**There are two documentation tracks. One is governed. One has silently rotted.**

| Track | Governance | Last substantive governance | State |
|---|---|---|---|
| **Product / launch** — `STATUS`, `PLAN`, `PROJECT_HISTORY`, active plan, contracts, kits | `CLAUDE.md` update rules + `PLAN.md` grouping rule | 2026-08-01 | Healthy |
| **Model research** — `experiment-protocol`, `feature-hunt-log`, `CURRENT_STATE`, `.claude/agents/*`, `/improve-model` | None since the branch migration | 2026-07-06 | **Actively misleading** |

And one structural gap affects both tracks:

**There is no mechanism that propagates a corrected fact.** When `STATUS.md` corrected the
Crossbar club count on 2026-08-02, the old figure survived in nine other places — including
`CLAUDE.md`, which is loaded as authoritative into every session.

The three highest-value actions, in order:

1. **Fix the branch references in the research track** before `/improve-model` is run again
   (§2.1). It would create four git worktrees on a branch two months stale.
2. **Stop storing measurements in `CLAUDE.md`** and add one executable doc check (§4.2, §4.3).
3. **Split `CURRENT_STATE.md`**, extracting its pipeline invariants the same way
   `product-invariants.md` was extracted (§5.2). It is 542 lines doing three unrelated jobs.

---

## 1. Complete inventory

51 markdown files under `docs/`, plus `CLAUDE.md`, `README.md`, and 5 files under `.claude/`.
Dates are git first-commit → last-commit. Line counts are current.

### 1.1 Tier 1 — Canonical (the four `CLAUDE.md` names as authoritative)

| Doc | Lines | Commits | Span | What it contains | Health |
|---|---:|---:|---|---|---|
| `docs/STATUS.md` | 386 | 33 | 07-23 → 08-02 | Current truth in four questions: what is live, what is broken, what happens next, what proves it. Production-state table with per-row proof; six ordered launch blockers; owner-action list; launch calendar; the "defects on the money path abort" safety rule. | **Excellent.** The model for the rest. |
| `docs/PLAN.md` | 100 | 169 | 05-10 → 08-02 | Navigation only. Read-order table; the 2026-08-01 grouping that files every `docs/` doc into exactly one of five groups with a retirement trigger; Now/Next/Later roadmap; documentation rules. | **Excellent.** Self-limiting at 100 lines. |
| `docs/CURRENT_STATE.md` | 542 | 38 | 06-06 → 08-02 | Model pipeline, cross-tier seeding, confederation calibration, league-family champions, metric convention, production build table, route-state taxonomy, model-card fields, data sources, config, dependencies, CI ownership, run commands, legacy map. | **Overloaded.** See §2.3. |
| `docs/PROJECT_HISTORY.md` | 766 | 26 | 06-21 → 08-01 | Narrative history: architecture evolution, model lineage, the 2024 regime shift, what was tried and failed, ~40 dated campaign entries (each 2–3 sentences from a deleted plan), permanent constraints. | **Good.** ~40 campaigns in 766 lines is strong compression. |

### 1.2 Tier 1b — Active execution

| Doc | Lines | Commits | Span | What it contains | Health |
|---|---:|---:|---|---|---|
| `docs/superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md` | 1,381 | 16 | 07-29 → 08-01 | The single active plan. Verdict log (append-at-top), execution state + next-action queue, ownership protocol, master sequence, then gated stages `G0` → `C1/M1/T1` → `D2` → `E3` → `P4/B4` → `R5` → `O6` → `CR7`, each with separate Ryan and Claude checklists. | Large but correctly scoped — it is *the* execution surface, and `CLAUDE.md` permits exactly one. |

### 1.3 Tier 2 — Standing contracts (never complete)

| Doc | Lines | Span | What it contains |
|---|---:|---|---|
| `docs/product-invariants.md` | 57 | 08-01 | 11 numbered invariants: truth/attribution (one fact one answer, no invented explanations, honest attribution labels, uncertainty types, route status, reproducible sims), the paid boundary (free-floor ratchet, public trust stays public, lock continuity not the current answer), security (private means access-controlled, no localStorage theater). Extracted from a deleted 1,405-line spec. |
| `docs/experiment-protocol.md` | 193 | 05-29 → 07-06 | The shared agent contract: baseline first, one change at a time, KEEP/DROP thresholds, the season-outcome gate, per-agent scope guard, logging format, branch rules, promotion-gate criteria. |
| `docs/paid-claim-matrix.md` | 30 | 07-29 → 07-31 | What may be claimed on each surface and the gate before expanding. |
| `docs/growth-measurement-contract.md` | 133 | 07-29 → 07-31 | Population and event definitions behind every reported growth number. |
| `docs/paid-launch-decision-record.md` | 54 | 07-29 → 08-01 | The `G0` owner decisions, approved 2026-07-29. |
| `docs/data-sources.md` | 341 | 06-21 → 07-25 | Per-source provenance, adapters, coverage, quirks. |
| `docs/drift-playbook.md` | 111 | 07-10 → 07-19 | How to read the drift report. |
| `docs/experiment-schema.json` | — | — | Machine schema for experiment records. |

### 1.4 Tier 3 — Operating kits (opened on a trigger, not read through)

`customer-discovery-kit.md` (77) · `club-watch-concierge-kit.md` (50) ·
`intelligence-hub-launch-runbook.md` (306) · `data-and-notification-incident-checklist.md` (42) ·
`launch-announcements.md` (192) · `growth-experiment-ledger.md` (44) ·
`social-media-strategy-2026-08-launch.md` (410) · `legal-copy-draft-2026-07-25.md` (100)

All 07-25 → 07-31. Correctly filed. The legal draft has a defined retirement trigger
(publication of Terms/refund/privacy) — the only kit that does.

### 1.5 Tier 4 — Reusable prompts (`docs/prompts/`)

`launch-readiness-audit.md` (682) · `site-ux-audit.md` (604) · `competitor-deep-dive.md` (599) ·
`league-qa-audit.md` (121). All single-commit 2026-08-01, 2,006 lines total.

These are **tools, not documents** — the most reusable asset in `docs/`, and the most
undersold. See §6.1.

### 1.6 Tier 5 — Built but unwired

`postgame-win-expectancy.md` (180) — documents `scripts/postgame_win_expectancy.py`, which
exists and is calibration-validated but is not shipped. `projection-drift-tracking.md` (56) —
design doc for the drift system.

`PLAN.md` correctly flags these as load-bearing: deleting one orphans working code.

### 1.7 Tier 6 — Dated evidence (superseded, kept for reasoning)

| Doc | Lines | Span |
|---|---:|---|
| `competitor-deep-dive-2026-08-01.md` | 1,695 | 08-01 |
| `offseason-model-improvement-audit-2026-07-30.md` | 1,012 | 07-31 |
| `league-qa-audit-findings.md` | 357 | 07-24 → 08-01 |
| `product-strategy-2026-07-26.md` | 319 | 07-26 |
| `product-roadmap-2026-07.md` | 293 | 07-18 → 07-29 |
| `league-expansion-report.md` | 289 | 07-10 → 07-26 |
| `feature-backlog-report-2026-07-13.md` | 287 | 07-13 → 07-26 |
| `competitive-intelligence-2026-07-combined.md` | 243 | 07-16 → 07-29 |
| `remaining-external-dependencies-2026-07-11.md` | 85 | 07-10 → 07-26 |
| `qa-pass-2026-07-17.md` | 60 | 07-17 |

**4,640 lines — 45% of all `docs/` prose.** Retirement trigger defined but never fired.

### 1.8 Tier 7 — Research logs

`docs/feature-hunt-log.md` (953 lines, 29 commits, 05-29 → 07-14). Live record of model
features tried and rejected. **The only one of four planned agent logs that exists.**

### 1.9 Tier 8 — Design specs (`docs/superpowers/specs/`)

Eight specs, 06-16 → 07-11, 1,224 lines, all single-commit. Continental competitions, DC roster
injection, promoted-teams cross-league strength, second-tier bidirectional bridge, webapp UI
redesign, UI feedback batch, league expansion round 4, NYT editorial redesign. Plus two HTML
mockups.

Every one is **shipped and summarized in `PROJECT_HISTORY.md`**. They are unfiled — `PLAN.md`'s
grouping covers `docs/*.md` but not `docs/superpowers/specs/`.

### 1.10 Tier 9 — Content drafts

`docs/content/` — README + 5 drafts (epl-2026-27-priors, market-blind-edge, model-explainer,
promoted-teams, relegation-risk), 230 lines, all single-commit 2026-07-10, untouched since.
**No build script, workflow, or page references this directory.**

### 1.11 Tier 10 — Agent and harness infrastructure (`.claude/`)

| File | Lines | Span | Contains |
|---|---:|---|---|
| `.claude/commands/improve-model.md` | 210 | 05-29 → 05-30 | The `/improve-model` orchestrator: preflight, baseline pinning, 4-agent parallel dispatch in worktrees, result collection, greedy forward-merge with re-eval gate. |
| `.claude/agents/hyperparameter-optimizer.md` | 97 | 05-29 | ELO grid, DC decay, XGB season-weight, schedule-density sweeps. |
| `.claude/agents/calibration-tuner.md` | 67 | 05-29 | Calibration method sweeps. |
| `.claude/agents/model-architect.md` | 65 | 05-29 | Structural model tests. |
| `.claude/agents/feature-engineer.md` | 56 | 05-29 | One feature candidate per invocation. |

**All five predate the 2026-06-10 branch migration and have not been touched since.**

### 1.12 Tier 11 — Root and session memory

`CLAUDE.md` (66 lines, 12 commits, 05-10 → 08-01) — project instructions: documentation
convention, active branch, eval script, and 13 "do not re-litigate" key decisions.

`README.md` (107 lines, 11 commits, 05-08 → 07-26).

`~/.claude/projects/-Users-ryangerda-Development-MLS/memory/` — 13 memory files + `MEMORY.md`
index, loaded into every session.

---

## 2. What is broken — verified findings

Each finding below was confirmed by direct file inspection, not inferred.

### 2.1 The research track points every agent at a branch abandoned two months ago

`CLAUDE.md:25-28` states development happens on `main` since 2026-06-10. The research track
was never updated:

| Location | Text |
|---|---|
| `docs/experiment-protocol.md:15` | "The baseline must be on the `claude/mls-prediction-dashboard-C2mQM` branch" |
| `docs/experiment-protocol.md:128` | "All work on `claude/mls-prediction-dashboard-C2mQM` (never push to main — CLAUDE.md rule)." |
| `.claude/commands/improve-model.md:38` | "Working directory is `claude/…-C2mQM` branch (per CLAUDE.md — never work on main)." |
| `.claude/commands/improve-model.md:78, 89-92` | Five `git worktree add … claude/…-C2mQM` commands |
| `.claude/commands/improve-model.md:202` | "Branch: `claude/…-C2mQM` only. Never main." |

Both files **cite `CLAUDE.md` as the authority for a rule `CLAUDE.md` reversed.** Running
`/improve-model` today pins a baseline on a stale branch, dispatches four agents into worktrees
built from it, and measures every delta against a two-month-old harness. The failure is silent —
the commands succeed.

**This is the single most consequential finding in this review.**

### 2.2 Three of four agent log files do not exist

`experiment-protocol.md:93-122` instructs each agent to append a structured entry after every
run:

| Agent | Target log | On disk |
|---|---|---|
| feature-engineer | `docs/feature-hunt-log.md` | **exists** (953 lines) |
| calibration-tuner | `docs/calibration-log.md` | **missing** |
| hyperparameter-optimizer | `docs/hyperparameter-log.md` | **missing** |
| model-architect | `docs/architecture-log.md` | **missing** |

`experiment-protocol.md:131` also points to `docs/improve-model-orchestrator.md` for the
merge/re-eval gate — **also missing**; that procedure exists only in
`.claude/commands/improve-model.md`.

Three-quarters of the agent fleet has no durable evidence trail. Their results survive only if
an orchestrator happens to write them into `PLAN.md` — and `PLAN.md` is now explicitly
"navigation, not a changelog," so that escape hatch has been closed too.

`experiment-protocol.md:87` also guards `scripts/daily_update.py` from agent edits. That file
does not exist.

### 2.3 `CURRENT_STATE.md` has become the changelog `PLAN.md` was rescued from

`CLAUDE.md` describes it as "canonical model config, metrics, run commands (**quick reference**)."
It is 542 lines and self-contradicts in its own header: `CURRENT_STATE.md:3` reads
"Last updated: 2026-07-26" while `CURRENT_STATE.md:462` is titled
"Who builds production (single pipeline, **2026-08-02**)".

It is doing three unrelated jobs:

1. **Config quick reference** (the stated job) — canonical model, metric convention, settings
   table, run commands, dependencies. ~150 lines.
2. **Pipeline invariants and hazard warnings** — genuinely load-bearing standing rules mixed
   into narrative prose. Examples:
   - `:73` "**always scope with `--conf`** — each run's 'prior' is the previous run's fitted
     value, so an unscoped re-fit walks every league a little every time"
   - `:108-117` "**Two CONMEBOL-specific hazards, both handled — do not 'simplify' them away.**"
     Club identity must resolve by ESPN team id, never name (4 genuinely different clubs
     collide); the ridge penalty has two modes and the wrong one let a 4-match league reach
     −2417 ELO.
   - `:56-58` A new confederation group must exist in `index.html` GROUP_ORDER + MAST_GROUPS
     *and* `build_static_pages.py` "or the league renders nowhere."
   - `:489-493` "If a generated artifact looks stale, check it has an owner in the table above."
   - `:419` The market-blind constraint.
3. **League-expansion changelog** — "Expansion round 4 (2026-07-11)", "round 5 (2026-07-14)",
   "round 6 (2026-07-24)", "CONMEBOL calibration (2026-07-24)", "Inter-confederation link
   (2026-07-26)", each a dated narrative block. ~250 lines that belong in `PROJECT_HISTORY.md`.

Job 2 is the valuable part and it is the part most at risk: those warnings are buried inside
dated entries that look retire-able. This is precisely the situation `PLAN.md:98-99` warns
about — "**Before deleting, extract.** A finished document can still hold a standing rule."

### 2.4 A corrected fact reached one file out of ten

On 2026-08-02, `STATUS.md:45` corrected the Crossbar scale and explicitly flagged the old
figure: *"1,172 clubs across 71 competitions … the previous '892 across 50' was stale."*

The stale figure remains in nine places:

| Location | Severity |
|---|---|
| `CLAUDE.md:62` | **Highest** — a "do not re-litigate" key decision, loaded as authoritative into every session |
| `CURRENT_STATE.md:98` | High — the config quick reference |
| `competitor-deep-dive-2026-08-01.md` ×7 (`:80, :650, :737, :1148, :1453, :1541, :1662`) | High — several appear inside **proposed public marketing copy** and a proposed daily puzzle concept built on the number |

The correction had no way to find them. Nothing in the system links a fact to its instances.

This matters beyond tidiness: `STATUS.md:42` records that the Crossbar page deliberately
*"reads figures from the payloads at build time, not written down."* That discipline was applied
to the customer-facing page and to nothing else.

### 2.5 A session memory instructs updates to files deleted five weeks ago

`~/.claude/…/memory/update-all-three-docs.md` — loaded into every session via `MEMORY.md` —
says: *"every loop iteration patches PLAN + CODE_WALKTHROUGH + HANDOFF together."*

`docs/CODE_WALKTHROUGH.md` and `docs/HANDOFF.md` do not exist. `PROJECT_HISTORY.md:220` records
their removal on 2026-06-27: *"two stale README references to deleted docs (`HANDOFF.md`,
`CODE_WALKTHROUGH.md`) were corrected."*

The README was fixed. The memory was not. `sync-before-evaluating.md` references the same two
files in its narrative, though its "How to apply" section was correctly updated to `main`.

### 2.6 A duplicate worktree doubles every document

```
/users/ryangerda/development/MLS/.claude/worktrees/adoring-lehmann-a92938  1c015a2 (detached HEAD)
```

It mirrors every doc at a commit well behind `main` (`1cf82a7`). Every repo-wide grep returns
each document twice; any agent reading by path could land on the stale copy. It appears to be
tool-managed, but it is carrying real drift.

### 2.7 Smaller items

- **`docs/superpowers/specs/` is unfiled.** `PLAN.md:20-21` states "Every file in `docs/`
  appears in exactly one group below. A file that belongs to no group is a bug." Eight shipped
  specs (1,224 lines) belong to no group. By the project's own rule, that is eight bugs.
- **`docs/content/` is referenced by nothing.** Six files, 230 lines, single-commit 2026-07-10,
  no build script or workflow consumes them. Either dead drafts or an undocumented manual
  publishing path.
- **`docs/STATUS.html` + `docs/STATUS_files/`** — a gitignored local Quarto render of
  `STATUS.md`. Harmless to the repo, but it is a stale local copy of the single most
  authoritative document, sitting beside the original.
- **Tier 6 evidence carries no as-of stamp.** The 1,695-line competitor deep-dive holds
  proposed public copy containing the stale 892 figure. Anyone lifting copy from it publishes a
  wrong number.

---

## 3. What is working — preserve these

Do not let a consolidation pass damage any of the following.

1. **`STATUS.md`'s proof column.** Every production claim cites a GitHub Actions run ID, a
   deployed commit SHA, or a live HTTP status. `STATUS.md:38` even documents a claim that was
   *true in source but false in production* for a day, and says so. That honesty is the single
   most valuable property in the whole system.

2. **`PLAN.md`'s exhaustive-grouping rule.** "Every file appears in exactly one group; a file in
   no group is a bug" is a genuine invariant with a checkable property. Most doc systems have
   nothing like it. §4.3 proposes making it executable rather than aspirational.

3. **"Before deleting, extract."** `product-invariants.md` — 57 lines rescued from a deleted
   1,405-line spec — is the best artifact in `docs/` and the template for §5.2.

4. **Delete-completed-plans, summarize in history.** ~40 campaigns compressed into 766 lines of
   `PROJECT_HISTORY.md`, with git retaining full text. This is why the repo has 51 docs and not
   200.

5. **The promotion gate is code, not prose.** `scripts/promotion_gate.py` with a `self-test`
   subcommand that proves it rejects identical, 2024-regressing, and calibration-blowup
   challengers. `experiment-protocol.md:56` says "the gate is final" — and the gate is
   executable, so the doc cannot drift from the behavior.

6. **Separating screening thresholds from promotion gates.** `experiment-protocol.md:52-56`
   explicitly distinguishes the harness A/B bar (Δ > 0.001) from the champion promotion gate,
   and notes a change can pass one and fail the other. That distinction prevents a whole class
   of false wins.

**The pattern worth naming:** *the docs that stayed healthy are the ones with either an
executable check or a retirement trigger. The docs that rotted have neither.* Every
recommendation below follows from that observation.

---

## 4. Recommended process going forward

### 4.1 Give every document class one of two things: a check or a trigger

| Class | Mechanism | Applies to |
|---|---|---|
| Canonical | **Executable check** — CI fails if the doc contradicts the repo | `STATUS`, `PLAN`, `CURRENT_STATE` |
| Contract / invariant | **Executable check** where possible; otherwise owner review on change | `product-invariants`, `pipeline-invariants`, `experiment-protocol`, claim matrix |
| Active plan | **Trigger:** deleted on completion, 2–3 sentences to `PROJECT_HISTORY` | `superpowers/plans/*` |
| Kit / prompt | **Trigger:** retired when its situation or surface is permanently gone | kits, `prompts/*` |
| Dated evidence | **Trigger:** retired once decisions are in `STATUS` and reasoning in `PROJECT_HISTORY`; **must carry an as-of header** | Tier 6 |
| Spec | **Trigger:** deleted on ship, same as plans | `superpowers/specs/*` |

### 4.2 Two new content rules

**Rule A — `CLAUDE.md` may state a decision. It may not state a measurement.**

`CLAUDE.md:62` says "892 clubs across 50 leagues sit on it." That is a measurement, it is wrong,
and it is loaded into every session as authoritative. The decision worth recording is *"Crossbar
is the public name of the shared cross-league strength scale; internally `global_elo`; the name
implies no accuracy claim."* The club count belongs where it is measured.

Applies equally to Brier scores, league counts, club counts, and test counts. Decisions and
thresholds stay; measured quantities move to `CURRENT_STATE.md` or are computed.

**Rule B — a figure published on more than one surface has exactly one source, and it is
measured, not typed.**

Already the practice for the Crossbar page (`STATUS.md:42`, figures read from payloads at build
time). Generalize it. §4.3 gives the enforcement.

### 4.3 One executable doc check — `scripts/check_docs.py`

Add to the existing suite (101 test files, `validate_payloads.py`, and a promotion-gate
self-test already establish the idiom — this is not new machinery, it is the same machinery
pointed at prose).

Four assertions:

1. **Exhaustive filing.** Every `docs/**/*.md` is named in a `PLAN.md` group. Makes
   `PLAN.md:20-21` real. *Currently fails: 8 specs + 6 content drafts.*
2. **No dangling references.** Every backticked or linked `docs/…md` path in any doc resolves
   to a file on disk. *Currently fails: 4 paths (§2.2).*
3. **Branch consistency.** No doc names a git branch other than the one `CLAUDE.md` designates
   active. *Currently fails: 2 files, 7 occurrences (§2.1).*
4. **Shared-figure manifest.** A small `docs/figures.json` maps each cross-surface figure
   (`crossbar_clubs`, `crossbar_competitions`, `champion_avg_brier`, `league_count`, …) to a
   value measured from the payloads, plus the files permitted to state it. The check fails when
   a doc disagrees. *Currently fails: 9 instances of one figure (§2.4).*

Assertion 4 is the direct structural fix for §2.4 and the only one that requires new data. The
other three are pure grep and could ship in an afternoon.

### 4.4 Repair the research track, don't retire it

The four agents, `scripts/experiment.py`, `promotion_gate.py` with its self-test, and the
1,012-line offseason audit (2026-07-31) are real, working, recently-invested infrastructure.
The problem is stale wiring, not a dead system.

Minimum repair, in order:

1. Replace every `claude/mls-prediction-dashboard-C2mQM` reference with `main` in
   `experiment-protocol.md` and `.claude/commands/improve-model.md`, and delete the
   "never work on main" instruction that now contradicts `CLAUDE.md`.
2. Collapse the four per-agent logs into **one `docs/research-log.md`** with a component column
   (see §5.4).
3. Either write `docs/improve-model-orchestrator.md` or repoint `experiment-protocol.md:131`
   at `.claude/commands/improve-model.md`, which already holds the procedure. Repointing is
   simpler and creates nothing new.
4. Drop the `scripts/daily_update.py` guard from `experiment-protocol.md:87` — the file is gone.
5. Add a "Last verified against `main`" line to `experiment-protocol.md`, the way `STATUS.md`
   carries its verification date.

**Do this before the next `/improve-model` run**, not after.

### 4.5 Fire the Tier 6 retirement trigger on a schedule

The trigger exists and has never fired; 4,640 lines have accumulated behind it. Make it a
calendar event rather than a hope: **at each launch-calendar gate, review Tier 6.** For each
doc, ask the one question `PLAN.md:52` already specifies — *does it contain a finding not yet
acted on?* If no: extract any durable reasoning to `PROJECT_HISTORY.md`, then delete.

### 4.6 Keep the memory directory in the same review

Session memory is documentation with a much higher blast radius — it loads into every session
without being requested. §2.5 shows it drifting the same way. Review it whenever a doc is
deleted: *does any memory reference this file?*

---

## 5. Consolidation opportunities

Ordered by value-to-risk. Line counts are current.

### 5.1 Retire Tier 6 dated evidence — up to ~4,600 lines

| Doc | Lines | Recommendation |
|---|---:|---|
| `competitive-intelligence-2026-07-combined.md` | 243 | **Delete.** Superseded by the 2026-08-01 deep-dive. Extract any un-acted finding first. |
| `product-strategy-2026-07-26.md` | 319 | **Delete.** Pre-decision thinking; the approved decisions live in `paid-launch-decision-record.md` and `STATUS.md:92-96`. |
| `product-roadmap-2026-07.md` | 293 | **Delete.** `PLAN.md`'s Now/Next/Later is the live roadmap; two roadmaps is one too many. |
| `qa-pass-2026-07-17.md` | 60 | **Delete** if findings are closed. |
| `remaining-external-dependencies-2026-07-11.md` | 85 | **Fold** open items into `STATUS.md` owner actions, then delete. |
| `feature-backlog-report-2026-07-13.md` | 287 | **Fold** live candidates into `feature-hunt-log.md`, then delete. |
| `league-expansion-report.md` | 289 | **Extract** the source-routing rules into pipeline invariants (§5.2); delete the rest. |
| `league-qa-audit-findings.md` | 357 | **Keep** until findings close — it has the most recent activity in the tier (08-01). |
| `offseason-model-improvement-audit-2026-07-30.md` | 1,012 | **Keep.** Presumed active queue for model work. Re-file as Tier 1b input, not evidence. |
| `competitor-deep-dive-2026-08-01.md` | 1,695 | **Keep, stamp.** Add an as-of header (§5.5) and fix the 7 stale figures — it holds proposed public copy. |

**Immediately deletable: ~1,000 lines. With extraction: ~1,600.**

### 5.2 Split `CURRENT_STATE.md` — highest structural value

Mirror the `product-invariants.md` extraction exactly:

| Destination | Content | Est. lines |
|---|---|---:|
| `docs/CURRENT_STATE.md` (kept) | Canonical model, metric convention, league-family champions, production path table, route-state taxonomy, model-card fields, config table, dependencies, CI ownership, run commands | ~180 |
| `docs/pipeline-invariants.md` (**new**) | The `--conf` scoping rule · both CONMEBOL hazards · the two ridge modes · ESPN-team-id resolution · the confederation-group registration requirement · market-blind constraint · "every generated artifact needs a workflow owner" · the outright-betting ≥25% gate · the tier-bridge seeding rule | ~90 |
| `docs/PROJECT_HISTORY.md` (append) | Expansion rounds 4/5/6, CONMEBOL calibration, inter-confederation link, global-ELO publication, value-tilt gate reversal — as dated entries | ~250 → compressed |

Also fix the header: `CURRENT_STATE.md:3` says 2026-07-26 while the file contains 2026-08-02
content.

`pipeline-invariants.md` becomes the technical sibling of `product-invariants.md` — and the two
together are the right pair to hand any new agent.

### 5.3 File or delete the unfiled

- **`docs/superpowers/specs/` (8 files, 1,224 lines).** All shipped and summarized in
  `PROJECT_HISTORY.md`. By `CLAUDE.md`'s own rule — completed plans are deleted, not archived —
  **delete them.** Then extend `PLAN.md`'s grouping sentence to cover `docs/**`, not just
  `docs/*`.
- **`docs/content/` (6 files, 230 lines).** No consumer found. **Confirm with the owner**
  whether this is a manual publishing path. If not, delete.
- **`docs/STATUS.html` + `docs/STATUS_files/`.** Gitignored, so repo-harmless — but a stale
  local copy of the canonical doc. Render to a scratch path instead.

### 5.4 Merge four research logs into one

`experiment-protocol.md` specifies four logs. One exists; three never did, across two months of
campaigns. That is evidence of over-partitioning, not of neglect.

Replace with **one `docs/research-log.md`**, newest-first, with a `component` column
(`feature` / `calibration` / `hyperparam` / `architecture`). Preserve `feature-hunt-log.md` as
is — it has 953 lines of real history and 29 commits, and the campaign protocol names it
directly; the merged log covers the other three components.

### 5.5 Stamp every Tier 6 doc with an as-of header

Two lines at the top of each:

```markdown
> **Dated evidence, as of YYYY-MM-DD.** Superseded by `docs/STATUS.md`. Figures inside are
> as-of and may be stale — re-measure before quoting, and never publish a number from here
> without checking `docs/figures.json`.
```

Cheap, and it directly prevents the §2.4 failure mode from reaching a customer.

### 5.6 Prune the duplicate worktree

`.claude/worktrees/adoring-lehmann-a92938` at `1c015a2`, detached, well behind `main`. If it
holds no unmerged work: `git worktree remove`. Cuts every repo-wide doc grep in half and removes
a stale-read hazard.

---

## 6. Enhancements to make next

### 6.1 Promote `docs/prompts/` — the most undersold asset

2,006 lines of reusable audit procedure (launch-readiness, site-UX, league-QA, competitor
deep-dive), each single-commit 2026-08-01, and each demonstrably productive — `league-qa-audit`
produced 357 lines of findings; `competitor-deep-dive` produced 1,695.

They are filed in `PLAN.md` as a footnote. Two upgrades:

1. **Convert each to a skill** so they are invocable as `/site-ux-audit` rather than
   copy-pasted. The `.claude/agents/` and `.claude/commands/` infrastructure already exists.
2. **Record each run's output location and date** in a short index at the top of
   `docs/prompts/README.md`, so a prompt's findings are traceable to its invocation.

### 6.2 `docs/figures.json` + a build step

The manifest from §4.3. Beyond enforcement, it lets `STATUS.md` and the Crossbar page share one
measured source instead of two independent claims. Start with the five or six figures that
already appear on multiple surfaces:

```json
{
  "crossbar_clubs":         {"value": 1172, "measured_from": "webapp/data/power.js",  "as_of": "2026-08-02"},
  "crossbar_competitions":  {"value": 71,   "measured_from": "webapp/data/*.js",      "as_of": "2026-08-02"},
  "champion_avg_brier":     {"value": 0.6330, "measured_from": "experiments/champion.json"},
  "club_pages":             {"value": 1446, "measured_from": "build_static_pages output"},
  "sitemap_urls":           {"value": 1543, "measured_from": "build_static_pages output"}
}
```

### 6.3 A `STATUS.md` freshness assertion

`STATUS.md` carries "Repository verified" and "Production last verified" dates. Make them
falsifiable: a CI step that re-runs the live checks already listed in the proof column (HTTP
200s, CORS preflight, config endpoint shape) and fails if a date is older than N days while
claims still read ✅.

This extends what the doc already does by hand into something that cannot quietly lapse — the
exact failure recorded at `STATUS.md:38`, where a source fix shipped but nothing rebuilt
`power.js` and the page served a stale ladder for a day.

### 6.4 A "new agent onboarding" path

There is no single answer to *"I am starting fresh on this repo — what do I read?"*
`PLAN.md`'s read-order table is close, but it is organized by question, not by role.

Add ~15 lines to `PLAN.md`:

```markdown
## Starting fresh

Product or launch work → STATUS.md → active plan → product-invariants.md
Model or pipeline work → CURRENT_STATE.md → pipeline-invariants.md → experiment-protocol.md
Both                   → CLAUDE.md key decisions (do not re-litigate)
Context on any past decision → PROJECT_HISTORY.md
```

### 6.5 Fold the doc-hygiene loop into the existing update rules

`CLAUDE.md`'s update rules fire on code change and on plan completion. Add a third trigger:
**on fact change.** See §7.

---

## 7. Drop-in instructions for `CLAUDE.md`

Paste the block below into `CLAUDE.md` under `## Documentation convention`, after the existing
`**Update rules**` list. It is written to match the file's existing voice and length budget.

```markdown
**Fact rules (apply to every document, including this one):**
- `CLAUDE.md` may state a **decision or a threshold**. It may not state a **measurement**.
  Club counts, league counts, Brier scores, and test counts belong in `CURRENT_STATE.md` or are
  computed at build time. A measurement in this file will go stale and be quoted as authoritative.
- A figure that appears on more than one surface has **one source, measured, not typed**.
  Register it in `docs/figures.json`; `scripts/check_docs.py` fails when a doc disagrees.
- **When you correct a fact, grep for it before you commit.** `rg '<old value>' docs/ CLAUDE.md
  README.md .claude/`. A correction that lands in one file and not its nine siblings is worse
  than the original error, because now the repository disagrees with itself.
- **When you delete a document, grep for its name** across `docs/`, `.claude/`, and the session
  memory directory. Dangling references outlive their targets — three agent log files and two
  deleted docs are still referenced today.

**Track ownership:**
- **Product/launch track** — `STATUS.md`, `PLAN.md`, `PROJECT_HISTORY.md`, the active plan,
  `product-invariants.md`, contracts, kits.
- **Model/research track** — `CURRENT_STATE.md`, `pipeline-invariants.md`,
  `experiment-protocol.md`, `research-log.md`, `feature-hunt-log.md`, `.claude/agents/*`,
  `.claude/commands/improve-model.md`.
- A change inside one track updates that track's docs in the same commit. A change that crosses
  both updates both. **The research track is the one that rots** — it has no daily reader.
  Re-read `experiment-protocol.md` against the repo before any campaign, and treat a stale
  branch name there as a blocking bug, not a typo.

**Never in `docs/`:** build artifacts, rendered HTML, or a second copy of a canonical document.
```

---

## 8. Drop-in skill — `.claude/skills/doc-hygiene/SKILL.md`

Create this file to make the rules invocable and self-enforcing. It follows the skill format
already used by this project's plugins.

```markdown
---
name: doc-hygiene
description: Use when creating, editing, deleting, or consolidating any documentation in this
  repo, when correcting a fact that may appear in more than one document, or when a task
  completes and docs must be updated. Enforces the MLS/Entenser documentation contract.
---

# Documentation hygiene — MLS/Entenser

## Before you write

1. Read `docs/PLAN.md` first. It is navigation and it names the canonical doc for every question.
2. Identify the **track**: product/launch or model/research. Different docs, different owners.
3. Identify the **class** of what you are writing:
   canonical · contract/invariant · active plan · kit/prompt · dated evidence · spec.
   If it is none of these, do not create a file — put it in the active plan.

## The two hard rules

**Every document needs an executable check or a retirement trigger.** A doc with neither will
rot. If you cannot name the trigger that retires the file you are about to create, do not
create it.

**Before deleting, extract.** A finished document can hold a standing rule.
`docs/product-invariants.md` is 57 lines rescued from a deleted 1,405-line spec. Ask: does this
file contain a constraint that outlives the work it describes? If yes, move it to an invariants
file first.

## Correcting a fact — mandatory sequence

Never edit a fact in one place. Corrections that land in one file and not its siblings make the
repository disagree with itself.

```bash
rg -n '<old value>' docs/ CLAUDE.md README.md .claude/ --glob '!**/worktrees/**'
```

Fix every hit in the same commit, or state explicitly in the commit message which you left and
why. Check `docs/figures.json` — if the figure is registered, update it there and let the check
find the rest.

Precedent: on 2026-08-02 a Crossbar count was corrected in `STATUS.md` and left stale in nine
other places, including `CLAUDE.md` and proposed public marketing copy.

## Deleting a document — mandatory sequence

```bash
rg -n '<filename>' docs/ CLAUDE.md README.md .claude/ --glob '!**/worktrees/**'
ls ~/.claude/projects/-Users-ryangerda-Development-MLS/memory/
```

Fix or remove every reference, **including session memories**. A memory outlives a deleted file
and keeps instructing sessions to update it.

## Per-class rules

- **Canonical** (`STATUS`, `PLAN`, `CURRENT_STATE`, `PROJECT_HISTORY`) — `STATUS.md` carries
  claims + proof only; every production claim needs a run ID, commit SHA, or live check.
  `PLAN.md` stays under 100 lines and is navigation, never a changelog. `CURRENT_STATE.md` is
  config and commands, not narrative — dated stories go to `PROJECT_HISTORY.md`.
- **Contract/invariant** — numbered, standing, never a checklist. Breaking one is the owner's
  call, not an implementation choice.
- **Active plan** — exactly one, unless the owner authorizes a second workstream. Deleted on
  completion with 2–3 sentences appended to `PROJECT_HISTORY.md`.
- **Kit/prompt** — retired when its situation or surface is permanently gone.
- **Dated evidence** — must open with an as-of header. Retired once its decisions are in
  `STATUS.md` and its durable reasoning is in `PROJECT_HISTORY.md`.
- **Spec** — deleted on ship, same as a plan.

## `CLAUDE.md` is not a fact store

It may state a decision or a threshold. It may not state a measurement. If you are about to
write a count, a score, or a total into `CLAUDE.md`, put it in `CURRENT_STATE.md` or
`docs/figures.json` instead.

## Before a model-research campaign

The research track has no daily reader and drifts silently. Verify before dispatching agents:

```bash
git branch --show-current
rg -n 'C2mQM|never work on main|never push to main' docs/ .claude/ --glob '!**/worktrees/**'
rg -no 'docs/[a-z-]+\.md' docs/experiment-protocol.md | sort -u   # then confirm each exists
```

A stale branch name in `experiment-protocol.md` or `.claude/commands/improve-model.md` is a
**blocking bug** — agents will run against the wrong baseline and every delta will be measured
against a stale harness, silently and successfully.

## Finishing

Run the doc check before claiming done:

```bash
python scripts/check_docs.py
```

State what you verified. Do not claim a doc is updated without showing the check passing.
```

---

## 9. Suggested sequence

Ordered so each step de-risks the next. No step depends on a later one.

| # | Action | Effort | Value |
|---|---|---|---|
| 1 | Fix branch references in `experiment-protocol.md` + `improve-model.md` (§2.1) | 10 min | **Critical** — blocks a silent failure |
| 2 | Fix the 9 stale Crossbar figures; start `docs/figures.json` (§2.4, §6.2) | 30 min | **Critical** — one instance is in public copy |
| 3 | Delete the stale `update-all-three-docs` memory; fix `sync-before-evaluating` (§2.5) | 5 min | High — loads into every session |
| 4 | Paste the `CLAUDE.md` block (§7) and create the doc-hygiene skill (§8) | 15 min | High — prevents recurrence |
| 5 | Repoint or write `improve-model-orchestrator.md`; create `research-log.md`; drop the `daily_update.py` guard (§4.4, §5.4) | 30 min | High — restores the agent evidence trail |
| 6 | Write `scripts/check_docs.py` with assertions 1–3 (§4.3) | 1–2 hr | High — makes the rules real |
| 7 | Split `CURRENT_STATE.md`; create `pipeline-invariants.md` (§5.2) | 2–3 hr | **Highest structural** |
| 8 | Delete shipped specs; file or delete `docs/content/` (§5.3) | 30 min | Medium — closes the filing rule |
| 9 | Retire Tier 6 evidence; stamp the survivors (§5.1, §5.5) | 1–2 hr | Medium — ~1,600 lines |
| 10 | Add assertion 4 (figure manifest) to the doc check (§4.3) | 1 hr | Medium |
| 11 | Prune the duplicate worktree (§5.6) | 5 min | Low, easy |
| 12 | Convert `docs/prompts/*` to skills (§6.1) | 2 hr | Medium — best long-term leverage |

Steps 1–4 are ~1 hour total and address every finding that can currently cause a wrong action or
a wrong published number.

---

## 10. Open questions for the owner

Genuine decisions, not busywork — each changes what gets done.

1. **`docs/content/` (6 files, 230 lines, untouched since 2026-07-10)** — is there a manual
   publishing path for these drafts, or are they dead? Nothing in the build references them.
2. **`offseason-model-improvement-audit-2026-07-30.md` (1,012 lines)** — is this an active work
   queue? If yes it should be re-filed out of "dated evidence," which is the retire-on-sight
   group.
3. **The research track** — is a model campaign expected before the 2026-08-17 launch gate? If
   not, the §4.4 repair can wait behind the launch work; if yes, step 1 is blocking.
4. **`.claude/worktrees/adoring-lehmann-a92938`** — safe to remove, or does it hold unmerged
   work?
5. **Priority** — steps 1–4 are cheap and high-value regardless. Step 7 (splitting
   `CURRENT_STATE.md`) is the largest structural win but costs a few hours during a launch
   window. Now or after 2026-08-17?

---

*End of one-time review. Delete this file once acted on.*
