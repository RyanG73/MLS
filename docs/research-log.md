# Research log — calibration, hyperparameter, and architecture experiments

Shared log for the calibration-tuner, hyperparameter-optimizer, and model-architect agents.
Newest entry first. Feature experiments have their own log: `feature-hunt-log.md`.

Format and thresholds are defined in `experiment-protocol.md` §4 and §6. A run with no entry
here did not happen.

```markdown
## <YYYY-MM-DD> — <component> — <one-line description>
**experiment_id:** <id> · **Verdict:** KEEP / marginal / DROP
**Δ best_brier:** <value> · **Δ max_cal_error:** <value>
**Notes:** <what changed, why it did or did not work>
```

---

## 2026-08-07 — cross-league — club-name resolution repaired, and a per-club continental layer
**experiment_id:** club-bridge-v1 · **Verdict:** KEEP
**Δ held-out 1X2 Brier:** −0.0083 (0.5857 → 0.5774), 9/10 seeds, 633 matches

Owner, rejecting the previous round: *"the internal domestic calibration might be great, but the
cross league calibration is a mess if PSG, who just played in the champions league final back to
back years, is #18 and portugal has three teams in the top ten despite no consistent deep european
competition runs in a long time."*

Both halves are checkable against data already in the repo. Quarter-final-or-better appearances,
2021–24: Real Madrid 16, Man City 11, Bayern 10, Inter 10, **PSG 9** — 5th most in Europe. Benfica
4. **Sporting CP 0. FC Porto 0.** The ladder had PSG 18th and those three Portuguese clubs 6th, 7th
and 10th.

**Cause 1 — a country coefficient is the wrong instrument for a club.** It measures an
association's DEPTH: how many of its clubs qualify and how far they collectively go. Portugal is
6th in Europe because Benfica, Porto, Sporting and Braga all enter and all accumulate; France is
5th despite PSG, because Ligue 1's other clubs exit early. Applied flat to every club it therefore
under-rates the elite of a top-heavy league and over-rates the elite of a deep one — in opposite
directions, which is why no single league-level parameter could fix both.

**Cause 2 — 40% of the continental evidence was being silently discarded.** `_resolve_uefa_team`
searched `_EXTENDED_UEFA`, which deliberately excludes the big five, so a big-5 club missing from
the hand-curated `_ESPN_TO_MODELED` map could never resolve by name and its entire European record
was dropped. Napoli, Sevilla, Villarreal, Marseille, Newcastle, Wolfsburg and Union Berlin were all
in that hole. A second group failed on football-data abbreviations ESPN writes out in full —
"Sp Lisbon" vs "Sporting CP", "Olympiakos" vs "Olympiacos", "FC Copenhagen", "Ajax".

Both fixed: name matching now searches every modelled UEFA league, with an **ambiguity guard** that
returns None on a cross-league collision rather than guessing (measured: 0 of 632 normalized keys
are claimed by more than one UEFA league, so opening the big five is safe, and the guard keeps it
safe as leagues are added), plus a small alias table. **Matches with both clubs resolved: 60% →
73%.** The bridge, the club layer and every future fit all gain that evidence.

That mattered directly: before the repair Sporting CP and FC Porto had **zero** resolved
appearances, so no amount of fitting could move them. After it they have 24 and 29.

**The layer** (`scripts/eval/club_bridge.py`): for each club, hold every opponent at its published
rating, find the additive adjustment that best explains that club's own continental results, and
shrink toward zero by evidence — `adj = MLE · τ²/(τ² + se²)`, τ = 60. Intra-league ties are kept
here although `league_bridge` drops them: they carry no cross-league signal but a great deal of
per-club signal. A club with no European history is untouched, which is right — for it the league
really is the only evidence. Gated on held-out Brier over 10 seeds exactly like the league fit, and
`offsets` is written EMPTY when the gate fails, so a rejected fit degrades to no adjustment.

Largest applied adjustments: Liverpool +86, Sporting CP −79, Real Madrid +65, FC Porto −63,
Chelsea +62, Benfica −60, Man Utd −58, Galatasaray −48, PSG +40, Club Brugge −27.

