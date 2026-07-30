# Growth experiment ledger

This ledger is separate from the model experiment registry. It tracks customer, offer, onboarding,
and acquisition tests. No row may be called a winner before its read window and stopping rule.

| ID | Test | Status | Dependency | Primary read | Stopping rule / gate |
|---|---|---|---|---|---|
| `E3-club-watch-concierge` | Full-price Club Watch concierge | blocked | Safe money path, `D2` job gate, five paid-pilot commitments | Prospect→paid, repeat update consumption, continuation choice | Go only at ≥10 buyers, ≥20% buy, ≥60% consume half of updates, ≥70% binding continuation |
| `P4-club-first-sample` | Club-first registration plus one complete sample | implementation ready; cohort not started | Approved boundary and production measurement | Club selection, activation, D30 return, activated→paid | Read after 300 registrations and four weeks |
| `P4-outcome-upgrade` | Outcome-led club-specific upgrade | designed; disabled | Real club movement treatment, stable baseline, sufficient traffic | Checkout starts and paid conversion | Directional read at ~1,000 qualified exposures/cell or 30 checkout starts; do not overstate confidence |
| `O6-trial` | No trial + sample versus event-based/card-required trial | deferred | Ordinary-price D60/D90 baseline | D60 contribution per qualified visitor | ≥50 paid starts/cell or replicated cohort; contribution +15%, retention ≥91% |
| `O6-run-in-pass` | $19–$29 Run-in Pass | deferred | Seasonal-demand evidence | Qualified visitor→paid and contribution | Isolated offer only |
| `CR7A-club-rate` | Manual Club Rate credits | deferred | 120–150 ordinary-price subscribers and retention gate | Incremental paid, contribution, D60/D90 | Referral lift must exceed dilution; retention within 5pp of control |

## One-page brief template

- **ID / owner / date:**
- **Decision this test informs:**
- **Hypothesis:**
- **Primary audience and exclusions:**
- **Control:**
- **Treatment:**
- **Single intended variable:**
- **Assignment unit and stickiness window:**
- **Primary metric:**
- **Guardrails:**
- **Sample/read window:**
- **Stopping rule:**
- **Customer-facing claims, price, spend, or outreach requiring owner approval:**
- **Data-quality checks:**
- **Result:** observation first, inference second
- **Owner verdict:** [ ] go  [ ] iterate  [ ] kill

## Evidence packet template

1. Exact observation window and eligibility rules.
2. Assignment balance and exclusions.
3. Funnel counts with numerators and denominators.
4. Core-value consumption and support/trust incidents.
5. Retention/refund state at the available cohort ages.
6. What was observed.
7. What is inferred and how uncertain it remains.
8. Recommendation and the one decision requested from the owner.

