# /codebase-unification-review — subtractive repository review

Make `main` the single, coherent, minimal expression of the project — with identical outputs.

**The prompt is `docs/prompts/codebase-unification-review.md`. Read it in full and follow it
exactly.** It is kept there, not duplicated here, so the prompt has one source and the evidence
documents that cite it keep resolving.

## Before you start

- This is a **subtractive** review. Success is lines removed, branches retired, duplicate paths
  collapsed — while every number the system produces stays bit-for-bit the same.
- A change that improves the model, adds a feature, or modernises style is **out of scope and
  counts as a failure of the task**, not a bonus.
- Sibling prompts own their own domains: `/site-ux-audit`, `/league-qa-audit`,
  `/launch-readiness-audit`. Log defects there and hand them over — do not fix them here.
- Read `docs/pipeline-invariants.md` first. Several things that look like duplication are
  deliberate and recorded there — the two ridge modes, ESPN-id club resolution, the `live-data`
  branch feeding the `workflow_run` deploy chain.

## Output

A dated report in `docs/`, stamped as dated evidence, with each item classified
(DELETE / HOIST / LEAVE / ESCALATE) and an owner decision noted where one is required. File it in
`docs/PLAN.md` and run `python3 scripts/check_docs.py`.
