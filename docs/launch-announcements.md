# Launch announcement drafts (launch plan H4)

**HOLD — owner approval required.** These are drafts for the free public
forecast surface, not approval for a broad paid launch. The current recommendation
uses 2026-08-17 only as the earliest controlled, full-price Club Watch beta.
Post nowhere until the active plan's commercial, legal, claim-truth, and
data-quality gates pass. When approved, use one or two places first so Ryan can
respond and refine before any wider push.

Live surfaces to link:
- Home: https://entenser.com/
- All leagues: https://entenser.com/leagues/
- A specific league (best for niche subs): e.g. https://entenser.com/leagues/nwsl/
- Weekly recap: https://entenser.com/weekly/
- After the World Cup: https://entenser.com/after-the-world-cup/
- Open data (CSV): https://entenser.com/open-data/
- About / methodology: https://entenser.com/?league=about

**Ground rules that make or break this:**
- On Reddit, self-promotion is tolerated only when you're a genuine participant.
  Comment in the sub for a week or two first; when you post, disclose it's your
  project in the first line. Lead with the thing that's useful to *them*, not
  with "I built a site."
- Never post the same text to multiple subs (cross-post detection + it reads as
  spam). Rewrite per community.
- Don't frame anything as betting picks or edges. The model trails the market;
  the story is transparency, not profit. This also keeps you clear of most subs'
  gambling-promo rules.
- Answer "how is this different from FotMob / Opta / Forebet?" honestly (see the
  ready answer at the bottom).

---

## Reddit — r/MLS (best first post; US-fan fit + post-World-Cup timing)

**Title:** I built a free, market-blind MLS forecast that publishes its own hits and misses — feedback welcome

**Body:**
> Mod note first: this is my own project. The public forecasts linked here are
> free, and there are no affiliate links. Entenser also has an optional paid
> Club Watch beta; this post is not an affiliate or betting promotion. Happy to
> take it down if it is not welcome.
>
> After the World Cup I wanted a "what happens next" view of the MLS race that
> wasn't just vibes or repackaged betting odds, so I built one. It runs playoff,
> Shield and MLS Cup probabilities from team strength, xG and form — and it never
> looks at bookmaker odds, so when it disagrees with the market that's genuinely
> independent.
>
> The part I actually care about: it grades itself in public. Every forecast gets
> scored against what happened, and the misses are on the same page as the hits.
> I'm not claiming to beat the market — sharp books usually edge it by a couple of
> percent — just to show the work.
>
> MLS page: https://entenser.com/leagues/mls/
> How it works: https://entenser.com/?league=about
>
> Would love feedback from people who watch more MLS than I do — especially where
> the numbers feel wrong. That's the useful signal.

---

## Reddit — r/NWSL (near-uncontested; genuinely underserved by models)

**Title:** Free NWSL Shield + playoff projections, updated daily — and it shows every time it's wrong

**Body:**
> (My own project. The linked forecasts are free; an optional paid Club Watch
> beta is separate. Mods, remove if not allowed.)
>
> There's almost no public probabilistic modeling for NWSL, which bugged me, so
> the model I run for the men's leagues now covers NWSL too: Shield and playoff
> odds from results and xG, refreshed daily, no betting odds used as inputs.
>
> It publishes its own calibration — hits and misses both — so you can judge
> whether the numbers are worth anything instead of taking my word for it.
>
> https://entenser.com/leagues/nwsl/
>
> Genuinely want to know where it's off. NWSL is hard to model and I'd rather hear
> it from people who follow it closely.

---

## Reddit — r/soccer (huge, strict; only after the niche subs go well)

**Title:** A football forecast model that publishes its own track record — every league, every miss

