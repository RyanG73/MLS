# /launch-readiness-audit — launch and revenue-path readiness

Assess whether Entenser can go live with subscriptions flowing, verifying every claim against
live systems rather than against `docs/`.

**The prompt is `docs/prompts/launch-readiness-audit.md`. Read it in full and follow it exactly.**
It is kept there, not duplicated here, so the prompt has one source and the evidence documents
that cite it keep resolving.

## Before you start

- Treat every launch claim in `docs/` as **unverified**. Status docs record what someone believed
  the day they wrote it — leads, not evidence. Confirm each green check against live systems,
  live code, and live config, or downgrade it.
- Scope is **launch readiness and the revenue path**. Interface quality belongs to
  `/site-ux-audit`; data correctness to `/league-qa-audit`.
- The money path is special: defects there abort launch, defects elsewhere fix forward.

## Output

Findings go to `docs/STATUS.md` where they change production truth (with proof — a workflow run
ID, deployed SHA, or live check), and to a dated report otherwise. Stamp any dated report as
evidence, file it in `docs/PLAN.md`, and run `python3 scripts/check_docs.py`.
