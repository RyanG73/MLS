# Entenser product invariants

**Standing constraints. Not a plan, not a checklist — these do not complete.**

Extracted 2026-08-01 from `intelligence-hub-implementation-instructions.md` §2, which was deleted
after the Intelligence Hub / Club Watch shipped. The implementation steps were finished work; these
rules were not, and were being lost inside a 1,405-line document nothing referenced. Git retains the
original.

Any change that breaks one of these is a product decision for Ryan, not an implementation choice.

## Truth and attribution

1. **One fact, one answer.** The hub, email, alert, response, export, and share card must read from
   the same computed event and evidence records.
2. **No invented explanations.** All numerical and causal language must be generated from structured
   calculations. An LLM may translate a user question into a supported intent; it may not create
   figures, causes, or unsupported football analysis.
3. **Label attribution honestly.** `race-deltas.js` cause values (`result`, `model`, `refresh`)
   identify the *class* of change. They do not prove how many percentage points came from the user's
   result, rival results, or schedule. Never present them as a decomposition.
4. **Do not confuse uncertainty types.** Monte Carlo sampling error, future-match uncertainty, model
   uncertainty, and data quality are different things. Never call a simulation percentile a
   confidence band unless its coverage has been statistically validated.
5. **Respect route status.** `live`, `preseason`, `completed`, results-only, and historical leagues
   support different features. An unsupported analysis renders a precise unavailable state — never
   fabricated or stale output.
6. **Reproducible simulations.** Saved scenarios, explanations, emails, and receipts carry the input
   snapshot, model configuration, simulation version, seed, and run count that produced them.

## The paid boundary

7. **Preserve the free-floor ratchet.** Current public forecasts, match probabilities, public
   grading, and current-season public trajectories remain free. Paid value comes from monitoring,
   personalization, proactive delivery, new analyses, private multi-season depth, saved work, and
   creator tools.
8. **Public trust stays public.** Model health, methodology, aggregate grading, and honest misses
   cannot become subscriber-only. Paid tiers may add personalized filtering and historical depth on
   top — never gate the record itself.
9. **Lock the continuity, never the current answer** (owner decision, 2026-08-01). Any number that
   exists today stays visible and free. What Club Watch sells is that someone watched it — what
   changed while you were away, the evidence behind it, saved scenarios, per-club history. A lock on
   a figure the public site already publishes makes the "free forever" promise false.

## Security

10. **Private means access-controlled.** A file is not private merely because it sits outside
    `webapp/`. This repository is publicly readable, so private archives must not be committed here.
    Store them in an access-controlled deployment artifact or object store.
11. **No localStorage security theater.** `IntelStore` is a presentation cache, not an entitlement
    system. It must never protect or grant paid data.

## Related

- `paid-claim-matrix.md` — what may be claimed on each surface, and the gate before expanding.
- `growth-measurement-contract.md` — population and event definitions behind every reported number.
- `CLAUDE.md` — model, training, and evaluation decisions not to re-litigate.