**Ladder**: PSG 18th → **9th**; Benfica 6th → **14th**, FC Porto 10th → **19th**, Sporting CP 7th →
**22nd**; Real Madrid 9th → **2nd** (16 quarter-finals, the most in Europe); Club Brugge → 26th,
Galatasaray → 49th, Celtic → 100th. Published per row as `global_elo_adj` so the total stays
reproducible from the payload alone, with contract tests for the arithmetic and a ±150 bound
asserting the shrinkage is doing its job.

**Also found:** nine club NAMES are duplicated on the ladder. Two are genuinely different clubs
(Liverpool FC and Liverpool FC of Montevideo; Santos of Brazil and Santos Laguna) — and keying
per-club work by name alone had silently handed the English Liverpool's European record to the
Uruguayan club until it was keyed by (league, club). The other seven are the SAME club appearing in
two divisions at once (Athletico-PR, Coritiba, Remo, Chapecoense in both Brazilian tiers;
Stenhousemuir in two Scottish ones; two Argentine cases), which is a stale-payload artifact and is
still open.

## 2026-08-07 — coefficients / ELO — fresh UEFA capture, per-competition HOME_ADV, tier dispersion
**experiment_id:** coeff-capture-2026-08 · **Verdict:** KEEP

Owner asked for all five recommendations from the ELO audit. Three were calibration.

**1. UEFA country coefficients recaptured** (five-year associations, as published for 2025-26).
The table's own PROVENANCE note had been asking for this since 2026-07-31; by then ten of its
twenty values were typed estimates and `_K_COEFF` had made them load-bearing for the whole ladder.
Every correction landed in the direction the continental residuals had independently pointed:

| league | was | now | residual measured BEFORE the capture |
|---|---|---|---|
| eredivisie | 61.0 | **51.6** | z = −2.8 (over-rated) — the largest anomaly in the set |
| austria-bundesliga | 33.0 | **25.3** | z = −0.9 |
| scottish-prem | 32.0 | **25.1** | z = −0.3 |
| swiss-super-league | 33.0 | **29.1** | z = +0.2 |
| poland-ekstraklasa | 32.0 | **43.5** | z = +1.9 (UNDER-rated — wrong way up) |
| serie-a | 76.0 | **87.7** | Italy had been placed below Spain; it is above |

**`_K_COEFF` refitted to 4.0** (4.04 ± 0.33) on the captured scale, down from 4.7 on the old one —
the captured table spans England-to-France 34.2 points where the old spanned 27, so the same
physical gap needs a smaller multiplier. The two are one calibration in two pieces. Note the
held-out margin shrank to −0.0025 (6/10) from −0.0079 (9/10), because the baseline improved on its
own: at k=3.0 the fresh coefficients already score 0.5621 where the old ones scored 0.5656. Most of
what k had been straining to correct was a wrong input table.

**Both manual overrides are now gone, and that is the finding.** The Eredivisie entry (−206, added
2026-08-06) was measured honestly — MLE −244 ± 30, z = −2.9, corroborated by a 101-appearance
residual check — and was still a patch on the wrong layer: its coefficient said 61 when the
published value is 51.6, so every "measurement" of the anomaly was a measurement of that error.
After the capture the Eredivisie sits **1.2σ** from its own prior and needs nothing. Primeira, the
other long-standing override, had already gone the same way. Two overrides, both correct
arithmetic, both symptoms of a stale input.

**Whole-scale validation**: mean |z| across 16 leagues **0.79**, where a perfectly calibrated set
gives ≈0.80. Progression: k=3.0 + old table → several leagues beyond 2σ and the EPL anchor itself
at +2.7; k=4.7 + old table → 0.87, two beyond; k=4.0 + capture → **0.79, one beyond**.

