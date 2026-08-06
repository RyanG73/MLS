# /site-ux-audit — full-site UX review, mobile and desktop

Run the canonical interface audit: every surface, every breakpoint, Chromium and real iOS WebKit.

**The prompt is `docs/prompts/site-ux-audit.md`. Read it in full and follow it exactly.**
It is kept there, not duplicated here, so the prompt has one source and the evidence documents
that cite it keep resolving.

## Before you start

- Treat every surface as **unreviewed**. Do not read prior review notes in `docs/` for verdicts
  or inherit their conclusions. Measure it yourself.
- Scope is **the interface**. Data correctness belongs to `/league-qa-audit`; launch and revenue
  readiness belongs to `/launch-readiness-audit`. Log cross-domain defects and hand them over.
- Screenshots lie at deep scroll — verify layout via DOM measurements, not screenshot inspection.

## Output

Write findings to a dated `docs/` report, stamped as dated evidence:

```markdown
> **Dated evidence, as of YYYY-MM-DD.** Superseded by `docs/STATUS.md` for anything it also covers.
> Figures inside are as-of and may be stale — re-measure before quoting, and never publish a
> number from here without checking `docs/figures.json`.
```

Then file the new report in `docs/PLAN.md` and run `python3 scripts/check_docs.py`.
