# Reading relegation odds without fooling yourself

Relegation battles are the most-followed story in the bottom half of every table — and the
place where preseason projections are most likely to mislead you. Entenser publishes
relegation probabilities across the Big-5, the European second tiers, and a growing set of
top flights worldwide. Here's how to read them well.

## The one number that matters: how much of the season is played

Entenser's own backtests are blunt about this. Preseason bottom-table odds carry **almost no
skill over base rates** — a preseason relegation probability is barely better than knowing
which clubs were promoted. Skill only reaches a usable level around **25% of the way into a
season** (roughly matchweek 9–10 in a 38-game league), when relegation calls start to
genuinely separate the doomed from the merely nervous.

Because of that, if season-market betting is ever offered, relegation and promotion
recommendations are **gated to ≥25% season progress**. Title and top-N markets, which carry
more preseason skill, can quote earlier. We built that rule *before* the feature exists, so
it can't be conveniently forgotten later.

## Why the model can see risk the table can't

Two features help Entenser flag a relegation candidate the raw table would miss:

- **xG-based strength.** A team riding a hot streak of narrow wins may have ugly underlying
  numbers; the model prices the underlying numbers, not the lucky results.
- **Squad-value priors** (team-level, for the leagues where they help). A bottom-half club
  whose recent form badly understates its roster quality gets a nudge back toward that
  quality — this specifically improved relegation calibration in testing without dragging
  the title race toward the richest club.

## How to use it

- **In July–August:** treat relegation odds as an opening prior. Be skeptical of confident
  numbers on promoted sides.
- **From ~matchweek 10 onward:** the numbers earn their keep. This is when a persistent
  high relegation probability is a real signal.
- **Always:** check the model-vs-market gap. A club the model fears far more than the market
  does (or vice versa) is where the interesting disagreement lives.