**2. HOME_ADV is per competition** (`scripts.eval.elo.home_adv_for`). Swept end to end — compute_elo
re-run at each value so the ratings themselves refit — on log-loss of expected against realised
score. **19 European domestic leagues, ~86,000 matches: best at 55 (0.64065) against 0.64356 at 80,
and 80 was optimal in ZERO of the 19.** Mean bias +0.0358 at 80 versus +0.0031 at 55. MLS: best 90,
80 within 0.0002, so **80 stays and the champion config is untouched**; Brazil likewise. The split
is mechanical — MLS and the Brasileirão are continental-travel leagues, which is exactly where a
large home advantage belongs. Everything else measured preferred 40–70 (Japan 40, Sweden 40,
Denmark 40, Austria 40, Switzerland 40, Argentina 55, Liga MX 55, Poland 55, Romania 55, Russia 55,
Norway 70, China 70), so 55 is a pooled estimate rather than a guess. **Takes effect on the next
league rebuild** — `apply_global_elo_payloads` only recomputes `global_elo` from existing `elo`.

**3. Tier bridges now translate spread, not just level.** A bridge had always been a pure shift,
which assumes a second tier's rating gaps mean what its parent's mean. Measured child/parent slope
ratios: championship/epl **0.782 ± 0.055**, bundesliga-2/bundesliga 0.723 ± 0.074, ligue-2/ligue-1
0.802 ± 0.072, league-two/league-one 0.823 ± 0.071, serie-b/serie-a 0.872, segunda/la-liga 0.875 —
and league-one/championship **1.026 ± 0.079**, so the compression is at the top-flight boundary,
not at every step, and is stored per hop. Applied about each league's own mean in
`apply_global_elo_scale`, published as `elo_scale.dispersion`/`pivot` so it stays checkable from
the payload alone. Burnley 1585 → **1540**.

Found while wiring it: `build_power_rankings` recomputed `elo + offset` itself instead of reading
the published rating, so the ladder and the league page disagreed for every second-tier club the
moment the translation stopped being a pure shift. It now reads `standings[].global_elo`.

**Ladder**: Club Brugge 9th → **22nd**, Union SG 10th → **23rd**, Galatasaray 12th → **25th**,
Celtic 38th → **87th**, Burnley 30th → **39th**, Lens (the original 2026-08-06 complaint) → **48th**.

**Open, and now pointing the other way:** Ligue 1 is the single league beyond 2σ at **+2.7 —
under-rated**, MLE −67 against a −137 prior. Its coefficient is a fresh capture so the input is
right, and hand-patching one league is precisely the mistake the two dead overrides above record.
Left to the bridge regression, which is the mechanism for it. Worth watching: we may have
over-corrected Ligue 1, and PSG at 18th is the visible symptom.

## 2026-08-07 — cross-league bridge — _K_COEFF fitted 3.0 → 4.7 (the compressed league scale)
**experiment_id:** kcoeff-4p7 · **Verdict:** KEEP
**Δ held-out 1X2 Brier (continental):** −0.0079 (0.5656 → 0.5576), 9/10 seeds · **fit:** 4.72 ± 0.37,
z vs 3.0 = **+4.6** · single parameter on 743 matches

**Notes:** Owner: "Club Brugge 54th → 9th, Union SG 61st → 10th, Galatasaray 57th → 12th … we need
to fix this in general". The general cause was `_K_COEFF`, the ELO-points-per-coefficient-point
multiplier. Its own comment described 3.0 as "the starting prior" for a calibration
(`validate_continental.py`) that was never performed. At 3.0 the entire Belgian league sat **117
ELO** below the Premier League — roughly an EPL title contender to a mid-table side — so any club
dominating a weak league landed in the world top ten. Every "X is not a top-ten team in Europe"
report since 2026-08-05 traces to this one number.

Corroborated three independent ways:

1. **Per-league drift.** At k=3.0 the leagues pull away from their own coefficient priors
   (Eredivisie z=−3.0, Austria −2.1, Scotland −1.7, Sweden −1.5). At k=4.7 they sit on it
   (Belgium +0.2, Austria −1.0, Scotland −0.4, Switzerland −0.1, Sweden −0.7).
2. **Per-club residuals.** Big-five elite under-rated (Bayern +2.6σ, Real Madrid +2.0, Chelsea
   +1.7), small-league clubs over-rated (Celtic −2.1, Galatasaray −1.3, Club Brugge −0.6). That
   gradient is what a too-small multiplier produces.
3. **Whole-scale residual check.** Mean |z| across 16 leagues: **0.87** at k=4.7 (a perfectly
   calibrated set gives ≈0.80). Only Eredivisie (−2.8) and Ligue 1 (+2.3) remain outside 2σ.

