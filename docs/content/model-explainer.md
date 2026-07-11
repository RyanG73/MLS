# How Entenser predicts football — and why it never looks at the odds

Entenser is a **market-blind** football prediction system. It publishes win / draw / loss
probabilities for matches, and season-long title, European-place, promotion and relegation
odds across more than two dozen leagues. Crucially, it is *never trained on betting odds* —
so when Entenser disagrees with the market, that disagreement is genuinely independent
information, not a repackaging of the bookmaker's number.

## The pipeline, in plain terms

Every projection is the blend of a few well-understood models:

- **ELO ratings** track each team's strength over time, with home advantage and
  between-season regression built in. ELO answers "how good is this team *right now*?"
- **Dixon–Coles** models how many goals each side tends to score and concede, with a
  120-day time-decay so a match from last month counts for more than one from last autumn.
- A **season-weighted XGBoost** classifier (a 5-model seed bag, for stability) blends
  expected goals (xG), recent form, rest days and schedule congestion.
- The pieces are combined and then **temperature-calibrated**: we tune the output so that
  when the model says 60%, the thing actually happens about 60% of the time.

## How we keep ourselves honest

We score predictions with the **Brier score** (lower is better). As a yardstick, a naive
"always pick the home team" baseline scores about 0.6667, and a uniform guess about 0.6406.
On 2022–2025 walk-forward tests — always predicting *forward*, never peeking at results the
model has already seen — the current champions land at:

| League family | Brier | Naive | Edge over naive |
|---|---:|---:|---:|
| Big-5 Europe | 0.593 | 0.649 | +8.5% |
| Europe lower tiers | 0.615 | 0.650 | +5.3% |
| USL Championship | 0.625 | 0.646 | +3.3% |
| MLS | 0.633 | 0.641 | +1.2% |
| NWSL | 0.646 | 0.651 | +0.8% |

**We do not claim to beat the sharpest bookmakers.** Against a book like Pinnacle, a
market-blind model typically trails by a couple of percent on aggregate. That's expected.
The value is in *specific pockets* where the model and market disagree, in transparency
about where the model is weak, and in tracking whether a projection is stable enough to act on.

## What we won't pretend to know

The strongest thing we can say about a prediction site is where it's *wrong*. Draws are
structurally hard, so draw-side recommendations are suppressed. Preseason numbers are
statistical priors, not live probabilities. Thin samples — early season, lower tiers, cup
ties — are flagged, not hidden. That honesty is the product.
