---
name: doc-hygiene
description: Use when creating, editing, deleting, or consolidating documentation in this repo; when correcting a fact that may appear in more than one document; when finishing a task that requires a doc update; or before starting a model-research campaign. Enforces the Entenser/MLS documentation contract.
---

# Documentation hygiene — Entenser / MLS

`CLAUDE.md` states the rules. This skill is how you carry them out, plus the failure modes that
produced them.

## Before you write anything

1. **Fetch first.** Four CI workflows push to `main` on their own schedules; the checkout goes
   stale within hours. `git fetch origin && git status -sb`.
2. **Read `docs/PLAN.md`.** It is navigation and names the canonical doc for every question.
   It is *not* current truth — that is `docs/STATUS.md`.
3. **Identify the track.** Product/launch (`STATUS`, `PLAN`, `PROJECT_HISTORY`, active plan,
   `product-invariants`, contracts, kits) or model/research (`CURRENT_STATE`,
   `experiment-protocol`, `feature-hunt-log`, `.claude/agents/*`, `.claude/commands/improve-model`).
   Update the track you changed, in the same commit.
4. **Identify the class** of what you are about to write: canonical · contract/invariant ·
   active plan · kit/prompt · dated evidence · spec. If it is none of these, **do not create a
   file** — put it in the active plan.

## The two hard rules

**Every document needs an executable check or a retirement trigger.** A doc with neither will
rot. If you cannot name the trigger that retires the file you are about to create, do not create
it. The research track rotted precisely because it had neither and no daily reader: it spent two
months pointing every agent at a branch abandoned on 2026-06-10.

**Before deleting, extract.** A finished document can still hold a standing rule.
`docs/product-invariants.md` is 57 lines rescued from a deleted 1,405-line spec. Ask: does this
file contain a constraint that outlives the work it describes? If yes, move it to an invariants
file *first*, then delete.

## Correcting a fact — mandatory sequence

Never fix a fact in one place.

```bash
rg -n '<old value>' docs/ CLAUDE.md README.md .claude/ --glob '!**/worktrees/**'
```

Fix every hit in the same commit, or say explicitly in the commit message which you left and why.

**First ask which population the figure describes.** Two numbers that look like corrections of
each other are often two different measurements:

| Figure key in `docs/figures.json` | Population | Source |
|---|---|---|
| `power_ladder_clubs` / `power_ladder_leagues` | the bridged Global Power ladder | `webapp/data/power.js` |
| `global_elo_clubs` / `global_elo_competitions` | every club carrying a `global_elo` — strictly larger | all `webapp/data/*.js` payloads |

Both are right for their own question. Blindly replacing one with the other *introduces* an error.
The values are named rather than typed here on purpose: this table itself carried a stale
`1,172` for three days after the payloads moved to 1,167. Read them from `figures.json`, which
`check_docs.py` re-measures, or measure them yourself with the snippet below.

**Measure, do not copy.** If a figure can be computed from the payloads, compute it:

```bash
python3 -c "
import re,json,pathlib
d=json.loads(re.search(r'=\s*(\{.*\})',pathlib.Path('webapp/data/power.js').read_text(),re.S).group(1))
print(len(d['teams']),'teams |',len({t['league'] for t in d['teams']}),'leagues')"
```

Precedent: on 2026-08-02 a Global ELO count was corrected in `STATUS.md` and left stale in nine
other places, including `CLAUDE.md` and proposed public marketing copy.

## Deleting a document — mandatory sequence

```bash
rg -n '<filename>' docs/ CLAUDE.md README.md .claude/ --glob '!**/worktrees/**'
ls ~/.claude/projects/-Users-ryangerda-Development-MLS/memory/
```

Fix or remove every reference **including session memories**. A memory outlives a deleted file
and keeps instructing sessions to update it — `update-all-three-docs` survived
`CODE_WALKTHROUGH.md` and `HANDOFF.md` by five weeks and loaded into every session that whole
time.

## Per-class rules

- **`STATUS.md`** — claims, blockers, next actions, and proof only. Every production claim needs
  a workflow run ID, a deployed commit SHA, or a live check. A claim true in source but false in
  production is a false claim; say so in the row.
- **`PLAN.md`** — navigation, under 100 lines, never a changelog. Every file in `docs/` belongs
  to exactly one group; a file in no group is a bug.
- **`CURRENT_STATE.md`** — config, commands, and standing pipeline rules. Dated narrative
  ("expansion round N…") belongs in `PROJECT_HISTORY.md`. Keep its header date honest.
- **`PROJECT_HISTORY.md`** — completed narrative and durable decisions, 2–3 sentences per
  campaign.
- **Contract / invariant** — numbered, standing, never a checklist. Breaking one is the owner's
  call, not an implementation choice.
- **Active plan** — exactly one, unless the owner authorizes a second workstream. Deleted on
  completion with 2–3 sentences appended to `PROJECT_HISTORY.md`. Git retains the text.
- **Kit / prompt** — retired when its situation or surface is permanently gone.
- **Dated evidence** — opens with an as-of header. Retired once its decisions are in `STATUS.md`
  and its durable reasoning is in `PROJECT_HISTORY.md`. Un-acted findings are the only reason to
  keep one.
- **Spec** — deleted on ship, same as a plan.

## Never

- Put a **measurement** in `CLAUDE.md`. It may state a decision or a threshold. Counts, scores,
  and totals go in `CURRENT_STATE.md` or are computed at build time.
- Put build artifacts, rendered HTML, or a second copy of a canonical document in `docs/`.
- `git add -A`. Stage explicit paths. Twice on 2026-08-02 an `-A` swept another session's
  uncommitted work and an unread file into a commit whose message described neither.

## Concurrent sessions are normal here

More than one session works in this repo at once. Before editing a shared doc:

```bash
git log --oneline -3 && git status --short
```

Uncommitted changes you did not make mean another session is live. **Do not clobber and do not
assume its work is wrong** — read the diff, keep what is correct, and tell the owner rather than
racing it. On 2026-08-02 two sessions executed the same plan minutes apart; the collision was
caught only because HEAD had moved mid-session.

## Before a model-research campaign

The research track has no daily reader and drifts silently. Verify before dispatching agents:

```bash
git branch --show-current
rg -n 'C2mQM|never work on main|never push to main' docs/ .claude/ --glob '!**/worktrees/**'
rg -o 'docs/[a-z-]+\.md' docs/experiment-protocol.md | sort -u   # then confirm each exists
```

A stale branch name in `docs/experiment-protocol.md` or `.claude/commands/improve-model.md` is a
**blocking bug**, not a typo — agents build worktrees from it, and every delta is then measured
against a stale harness, silently and successfully.

Agent verdicts go in `docs/feature-hunt-log.md` (feature-engineer) or `docs/research-log.md`
(all others). A run with no log entry did not happen.

## Finishing

Run the doc check and show its output:

```bash
python3 scripts/check_docs.py
```

It asserts four things: every doc is filed in `PLAN.md`, no doc reference dangles, no doc names
a retired branch, and every figure in `docs/figures.json` matches what the payloads actually
measure. It is part of `make test`.

State what you ran and what it returned. Do not claim a doc is updated without showing the
check pass.