**Both `_MANUAL_LEAGUE_OFFSET` entries removed.** Primeira (added 2026-07-13) and Eredivisie
(added 2026-08-06) were the same bug twice: each was hand-placed because "the generic `_K_COEFF`
static fallback under-penalises this league". With k fitted, Primeira's own record sits 0.7σ from
its coefficient prior and needs nothing. Eredivisie still rejects at 2.9σ and was re-added at
**−206**, the empirical-Bayes posterior of a −155 prior (σ=35, a captured C1 coefficient) against
a −244 ± 30 MLE — not the raw MLE, which over-corrects PSV Eindhoven, whose own 12-match record is
consistent with ≈−197.

**Ladder:** Club Brugge 9th → **20th**, Union SG 10th → **23rd**, Galatasaray 12th → **30th**,
Celtic 38th → **75th**, Lens 33rd → 43rd, PSV 17th. Global ELO range 762–1,767 → **748–1,756**.

**Rejected again, now under clean conditions.** The shared spread factor — "a club that wins 80% of
its domestic matches climbs regardless of whom it beats" — was re-fitted at k=4.7 and came out
**b = 1.045 ± 0.127 (z = +0.4)**, held-out 0.5607 vs 0.5593 for b=1, 4/10 seeds. At k=3.0 it had
measured 0.900 ± 0.126. Both fail. With the level error removed there is no spread error left:
each league's internal ELO spread maps 1:1 onto the global scale. **The "weak leagues have
inflated ELO spread" hypothesis is dead** — see the domestic-calibration table below, which shows
the opposite.

