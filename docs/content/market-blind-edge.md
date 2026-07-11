# Why "market-blind" is the whole point

Most football prediction sites quietly lean on the betting market. They ingest the odds,
maybe dress them up with a model, and hand you back a number that is — underneath — the
bookmaker's own opinion. That's fine for a lot of uses. It's useless for one thing you might
actually care about: knowing when the market is *wrong*.

Entenser is built the other way around. The model is **market-blind**: betting odds are never
a model input. Not the opening line, not the closing line, nothing. Team strength, expected
goals, form, rest, schedule — those go in. Odds never do.

## Why the constraint is a feature, not a limitation

If you train a model on closing odds, it learns to reproduce them. Its predictions collapse
toward the market, and the quantity you wanted — `model probability − market probability` —
goes to roughly zero. You've built a very expensive mirror.

By refusing to look at the market, Entenser keeps that gap *real*. When the model says a team
should win 44% of the time and the market implies 31%, that 13-point gap is an independent
second opinion. It might be the model spotting something (an xG profile the price hasn't
caught up to). It might be the model missing something the market knows (an injury, a rotation
plan). Either way, it's information — and you can only have it if the two numbers were formed
independently.

## Where odds *do* show up

After a prediction is made, we compare it to the market — to measure honesty, not to make the
call. That's how we compute Brier-vs-market and closing-line value (CLV), the disciplines
that tell you whether a disagreement was actually worth acting on over time. Odds are a
scoreboard here, never a coach.

## The honest bottom line

A market-blind model will usually *trail* a sharp bookmaker on aggregate accuracy. We say so
plainly on our About page. The point was never to beat Pinnacle on every match. The point is
to give you a genuinely independent probability, show you exactly where it disagrees with the
crowd, and then keep score in public so you can decide whether that independence is worth
anything. That transparency — not a promise of profit — is the product.