**Body:**
> Disclosure: my project. The linked forecasts and public grading are free; an
> optional paid Club Watch beta is separate.
>
> Since FiveThirtyEight's SPI shut down there hasn't really been a free,
> transparent, always-on club-forecast site. I tried to build the thing I missed:
> title/relegation/qualification odds across 70+ competitions, a model that's
> never trained on betting odds, and — the point — a public grade on every
> forecast, misses included.
>
> Weekly recap of the biggest movers and how the calls did:
> https://entenser.com/weekly/
> Open data (CSV per league, free with attribution): https://entenser.com/open-data/
>
> Not a tipster site, no picks, no edges — it trails the market and says so. Keen
> on feedback, especially on leagues you know well.

---

## Hacker News — Show HN (technical audience; lead with the engineering + honesty)

**Title:** Show HN: Entenser – a market-blind football forecast that grades itself in public

**Body:**
> It forecasts title/qualification/relegation odds for 70+ football competitions. Two
> things make it unusual:
>
> 1. The model never sees betting odds. Most public "predictions" either are
>    betting odds or are trained on them; this one uses only results, xG and
>    team-strength ratings (Dixon-Coles + a season-weighted XGBoost, temperature-
>    calibrated). So model-vs-market disagreement is actually independent signal.
>
> 2. It publishes its own calibration. Every forecast is scored against what
>    happened, and the misses sit next to the hits. It does not beat the market on
>    aggregate (Brier trails a sharp book by ~2%) and the site says so — the point
>    is a transparent track record, not profit.
>
> Stack is deliberately boring: a static PWA and crawlable league/club pages,
> per-league payloads rebuilt by a Python pipeline, plus a small Vercel API for
> magic-link accounts, durable preferences, and Stripe-authoritative
> entitlements in managed KV. Aggregate production analytics use GA4.
>
> Live: https://entenser.com/  · Methodology: https://entenser.com/?league=about
> Open data (CSV): https://entenser.com/open-data/
>
> Happy to go deep on the modeling, the calibration approach, or the static-site
> build. Feedback and teardowns welcome.

---

## X / Bluesky — short thread

**1/**
Since 538's soccer model died, there's been no free, transparent, always-on club
forecast. So I built one: title, playoff & relegation odds for 70+ competitions.

It never sees betting odds. And it grades every forecast in public — misses too.

https://entenser.com

**2/**
Why "market-blind" matters: most prediction sites just reprocess bookmaker odds.
This one uses only results, xG and team strength. So when it disagrees with the
market, that's real independent signal — not a laundered line.

**3/**
The honest part: it does NOT beat the market. Sharp books edge it by ~2% on
aggregate, and the site says so on every trust page. The pitch isn't profit —
it's a track record you can actually check.

This week's movers + how the calls did → https://entenser.com/weekly/

**4/**
Just finished the World Cup and want somewhere to point that new interest?
Live MLS / NWSL / Liga MX races here → https://entenser.com/after-the-world-cup/

The current forecasts, public grading, and current open data remain free.
Optional Club Watch adds continuity after a complete free sample. Tell me where
the forecasts are wrong.

---

## Ready answer: "how is this different from FotMob / Opta / Forebet?"

- **FotMob / Sofascore:** great live-score apps, but their "predictions" are a
  user guessing game or displayed market odds — not an original, graded model.
- **Opta's supercomputer:** strong data, but the model *ingests betting odds*, its
  method is opaque, and it publishes no calibration. Entenser is the inverse:
  market-blind and publicly graded.
- **Forebet and tipster sites:** betting-framed, black-box, no public track record.
- **Entenser's one-line claim:** the only football model I know of that ignores
  bookmaker odds *and* grades every forecast in public. It doesn't beat the
  market and doesn't pretend to.

## Sequencing suggestion

1. Day 1 (Mon Aug 17): r/NWSL or r/MLS (whichever you're more active in) + the
   X/Bluesky thread.
2. Day 2–3: Show HN (mornings ET land better), once you've fielded the first
   round of feedback.
3. Later that week: r/soccer, only if the niche posts went well and you can point
   to real engagement.
4. Hold r/soccermaths / r/footballanalytics style subs for a data-forward version
   (lead with the open-data + calibration, not the product).
