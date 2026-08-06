# /competitor-deep-dive — hands-on teardown of comparable products

Mine successful sports-data businesses for mechanisms Entenser can adopt: how they are built,
packaged, priced, billed, and made habitual — screen by screen.

**The prompt is `docs/prompts/competitor-deep-dive.md`. Read it in full and follow it exactly.**
It is kept there, not duplicated here, so the prompt has one source and the evidence documents
that cite it keep resolving.

## Before you start

- This is **not** market sizing or positioning. `docs/competitive-intelligence-2026-07-combined.md`
  did that on 2026-07-16 and remains the strategic evidence base — the prompt goes one level below
  it, into flows, pricing pages, notification settings, onboarding, paywall placement, and billing
  screens.
- **If a finding could have been written without opening the site, it does not belong in the
  report.**
- Respect the product's own constraints when proposing mechanisms: the paid boundary in
  `docs/product-invariants.md` (lock the continuity, never the current answer) and the claim
  limits in `docs/paid-claim-matrix.md`.

## Output

A dated report in `docs/`, stamped as dated evidence. **Any figure you quote must come from
`docs/figures.json` or a live measurement** — the previous deep dive carried a stale club count
into proposed public marketing copy, in seven places. File the report in `docs/PLAN.md` and run
`python3 scripts/check_docs.py`.