**Domestic ELO calibration by league** (logistic refit of result on the league's own pre-match
rating gap; slope < 1 = that league's gaps are too wide). This is measured on 70,000+ domestic
matches, not the 743 continental ones:

| | slope | | | slope |
|---|---|---|---|---|
| Greek Super League | 1.04 | | 2. Bundesliga | 0.62 |
| Primeira | 0.98 | | Ligue 2 | 0.68 |
| Eredivisie | 0.95 | | Championship | 0.70 |
| La Liga | 0.94 | | League One | 0.71 |
| Süper Lig | 0.93 | | Serie B | 0.76 |
| **EPL** | **0.89** | | League Two | 0.59 |
| Ligue 1 | 0.84 | | | |
| Belgian Pro | 0.83 | | | |

Mean slope: **top flights 0.91, second tiers 0.70**. The top-heavy "weak" leagues are the
best-calibrated in the set; the Premier League and Ligue 1 are worse. Second and lower tiers are
30–40% over-dispersed, which is an independent confirmation of the relegated-club problem and says
the ±120 tier bridges are translating an inflated scale as though it were the Premier League's.

**Still open:** Benfica 8th, Sporting CP 9th, FC Porto 10th. Primeira's own continental record is
0.8σ from its prior, its internal calibration is near-perfect (slope 0.98) and its domestic ELO SD
(132) is the largest of any league — so nothing in the evidence supports moving it, and the three
clubs are what the model honestly believes. Resolving it needs external evidence (a fresh capture
of the UEFA country coefficients), not more fitting.

## 2026-08-06 — cross-league bridge — UEFA match constants calibrated; offsets return to priors
**experiment_id:** uefa-const-1p25-1000-110 · **Verdict:** KEEP
**Δ held-out 1X2 Brier (continental):** −0.0298 mean over 10 seeds (0.6006 → 0.5708), offsets refit
at every grid point · **robustness:** beats the live model 10/10 seeds · **calibration error**
(|predicted − actual| summed over H/D/A): 0.216 → 0.085

**Notes:** Owner reported "the global rankings have Ligue 1 teams way too high" (Lens 10th). The
cause was not the offsets. `_CONF_CONST["UEFA"]` was the only confederation never fitted — its
note called the values "physically-grounded priors" while Concacaf, CONMEBOL and AFC had all been
grid-swept. At `goal_scale` 3000 a 300-ELO gap is a 1.26× goal rate, far too flat to express
dominance, and over 743 matches the model predicted **39.5% home wins against an actual 50.3%**.
At n=743 the standard error on a 50% rate is 1.8pp, so an 11pp miss is ~6σ.

A model that under-predicts strong clubs must put the missing strength somewhere, and the only
free parameters are the league offsets. So leagues whose European entrants win a lot were
inflated — Ligue 1 to −18 from a −81 prior. The EPL, being the anchor at 0, could not inflate and
simply kept the largest residual of any league (+0.43 points per appearance): the same miss with
nowhere to go, visible in the data the whole time.

| base_goals | goal_scale | home_adv | mean Brier | seeds | even-tie goals |
|---|---|---|---|---|---|
| 1.35 | 3000 | 80 | 0.6006 | — (live) | 1.35 + 1.35 = 2.70 |
| 1.35 | 1600 | 100 | 0.5810 | 10/10 | 1.53 + 1.35 = 2.88 |
| **1.25** | **1000** | **110** | **0.5708** | **10/10** | **1.61 + 1.25 = 2.86** |
| 1.35 | 900 | 110 | 0.5684 | 10/10 | 1.72 + 1.35 = 3.07 — rejected, too many goals |

**Constrained, not merely optimised.** `bracket_sim` samples scorelines from these lambdas and the
1X2 objective cannot see goals, so the grid was restricted to an even non-neutral tie yielding
1.35–1.70 home and 2.60–2.95 total. The unconstrained optimum keeps running to `goal_scale` ~900
for another 0.002, inside the noise on 743 matches and not worth an unphysical scoreline model.
`tests/test_bracket_sim.py` now asserts the scoreline bound for all four confederations; it
replaces a `goal_scale ≥ 2000` floor that bound on the fit without bounding what mattered.

**Consequence: the fitted offsets stopped being worth adopting.** Refit at the new constants, the
UEFA fit scores 0.5748 held-out against 0.5661 for the priors — a degradation — and the existing
robustness gate rejects it and writes the priors, unprompted. The adaptive ridge was re-swept
across its own λ scale (1e-4…1e-3) and no setting beats the priors either (best +0.0001, 5/10).
**Read plainly: most of what the 2026-08-05 ridge loosening bought was compensation for this
calibration error.** That change was not wrong to make — it improved held-out Brier at the
constants then in force — but its mechanism was not the one the note claimed.

**Priors then tested one at a time** by profile likelihood (all other leagues held at their
priors, so the question is only whether a league's own record rejects its own prior). Sixteen of
seventeen are within noise. **Ligue 1: MLE −38 ± 28, z = +1.7 — the −81 prior stands untouched**,
and Lens falls 10th → 33rd on the constants change alone. One prior is rejected: **eredivisie,
MLE −197 ± 30 against −99, z = −3.3** (101 appearances, 1.12 observed points per appearance vs
1.51 expected), now a `_MANUAL_LEAGUE_OFFSET` entry.

**Rejected in the same session, recorded so they are not re-tried blind:**
- *Per-league slope* on (elo − league mean), ridge-regularised. Improves Brier (0.5994, 10/10 at
  λ_b=1e-2) but moves the ladder the WRONG way: it raises clubs above their league mean, so Lens
  goes up, not down. Wrong parameterisation for the problem.
- *Single shared spread factor* for all non-anchor leagues — the right shape for "a club that wins
  80% of its domestic matches climbs regardless of whom it beats". Fitted **b = 0.900 ± 0.126,
  z = −0.8**, held-out Brier 0.5666 vs 0.5656 for b=1, 3/10 seeds. Not supported.
- *Adaptive (constant-weight) ridge* as a replacement for count-weighting. The count-weighted form
  provably cancels against the NLL — penalty λ·n and curvature n·I give shrinkage 2λ/(2λ+I),
  independent of n — so every league shrinks equally regardless of evidence, which is how Finland
  moved 302 ELO on FOUR appearances. Adaptive is the correct shape, but at the calibrated
  constants it does not beat the priors, so nothing turns on it today.

**Open, unresolved:** Club Brugge 54th → 9th, Union SG 61st → 10th, Galatasaray 57th → 12th. Their
priors match their own records (Belgium z = −0.7), so no evidence moves them. The residual defect
is within-league ELO inflation — Club Brugge's domestic 1773 exceeds Arsenal's 1756 — and the two
spread corrections above both failed to find it in this data. The next real step is external:
a fresh capture of the UEFA country coefficients, which `_LEAGUE_COEFF`'s own PROVENANCE note has
been asking for since 2026-07-31.

## 2026-08-05 — cross-league bridge — UEFA ridge loosened 2e-5 → 5e-7
**experiment_id:** uefa-ridge-5e7 · **Verdict:** KEEP
**Δ held-out 1X2 Brier (continental):** −0.0090 mean over 10 seeds (0.6096 prior → 0.6006 fitted);
seed-42 split −0.0121 (0.6139 → 0.6018) · **robustness:** fitted beats prior 10/10 seeds
**Notes:** Owner reported the ladder as wrong — "PSV is simply not a top ten team in europe",
Netherlands and Belgium listed too high. The cause was not the coefficient table (fixed
2026-07-31) but the ridge on top of it. At λ=2e-5 every fitted UEFA offset landed within ~15 ELO
of its prior, so `league_bridge` was decorative: the published ladder was
`_K_COEFF * (coeff − 94)` and the 743 continental matches were barely consulted.

λ swept on **mean** held-out Brier across all 10 robustness seeds, not one split:

| λ | mean Brier | Δ vs prior | seeds won |
|---|---|---|---|
| 2e-5 (was live) | 0.6088 | −0.0008 | 10/10 |
| 5e-6 | 0.6070 | −0.0027 | 10/10 |
| 2e-6 | 0.6045 | −0.0051 | 10/10 |
| 1e-6 | 0.6023 | −0.0073 | 10/10 |
| **5e-7 (adopted)** | **0.6006** | **−0.0090** | **10/10** |
| 2e-7 | 0.5994 | −0.0102 | 8/10 — fails robustness |

5e-7 is the loosest setting that still wins on every seed. Below it thin leagues separate toward
−∞ (unregularised, Finland reaches −1427) and seed agreement breaks.

**The adaptive ridge was tested and rejected for UEFA.** `ridge_by_count=False` is the correct
shrinkage shape in principle and is what CONMEBOL/AFC use, but measured here it is worse: at a
matched Brier of 0.6008 it wins only 8/10 seeds and sends Sweden 684 ELO from its prior, against
10/10 and 431 for the count-weighted fit at 5e-7. UEFA keeps `ridge_by_count=True`.

`_MAX_DELTA_BY_CONF["UEFA"]` raised 150 → 450 in the same change, because ±150 was calibrated
when nothing moved more than ~15 ELO and it now binds hardest on the fifteen leagues whose prior
is a typed estimate rather than a captured coefficient. 450 still catches a runaway.

**Ladder effect** (`power.js` rebuilt, 965 clubs / 55 leagues unchanged): PSV 7th → **27th**,
Club Brugge 10th → **54th**, Union SG 12th → **61st**, Feyenoord 31st → **106th**, Benfica 16th →
**31st**. Top nine is now nine big-five clubs: Bayern, Barcelona, Arsenal, Real Madrid, Man City,
PSG, Inter, Dortmund, Man Utd. Global ELO range moved 770–1770 → **697–1797** (`docs/figures.json`).

**Caveat to carry forward:** the fit is generous to Ligue 1 (−18, from a −81 prior), putting Lens
10th and Lille 12th. That is what 116 Ligue 1 continental matches say, but it is the least
intuitive part of the result and the first thing to re-examine at the next refit.

## 2026-08-05 — log created

`experiment-protocol.md` §6 specified `calibration-log.md`, `hyperparameter-log.md`, and
`architecture-log.md` from 2026-05-29. None was ever created, so three of the four agents ran
without a durable evidence trail — their results survived only if an orchestrator happened to
write them into `PLAN.md`, and `PLAN.md` became navigation-only on 2026-08-01.

The three were collapsed into this single log rather than recreated separately: the fleet runs
as one cycle, and four logs for four components was the over-partitioning that caused three of
them never to exist.

**Prior results are not lost** — they are recorded per campaign in `PROJECT_HISTORY.md` and in
`experiments/registry.jsonl`. This log starts clean and is authoritative from today forward.
