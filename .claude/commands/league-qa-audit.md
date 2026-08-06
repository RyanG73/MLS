# /league-qa-audit — per-league data-correctness audit

Audit the league payloads one league per pass: fields, units, buckets, and whether the published
probabilities describe the competition's real format.

**The prompt is `docs/prompts/league-qa-audit.md`. Read it in full and follow it exactly.**
It is kept there, not duplicated here, so the prompt has one source and the evidence documents
that cite it keep resolving.

## Before you start

- **One league per pass.** Produce a findings block, then move to the next. The prompt is
  self-contained and names the exact files, fields, and units.
- Scope is **data correctness**. Interface defects belong to `/site-ux-audit`.
- Read `docs/pipeline-invariants.md` first. Several classes of defect this audit finds are
  already-known hazards with recorded causes — split-round formats approximated as plain tables,
  league-specific helpers applied league-wide, unbridged leagues excluded from the ladder.

## Output

Append to `docs/league-qa-audit-findings.md`, which is stamped dated evidence and is retained
precisely because its findings are not all closed. Anything that changes production truth also
goes to `docs/STATUS.md` with proof. Then run `python3 scripts/check_docs.py`.
