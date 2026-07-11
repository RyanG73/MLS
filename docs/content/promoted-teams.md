# Promoted teams: what the model knows, and what it honestly doesn't

Every summer, newly promoted clubs are the hardest teams to rate. They arrive with no
top-flight results in the current squad's context, and the market often over- or
under-reacts. Here's exactly how Entenser handles them — including where we've tried to do
better and *failed*, because that's the honest part.

## Seeding a team that has no top-flight history yet

Entenser doesn't guess. It uses a **cross-tier ELO bridge**: a fitted offset that maps a
club's strength in the division it's leaving onto the division it's joining. Those offsets
are learned per league-pair (Championship→Premier League, 2. Bundesliga→Bundesliga, and the
Spanish, Italian and French equivalents), and they're bidirectional — the same machinery
seeds *relegated* teams dropping down a level. A promoted team below the target division's
floor is seeded as a promotion-favourite-to-struggle, never snapped to "worst team ever".

## The experiment that didn't work (and why we're telling you)

The intuitive next step is: once a promoted team starts playing, *quickly* forget the bridge
prior and trust their new-division results. We tested exactly that — a "bridge-decay" scheme
that fades the prior out over the first 5, 8 or 10 matches — on the full England promotion
chain.

The result: **no improvement.** Decaying the prior tied normal destination-league updating
(Brier ≈ 0.6326 vs 0.6325) and both beat a permanently-frozen bridge (0.6410) — but there was
no hidden first-five-match win to capture. So we kept the simpler approach: bridge-seed in
preseason, update normally once real matches arrive. No change shipped, and we logged the null
result so nobody "rediscovers" it the hard way.

## What this means if you're using the numbers

- A promoted team's **preseason** projection is a reasonable prior, but it's a prior — it
  can't see a new signing or a tactical reset.
- Promotion and relegation probabilities carry **almost no skill until ~25% of the season**
  has been played. Before that, treat them as a starting point, not a verdict.
- Once results accrue, the model updates like any other team — no special "promoted-team
  penalty" lingers longer than the data supports.

The takeaway: be most skeptical of promoted-team odds in July and August, and let the first
handful of real matchdays do the talking.
