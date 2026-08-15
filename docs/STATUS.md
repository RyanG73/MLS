# Entenser — Current Status

**Repository verified:** 2026-08-15 · **Production last verified:** 2026-08-15 (merge `99d045a` deployed and re-checked) ·
**Owner:** Ryan · **Approved direction:** controlled Club Watch beta no earlier than 2026-08-17,
pending every commercial, production, customer-evidence, and launch gate

**How the 2026-08-15 stamp was earned.** Every row below was re-checked against production, not
read from source: live HTTP against `entenser.com` and `api.entenser.com`, the live `data/power.js`
and `/global-elo/` payloads, and the GitHub Actions API for run conclusions. **Production serves
exactly `8f71fc6`** — the live service worker is stamped `entenser-shell-8f71fc6239e4`, which is
this repository's HEAD, so no row below is stale for want of a deploy. Rows that could not be
verified from this environment say so in words rather than inferring from source. The re-check
found the two ⛔ rows immediately below, which the 2026-08-02 stamp did not cover.

**What that stamp does and does not cover.** It covers everything checkable without a browser:
HTTP status and response bodies, the CORS contract, the live `power.js` and `/global-elo/`
figures, sitemap and club-page counts, copy assertions against the served HTML and JS, workflow
run conclusions, and the deployed commit. Because production serves HEAD, a row whose proof is an
older Pages or API run is deployed by construction — that run ID is a historical record of when
the change shipped, not a claim needing re-running. **Two classes could NOT be verified from this
environment and are not asserted fresh:** (a) every rendered-UI measurement — the 375px/320px
layout numbers, the swipe-drift and sticky-header behaviour, the pixel widths in the Mobile UI
rows — because `pytest-playwright` will not install here and those claims need a real browser;
(b) the authenticated Club Watch render, which needs a signed-in session. Both are stated as
of their original verification date and are ranked for re-checking below (Claude queue #6).
Treat them as unverified as of 2026-08-15 rather than as re-proven.

This is the canonical answer to four questions:

1. What is live?
2. What is broken or unverified?
3. What happens next?
4. What evidence supports those claims?

Historical narrative belongs in `PROJECT_HISTORY.md`. Detailed execution belongs in the single
active plan, `superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md`.

---

## Current objective

**Changed 2026-08-15 by owner decision: the paywall is off for the initial launch.**
There is no transaction to complete while the product is free, so the milestone
below replaces the one this section carried since 2026-07-27. The old one is not
cancelled — it is deferred, and it returns intact with the paywall.

Get a supporter through the whole Club Watch job, free:

> A supporter finds a club page, sees what changed and why, creates a free
> account, watches that club, comes back after a matchweek, and finds the
> continuity waiting for them — correct, current, and worth the return visit.

That reframes the launch around evidence rather than revenue, which is what the
free launch is for: the recurring-job question (`D2`) can now be answered by
observed behaviour instead of interviews plus a paywall nobody has crossed.

**Deferred, unchanged, and gated on the paywall returning:** one complete
production transaction — select, sign in, see the amount, pay through
`api.entenser.com`, receive durable access, manage billing, cancel, and receive
a refund with the entitlement updated correctly. Every mechanism for it is
built, tested and still in the path; none of it may be removed while it waits.

No new feature, live notification claim, Club Rate test, or broad promotion
outranks the milestone above.

## Production state

| Surface | State | Proof |
|---|---|---|
| **Getting off ESPN — the name-map blocker** | 🔄 **Tool shipped 2026-08-15; the derivation must run in CI** | **ESPN was never removed, and the record should say so plainly.** `source_registry` routes exactly **3 of 78** leagues, and MLS is routed ESPN-*first* by design — so ESPN is still the primary fixtures source for ~75 leagues, which is why 49 payloads went stale when it went dark. `espn_continental` is also the evidence base behind Global ELO (`league_bridge`, `club_bridge`, `interconf_calibrate`), so removing ESPN is not one change. **The blocker was never routing — it was club-name maps.** `config/api_football_team_names.json` covers 3 leagues because MLS's was worked out by hand. An unmapped club is *not* a visibly missing club: it fails to resolve, is discarded downstream as "not in this league", and the payload still looks healthy, short a team nobody counted. `scripts/generate_spine_name_maps.py` generalises the protocol that proved MLS: **a pair is proven by fixture diff — date, opponent and scoreline — never by name similarity**, because fuzzy matching once proposed `Bristol City → Stoke City`, which would have attributed one club's season to another and looked entirely plausible. Seeded constraint propagation from production's own token matcher; a club whose fixtures corroborate two targets equally is **refused, not guessed**; the floor is *every* club, not a share, because 29 of 30 clears any percentage and silently drops a club. 11 tests, including the indistinguishable-fixtures case and the one-day kickoff slack. ⚠️ **It cannot run from a developer checkout** — `API_FOOTBALL_KEY` lives only in CI — so `.github/workflows/spine-name-maps.yml` runs it, report-only by default. **Remaining after the maps land:** wire `api_football.LEAGUE` from the 78-league map (it currently hardcodes 6), flip the registry per validated league, then move the continental evidence base. Routing a league before its map is proven is the one thing that must not happen. |
| **Paywall — OFF for the initial launch** | ✅ **Shipped 2026-08-15; preserved, not removed** | Owner decision: the whole product is free for launch, and the paywall comes back later. Implemented as a single committed constant, `LAUNCH_FREE` in `server/open_access.py` — **setting it to `False` and deploying is the entire restore operation**, and a test asserts that, so the comment cannot quietly become untrue. **Deliberately a code constant rather than the existing KV promo**: the promo lives in a key/value store and is set by an admin call against production, so a KV outage or a fresh environment would silently re-lock the site — a launch that costs nothing must not depend on a network write staying put. It also has no expiry, and `MAX_PROMO_SECONDS` (90 days) is left exactly as it was: that guard exists so a *promo* cannot become permanent by accident, and free launch is a different, deliberate state, so it got its own switch instead of weakening the one protecting the other case. **Nothing was deleted.** Plan ranks, `require_entitlement`, the Stripe webhook, the client lock chrome and the checkout gate are all still present, still tested, and still in the path; `is_open()` is the one question they already asked. **Two properties hold while it is off, both tested.** Signing in is still required for anything per-user — open access has always meant "no payment required", never "no account required", because Club Watch state (saved clubs, scenarios, journal, alert state) needs somewhere to live; the public site was already free to *view* with no account and is unchanged. And **checkout stays shut whatever Stripe is configured to do**, including against an explicit `owner_enabled` override, because selling a subscription to something being given away produces a refund and a broken promise at once — live config now reads `reason: free_launch` instead of `owner_disabled`. A canceled account is still refused: a cancellation is a decision, not a missing entitlement. Client side: `OpenAccess.state()` had demanded an expiry timestamp unconditionally, so an indefinite record read as inactive and the UI would have kept painting lock chrome the server no longer enforced; it now accepts `indefinite`, and the banner says the product is free rather than inventing a countdown nobody set. 2,173 tests pass (42 skipped). **Live and verified 2026-08-15** (Pages run `31891557318` and API run `31891557361`, merge commit `99d045a`): the live service worker is stamped `entenser-shell-99d045aad59e`, so production serves exactly this commit; `https://api.entenser.com/v1/public/config` returns `open_access {active: true, indefinite: true, note: "free during launch"}` and `checkout {enabled: false, reason: "free_launch"}`; and the live `index.html` carries the `indefinite` branch, so the client drops its lock chrome instead of painting a countdown. |
| **The data pipeline is running on one source** | ⛔ **Open — found 2026-08-15** | ESPN is dark across the board and nothing in this table said so. Measured from `data/source_health_summary.json` as written by daily run `31797104344` (2026-08-14 12:01 UTC): **`espn_fixtures` 384/384 fetches failed, `espn` 28/29 failed, `espn_continental` 83/83 failed and is dark for 6 consecutive runs, `football_data` 41/41 failed.** Only `api_football` answered — 70 of 71. The daily refresh therefore **fails at its own gate**: `build_source_health.py --check` exits 1 with "failing the run — dark feeds: espn_continental (6 runs)". That gate is working as designed and runs *after* the commit, so good payloads still land; the run is red because the sources are, not because the guard is wrong. **User-visible consequence, measured from the committed payloads: 49 of 91 carry a `generated` stamp of 2026-08-03/04/05** — `epl`, `la-liga`, `bundesliga`, `championship`, `eredivisie`, `belgian-pro` among them — against 33 stamped 2026-08-14. The European top flights have not had a real data rebuild in 12 days, with the 2026-27 season opening. This is the single largest correctness risk in front of the launch and it is Claude-executable: the fix is to route more of Tier A onto the spine that is still answering. |
| **Fast refresh is failing every time it selects a spine league** | ✅ **Fixed 2026-08-15; awaiting a green scheduled run** | The row further down calling this "✅ Live" cited a run from 2026-07-26 and was three weeks out of date. **Measured: 12 of the 15 fast-refresh runs on 2026-08-14 failed** (e.g. `31852302547`, `31848892524`, `31844826445`), every one with `RuntimeError: API_FOOTBALL_KEY not set` raised at `data_pipeline/api_football.py:152` via `fast_refresh.py:187`. **Three independent defects compound here.** (1) `refresh-fast.yml` is the only refresh workflow that never got the secret — `refresh-daily.yml`, `refresh-leagues.yml` and `fault-injection.yml` all pass `API_FOOTBALL_KEY`; the workflow was last edited 2026-08-08 and the spine path landed 2026-08-09, so it was never wired. (2) The per-league isolation added on 2026-08-07 catches `requests.RequestException` only, and a missing key raises `RuntimeError`, so one league still aborts the whole run — **the exact blast radius that fix was written to remove**. (3) `refresh_league` picks one source from `uses_spine()` and calls it with **no fallback**, although `source_registry` declares `["api_football", "espn"]` in that order; the ordered fallback is honoured in `build_league_data` and not here. The two spine-routed leagues are `northern-super-league` and `usl-super-league`, which is why the failures are intermittent rather than constant — a tick that selects neither still passes. Issue #8 has been open since 2026-08-08 and has **74 comments**, one per failed run. **All three are fixed together**, because fixing the first alone leaves the other two armed for the next cause. (1) `refresh-fast.yml` now carries `API_FOOTBALL_KEY`, `API_FOOTBALL_PLAN` and `API_FOOTBALL_OPS_BUDGET`, matching its three siblings verbatim. (2) `_routed_feed` walks `sources_for(league, "fixtures")` in order and returns the first source that answers, recording every failure in `source_health` so a fallback is never silent. **`source_registry.resolve()` is deliberately NOT reused**: it counts an empty result as a failed source, which is right for a standings frame and wrong here — a league with no fixtures in the ±2-day window legitimately returns zero rows, and demoting that to "source failed" would call ESPN on a good answer and then raise when ESPN agreed there were none, inventing an outage out of a quiet Tuesday. (3) A new `FeedUnavailable` joins `requests.RequestException` in the isolation handler. It is a distinct type on purpose — catching a bare `RuntimeError` there would have isolated the missing key **and** buried every `RuntimeError` a payload can raise, which is the opposite mistake and the one the original narrow handler was written to avoid. **Proven by reverting each defect in turn:** restoring the narrow handler fails 1 test, removing the fallback fails 3. 2,163 tests pass, 7 new. ⚠️ **Not yet observed on a scheduled run** — the next quarter-hourly tick that selects a spine league is the real proof, and issue #8 should close only after it. |
| Public site | ✅ Live | `https://entenser.com/` returns 200 (re-verified 2026-08-15) |
| MLS/home presentation follow-up | ✅ Live | MLS uses table-first movement placement, neutral team links, dual-country flags, and a horizontal desktop home hero. Pages run `30629626679` deployed commit `b468f6e`. |
| Presentation + Club Watch surface batch | ✅ Live | Shipped together in `f0fbed9` (they share `webapp/index.html` and could not be separated safely). One shared `ladderPanel()` for every league page — MLS verified live with GP/GD columns and no legacy sub-line; one `METRIC_RGB` palette so a projection category is the same colour everywhere; desktop home round 3; league header no longer wraps "Division 1" and drops the build stamp; Matches-page rails stack club names and label the swing score, and the slate lost the win percentages duplicated inside each bar (verified live: 7px meter, zero in-bar percentages). Club Watch locks render three cards on club pages (verified live: 3 `.cw-locked`, "what changed while you were away"), and the teaser sells worked examples instead of internal codenames. |
| Global power rankings recalibrated (coefficients) | ✅ Live | Ten UEFA top flights had no country coefficient, and an absent coefficient priors at `0.0` — Premier League strength on an EPL-anchored scale. `league_bridge` also built its prior from `league_offset()`, so each fit was ridged toward its own previous output. Added the ten coefficients, a `_UEFA_UNLISTED_COEFF` floor, `static_league_offset()`, and a decaying `suspended_estimate` for Russia. Held-out Brier 0.6139 → 0.6131, 10/10 seeds. **Reached production only on 2026-08-02**: the source fix shipped in `af12ed8` but nothing rebuilt `webapp/data/power.js`, so the Global Power page served the old ladder for a day. A regression test now asserts `power.js` and the league payloads agree. Added coefficients remain estimates pending a uefa.com refresh. **Superseded on 2026-08-05 by the ridge refit below** — the coefficient fix was necessary but not sufficient. |
| Global power rankings recalibrated (UEFA ridge) | ✅ Live | Owner rejected the ladder on 2026-08-05: "PSV is simply not a top ten team in europe", Netherlands and Belgium listed too high. Root cause was the ridge, not the coefficients: at λ=2e-5 every fitted UEFA offset landed within ~15 ELO of its prior, so the 743 continental matches were barely consulted and the ladder was really `_K_COEFF * (coeff − 94)`. λ → **5e-7** (`_RIDGE_BY_CONF["UEFA"]`), chosen on **mean** held-out Brier over all ten robustness seeds: **0.6096 prior → 0.6006 fitted (−0.0090), 10/10 seeds**; the adopted run's own split reports 0.6139 → 0.6018. `_MAX_DELTA_BY_CONF["UEFA"]` 150 → 450 in the same change. The adaptive ridge was measured and **rejected** for UEFA (8/10 seeds, Sweden 684 from prior). Sweep and caveats: `research-log.md`. Rebuilt end to end: 71 committed payloads and `power.js` (965 clubs / 55 leagues) are in the diff; the 78 league + 1,441 club static pages are gitignored and rebuild in CI, so they were built locally only to confirm they pick the change up — `/global-elo/` regenerated to 697–1,797 unprompted, which is the build-time-measured behaviour working. **PSV 7th → 27th, Club Brugge 10th → 54th, Union SG 12th → 61st, Feyenoord 31st → 106th; top nine are nine big-five clubs.** 1,752 tests pass (21 skipped, Playwright suites not installed locally); `check_docs.py` PASS. **Live and verified 2026-08-06**: Pages run `31116599915` and API run `31116599746` both succeeded for commit `4a72ec0`. `https://entenser.com/global-elo/` serves "697 to 1,797" and Eredivisie's strongest club at 1,589; the live `data/power.js` returns PSV 27th, Club Brugge 54th, Union SG 61st, Feyenoord 106th, and nine big-five clubs in the top nine. Rebased onto the 2026-08-06 daily refresh before shipping, so the offsets meet today's domestic ELOs, not yesterday's. |
| Cross-league calibration — the per-club layer | ✅ Live | Owner rejected the previous round: "the cross league calibration is a mess if PSG, who just played in the champions league final back to back years, is #18 and portugal has three teams in the top ten". Both halves check out against data already in the repo — quarter-final-or-better appearances 2021–24: Real Madrid 16, Man City 11, Bayern 10, Inter 10, **PSG 9** (5th most in Europe), Benfica 4, **Sporting CP 0, FC Porto 0**. **Cause: a country coefficient is the wrong instrument for a club.** It measures an association's DEPTH — Portugal is 6th because four of its clubs enter Europe and all accumulate; France is 5th *despite* PSG, because Ligue 1's other clubs exit early. Applied flat it under-rates the elite of a top-heavy league and over-rates the elite of a deep one, in opposite directions, which is why no single league-level parameter could fix both. `scripts/eval/club_bridge.py` adds a second, narrower layer: each club's own European record, shrunk toward zero by how much of it there is (`adj = MLE·τ²/(τ²+se²)`, τ=60), leaving clubs with no continental history untouched. Gated on held-out Brier over 10 seeds like the league fit — **0.5857 → 0.5774 (−0.0083), 9/10 seeds** — and it writes an EMPTY offset set when the gate fails, so a rejected fit degrades to no adjustment. Published per row as `global_elo_adj` so the total stays reproducible from the payload, with contract tests for the arithmetic and a ±150 bound. **PSG 18th → 9th; Benfica 6th → 14th, FC Porto 10th → 19th, Sporting CP 7th → 22nd; Real Madrid 9th → 2nd** (16 quarter-finals, the most in Europe). 1,907 tests pass.  **Live, first verified 2026-08-07** (Pages run `31210906157`, API run `31210906298`, commit `f1bdddd`) and **re-verified 2026-08-15**: `/global-elo/` returns 200 and reads "Global ELO", `/crossbar/` returns 200 and canonicals to it, and the live `data/power.js` still ranks every club exactly once, dense 1..n. **The ladder census is deliberately not repeated here.** Four rows of this table each carried a byte-identical copy of it, so one rebuild made four rows wrong at once — which is what happened: the 2026-08-07 copy was 958 clubs with Celtic 99th and "Liverpool (Uruguay)" 666th, and the live payload now serves 959, 113th and 668th. Nothing broke; daily rebuilds move ranks, which is the whole reason `CLAUDE.md` says a cross-surface figure has one measured source. Read the counts from `docs/figures.json`, which `scripts/check_docs.py` re-measures against the payloads on every run.|
| Continental club-name resolution repaired | ✅ Live | **40% of the continental evidence was being discarded in silence.** `_resolve_uefa_team` searched `_EXTENDED_UEFA`, which deliberately excludes the big five, so a big-5 club missing from the hand-curated `_ESPN_TO_MODELED` map could never resolve by name and its entire European record was dropped — Napoli, Sevilla, Villarreal, Marseille, Newcastle, Wolfsburg and Union Berlin were all in that hole. A second group failed on football-data abbreviations ESPN writes out in full ("Sp Lisbon" vs "Sporting CP", "Olympiakos", "FC Copenhagen", "Ajax"). Name matching now searches every modelled UEFA league with an **ambiguity guard** that drops rather than guesses on a collision — measured, 0 of 632 normalized keys are claimed by more than one UEFA league, so opening the big five is safe today and the guard keeps it safe as leagues are added — plus a small alias table. **Matches with both clubs resolved: 60% → 73%**, and everything still unresolved belongs to a league this site does not model. This was load-bearing for the round above: before the repair Sporting CP and FC Porto had **zero** resolved appearances, so no amount of fitting could have moved them; they now have 24 and 29. |
| Duplicate club entries on the ladder | ✅ Live | Nine club names appeared twice in `power.js`, and they were two problems wearing one symptom. **The country separates them, so the rule is a measurement rather than a hardcoded list.** SAME country ⇒ one club listed twice: all seven were promoted sides whose old division still publishes its COMPLETED prior season — Athletico-PR, Coritiba, Remo and Chapecoense went up from Brazil's Série B in 2025 and play Série A in 2026; likewise two Argentine clubs and Stenhousemuir. That is right for the Série B page, which shows last season's final table until the new one kicks off, and wrong for a global ladder, which must rank a club where it plays now — newest season wins, higher division breaks a tie. **965 → 958 clubs**, seven phantom entries gone. DIFFERENT countries ⇒ two real clubs sharing a name, both of which belong: Liverpool of England and Liverpool of Montevideo, Santos of Brazil and Santos Laguna of Mexico. They now render as **"Liverpool (England)" / "Liverpool (Uruguay)"** via a separate `display` field — **superseded in the working tree by "Mobile UI pass 3" above, which tags only the lower-ranked one, so the English club will render bare after the next deploy** — `team` is left alone because it is an identity key that club URLs, crest lookup and team ids are all built from, and the English club's link still resolves to `/leagues/epl/clubs/liverpool/`. Search matches the disambiguated name, so "uruguay" finds the right one. **A third collision surfaced while fixing this**: `_logoFor` falls back to a NAME-keyed logo map, so Liverpool of Montevideo — which ships no crest of its own — was being drawn with Liverpool FC's badge, 660 places below it on the same ladder. `crest()` takes a `strict` flag that refuses the fallback for an ambiguous name and shows the monogram instead. Two contract tests guard it: no club ranked twice without distinct display names, and `global_rank` dense 1..n so a dropped row can never leave a hole. 1,909 tests pass.  **Live, first verified 2026-08-07** (Pages run `31210906157`, API run `31210906298`, commit `f1bdddd`) and **re-verified 2026-08-15**: `/global-elo/` returns 200 and reads "Global ELO", `/crossbar/` returns 200 and canonicals to it, and the live `data/power.js` still ranks every club exactly once, dense 1..n. **The ladder census is deliberately not repeated here.** Four rows of this table each carried a byte-identical copy of it, so one rebuild made four rows wrong at once — which is what happened: the 2026-08-07 copy was 958 clubs with Celtic 99th and "Liverpool (Uruguay)" 666th, and the live payload now serves 959, 113th and 668th. Nothing broke; daily rebuilds move ranks, which is the whole reason `CLAUDE.md` says a cross-surface figure has one measured source. Read the counts from `docs/figures.json`, which `scripts/check_docs.py` re-measures against the payloads on every run.|
| UEFA country coefficients recaptured | ✅ Live | The table's own PROVENANCE note had asked for this since 2026-07-31; by 2026-08-07 ten of its twenty values were typed estimates and `_K_COEFF` had made them load-bearing for the whole ladder. Recaptured from the published five-year association coefficients, and **every correction landed in the direction the continental residuals had independently pointed**: Netherlands 61.0 → **51.6** (measured z = −2.8, over-rated — the largest anomaly in the set), Austria 33.0 → 25.3, Scotland 32.0 → 25.1, Poland 32.0 → **43.5** (z = +1.9, under-rated — wrong way up), and Italy moved above Spain, where the old table had it below. `_K_COEFF` refitted to **4.0** (4.04 ± 0.33) because the captured scale spans England-to-France 34.2 points against the old 27 — the table and the multiplier are one calibration in two pieces and must be refit together. **Both `_MANUAL_LEAGUE_OFFSET` entries are now gone.** The Eredivisie override added the day before was measured honestly (MLE −244 ± 30, z = −2.9) and was still a patch on the wrong layer — after the capture that league sits **1.2σ** from its own prior and needs nothing. Whole-scale validation: **mean \|z\| across 16 leagues 0.79**, where a perfectly calibrated set gives ≈0.80. |
| HOME_ADV is per competition | 🔄 Deployed, lands on the next league rebuild | Swept end to end (compute_elo re-run at each value, so the ratings refit rather than being re-scored), objective = log-loss of expected against realised score. **19 European domestic leagues, ~86,000 matches: best at HOME_ADV 55 (0.64065) against 0.64356 at 80 — and 80 was optimal in ZERO of the 19.** Mean bias +0.0358 at 80 versus +0.0031 at 55. MLS: best 90, with 80 within 0.0002, so **MLS keeps 80 and the champion config is untouched**; Brazil likewise. The split is mechanical rather than arbitrary — MLS and the Brasileirão are continental-travel leagues, which is where a large home advantage belongs; everything else measured preferred 40–70. `scripts.eval.elo.home_adv_for` is now the single source and every production build path calls it. ⚠️ **Not yet visible**: `apply_global_elo_payloads` only recomputes `global_elo` from the existing `elo`, so the new ratings arrive with CI's next league rebuild. The payloads remain self-consistent in the meantime. |
| Tier bridges translate spread, not just level | ✅ Live | A tier bridge had always been a pure shift, which assumes a second tier's rating gaps mean what its parent's mean. Measured child/parent slope ratios over 3,600–6,600 domestic matches each: championship/epl **0.782 ± 0.055**, bundesliga-2/bundesliga 0.723, ligue-2/ligue-1 0.802, league-two/league-one 0.823, serie-b/serie-a 0.872, segunda/la-liga 0.875 — and league-one/championship **1.026**, so the compression sits at the top-flight boundary rather than at every step and is stored per hop. Applied about each league's own mean so the league's overall position is unchanged and only the spread narrows; published as `elo_scale.dispersion` and `elo_scale.pivot` so the translation stays reproducible from the payload alone, with a contract test asserting it. **Burnley 1585 → 1540 (30th → 39th).** Found while wiring it: `build_power_rankings` recomputed `elo + offset` itself rather than reading the published rating, so the ladder and the league page disagreed for every second-tier club the moment the translation stopped being a shift — it now reads `standings[].global_elo`. |
| Payload regression guard | ✅ Built and tested | `write_js_payload` — the single chokepoint for every payload write — now refuses a league payload whose season goes backwards or whose field turns over by more than 60% in one build, with `ENTENSER_ALLOW_PAYLOAD_REGRESSION=1` for a deliberate re-baseline. Both real failure modes from 2026-08-07 are covered by tests: the season-2026-over-2025 case that hit `championship`, and the wholesale-swap case that left the Spanish second tier holding ten Scottish clubs. A normal promotion/relegation rollover (three of eight clubs, season +1) still passes, and a refused write leaves the good payload intact. |
| Manual offsets no longer shadowed | ✅ Built and tested | `league_offset` checked `experiments/league_offsets.json` before `_MANUAL_LEAGUE_OFFSET`, on the reasoning that a real bridge fit supersedes a hand-calibrated value. That stopped being true once `league_bridge` began writing the PRIORS to the same file whenever its gate rejects a fit — an override was then shadowed by a copy of the prior it existed to correct. Hit live on 2026-08-07: the Eredivisie override was added, payloads and `power.js` rebuilt, and PSV Eindhoven did not move an ELO point, with no warning. The override now wins and logs when the file disagrees; a genuine future fit supersedes it by deleting the entry. |
| Global ladder — the compressed league scale | ✅ Live | Owner 2026-08-07: "Club Brugge 54th → 9th, Union SG 61st → 10th, Galatasaray 57th → 12th … we need to fix this in general". **The general cause was `_K_COEFF`** — ELO points per UEFA coefficient point — whose own comment called 3.0 "the starting prior" for a calibration that was never run. At 3.0 the entire Belgian league sat 117 ELO below the Premier League, so any club dominating a weak league landed in the world top ten; every "X is not a top-ten team in Europe" report since 2026-08-05 traces to it. Fitted on the 743 continental matches: **4.72 ± 0.37, z vs 3.0 = +4.6**, held-out Brier 0.5656 → 0.5576 (−0.0079), 9/10 seeds; shipped as 4.7 since the third digit is inside the standard error. Corroborated per-league (leagues drift off their coefficient priors at 3.0 and sit on them at 4.7), per-club (big-five elite under-rated — Bayern +2.6σ, Real Madrid +2.0 — small-league clubs over-rated — Celtic −2.1, Galatasaray −1.3), and whole-scale (**mean \|z\| across 16 leagues 0.87**, where a perfectly calibrated set gives ≈0.80). **Both `_MANUAL_LEAGUE_OFFSET` entries removed** — Primeira (2026-07-13) and Eredivisie (2026-08-06) were the same bug twice, each hand-placed to compensate for the compressed scale; Primeira now sits 0.8σ from its prior unaided. Eredivisie alone still rejects at 2.9σ and is re-entered at −206, the empirical-Bayes posterior rather than the raw −244 MLE. **Ladder: Club Brugge 9th → 20th, Union SG 10th → 23rd, Galatasaray 12th → 30th, Celtic 38th → 75th, PSV 17th.** Global ELO range 762–1,767 → **748–1,756**; `docs/figures.json` re-measured, `check_docs` PASS, 1,757 tests pass. ⚠️ **Open:** Benfica 8th, Sporting CP 9th, FC Porto 10th. Primeira's continental record is 0.8σ from its prior, its internal calibration is the second-best in the set (slope 0.98) and its domestic ELO SD (132) is the largest of any league — nothing in the evidence moves it. |
| Continental cache silently deleting seasons | ✅ Live | **A transient upstream failure was permanently erasing evidence.** `espn_continental.continental_results` computed `old_kept = existing[~existing.season.isin(refetch_season_set)]` with a refetch window of every season 2018–2026, so "keep all old seasons NOT in the refetch window" kept nothing; `_fetch` swallowed HTTP errors and returned `[]`, which is indistinguishable from "that season had no matches". Caught in the act: at **2026-08-07 06:32** a refresh hit ESPN 403s and all three UEFA competitions lost season 2025 — the evidence base behind the global ladder fell from **743 matches to 528** with no error, no signal, and the next bridge refit would have re-fitted every league offset on the smaller set. `_fetch` now returns `None` on transport failure and only seasons ESPN actually answered for are replaced; a failed refresh logs which seasons were retained. Verified by re-running against a fully-403ing ESPN: every season failed and the cache was **retained** where before it would have been wiped. The lost 2025 rows cannot be refetched from this environment (ESPN blocks it); CI will restore them on its next successful fetch. |
| Payloads regressing to the prior season | ✅ Guard built (row above); **cause corrected 2026-08-08** | The same failure class one layer up, and worse. A local refresh at **2026-08-07 06:02–06:32** rebuilt the league payloads while every 2026 upstream source returned 404/403, and **38 payloads silently regressed to last season's rosters** — `championship` came back with last year's field. `power.js` was then rebuilt at 06:32 from that corrupted set. Every file was reverted to HEAD and the ladder rebuilt from clean payloads. `build_league_data` exits 0 and writes in this situation; nothing downstream can tell. **Correction:** `segunda.js` holding **ten Scottish clubs** (Hamilton, East Kilbride, Ross County…) was recorded here as part of the same 404-driven regression. It was not. Root-caused 2026-08-08 to a football-data.co.uk **301 redirecting `2627/SP2.csv` onto `SC2.csv`** — a successful fetch of the wrong division, not a stale-roster fallback, and the one case in this row that a 404 could never explain. Fixed at source; see the xG-join section below. The write guard in the row above still covers the symptom either way, and a local league rebuild remains untrustworthy — see the session memory `local-league-rebuild-regresses-payloads`. |
| Domestic ELO — measured defects, not yet acted on | ⚠️ Open — evidence gathered 2026-08-07 | Two findings from auditing the ELO construction over ~70,000 domestic matches across 19 leagues. **(1) `HOME_ADV=80` is too high for European domestic football.** The model over-states the home side's expected score in every league and in every season measured, 2014–2026, with an implied home advantage averaging ≈53 ELO and never once reaching 80 (2020–21 fell to 37–41 with empty stadiums; 2023–26 sits at 47–60). The champion config was tuned on MLS, where travel makes home advantage genuinely larger. **(2) Lower divisions are 30–40% over-dispersed** — the logistic refit of result on rating gap wants a slope of 0.62 in the 2. Bundesliga, 0.68 Ligue 2, 0.70 Championship, 0.71 League One, against 0.91 for top flights. The ±120 tier bridges therefore translate an inflated scale as though it were the Premier League's, which is the mechanism behind relegated clubs ranking too high. Neither is fixed here: both change the champion ELO config, which is a `CLAUDE.md` key decision and wants its own A/B against the eval harness. |
| Mobile UI pass 2 | ✅ Live | Owner feedback 2026-08-06, eleven items; eight were presentation and are verified in-browser at 375×812, 320×700, 812×375 and 1280×900. **The portrait league table was three bugs with three distinct causes, all introduced by the 2026-08-05 freeze work.** (a) The 159px "gap" under the panel heading was `.sim-gate-overlay` — a hover-only upsell held at `visibility:hidden` — switched from `absolute` to `sticky` at ≤620px, so an element that can never be seen on a touch device still reserved flow height; measured 159px → **0px**. (b) "Numbers don't line up with the headers": `.thead` and each `.trow` are SEPARATE grid containers, and `min-width:max-content` made each resolve the shared track list against its own content — the club track was 171px in the header and 320px in the rows. ladderPanel now emits `--tgrid-m`, an all-definite twin used wherever the table can overflow; header and row cell offsets are now **identical at every width tested**. (c) "Only see down to 14th" and "top row doesn't freeze" were one cause: the base rule is `.ladder{overflow:hidden}`, so `overflow-y` was `hidden`, not the `auto` the 2026-08-05 note assumed — `max-height` clipped 442 of 1120px unreachably and a sticky header inside a non-scrolling scrollport never sticks. Also found in passing: at landscape-phone widths (812px) the table overflowed by 24px with `overflow-x:hidden`, so the last column was clipped with no gesture to reach it; the overflow band now starts at 1024px. **Home swipe** now tracks the finger (transform + fade, axis latched once at 6px so a 45° drag stays a scroll) and every rotation — including the 6s auto-advance — anchors the panel's viewport position: measured drift across three swipes **0.0px**, where before the page jumped. The rAF that finished the animation was replaced with a timer, because rAF is paused in a hidden tab and would have left the panel parked off-screen at `opacity:0`. **Boot interstitial**: `<h1>` was hardcoded "MLS Projections" and the data chain is parser-blocking, so every navigation flashed a blank page under a confident wrong headline; now a neutral "Entenser" upgraded from the URL before any data loads, plus a skeleton that is removed in the same synchronous pass that fills `<main>`. **Global Power** lost the relative-strength bar (it redrew the number beside it and, at 320px, pushed the rating column off-screen and truncated the header to "CR"); nothing overflows the panel at 320px now.  **Live, first verified 2026-08-07** (Pages run `31210906157`, API run `31210906298`, commit `f1bdddd`) and **re-verified 2026-08-15**: `/global-elo/` returns 200 and reads "Global ELO", `/crossbar/` returns 200 and canonicals to it, and the live `data/power.js` still ranks every club exactly once, dense 1..n. **The ladder census is deliberately not repeated here.** Four rows of this table each carried a byte-identical copy of it, so one rebuild made four rows wrong at once — which is what happened: the 2026-08-07 copy was 958 clubs with Celtic 99th and "Liverpool (Uruguay)" 666th, and the live payload now serves 959, 113th and 668th. Nothing broke; daily rebuilds move ranks, which is the whole reason `CLAUDE.md` says a cross-surface figure has one measured source. Read the counts from `docs/figures.json`, which `scripts/check_docs.py` re-measures against the payloads on every run.|
| Mobile UI pass 3 + champion odds | ✅ Live (deployed `7165ce0`; champion odds land league by league) | Owner feedback 2026-08-07, eight items. Item 2 (UEFA competition forecasting) is scoped separately and NOT in this batch. **Item 6 was a regression of a fix the owner had already been given**: `webapp/index.html:5192` carries their 2026-08-05 words — "team names are cut off. the bar in the middle isnt really helpful" — and that fix shipped only to the Matches board (`.mxcard`). The league tab's `.grow` kept the old six-track `time \| home \| proj \| bar \| proj \| away` row, which spent 262px of 343px on fixed tracks, gaps and padding; each team track resolved to ~40px and, minus a 20px crest and an 8px gap, the NAME got **12px** while "New England Revolution" wanted 141px — measured 30 clipped names on one screen, and the win % had been hidden outright to buy the room. Now stacked on named grid areas exactly as `.mxcard` is: **names 12px → 163px, 30 clipped → 0, rows 62px, 13 matches per screen**, win % restored, draw price moved to the left rail so losing the bar costs nothing. **Item 4** — the club column is FROZEN at ≤760px, so its width comes off the screen before any data column is visible: 176px of 341px, table 823px wide. `.tlad .tname` 14px → 12px **paired with `clubColWidth(names, narrow)`**, because the canvas measurement is what the grid track is built from and a CSS-only change reclaims nothing. Caught in verification: `--tgrid-m` spans the whole 1024px band while the 12px font stops at 760px, so building it from the phone metric clipped "Manchester United" between them — added `--tgrid-p`, same track COUNT, so the cells-vs-tracks hazard the 1024px comment warns about cannot apply. Club column 176 → **157px**, visible data 139 → **158px (+14%)**, 0 clipped names and header/row templates identical at 375 / 966 / 1280. **Item 1** — the home hero was 157px on a 375px screen: a 51px two-line headline and a 52px three-line paragraph above the 35px of buttons that are the only actionable thing on it. One-line headline at 17px on phones, sub hidden, both CTAs kept: **157px → 67px**. **Items 3 + 8** — `ELO+` → **`League ELO+`** on both the ladder and the Global Power head, with a visible legend under each ("100 is that league's average, 125 is a 100-point edge") because a `title=` tooltip is invisible on the touch device where the table is hardest to read. The phone keeps the short `ELO+` and the legend carries the full name, so the rename does not eat the width item 4 just reclaimed; the desktop track went 68 → 78px because the renamed header measures 66px and 2px of clearance would not survive a webfont swap. **Item 5** — only the LOWER-ranked club of a shared name is tagged ("everyone knows the big liverpool"): **Liverpool 6th renders bare with its own crest, "Liverpool (Uruguay)" 666th tagged with a monogram**; Santos 174th bare, "Santos (Mexico)" 942nd tagged. `display` had been doing double duty as the ambiguity flag that stops `_logoFor` handing a namesake the famous club's badge, so a new `country` field now carries that signal on ALL members of a group — search still resolves "liverpool england" and "liverpool uruguay" separately. `power.js` diff vs `f1bdddd`: 958 clubs, **0 rank changes, 0 strength changes**. **Item 7 — the defect was every second tier, not just England's.** `_PROMO` and `_PROMO_DIRECT` emitted no `title` bucket at all, and `eerste-divisie` hand-writes its buckets so it needed the same fix separately. **48 of 70 leagues → 62 of 70**; 14 gained champion odds, the Championship now reads Champ / Auto / Playoff / Promoted / Releg. Where promotion is a single place it IS first place, so `promo` is suppressed rather than printing one number under two headings. The 8 still exempt are `_PLAYOFFS` formats whose champion comes out of a post-season bracket this sim deliberately does not play — a standing decision, now guarded by a test that names them. **1,911 tests pass** (35 skipped; the two Playwright suites are not installed locally). ⚠️ **Item 7 is a code change only** — `build_league_data` cannot be run locally without regressing payloads to the prior season, so the Champ column reaches the site with CI's next league rebuild. Every other item is presentation and lands with the deploy. |
| Weekly rebuild left the ladder stale and a club in the wrong crest | ✅ Both fixed; payloads regenerated | Two defects the 2026-08-08 rebuild (run `31234585894`) exposed, each caught by an existing guard. **(a) `refresh-leagues.yml` never regenerated `power.js`.** It rebuilds league payloads, from which the ladder is derived, so 206 clubs disagreed between the two and the live Global Power page served ratings the payloads no longer held. `refresh-daily.yml` has always had the step; this job never did — the same gap that put a stale ladder into production on 2026-08-02. Step added, and `power.js` regenerated: **958 → 959 clubs**. **(b) A cross-country crest collision.** Scotland's **Queens Park** — logo-less in its payload — reached `queens park rangers` through the resolver's global substring pass and wore QPR's badge. The pass is scoped by country and confederation, but England and Scotland are both UEFA, and the last-resort global step had no country guard at all. Steps 5 and 6 now run **only for names with no known country**: if a club's country is known, it has already been searched exactly and by substring, so a cross-border prefix hit is a different club that merely starts the same way. Queens Park now renders an honest monogram. The fix also resolved **San Antonio Bulo Bulo (Bolivia) vs San Antonio FC (USA)**, which `KNOWN_NAME_CLASHES` had listed as structurally unfixable — it was a prefix match, not an identical name, so it was a resolver bug and the list is now one shorter. **Also fixed: the Leagues Cup was requesting five seasons that never existed** (2018–2022 for a competition founded 2023), against an API that rate-limits by IP — a per-competition first-season floor now clamps the window, caller-supplied ranges included. 1,928 tests pass. |
| ESPN rate limiting had been failing the refreshes for three days | ✅ Fixed in `data_pipeline/http.py`, awaiting a green scheduled run | Found 2026-08-07 while diagnosing why the Leagues Cup cache held only 2024. **The daily refresh failed on 2026-08-05, 08-06 and 08-07, and the fast refresh failed seven consecutive runs** (16:03→21:56 UTC) before recovering unaided at 22:47 UTC — all with `403 Forbidden` raised at `http.py:24`. The Aug 7 daily failure was on **`usa.1`, MLS itself**. **The 403 is a rate limit, not an authorisation verdict**, and ESPN applies it per IP across every endpoint: measured directly, `concacaf.leagues.cup/scoreboard` returned 200 and within a minute that same URL and `uefa.champions` — which had also just returned 200 — were both 403. The unaided 22:47 recovery is the same evidence from the other side. `espn_get` had **no retry at all**; its docstring deferred that to callers and no caller did it, so `_fetch` turned a transient limit into "season not refreshed" and the build carried on reporting success. Now: a process-wide 0.35s floor between requests (the build loops ~70 leagues plus continental comps back to back, which is the burst shape that trips it), and 4 attempts with exponential backoff, jitter and `Retry-After` support on 403/408/429/5xx. **400 and 404 are deliberately not retried** — ESPN returns 400 for a date window it dislikes and 404 for a missing slug, both deterministic. Five new tests cover retry, non-retry, exhaustion, `Retry-After` and connection resets. A session fixture disables the ladder under pytest: a few tests reach ESPN for real and against a limited host the suite went 75s → 9m41s, one test alone at 553s; it is back to 71.8s. 1,916 tests pass. ⚠️ **Still unproven against a real 403.** The fix landed at 23:23 UTC, 36 minutes *after* the 22:47 UTC recovery, so no scheduled run has yet exercised the retry ladder in anger: fast-refresh runs `31227735426`, `31230365497` and `31235644800` are green but every one of them found ESPN already answering. Verification is the next scheduled run that meets a live rate limit, not the next green one. |
| One dead league feed could abort the whole fast refresh | ✅ Fixed in `scripts/fast_refresh.py` and `refresh-fast.yml`, proven by test | The other half of the row above, and the reason its blast radius was site-wide. The retry ladder makes a 403 survivable; it does not make an *exhausted* 403 survivable, and `main()` refreshed leagues in a bare list comprehension, so the first league to run out of attempts took every remaining league with it. Runs `31221990714` and `31218282187` both died on **`bol.1`** — Bolivia — and every other league's projections went stale behind a competition almost nobody on the site follows. `refresh_selected()` now isolates each league: a `requests.RequestException` is logged to stderr and recorded in a `{"refreshed": [...], "failed": [...]}` report instead of propagating. **Deliberately narrow** — a `ValueError` from `_advance_standings` or the pmatrix `AssertionError` is a payload bug, not a dead upstream, and still stops the run; a test asserts that isolation does not swallow it. Blanket tolerance would have been the opposite mistake, because ESPN rate-limits *per IP across every endpoint*, so a real block fails most leagues at once: above `_FAILURE_TOLERANCE` (half the selected leagues) the run still exits non-zero. Measured across the boundary — 1 of 60 failing publishes, 1 of 1 and 31 of 60 fail the run, nothing selected exits 0. **`refresh-fast.yml` had no failure alert at all**, unlike `refresh-daily.yml` and `refresh-leagues.yml`; that absence is why seven consecutive red runs went unnoticed for six hours, so it now carries the same idempotent `refresh-failure` issue step and `issues: write`. ⚠️ Not yet observed on a scheduled run — the isolation path only executes when a league's feed is genuinely down. |
| Data refresh workflows discarded their work on a push race | ✅ Fixed in all three refresh workflows, reproduced and proven locally | **Two rebuilds were lost before this was right.** Run `31224260724` rebuilt all 70 leagues and failed on `failed to push some refs` (1h45m lost) because a docs commit landed on `main` mid-run. A rebase-and-retry was added — and run `31226978927` then lost **2h50m to the same step**, because the retry itself could not run: `error: cannot pull with rebase: You have unstaged changes`. **The cause is the repo's own staging rule.** These steps stage explicit paths rather than `git add -A` (correctly — see `CLAUDE.md`), so the build's other tracked changes are still unstaged when the retry fires, and plain `git pull --rebase` refuses on a dirty tree. The handler then mislabelled that as a conflict. **`--autostash` is the fix**, and it is required rather than tidiness. Verified by reproducing the exact failure in a scratch repo — staged data path, second tracked file left dirty, a rival commit on the remote — where plain `--rebase` reproduces the error and the `--autostash` loop pushes on attempt 2 with the rival's commit intact and the unstaged change preserved. Applied to `refresh-leagues.yml`, `refresh-daily.yml` and `refresh-transfermarkt.yml`, which all shared the pattern; `refresh-fast.yml` is already race-proof by construction (it builds a commit with `git commit-tree` and force-pushes to a separate `live-data` branch). Operational note: avoid pushing to `main` while a data rebuild is running — the retry is a safety net, not a licence. |
| Leagues Cup — rules, venue and draw corrected | ✅ Fixed in the model, lands on the next continental build | Owner 2026-08-07: "its rules have changed over time and need to be accounted for in your modeling. In addition, factor in home field vs. neutral site games played at true home or true neutral venues." All three defects below are now fixed in `scripts/eval/bracket_sim.py`. **(a) The points rule.** The shootout branch ran unconditionally — a level match gave the shootout winner 3 and the loser 0 — while the published `rules` string said "1 for a draw, no group-stage shootout". `no_draws` existed in `FORMATS` but was **never read**, so the model could not express a competition that allows draws. It is now read, and the current edition is set to `False`. **(b) Venue.** `neutral` was `False` on all 77 cached rows and the group phase hardcoded it, so every nominal host got full home advantage. Measured on 2024: a home side won **44.2%** of all matches but a Liga MX side nominally at home won **28.0% (n=25)**, barely above the 24.7% away sides managed — every edition has been played in the US and Canada, so those clubs held the label without the venue. A `host_league` key now marks the hosting league and every other club is simulated as neutral, **in the knockout as well as the group phase**. **(c) The draw was alphabetical.** Opponents came from `B[(k + gi) % len(B)]` over field-ordered lists, so a club's three opponents were a deterministic function of its name and identical in all N simulations. The pairing is now resampled per simulation, preserving the "three distinct cross-league opponents" property. **Measured effect on the live field** (N=20,000, same seed): the group-phase fixes alone move a club's advance odds by at most 1.1pp, because each table advances exactly 4 of 18 regardless — but once the venue policy reaches the knockout, **MLS champion probability goes 45.6% → 50.9% and Liga MX 54.4% → 49.1%, a 5.2pp swing**. That is the size of the advantage the model had been giving Liga MX clubs for free. **Per-edition formats**: `SEASON_FORMATS` + `format_for(comp_id, season)` now govern which rules a season runs under, and `simulate()` takes a `season`. 2023–2025 are recorded as **unsupported and raise** rather than being replayed under 2026's two-table spec — they used a 47-club field with three-club groups and shootouts (2024 measured: 29 MLS-v-MLS ties, 24 of 77 level in regulation with all 24 recording a winner). 1,922 tests pass, six of them new. ⚠️ Reaches the site on the next continental build. **Correction (2026-08-07): the Atlante "resolution failure" reported here earlier was not one.** Atlante won promotion to Liga MX for this season (owner-confirmed), and the `liga-mx` payload carries them among its 18 clubs with 4 points from 3 games. Club resolution was right; the finding was mine and it was wrong. **2025 also now runs under the current spec** — owner-confirmed as sharing 2026's rules — which makes it the earliest season this engine can replay. |
| ~~Leagues Cup 2026 forecast — live but modelling the wrong competition~~ | Superseded by the row above | Original finding, kept for its evidence: | Found 2026-08-07 while scoping the owner's Leagues Cup request; design in `superpowers/specs/2026-08-07-leagues-cup-forecasting-design.md`. The forecast itself IS live (36 clubs, 54 fixtures dated 2026-08-04 → 08-14, Inter Miami 6.8% / Pumas 6.1% / América 4.8%). (1) **No results are being ingested.** 0 of 54 fixtures carry a result though the competition began 2026-08-04; the cache `data/espn_continental/leagues-cup.parquet` holds 77 rows, **all from 2024** — no 2023, 2025 or 2026. The payload's `status` reads `knockout_live`, which for a tournament with zero results is misleading. (2) **The sim runs the old points rule.** `bracket_sim.py:322` awards the shootout winner 3 points and the loser 0 on any level match, while the published `rules` string says "3 points for a win, 1 for a draw, no group-stage shootout" — 2023-24 rules under a 2026 description. `"no_draws": True` in `FORMATS` is **never read**; the shootout branch is unconditional, so the model currently cannot express a competition that allows draws. 2024 data confirms which rule was which: 24 of 77 matches level in regulation, all 24 with a winner recorded, 15 of 15 in the group stage. (3) **The draw is alphabetical.** `bracket_sim.py:317` pairs `A[k]` with `B[(k+gi) % len(B)]` over field-ordered lists, so a club's three opponents are a deterministic function of its name — identical in every simulation, no schedule uncertainty in any published number. **Venue bias, measured:** `neutral` is `False` on all 77 cached rows and the group phase hardcodes it, so every nominal host gets full home advantage. In 2024 a home side won 44.2% overall but a **Liga MX club listed as home won 28.0% (n=25)**, barely above the 24.7% away rate — every match was played in the US or Canada, so those clubs had the home label without the venue. n is small and strength is confounded, so the design proposes fitting the effect rather than adopting 28% as a constant. Also noticed: **Atlante appears in the Liga MX table** and is a Liga de Expansión club — the resolution failure `continental_resolve.py` exists to prevent. A full rebuild (run `31224260724`) may repair ingestion on its own; verify before building anything else. |
| ELO+ — club against its own league | ✅ Live | **Renamed to `League ELO+` in the working tree — see "Mobile UI pass 3" above; this row describes what production serves today.** New column on both the league table and the Global Power ladder: `100 + (elo − league mean)/4`, so the league average is 100 and a 100-point edge reads +25 (owner chose the scale 2026-08-06 from three candidates). Deliberately a difference, not a ratio — ELO's zero point is arbitrary, and `100 × elo/mean` compresses a whole top flight into 91–112. The construction is bridge-invariant: `global_elo` is domestic ELO plus one constant per league, so the constant cancels and ELO+ is identical whichever is fed in. Computed client-side from numbers already in the payloads, so it adds no build step and cannot drift from the ratings beside it. Premier League reads Arsenal 148, Man City 142, Brentford 101 (league average), Ipswich 64. On a phone ELO+ replaces the raw rating, which is the widest number in the table. |
| UEFA match constants calibrated | ✅ Live | **`_CONF_CONST["UEFA"]` was the last confederation still carrying typed "physically-grounded" priors** while Concacaf, CONMEBOL and AFC had all been grid-swept. It was wrong in a way that bent the published ladder: at `goal_scale` 3000 a 300-ELO gap is only a 1.26× goal rate, so the model predicted **39.5% home wins against an actual 50.3%** over 743 continental matches — a ~6σ miss, not noise — and the league offsets were absorbing the difference. Recalibrated to **1.25 / 1000 / 110** (was 1.35 / 3000 / 80), chosen on mean held-out 1X2 Brier over the same 10 seeds the bridge gate uses, offsets refit at every grid point: **0.6006 → 0.5708 (−0.0298), 10/10 seeds**; predicted split 0.478/0.209/0.313 against actual 0.503/0.182/0.315, total calibration error **0.216 → 0.085**. Constrained, not merely optimised — `bracket_sim` samples goals from these lambdas, so the grid was restricted to points where an even non-neutral tie yields 1.35–1.70 home and 2.60–2.95 total; the unconstrained optimum runs to `goal_scale` ~900 for a further 0.002, inside the noise. A new parametrised test asserts the scoreline bound for all four confederations, replacing the `goal_scale ≥ 2000` floor that bound on the fit without bounding what mattered. |
| Global power rankings — Ligue 1 and the Eredivisie | ✅ Live | Owner 2026-08-06: "the global rankings have Ligue 1 teams way too high". Root cause was the mis-calibrated constants above, not the offsets: a model that cannot express dominance must put the missing strength somewhere, and the only free parameters are the league offsets, so leagues whose European entrants win a lot got inflated — Ligue 1 sat at **−18 against a −81 prior**, which put Lens 10th in the world. **With the constants fixed the fitted offsets no longer beat the coefficient priors on held-out data at all** (fitted 0.5748 vs prior 0.5661) and the existing robustness gate adopts the priors on its own — the 2026-08-05 fit had largely been compensating for the calibration error. Each prior was then tested against its own continental record by profile likelihood, all others held fixed: sixteen of seventeen are within noise, including **Ligue 1 at z = +1.7 (prior fine, untouched)**. One is rejected — the **Eredivisie at z = −3.3** (101 appearances, observed 1.12 points per appearance against 1.51 expected, MLE **−197 ± 30** vs a −99 prior), which is why PSV ranked 6th off a 1804 domestic ELO; it is now an explicit `_MANUAL_LEAGUE_OFFSET` entry, the same mechanism Primeira has used since 2026-07-13. **Result: Lens 10th → 33rd, Lille 12th → 39th, Marseille 26th → 57th, PSV 24th.** Global ELO range 697–1,797 → **762–1,767** (`docs/figures.json` re-measured, `check_docs` PASS). ⚠️ **Known trade, not yet resolved:** the same change moves Club Brugge 54th → 9th, Union SG 61st → 10th and Galatasaray 57th → 12th. Their own continental records match their priors (Belgium z = −0.7), so there is no evidence to move them; the previous suppression came from a mis-calibrated model plus a loose ridge, i.e. the right-looking answer by the wrong mechanism. The remaining defect is **within-league ELO inflation** in top-heavy leagues — Club Brugge's domestic 1773 exceeds Arsenal's 1756 — which is a spread problem a per-league shift cannot fix. Both a per-league slope and a single shared spread factor were fitted and **rejected**: the shared factor came out 0.900 ± 0.126 (z = −0.8) and did not improve held-out Brier. Fixing it needs evidence this repo does not have — a fresh capture of the UEFA country coefficients — not more fitting. |
| Cross-division ELO for relegated clubs | 🔄 Deployed, lands on the next league rebuild | Owner 2026-08-06: "Burnley has a high elo (#30) despite just being relegated". The reverse tier bridge rewrote a relegated club's Dixon-Coles attack/defence but **never its ELO**, and `elo_now` comes from `compute_elo` over the destination division's own history — so a club returning to the Championship resumed the rating it left with, as though its top-flight season had not happened. Burnley carried **1705**, earned winning the Championship two seasons ago and untouched since; its actual Premier League record puts it at **1359**. Because `championship_to_epl` (−120) is the exact inverse of `epl_to_championship` (+120), that round-tripped to a published 1585 and 30th in the world, while the DC half of the same seeding said "a relegated side" — the two halves plainly disagreed. `build_league_data` now assigns the bridged rating to `elo_now` as well, in both directions. **Not yet visible**: realising it needs a league rebuild, and every 2026 upstream source 404/403s from a local checkout — a local `--league championship` run silently regressed the payload to season 2025 and was reverted. CI's daily refresh will apply it. |
| Mobile UI pass | ✅ Live | Owner feedback 2026-08-05, all items addressed and checked at 375×812 in-browser: home order is now matches → title probabilities → league tables → the rest; the rotating league carousel is swipeable (horizontal-dominance guard, dot tap resumes); "Club Watch" is one line in the bottom bar (55px, was 72px and wrapping); the country ribbon is frozen (`#mast` → `display:contents`, since a sticky element is clipped to its containing block); mobile search collapsed to a magnifying glass beside the wordmark; the Matches slate rebuilt as stacked full-width club rows (62px, was 62px with truncated names in a 116px column); league tables freeze the header row and the club column and no longer show a dead band beside the panel heading; the UEFA-spots table shows a country on every row. Two latent bugs fixed in passing: `body{overflow-x:hidden}` was silently defeating every `position:sticky` on mobile, and the outcome-column header labels overprinted each other (`minmax(40px,.5fr)` → `minmax(max-content,.5fr)`). **Live and verified against `https://entenser.com` at 375×812 on 2026-08-06** (Pages run `31116599915`, commit `4a72ec0`): home order and the one-line 55px tab bar confirmed on the live DOM, the ribbon holds `top:0` at scroll 1400, the live Matches slate renders 118 fixtures at a uniform 62px with **zero truncated club names**, the Eredivisie table keeps "PSV Eindhoven" visible at `scrollLeft:380` with the heading pinned full-width, and the live UEFA-spots table reads Norway / Denmark / Austria. |
| Race "Changes since" diff mode | ✅ Live | The race panel renders as a diff against a reader-chosen baseline date (`?league=mls&mode=changes&since=2026-03-01`), modelled on the FanGraphs playoff-odds Changes mode. Works logged out, no personalization, URL-addressable. Every diff carries the provenance of **both** endpoints; a window straddling the reconstruction boundary says so in words and flags each affected row `replay`. Baselines never interpolate. Empty windows read "Nothing moved." Seven contract tests. |
| Matches-to-watch rail ordering | ✅ Live | The "one per league" rail promised "biggest leagues first" and sorted on `tier` alone — 267 fixtures are tier 1, so Uruguay and the Premier League tied and it fell through to raw leverage, leading with Uruguay 78, Bolivia 61, Honduras 40. `build_match_leverage.py` now publishes `league_strength` (the Global ELO offset) and the rail sorts tier → strength → pct → leverage. Now leads with Eredivisie, Brasileirão, Belgian Pro League, Eliteserien, Superliga. The exotic rail was already correct and keeps the volatile small leagues under "biggest swings anywhere — often leagues you have never watched". **Forecast-first copy leak fixed 2026-08-05:** the plain-language rewrite in `f0fbed9` replaced `±7.2pp` with "odds swing up to 7.2 points" and hardcoded an explainer ending "title, European and relegation odds", putting betting vocabulary on a free public surface that the rest of the product calls likelihoods. Both now read "likelihood"; `TestForecastFirstPublicLayer` guards `?league=command` again. **Live and verified 2026-08-07** (Pages run `31137310382`, commit `1451e9f`): the live `https://entenser.com/index.html` serves "likelihood swings up to" and "relegation likelihoods", and zero occurrences of either betting phrasing. |
| Point-in-time season history | ✅ Live | The 71 domestic race pages now merge provenance-labeled historical replays with authoritative archived forecasts. Thirty-five leagues received 5,725 reconstructed team-points; the other 36 were already archived before their current season began. Replays exclude later scores and undated roster/injury/value inputs; dashed chart segments are reconstructed and solid segments are archived. Pages run `30637496201` deployed commit `871eaa4`. |
| Global ELO — the named strength scale | ✅ Live | Renamed from **Crossbar** on 2026-08-06 (owner: the coined name did not tell a reader what the number was). The page moved to `/global-elo/`; `/crossbar/` is retained as a canonical redirect because it shipped in every club-page footer and in the sitemap for five days. The cross-league scale is publicly named **Global ELO**, which is also the payload field name — one name instead of two. Free self-canonical page with `DefinedTerm` JSON-LD, linked from every club page that shows the number — the live Arsenal page reads `Global ELO 1756` and links through. Figures are read from the payloads at build time, not written down — and this row used to write them down anyway, which is how it came to state a range the site had already moved off. The club count, competition count and rating range now live only in `docs/figures.json`, where `scripts/check_docs.py` re-measures them against the payloads; the live `/global-elo/` page renders the same three numbers from the same source, and on 2026-08-15 page and manifest agree. States what the scale is *not* (form table, bookmaker-derived, betting rating, trophy count), that the league offset cannot change a forecast, and the evidence tier behind each league's placement (41 fitted, 13 confederation-anchored, 9 estimated priors, 7 tier bridges, 1 frozen). Seven contract tests, one asserting no accuracy or betting claim.  **Live, first verified 2026-08-07** (Pages run `31210906157`, API run `31210906298`, commit `f1bdddd`) and **re-verified 2026-08-15**: `/global-elo/` returns 200 and reads "Global ELO", `/crossbar/` returns 200 and canonicals to it, and the live `data/power.js` still ranks every club exactly once, dense 1..n. **The ladder census is deliberately not repeated here.** Four rows of this table each carried a byte-identical copy of it, so one rebuild made four rows wrong at once — which is what happened: the 2026-08-07 copy was 958 clubs with Celtic 99th and "Liverpool (Uruguay)" 666th, and the live payload now serves 959, 113th and 668th. Nothing broke; daily rebuilds move ranks, which is the whole reason `CLAUDE.md` says a cross-surface figure has one measured source. Read the counts from `docs/figures.json`, which `scripts/check_docs.py` re-measures against the payloads on every run.|
| Forecast landing page and RSS | ✅ Live | `/football-forecasts/` and `/forecast-feed.xml` return 200 |
| Crawlable club forecast pages | ✅ Live | Static build emits 1,446 competition-scoped club pages and a 1,543-URL sitemap; Pages run `30627028178` deployed them successfully |
| Global Power and Global ELO | ✅ Live | 1,167 clubs across 71 competitions carry a Global ELO rating (range re-measured 2026-08-08 against the committed payloads: 749–1,742). The bridged Global Power ladder at `?league=power` is a strictly smaller population — **959 clubs** across 55 leagues, because it additionally requires measured bridge evidence and, since 2026-08-07, ranks each club exactly once. Two correct numbers for two different questions; both are registered in `docs/figures.json`. Publicly named **Global ELO**, matching the payload field. Both league tables and the ladder also publish **ELO+** (the club against its own league, average = 100), computed client-side from the same numbers. Displayed on club pages, league tables, projection context, team pages, selectors, run-in difficulty and history charts, and ranked at `?league=power`. |
| Fast result/projection refresh | 🔄 **Fixed in code 2026-08-15; proof is the next scheduled run** | **This row read "✅ Live" on the strength of run `30205921705` from 2026-07-26 and was false when re-checked.** See the ⛔ row at the top of this table for the measured failure rate, the three compounding causes, and the fix. Kept here rather than deleted because a row that was wrong for nineteen days is itself the finding: the proof was a run ID that had stopped being re-run, which is how a green stamp outlives the thing it certified. Any row whose proof is a single dated run needs re-running, not re-reading. |
| Intelligence API on Vercel host | ✅ Reachable | `https://mls-five.vercel.app/v1/public/config` returns 200 |
| `api.entenser.com` | ✅ Live | `GET https://api.entenser.com/v1/public/config` returns 200; a CORS preflight for it from `https://entenser.com` returns 204 with `access-control-allow-origin: https://entenser.com` (re-verified 2026-08-06). **The bare origin returns 404 and that is correct** — the API only serves versioned `/v1/...` routes, and there is no `/`, `/health`, or `/docs`. This row used to read "HTTPS GET returns 200" without naming a path, so re-verifying it by hitting the origin looked like an outage. |
| Production application configuration | ✅ Core runtime configured | Upstash, token, admin, unsubscribe, API URL, and production-mode variables are Production-only |
| Legal business entity | 🟡 Formation chosen | Owner chose an Ohio single-member LLC; legal name remains open |
| Public pricing configuration | ⏸️ Empty, and now correctly so | Production `/v1/public/config` still returns `"pricing": {}` (verified 2026-08-15). While the product is free this is the right answer rather than a gap — no surface can quote a price, because there is none to quote. It becomes a blocker again when the paywall returns. |
| Paid transaction path | ⏸️ **Deliberately shut — free launch** | Was "blocked by Stripe configuration and legal publication", which is still true and no longer the reason it matters. The paywall is off by owner decision (row above), so there is no transaction to operate; the path stays built and tested against the day it returns. Stripe, pricing and legal remain genuinely unfinished and are still owner-blocked — they are simply not on the critical path to launching any more. |
| Club Watch repository packaging | ✅ Deployed and smoke-verified | Club-first intent, one durable free sample, outcome-triggered conversion moments, coherent free/paid boundary, authenticated Account, and customer-facing naming shipped in commit `1d954fa` |
| Club Watch season forecast history | ✅ Live and published | Club Watch merges current-season point-in-time replays with the exact nightly archive, labels dashed reconstructed versus solid archived checkpoints, lets members inspect available historical targets, and includes a frozen history chart in the complete free sample. Exact archives win same-day conflicts; public league history remains free. Commit `4beee51` deployed in Pages run `30646510561` and API run `30646510217`; the latter rebuilt 66 competitions/1,108 club records with zero failures and published all 1,108 through the scoped authenticated relay. The live feature copy is present, the public API is healthy, the relay returns `401` without its publisher credential, and the final suite passed 1,729 tests with 14 intentional skips. **Chart-truncation defect found and fixed 2026-08-05:** the panel honoured the club's pinned season target whenever the archive held *any* checkpoint for it, but metric coverage is not uniform — `spoon`, `conf_win` and `hfa` only began being archived on 2026-08-01 — so a club pinned to a thinly-covered target drew only those few checkpoints and lost the reconstructed replay the key advertises. Measured over the local artifact tree on 2026-08-05: 114 of 1,141 clubs carrying history were affected, most pinned to `continental`; Atlanta United drew 3 of its 33 checkpoints. An inherited target must now clear half the best-covered metric's checkpoints; a target the reader picks in the selector is still honoured at any coverage, because the option states its count. **Live 2026-08-07** (Pages run `31137310382`, commit `1451e9f`): the fix is client-side logic over artifacts that are already published, so no artifact rebuild was needed — the live `https://entenser.com/intelligence.js` carries `HISTORY_COVERAGE_FLOOR`, and the service worker is stamped `entenser-shell-1451e9fc5539` so installed PWAs take the new shell. Verified end to end against the artifact tree before shipping: Atlanta United now defaults to `playoff · 33 checkpoints` and draws 9 reconstructed + 24 archived, against 3 archived and no replay before. The live authenticated render was not re-checked post-deploy. |
| Checkout safety | ✅ Deployed, not production-rehearsed | Production requires four immutable Prices, Stripe/webhook/auth/KV dependencies, three approved policy versions, and an owner switch; live config reports checkout disabled without exposing missing secret names |
| Growth measurement | ✅ Deployed foundation | Canonical funnel/lifecycle dictionaries, privacy-limited server ledger, cancellation/support/testimonial capture, Stripe/delivery events, shadow-review evidence, and owner scorecard shipped; GA4/GSC production inputs remain missing |
| Live alerts and briefings | ❌ Not offered | UI labels delivery unavailable; live scripts require both protected send switches, two matchweeks of shadow QA, one quiet cycle, and owner approval |
| Platform reliability — Phase 1 of the 2026-08-09 spec | 🔄 Merged as code and CI config; **no scheduled run has exercised it yet** | Branch `auto/spec-exec-2026-08-09`. **MLS schedule routed** — `build_dashboard_data` resolves its schedule through `source_registry` with ESPN first and API-Football (af_id 253) as ordered fallback, so a 403 on `usa.1/scoreboard` stops being fatal. ESPN stays primary deliberately: a healthy build takes the rows it takes today. **The fallback now answers, verified live 2026-08-09.** `config/api_football_team_names.json['mls']` is generated and committed: 29 of API-Football's 30 MLS clubs already resolved on token matching, and the one that did not — `'Los Angeles Galaxy'` → `LA Galaxy` — was proven by fixture diff, not name similarity (all 19 played 2026 meetings matched on date and opponent with **zero scoreline disagreements**; one 23:30 UTC kickoff matched a calendar day later at the same 2-1). **Acceptance met, in CI:** with `ENTENSER_BLOCK_ESPN=1` blackholing ESPN at the HTTP layer, `routed_schedule` returns **510 fixtures across all 30 clubs** from the spine. Note what this does and does not claim: `build (mls)` failed 08-06 to 08-09 on a 403 for `usa.1/scoreboard` and went green again on **08-10, before this work landed** — ESPN simply started answering. The routed fallback has never been needed by a scheduled run; what it buys is the NEXT outage, and the Fault Injection Drill is the only thing that proves it. **The name floor was raised 0.95 → 1.0** on this evidence: 29/30 is 96.7% and *clears* a 95% floor while silently dropping every LA Galaxy fixture, because an unmapped club is discarded downstream as "not an MLS team" and the payload still looks healthy. A share threshold is the wrong shape for a closed league with a known club set. **Rebuild serialization**: `refresh-leagues.yml` carries a constant concurrency group, `cancel-in-progress: false`. **Source health**: `scripts/build_source_health.py` folds each run's gitignored parquet into a committed JSON summary and fails the run after three consecutive dark runs for a feed; `--check` runs after the commit so a verdict cannot discard good payloads. **Fault-injection drill**: weekly, `ENTENSER_BLOCK_ESPN=1`, asserting a routed league survives, an unrouted one fails visibly, and the MLS schedule falls through. Verified by test, not by a scheduled run. |
| Data-integrity checks — standings and payload self-consistency | 🔄 Merged; standings check is credential-blocked until it runs in CI | `scripts/check_standings.py` diffs every published table against API-Football `/standings` (~78 requests/day, exact name matching only — a fuzzy matcher proposed `Bristol City → Stoke City` during Stage 3). Verified offline against the committed payloads: with no credential every league reports `error` with its reason and the exit code stays 0. `scripts/check_payload_consistency.py` reads the payloads the way a client does and checks club sets, each club's `gp` against its own fixtures, pair multiplicity, and names differing only by whitespace; `config/payload_consistency_baseline.json` records today's measured deviations so a NEW one fails the run. **Both findings adjudicated 2026-08-09.** *NWSL `gp`*: the TABLE WAS RIGHT. Gotham and Kansas City each read one game short because the `games` list published their 2026-06-26 meeting (Gotham 2-0) while the standings loop correctly filtered it — ASA marks it `is_playoff=1`, the only knockout fixture in NWSL's 2026 season. Proved by arithmetic on both clubs at once: dropping that one fixture gives Gotham 18gp/37pts and Kansas City 18gp/29pts, which is exactly what the table publishes, while "drop each club's most recent match" gives Kansas City 28 and fails. The builder now emits `knockout: true` on such fixtures and both consistency checks skip them — deliberately NOT keyed `ko`, which is already the kickoff timestamp on upcoming cards in 32 leagues; reusing it read every scheduled fixture as a knockout and silently emptied the checks. *Trailing space*: six clubs, not one, all in `australia-aleague-women`; fixed at the ESPN source boundary in commit `e73049d0`. |

**Repository verification proof (2026-07-31):** the integrated release passed
1,719 tests with 14 intentional skips; all 79 public payloads, the Intelligence
artifact contract, history-growth gate, promotion-gate self-test, Python
compilation, JavaScript syntax, and `git diff --check` passed. The static build
emitted 78 league pages, 1,446 club pages, and a 1,543-URL sitemap.

**Historical replay proof (2026-07-31):** the replay coverage manifest reports all 71 domestic
league race pages covered: 35 reconstructed and 36 whose exact archive predates the current season.
The committed reconstructed dataset has 5,725 unique `(league, team, date)` rows, stays strictly
before each league's first authoritative archive date, contains only current standings members,
and keeps every probability in `[0,100]`. Regression coverage proves future fixture scores do not
affect an earlier replay and that archived rows win every same-day merge.

**Historical replay deployment proof (2026-07-31):** GitHub Pages run `30637496201` completed
successfully for commit `871eaa4`. The live MLS payload begins on `2026-02-20` with
`kind: reconstructed`, and the live page labels dashed segments as reconstructed and solid segments
as archived. This is a point-in-time model replay, not a claim that those forecasts were published
on those historical dates.

**Production verification proof (2026-07-31):** GitHub Pages run `30627028178`
and Vercel API run `30627028137` completed successfully for commit `1d954fa`.
The live homepage serves the Club Watch promise, and
`https://api.entenser.com/v1/public/config` returns the deployed checkout
contract with `enabled: false` and `reason: owner_disabled`. This proves the
release and kill switch are live; it does not pass pricing, legal, transaction,
delivery, or customer-evidence gates.

**Presentation follow-up proof (2026-07-31):** GitHub Pages run `30629626679`
completed successfully for commit `b468f6e`. The live index contains the MLS
dual flags, table-first movement placement, neutral link styling, honest
season-start baseline, horizontal desktop hero, and consolidated masthead
ticker; the deployment also refreshed the live service-worker cache.

**Owner decision recorded (2026-07-29):** Ryan approved the paid-launch decision record as written:
7,000 active paid is the objective; Club Watch, its primary audience, boundary, launch pricing,
no-trial guarantee treatment, validation shortlist, scope freeze, and earliest controlled-beta
milestone are approved. The exact target date for reaching 7,000 remains open; 24 months is only a
provisional planning horizon.

## Launch blockers, in order

### 1. Connect the production API domain — completed 2026-07-26

`api.entenser.com` is attached to the Vercel production environment through the Namecheap CNAME
`3b4876572083db00.vercel-dns-017.com`. Cloudflare and Google public DNS resolve it, HTTPS is active,
`GET /v1/public/config` returns 200, and a preflight from `https://entenser.com` returns 204 with
the exact allowed origin.

**Exit test:** ✅ passed.

### 2. Provision durable storage and production secrets — completed 2026-07-26

The Upstash database is live and the required variables are configured Production-only:

- `ENTENSER_ENV=production`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `ACCESS_TOKEN_SECRET`
- `ADMIN_TOKEN`
- `UNSUBSCRIBE_SECRET`
- `PUBLIC_API_URL=https://api.entenser.com/v1`

The latest Production deployment is Ready. With `ENTENSER_ENV=production`, the custom-domain
`GET /v1/public/config` returns 200 through Upstash; a production magic-link request completed and
its email arrived, proving the deployed application can write durable auth state as well as read it.

**Exit test:** ✅ passed.

### 3. Form the Ohio single-member LLC without publishing the home address

The owner decision is an Ohio single-member LLC with its default federal tax treatment. Do not elect
S-corporation taxation during formation unless a CPA later recommends it based on sustained profit.
Ryan lives and operates in Ohio, so use Ohio rather than adding the fees and filings required to form
elsewhere and then qualify the foreign LLC in Ohio.

#### Address-privacy setup — complete before filing

1. Choose a reputable Ohio statutory-agent service. “Statutory agent” is Ohio's term for a
   registered agent.
   - The service receives lawsuits and official state documents; it is not automatically the
     company's ordinary mailing address.
   - The agent must accept the appointment and provide an Ohio street address where an authorized
     person is normally present during business hours.
   - The agent's name and address appear in the public Ohio business record. Using a professional
     service keeps Ryan's home address out of that required public field.
2. Obtain a separate business mailbox from a Commercial Mail Receiving Agency (CMRA) or
   privacy-oriented virtual-mail provider.
   - Prefer a real street-style address with a unique PMB or suite number, mail scanning, check
     deposit or forwarding if needed, and preferably an Ohio location.
   - Complete USPS Form 1583 and its identity check. A CMRA receives ordinary business mail; it is
     not a valid Ohio statutory-agent address. A provider offering both services must use its actual
     staffed Ohio office—not the rented private-mailbox address—for the statutory-agent role.
3. Ask both providers exactly which filing fields their addresses may be used for. Some registered
   agents also sell a permitted business-address service; do not assume the basic agent plan includes
   it.
4. Preview Ohio Articles of Organization Form 610 and identify which entered fields will become
   public. Ohio law requires the LLC name plus the statutory agent's name, Ohio street address, and
   signed acceptance; avoid adding optional personal information to the Articles.
5. Use the CMRA address for public business/mailing fields only where the state permits it, and use
   the registered-agent address only in fields the agent authorizes.
6. Do not put the home address, personal phone number, or personal email in an optional public field.
   Create an LLC-specific email and use the Entenser support email or business mailbox where accepted.
7. Never provide a false address. The IRS, bank, Stripe, and other identity checks may privately
   require Ryan's real residential or physical address. Give it to them when required; the goal is
   to keep it out of public records and marketing lists, not to conceal the owner from regulators or
   financial institutions. The IRS permits a separate mailing address but requires a physical street
   address when it differs and does not allow a P.O. box in that physical-address field.

#### Formation checklist

1. Use the [Ohio Secretary of State filing page](https://www.ohiosos.gov/business/business-filing-forms)
   and Ohio Business Central. File domestic LLC Articles of Organization, Form 610; the current
   standard filing fee is $99. Avoid third-party formation sites unless deliberately hiring one.
2. Choose the exact LLC name, search the state database, and search the
   [USPTO trademark database](https://www.uspto.gov/trademarks/search) for confusingly similar
   names. Decide whether the legal name will include `Entenser`; record the final spelling exactly.
3. Confirm whether `Entenser` needs a state or local DBA/assumed-name filing if it differs from the
   LLC's legal name.
4. Hire the registered agent and open the CMRA/virtual mailbox before submitting the state filing.
5. File the Articles of Organization directly through the official state site. Use the approved
   privacy addresses in the correct fields, select member-managed unless counsel recommends
   otherwise, save the submitted form and receipt, and decline unnecessary third-party upsells.
6. After approval, download and securely store the stamped Articles/Certificate of Organization and
   state entity ID.
7. Sign a single-member operating agreement naming Ryan as the sole member and documenting initial
   ownership, management authority, and the tax year. Keep it internally; do not publish it unless
   the state requires filing.
8. Apply for the EIN free through the [official IRS EIN application](https://www.irs.gov/businesses/employer-identification-number)
   only after the LLC is approved. Use the LLC's exact legal name, save the EIN confirmation
   immediately, use the business mailbox for IRS correspondence where allowed, and provide the real
   physical address where the application requires it.
9. Open a business checking account in the LLC's legal name using the approved formation document,
   EIN confirmation, operating agreement, and Ryan's identity documents. Fund it with a documented
   owner contribution and do not mix personal and LLC transactions.
10. Register or verify requirements with the Ohio Department of Taxation and the relevant city or
    municipality. Ask a CPA about Ohio's Commercial Activity Tax, municipal net-profits tax,
    whether Entenser subscriptions are taxable, and when multistate or international sales-tax/VAT
    registration could be triggered.
11. Check the current [FinCEN BOI page](https://www.fincen.gov/boi). As verified 2026-07-27,
    U.S.-created entities are currently exempt from federal BOI reporting, but recheck because this
    rule can change.
12. Create a compliance calendar for the statutory-agent renewal, mailbox renewal, federal and Ohio
    tax deadlines, municipal filings, license renewals, and domain renewals. The Ohio Secretary of
    State's current LLC guide says Ohio LLCs do not file annual or biennial reports, but recheck this
    each year because the rule can change.
13. Ignore official-looking formation solicitations until independently verified on the relevant
    government website. State filings commonly trigger private mail selling certificates, posters,
    filing services, or other items that may not be required.
14. Update Stripe, the business bank account, Terms, Privacy Policy, refund policy, invoices, support
    footer, and tax records with the exact LLC name and business mailing address. Keep residential
    information in private verification fields only.

Official references: the
[Ohio LLC guide](https://www.ohiosos.gov/assets/business-start-a-llc.pdf) and
[Ohio business FAQ](https://www.ohiosos.gov/business/ohio-business-roadmap/frequently-asked-questions)
define the statutory-agent and filing requirements; the
[SBA registration guide](https://www.sba.gov/business-guide/launch-your-business/register-your-business)
explains state filing and registered-agent basics; the
[USPS CMRA guide](https://faq.usps.com/articles/Knowledge/Commercial-Mail-Receiving-Agency-CMRA)
explains private mailboxes and Form 1583; and the
[IRS SS-4 instructions](https://www.irs.gov/instructions/iss4) distinguish mailing and physical
addresses.

**Exit test:** the Ohio business database shows the LLC active; the formation approval,
operating agreement, and EIN notice are securely saved; the LLC bank account is open; the registered
agent and business mailbox both work; and a review of the public state record confirms the home
address does not appear except where the state expressly requires it.

### 4. Activate and configure Stripe

- Finish Stripe business, bank, and identity activation.
- Create four immutable Prices:
  - `STRIPE_PRICE_INTEL_MONTHLY_LAUNCH` — $5.99/month
  - `STRIPE_PRICE_INTEL_ANNUAL_LAUNCH` — $59.99/year
  - `STRIPE_PRICE_INTEL_MONTHLY_STANDARD` — $7.99/month
  - `STRIPE_PRICE_INTEL_ANNUAL_STANDARD` — $79.99/year
- Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`.
- Point the Stripe webhook at the production API.
- Enable cancellation and payment-method updates in the Stripe Customer Portal.

**Exit test:** `/v1/public/config` exposes monthly and annual launch prices, and a test Checkout
Session returns a Stripe URL.

### 5. Publish the legal contract

Resolve the owner decisions in `legal-copy-draft-2026-07-25.md`, then publish:

- Terms of Service
- 30-day refund policy
- Corrected privacy policy

The current privacy language predates accounts and paid subscriptions and cannot remain the
customer contract.

### 6. Run the production dress rehearsal

On a real device and cold browser session, run both monthly and annual:

1. Sign in by magic link.
2. Start checkout and pay in the intended Stripe mode.
3. Confirm the entitlement is durable across a new session.
4. Open the Customer Portal.
5. Cancel.
6. Request and process a refund.
7. Confirm webhook idempotency and the resulting entitlement state.

Record Stripe event IDs and API responses in the active launch plan. Any failure on this path
blocks launch.

## Next actions — Claude-executable now (ranked 2026-08-15)

Needs no owner account, decision, or payment. Ranked by (milestone impact × confidence) ÷ effort,
against the current objective: **one complete production transaction through the real Club Watch
path**. None of these need Stripe to be live, and every one of them is work the transaction
depends on — a supporter will not pay for a forecast built on twelve-day-old data, and a rehearsal
cannot be trusted against a red suite.

**1 and 2 shipped together on 2026-08-15** and are struck through below; they were one incident,
and landing the one-line fix alone would have left the other two defects armed for the next cause.
**#3 is now the top of the queue and the largest remaining correctness risk before launch.** The
one thing still owed on 1–2 is a green scheduled run: the fix is proven by test and by reverting
each defect in turn, not yet by CI meeting a live spine league.

| # | Action | Why it ranks here | Proof it is ready to do |
|---:|---|---|---|
| ~~1~~ | ✅ **DONE 2026-08-15** — ~~Add `API_FOOTBALL_KEY` to `refresh-fast.yml`~~ | One line, certain diagnosis, and it stops the site's freshness engine failing most of the day. `refresh-daily.yml`, `refresh-leagues.yml` and `fault-injection.yml` already carry it; this workflow was last edited 2026-08-08 and the spine path landed 2026-08-09, so it was simply never wired | The exact failing line is `data_pipeline/api_football.py:152`, reached from `fast_refresh.py:187`; the fix is `API_FOOTBALL_KEY: ${{ secrets.API_FOOTBALL_KEY }}` in the existing `env:` block at line 16 |
| ~~2~~ | ✅ **DONE 2026-08-15** — ~~Make the fast refresh degrade instead of aborting~~ | Two defects behind #1, and #1 alone leaves both live for the next cause. `refresh_selected` catches `requests.RequestException` only, so any other exception still takes every league down — the blast radius the 2026-08-07 isolation was written to remove. Separately `refresh_league` calls one source and stops, although `source_registry` declares `["api_football", "espn"]` in that order; `build_league_data` honours the fallback and the fast path does not | Both are in `scripts/fast_refresh.py` (`refresh_league` ~line 378, `refresh_selected` ~line 410). Keep the narrowness that was deliberate — a `ValueError` or the pmatrix `AssertionError` is a payload bug and must still stop the run |
| 3 | **Move the stale Tier-A leagues onto the spine** — *step 1 of 3 shipped 2026-08-15* | The largest correctness risk before launch: 49 of 91 payloads have not been rebuilt since 2026-08-03/05, including every European top flight, with the 2026-27 season opening. ESPN is dark (`espn_fixtures` 384/384 failed); `api_football` answers 70 of 71. This is the reliability spec §3.2, and the plan is bought and paid for — CI already runs `API_FOOTBALL_PLAN: mega` | Ranked third only because it is per-league validated work, not because it matters least. Precedent exists: three leagues are already routed, and the MLS name map was proven by fixture diff rather than name similarity |
| ~~4~~ | ✅ **DONE 2026-08-15** — ~~Stop `tests/test_surface_contract.py` failing on a fresh clone~~ | Cheapest trust repair available. Two tests fail for anyone who has not built the gitignored `data/team_intelligence/` tree — the identical defect fixed for `test_static_pages` on 2026-08-11, missed on this file. A suite that is red for a reason unrelated to your change is a suite people stop reading, and the transaction rehearsal is exactly when that costs most | Reproduced here: `2 failed, 2145 passed, 40 skipped`, both `ArtifactNotFound` for `epl/v1_1c90591709108353`. `test_static_pages.py:117-121` already has the skip to copy |
| 5 | **Tell readers how fresh each league is** | Trust, and it needs no owner. The site currently presents a 12-day-old Premier League table with the same confidence as a table rebuilt this morning. Publishing per-league freshness — or degrading the claim when a payload is stale — is the honest version of the product-invariants truth rule, and it is the difference between a data outage and a credibility one | `source_health_summary.json` and every payload's `generated` stamp already carry the data; nothing new needs measuring |
| 6 | **Re-check the authenticated Club Watch render in production** | Directly on the milestone path — it is the surface the transaction delivers. The Club Watch history row below still says in its own words that "the live authenticated render was not re-checked post-deploy", and that gap has now survived two deploys | Everything needed is live: the artifacts are published, the public API is healthy, and the relay correctly returns 401 without its publisher credential |
| ~~7~~ | ✅ **PARTLY DONE 2026-08-15** — ~~Close issue #10~~ (closed; the fault drill was fixed in `7a8681a` and has passed twice since, once on schedule). The three `refresh-failure` issues stay open on purpose: #8 closes on a green fast-refresh run that actually selects a routed league, and #6/#7 close when the feeds come back. | Pure noise reduction, near-zero effort. #10 says the fault-injection drill proves the ESPN fallback is broken; it does not — the drill was testing its own copy of the resolver, was fixed in `7a8681a`, and has passed twice since, including a scheduled run | Runs `31557258012` and `31574725142` (the latter `event: schedule`) both succeeded. Four `refresh-failure` issues are open and #8 alone has 74 comments, which is how a real alert gets missed |

## Next actions — owner-blocked (ranked 2026-08-15)

Each needs one decision or one account. Nothing here is work Claude could do instead.

**Re-scoped 2026-08-15.** With the paywall off, **none of this blocks launching any more** — it blocks *charging*, which is now a later milestone. The list is unchanged and still accurate; what changed is its urgency. Ranks 1–3 are the paywall's return, not the launch. The two that still matter for the free launch are **GA4/GSC access** and **`D2` recruiting**, because a free launch whose behaviour nobody measures produces no evidence, which is the entire reason for running one.

| # | Blocked on | Single thing needed | What it unblocks |
|---:|---|---|---|
| 1 | **Stripe activation** | Activate the account; create the four immutable Prices; register the webhook; configure Customer Portal, receipts, refunds, failed-payment behaviour | The entire current objective. `/v1/public/config` returns `"pricing": {}` and `checkout.enabled: false, reason: owner_disabled` — verified 2026-08-15. No transaction, rehearsal, or `C1` gate can run without this |
| 2 | **LLC, EIN, bank account** | Complete the Ohio single-member LLC and its private mailing setup, then EIN, then bank | Gates Stripe (#1) and the legal name every policy document needs. Formation type is chosen; the legal name is still open |
| 3 | **Legal approval** | Decide the draft's open terms using the final legal name, then approve Terms, Privacy, refund, cancellation, renewal, and affiliation language | Publication. `/terms/`, `/privacy/` and `/refunds/` all return 404 as of 2026-08-15. Also the retirement trigger for `legal-copy-draft-2026-07-25.md` |
| 4 | **GA4 and Search Console access** | Create or confirm access; submit the sitemap | The `M1` funnel and Stripe reconciliation. The measurement foundation is deployed and blind without production inputs |
| 5 | **`D2` recruiting** | Recruit ≥15 primary supporters plus ~3 quantitative users and ~3 creators | The recurring-job gate, and every downstream concierge and pricing decision |
| 6 | **Vendor confirmations** | Confirm Vercel Pro, Resend capacity, `support@entenser.com`, and the support/refund schedule | Delivery capacity and the refund promise the paid-launch record already committed to |
| 7 | **The 7,000-subscriber target date** | One calendar date | Closes `G0.2`, the last open item in an otherwise approved decision record. 24 months remains provisional planning, not a commitment |

**Removed from this list on 2026-08-15:** the API-Football Mega purchase. It is bought — CI runs
`API_FOOTBALL_PLAN: mega` with a 2,000/day ops budget — so the migration spec's purchase
checkpoint has passed and no owner action remains behind it.

## Owner actions

These require account access or business decisions and cannot be completed from the repository:

1. Supply the explicit target date for reaching 7,000 active paid subscribers. All other
   `G0.1–G0.10` decisions are approved and recorded.
2. Form the single-member LLC, establish its private mailing setup, obtain its EIN, and open its bank
   account.
3. Activate Stripe; create the four immutable Prices; register the webhook; configure the Customer
   Portal, receipts, refunds, and failed-payment behavior.
4. Decide the legal draft's remaining open terms using the LLC's final legal name and jurisdiction,
   then approve the Terms, Privacy, refund, cancellation, renewal, and affiliation language.
5. Confirm Vercel Pro, Resend capacity, `support@entenser.com`, and the support/refund schedule.
6. Create or confirm GA4 and Google Search Console access; submit the sitemap; export all available
   analytics, search, waitlist, support, and customer evidence or explicitly mark it missing.
7. Recruit the `D2` discovery sample using `docs/customer-discovery-kit.md`: at least 15 primary
   supporters plus approximately 3 quantitative users and 3 creators.
8. Approve any broadcast email. No broadcast is sent without explicit approval.

## Agent work immediately after owner decisions and access

1. Record approved `G0` decisions in canonical documentation and reconcile final Account, claim,
   cancellation-reason, support-taxonomy, testimonial-consent, and local-versus-durable behavior.
2. Populate public pricing and publish the approved Terms, refund, and corrected privacy routes.
3. Verify the remaining authenticated production paths and fail-closed error behavior.
4. Execute the monthly and annual dress rehearsals with Ryan, including the checkout-disable test.
5. Verify the complete GA4 funnel and Stripe reconciliation.
6. Confirm the custom domain, CORS, auth, checkout, webhook, portal, export, cancellation, refund,
   deletion, and entitlement paths in production.
7. Code the discovery evidence and issue the `D2` go/iterate/kill recommendation before any
   concierge or automated-delivery expansion.

## Recently completed

- Two contract tests made honest about the working tree (2026-08-11, tests only). Both failed on
  every developer machine here and passed in CI, which is the failure mode that teaches people to
  ignore a red suite. `test_logo_map` compared the COMMITTED `KNOWN_NAME_CLASHES` allowlist
  against WORKING-TREE payloads, so a local logo rebuild reported `3472.png` as a stale entry
  while it still collides (Portugal vs Uruguay) in everything anyone else sees; it now reads
  `git archive HEAD`, matching the precedent set by the payload-consistency test, and still fails
  when a real collision appears. `test_static_pages` compared a GITIGNORED intelligence artifact
  against a COMMITTED payload — an asymmetry that guarantees drift, since CI refreshes the payload
  several times a day and the artifact is whatever the last local build left (measured: artifact
  08-04 12:58 UTC at 28.6, payload 08-11 11:44 UTC at 28.8, with a pristine `mls.js`). It now
  skips only when the artifact is strictly OLDER, so a newer or equal-but-disagreeing artifact
  still fails, and the co-generation check is evaluated after the page contract so a stale
  artifact costs no other coverage. Suite 2149 passed / 0 failed / 36 skipped.

- **Backfilled xG ported to four leagues** (2026-08-09, spec §4.1/§4.2; owner-authorised). The
  §4.2 undiluted re-run settled it: the 2022–2025 folds dilute every delta ~25% because xG begins
  in 2023, so the first fold is identical in both arms. Re-measured on 2023–2025 at two seeds,
  `n_bags=5`, sum-form Brier (negative = better): `primeira` **−0.0075**, `belgian-pro`
  **−0.0027**, `eredivisie` **−0.0018**, `championship` **−0.0015**, each clearing the −0.0010
  bar on *both* seeds independently. Wired in `_routed_frame`, the single production frame load
  and the same point the campaign's treatment arm used, so what ships is what was measured;
  `attach_xg` fills only empty values and cannot change row count, so every unwired league is
  byte-identical. Verified end to end: `championship` 1,654 of 6,624 rows filled,
  `brazil-serie-a` 0. **`super-lig` was NOT promoted** — its mean (−0.0012) clears the bar but
  its seeds span −0.0020/−0.0004, a 0.0016 spread against a stated single-run σ≈0.0002, and the
  protocol asks a second seed to *confirm* a gate-bound claim. **`brazil-serie-a` stays
  REJECTED** at +0.0037 on both seeds, worse than the diluted +0.0026. Champion config
  unchanged. Payload effects appear on the next CI rebuild, not before. 5 new tests; suite 2148
  passed, 2 pre-existing failures unrelated to this change (`test_logo_map`, `test_static_pages`,
  both reproduced with the change stashed and both artefacts of a dirty local-refresh tree).

- Club display names normalised at the ESPN source boundary (2026-08-09, code only — payloads
  change on the next CI rebuild, not before). ESPN's `aus.w.1` feed returns 6 of 11 A-League
  Women clubs with a **trailing space** in `displayName` (`'Western Sydney '`, `'Sydney FC '`,
  `'Adelaide United '`, `'Canberra United '`, `'Melbourne Victory '`, `'Newcastle Jets '`), and
  every one reached the published payload untouched, in the standings table and the fixtures
  alike. **Adjudicated as display-only, no migration:** `canonical_team_id` already strips and
  casefolds before hashing, so club ids — and the fixture ids derived from them — are
  whitespace-invariant, and no archived record is keyed on the untrimmed form; verified by
  recomputing `australia-aleague-women` fixture ids trimmed and untrimmed to the same
  `v1:e67993e5a7ac50ec`. The exposure was forward: any join or filter matching the display name
  rather than the id drops those clubs, the shape that came 2,114 rows from deleting a third of
  a league. Fixed once in `data_pipeline/names.py` (stdlib-only, so `fast_refresh --select`
  still imports on the runner's bare Python — R6 asserted) and applied at all four ESPN read
  sites: `espn_fixtures`, `espn_continental`, `espn_soccer`, `fast_refresh`. Fixing one and not
  its siblings would have left the fast path matching untrimmed names against a trimmed build.
  6 new tests; suite 2052 passed / 0 failed / 35 skipped (Playwright modules excluded — not
  installed locally).

- API-Football migration Stage 0 (2026-08-08, build blind, zero requests): budget governor
  (`data_pipeline/api_budget.py` — fail-closed ops/backfill allowances counted from
  `source_health.parquet`, plan assertion from rate-limit headers as the silent-lapse guard,
  ≤50%-of-plan throttle), pagination handling in the API-Football adapter, and a per-family
  source registry (`data_pipeline/source_registry.py`) wired through `build_league_data` with
  payload `provenance` published. Registry is empty, so no league's sourcing changed. 34 new
  tests; suite 1975 passed / 0 failed. **Stage 1 also complete** (13 free-key requests, all
  governed and recorded): statistics are per-fixture; real xG exists from the **2023 season**
  (backfill ceiling drops ~139k → ~46k); historical closing odds do not exist on the API
  (football-data keeps the odds column, now measured); 64/78 competitions reach 2017 by catalogue
  metadata; a 557-fixture season does not page. League map drafted 78/78
  (`config/api_football_league_map.json`, 77 high/anchor; Paraguay needs two ids; **map approved
  by owner 2026-08-08**). **Stage 2 passed** (~6 requests): Brasileirão 2022–2024 built from the
  spine and diffed against football-data — 1,140/1,140 scorelines agree, standings identical,
  champion feature builder accepts the frame unmodified; ten club-name pairs measured as the
  Stage-3 name-map seed. **Backfill job built** (`data_pipeline/backfill_statistics.py`,
  resumable/idempotent, statistics-only, 205 units / 52 competitions planned, refuses to run on
  the free plan by construction). **Mega purchased and header-verified 2026-08-08; Stage 3
  batch 1 shipped:** northern-super-league and usl-super-league migrated to spine-first with ESPN
  fallback (100% scoreline agreement, standings identical; USL-SL gains its 2024 inaugural
  season); costa-rica-primera held on ESPN-first (2015-history + 4 unadjudicated scoreline
  disagreements, recorded); CPL widened to 2020+, K League 1 to 2018+ with the Sangju→Gimcheon
  identity unified (DATA_STATUS flip deferred until CI rebuilds their payloads); CI carries
  `API_FOOTBALL_KEY`/`API_FOOTBALL_PLAN=mega`. Batch 1's observation week runs on CI; batch 2
  gates on it. **Stage 4 complete:** 46,205 statistics sheets fetched across 205 league-season
  units / 52 competitions for 46,485 requests (31% of one Mega day, ~4.5 h). **Usable xG is 43.9%
  — corrected from an initially reported 92.1%**, which counted sheets where the `expected_goals`
  field appeared; API-Football emits that field with a **null value** about half the time.
  Counting matches where BOTH teams carry a real value — the only form a rolling window can use —
  **only 7 competitions clear 90%**: `championship` (1,664 matches), `brazil-serie-a` (1,343),
  `segunda` (1,140, 100%), `super-lig` (1,026), `eredivisie` (920), `primeira` (919),
  `belgian-pro` (937). 11 are partial (50–90%), **34 are under 50%**. Honest headline: the
  platform's xG coverage roughly **doubles, 7 competitions → 14** (understat 5 + ASA 2 + these 7,
  all previously football-data sourced with no xG at all) — not the "90% of competitions" §10 of
  the spec claims, which is corrected there. The data is INERT — per invariant 4 it reaches the
  model only through a gated Brier-compared experiment.
- **xG join built** (2026-08-08, commit `9d2f5e48`, `data_pipeline/xg_store.py`). Joins the
  statistics store onto canonical frames via the backfill's own fixture inventories, since
  football-data frames carry no API-Football fixture id. **6,787 matches gain xG** at 99–100% of
  stored rows: championship 1,654 · brazil-serie-a 1,343 · super-lig 1,026 · belgian-pro 932 ·
  primeira 918 · eredivisie 914. Assigns by team id (never sheet order), requires both sides
  non-null, and never overwrites an existing value (Tier C owns its xG). **Not wired into any
  build** — see the campaign verdict below.
  **League-map defect found and fixed:** `segunda` mapped to af_id 140 **La Liga**, not Segunda —
  fuzzy matching scored "LaLiga 2" closer to "La Liga" than to "Segunda División", it was marked
  high confidence, and only the join exposed it by putting Real Madrid into a second-division
  frame. Corrected to 141; `tests/test_league_map_ids.py` pins every id confirmed against the
  clubs in its own fixtures. **Consequence: segunda's 1,140 stored sheets are La Liga's** and must
  be re-fetched under id 141 before segunda can join the campaign. **Re-fetched 2026-08-08 (1,404
  sheets, af 141 confirmed to hold 22 real Segunda clubs): segunda's true usable xG is 163/1,404 —
  12%**, far below the bar. It is OUT of the campaign; the usable set is **6 competitions**, and
  the platform's xG coverage goes 7 → 13, not 7 → 14.
- **xG feature campaign run and judged** (2026-08-08, `scripts/xg_feature_campaign.py`, two seeds,
  n_bags=5, 4 folds; full record in `docs/feature-hunt-log.md`). Per-league A/B where the only
  variable is whether xG carries values. **4 KEEP** — `primeira` −0.0055, `belgian-pro` −0.0020,
  `championship` −0.0012, `eredivisie` −0.0011 (mean Δ Brier, lower is better). **1 marginal** —
  `super-lig` −0.0009. **1 REJECT** — `brazil-serie-a` **+0.0026, regresses on both seeds**
  despite 100% xG coverage and a Stage-2 diff matching football-data 1,140/1,140; more features
  are not free, which is why the gate exists. The two-seed protocol was load-bearing: on seed 42
  alone `super-lig` read KEEP and `championship` read noise, and on seed 7 they swap. All deltas
  are diluted ~25% because xG starts in 2023 while the folds run 2022–2025, so the first fold is
  identical in both arms. **NOT promoted** — wiring `xg_store.attach_xg` into the frame load for
  the KEEP leagues is a separate, owner-gated production port.
- ✅ **Resolved 2026-08-08 — the Segunda contamination was an upstream 301, not a fallback.**
  football-data.co.uk redirects the not-yet-published Spanish 2026-27 files onto the Scottish
  ones: `mmz4281/2627/SP2.csv` → `SC2.csv` and `SP1.csv` → `SC1.csv`, confirmed by `Location`
  header. requests follows redirects and `raise_for_status()` sees the final 200, so the fetch
  looks clean at every layer — the redirect is invisible to HTTP-level checks, but the division
  the file names for itself is not. Five Scottish League One results were cached as
  `SP2-2627.csv` and parsed into LaLiga 2's frame, pushing its `max_played_season` to 2026 and
  suppressing the pre-season flip to ESPN's real fixtures.
  **Scope, measured not assumed:** all 19 divisions swept live — exactly two redirect (SP1, SP2);
  every other division returns a clean 404 (season not started) or 200. All 270 cached raw CSVs
  checked against their own `Div` column — exactly two mismatch, both in the live season, none
  historical. Cross-league club-set check across all 17 footballdata leagues: `segunda` alone is
  contaminated (10/10 live clubs foreign); the two Scottish leagues it flags are genuine
  promotion/relegation. La Liga takes no fixture damage (Understat-sourced) — SP1 poisons only
  `market_probs`, and those Scottish names fail the `(season, home, away)` merge, so La Liga got
  zero 2026 odds rather than wrong ones.
  **Fix** (`data_pipeline/football_data.py`): `_fetch_csv` validates every response *and* every
  cache hit against the `Div` column the file declares, and writes nothing to disk until it
  passes — so a poisoned response can no longer be persisted, and an already-poisoned cache is
  refused rather than served. Chosen over the roster filter first proposed: `Div` is exact and
  self-maintaining, whereas a roster needs per-league-per-season upkeep and would wrongly drop
  legitimately promoted clubs. `tests/test_football_data.py` (new, 7 tests) pins the redirect
  case, the poisoned-cache case, and the mangled-BOM header the real cache carries. Verified on
  live data: segunda 5,549 → 5,544 rows, 0 Scottish, `max_played_season` back to 2025 so the
  pre-season flip works again; La Liga 2026 market rows 5 → 0. **2032 passed, 35 skipped.**
  **Not yet in production** — source-side only; lands on the next league rebuild. The shipped
  `webapp/data/segunda.js` was built 2026-08-03 07:05 UTC, before the redirect appeared, so it
  is clean (22 Spanish clubs); an unguarded refresh would have been the first to publish it.
  **Left open:** `_fetch_csv` persists `r.text`, and requests decodes a charset-less `text/csv`
  as ISO-8859-1, so every cached file's header carries a mangled BOM (`ï»¿Div`). Harmless today
  because `_parse_results` never reads `Div`; the guard reads the column positionally to cope.
- ✅ **Resolved 2026-08-08 — the same defect class one adapter over, and this one was already in
  the shipped data.** `data_pipeline/football_data_intl.py` filtered on season alone and never
  read the `League` column its own CSVs carry. `new/<CCC>.csv` is a **country** file, not a
  competition file, and two of the fourteen mix competitions.
  **Scope, measured not assumed** (all 14 cached files, `League` and `Country` value counts):
  ARG carries `Liga Profesional` 5,360 + `Copa De La Liga Profesional` **920**; SWZ carries
  `Super League` 2,685 + `Challenge League` **2**. The other twelve are single-competition.
  Five files (ARG, DNK, FIN, IRL, SWE) additionally carry a **trailing-space variant of their own
  name** — an era split, not a second competition: `'Liga Profesional '` alone is 2,114 rows,
  a third of the Argentine file, so an exact-match filter would have deleted a third of the
  league. Comparison is normalised (whitespace-collapsed + casefolded) for exactly that reason.
  **Fix:** `LEAGUE_COMPETITIONS` / `NON_LEAGUE_COMPETITIONS` / `FOREIGN_COMPETITIONS` declare, per
  league id, what each file may contribute; `_select_competitions` drops foreign rows, marks
  same-tier non-league rows `is_playoff=1`, raises rather than return an empty league if the
  filter matches nothing, and logs any **undeclared** value loudly so a football-data rename is
  visible rather than silent.
  **Argentina is a deliberate KEEP, not a drop.** The Copa de la Liga is not an open cup: since
  2020 it is one of two top-flight championships, entered only by Primera clubs. Dropping it would
  delete the whole of 2020 (134 Copa rows, no Liga rows that year) and split the history, because
  from 2025 football-data stopped distinguishing the two and files everything as `Liga Profesional`
  (510 rows in 2025, pairs meeting up to 3×). It stays in the rating history and leaves the table.
  **Blast radius:** frames change size for **swiss-super-league only** (2,687 → 2,685; the two rows
  are the Thun–Sion relegation barrage of 27/30 May 2021, and Super League 2020/21 already carries
  its full 180 rows without them). Its ELO history therefore shifts, but the **published rating does
  not**: five seasons and `regress=0.40` leave Thun **+0.009** and Sion **−0.0002**, below the
  integer rounding the payloads use. Argentina's frame is unchanged in size; **920 rows move to
  `is_playoff=1`, so its league table drops 6,280 → 5,360 counted matches.** Twelve leagues are
  byte-identical.
  **Found while fixing it, and larger:** `attach_market` merged on `(season, home_team, away_team)`,
  which is **not a unique key** — split-year leagues meet a pair 2–4× a season. The left-merge was
  fanning out **~15,500 duplicate rows across 9 of 14 leagues** (swiss 2,685 → 5,253, austria
  2,644 → 4,732, ireland 2,692 → 4,802, denmark +1,804, romania +1,740, finland +1,364, argentina
  +1,046, poland +784, china +24), attaching another fixture's closing odds. `market_probs` now
  carries `date` and `attach_market` merges on it, falling back to a de-duplicated market side when
  the caller has no date column (`build_league_data:2149` slices to three columns). Odds coverage
  after the fix is 100% for twelve leagues, 99.8–99.9% for China/Russia — nothing lost.
  **Also found:** this module's own tests had overwritten the real `BRA.csv` and `JPN.csv` raw
  caches with their 2- and 1-row synthetic fixtures, because `_fetch_csv` persists to
  `_RAW_CACHE_DIR` as a side effect and only some tests monkeypatched it. Latent rather than live
  (every build refetches first), but it disarmed the offline fallback for those two leagues. An
  autouse fixture now isolates both cache dirs; a full run leaves the raw dir empty.
  15 new tests; `tests/test_football_data_intl.py` 34 passed, 1 skipped. **Not yet in production**
  — source-side only, lands on the next league rebuild.
- **Three Stage-3 defects found and fixed by exercising the migration against production**
  (2026-08-08, commit `3a871e6`, suite 1999 passed): (1) **payload provenance was never actually
  published** — `"provenance"` was assigned twice in one dict literal in `build_league_data`, so
  Python kept the model block and silently discarded the routing block; invariant 5 was false for a
  day while being reported as shipped. Now nested as `provenance.sources`, with an AST test that
  fails on any duplicate key in the payload builders. (2) **Fast refresh was still 100% ESPN** —
  the workflow whose seven consecutive 403s motivated this entire migration never consulted the
  source registry, so the two leagues already migrated kept dying behind the ESPN circuit breaker;
  it now routes through the spine (`fetch_spine_scoreboard`), and `select_leagues` no longer gates
  on `espn_code` alone (which would have excluded canadian-pl outright). (3) **Backfill spend
  exhausted the ops allowance** — spend was counted in aggregate, so the 46k-sheet backfill locked
  the daily refresh out for the rest of the UTC day, exactly the coupling two allowances exist to
  prevent; spend is now counted per kind. **Note: ESPN's circuit breaker is open site-wide as of
  22:05 UTC**, so every unmigrated league's fast refresh is failing — which is the argument for
  continuing Tier A migration, not a new problem.
- **Canadian PL and K League 1 are un-staled — the paid plan's first visible win** (2026-08-08,
  commit `bbf8010`). Both had been pinned to 2024 by the free plan's season cap; both now publish
  the live 2026 season and validate clean: CPL `2026-04-04 → 2026-10-25` (112 games), K League 1
  `2026-02-28 → 2026-10-24` (198 games, 12 teams — the `ROUND_EXCLUDE` fix holding the cross-tier
  playoff out of the table). Both carry `provenance.sources`, confirming invariant 5 live. A third
  copy of the stale limitation lived in `tests/test_season_rollover.py`'s `SOURCE_BLOCKED` and was
  caught by that file's own accuracy test. **Operational rule learned:** league rebuilds must be
  **serialized** — two concurrent `refresh-leagues` runs race on the shared `power.js`,
  `team-catalog.js` and `news/*.js` artifacts; the second failed its rebase and the workflow
  correctly refused to force a data commit rather than clobbering the first.
- ✅ **Resolved: the 26-of-79 `validate_payloads` Global ELO failures were the CHECKER, not the
  data.** Every published `global_elo` was already correct — measured across all 79 payloads,
  **zero rows** disagree with the payload's own `elo_scale` metadata, and `bundesliga-2` Hannover
  96 reconciles exactly: `1503 + 0.723·(1597−1503) − 186.964 = 1383.998 → 1384`. The checker was
  still asserting `global_elo == elo + offset`, the pure-shift formula that `f4994158`
  (2026-08-07 15:14) retired when it added tier dispersion and `global_elo_adj`. That commit
  taught every consumer — `build_power_rankings.py`, `build_static_pages.py`, `webapp/index.html`
  — and six test files, and missed `scripts/validate_payloads.py`, which had no test coverage of
  this check at all. The two failure classes map 1:1 onto the two new terms: seven second tiers
  fail broadly on dispersion, and in the 19 top flights the failing rows are **exactly** the 75
  clubs carrying a continental adjustment (sets identical in all 19).
  **This was not cosmetic — it was breaking production.** `validate_payloads.py` exits 1, and
  `refresh-daily.yml` runs it bare inside a `run:` block, which is `bash -e`. The first nightly
  after `f4994158` (run `31254825570`, 2026-08-08) died at that line with
  `##[error]Process completed with exit code 1`, taking the rest of the step with it:
  `validate_history_growth`, `archive_intelligence_state`, `build_intelligence_events`,
  `build_intel_events_payload`, `build_team_intelligence`, `build_team_catalog` and
  `validate_intelligence_launch` never ran. The 08-07 nightly passed because it ran at 11:40,
  before the 15:14 commit.
  **Fix:** the checker now derives its expectation the way a *client* does — from the payload's
  own `dispersion`/`pivot`/`global_elo_adj`, mirroring `scaledElo`/`publishedElo` in
  `webapp/index.html` — rather than by calling `apply_global_elo_scale`, which would pass
  tautologically. Tolerance 0.51 → 0.6, documented as an error budget: reconstructing from
  metadata rounded to 4dp/1dp costs ~0.57 worst case where the old budget covered only the 0.5
  int-rounding, and the measured headroom was 0.01. **No rebuild required** — the payloads were
  never wrong. `python -m scripts.validate_payloads` → **All 79 payload(s) valid**, rc=0.
  Guarded by 7 new tests including a producer↔checker drift test that runs the real
  `apply_global_elo_scale` and asserts the checker accepts its output; reverting the checker to
  the old formula fails 5 of them.
- ⚠️ **Two adjacent defects found while investigating the above, both still open:**
  (a) **The club ELO chart contradicts the league table.** `currentElo` in `webapp/index.html`
  takes the last point of `teamEloSeries`, which applies `scaledElo` — dispersion and offset but
  **not** `global_elo_adj` — so Liverpool's Global ELO reads **1706** in the EPL table and
  **1643** on its own team chart, a 63-point disagreement on a published figure; Chelsea is 64
  out. 75 clubs carry an adj (up to ±86.3: Liverpool +86.3, Sporting CP −79.4, Real Madrid +65.5)
  and all 75 have a history series. Fixing it needs a product decision first — whether a club's
  shrunk continental adjustment should be carried back across its whole history — so it is not
  bundled here.
  (b) **`Fast Result and Projection Refresh` fails on every run**, and has nothing to do with the
  above: it dies at `Select hourly or in-window leagues`, several steps before
  `validate_payloads` is reached (runs `31284262348`, `31282536199`, `31280813242`, all
  2026-08-08, validator step `skipped`). Separately, `build (mls)` in the nightly has failed
  since at least 2026-08-06 on `403 Forbidden` from
  `site.api.espn.com/.../usa.1/scoreboard`.
- Club Watch season history: the existing History view now consumes the reconstructed early-season
  dataset, preserves exact-archive precedence and point provenance, selects a useful historical
  target when the current target lacks prior coverage, and includes the frozen path in the free
  sample. The public current-season history remains free; Club Watch adds the integrated,
  continuously updated club-season view.
- Approved outcome conversion: meaningful movers, high-leverage match previews,
  one-match scenarios, complete samples, and a real additional-club boundary now
  route into club-specific Club Watch continuation copy without paywalling the
  value just consumed.
- Customer evidence and delivery review: categorized cancellation/support
  reasons, explicit anonymous-testimonial consent, corrected/duplicated/
  suppressed delivery states, bounded shadow-candidate reviews, and automated
  threshold reporting are implemented. Live sends still require the complete
  manual evidence gate and Ryan's separate approval.
- Cross-surface contract: static, interactive, personalized, email, and share
  card paths use tested club, competition, probability, timestamp, generated,
  and snapshot identity fields.
- Club Watch packaging and durable activation: club-first magic-link intent,
  one server-backed free club, one frozen sample, sample-first upgrade, up to ten
  paid clubs, and explicit import of browser favorites.
- Production checkout fail-closed control: owner kill switch, four-Price
  requirement, approved-policy version gates, public readiness state, and
  owner-only lifecycle scorecard.
- Account truth: server-authoritative plan/email/followed clubs/notification
  preferences, billing portal, export, active-paid deletion protection, and
  refresh/private-ledger cleanup on erasure.
- Measurement and lifecycle foundation: canonical funnel and core-value events,
  Stripe purchase/renewal/cancellation/expiration/refund/dunning/recovery state,
  and notification provider delivery events.
- Trust repair: explicit non-football news rejection, word-boundary routing,
  reset/bootstrap diagnostics that suppress ±100pp movers, honest forecast-state
  badges, canonical club-page events, and cross-surface claim tests.
- Operating assets: paid-launch decision record, growth measurement contract,
  experiment ledger, claim matrix, discovery kit, concierge kit, and data/
  notification incident checklist.
- Competition-scoped club acquisition pages: 1,444 self-canonical club forecasts with unique
  metadata, `SportsTeam`/dataset schema, match and season outlooks, league-table links, interactive
  dashboard handoff, and sitemap coverage. Repository verification is green; production deployment
  is still pending.
- Durable league-qualified “since your last visit” Intel cursor.
- Followed-team win/draw/loss stakes cards and timezone-aware match-morning briefings.
- No-refit fast refresh: results and kickoff changes re-simulate tables every 15 minutes in match
  windows and hourly otherwise; fitted-model and market-price clocks remain separate.
- Forecast-first acquisition layer, European breadth landing page, local league aliases, RSS, and
  authenticated opt-in market comparison mode.
- Global Power restored as one ladder, with shared cross-league ELO applied to league tables,
  projection context, team pages, selectors, run-in difficulty, and history charts.
- Paid-path code hardening: case-insensitive headers, fail-closed webhooks, durable webhook retries,
  billing portal support, refund handling, pricing tiers, checkout return handling, and funnel events.

## Non-blocking backlog

These are preserved from the retired UX plans and should not interrupt the transaction milestone:

- Decide whether desktop Home should place volatile content above reference tables.
- Repair the 768–900px tablet layout. Confirmed still broken 2026-08-02: at 820px, 20 of the 100 `.wbox` run-in fixture chips render past the viewport edge inside `.wgroup.wlocked`, which has `overflow-x: visible`, so they are silently clipped rather than scrollable.
- Ratify the type floor and remaining sub-11px exceptions.
- Update the interface contract for the shipped Georgia serif, overlay shadows, and horizontal
  fixture strip—or change the product to match the contract.
- Complete production QA for signed-in Intel, Account, Rankings, PWA-installed mode, landscape,
  and iPad WebKit.
- Add domestic championship-playoff simulation where the published competition format requires it.
- Re-check the Matches to Watch rail once European seasons start 2026-08-21. The "biggest leagues first" ordering was repaired 2026-08-02 by sorting on Global ELO league strength; nine leagues still sit on estimated priors, so the ordering will shift as those firm up.
- Revisit the inter-confederation ELO shifts after the next Club World Cup adds evidence.
- Decide whether `scripts/season_state_report.py` survives the 2026-08-21 European rollover.
  Extracted from the codebase-unification review before that document was retired, because it was
  the script's only inbound reference — deleting the report would have orphaned a live dated
  trigger. It is the sole orphan of 97 scripts, writes only to gitignored `output/`, and is in no
  build path, so it was kept deliberately: it diagnoses exactly the question the rollover raises —
  which leagues still show last season's final table rather than a projection for the new one.
  Keep it if the rollover uses it, delete it if it goes untouched.

## Launch calendar

| Date | Gate |
|---|---|
| By 2026-08-02 | LLC, business bank account, DNS, Upstash, Stripe, production secrets, and legal decisions complete |
| 2026-08-03–09 | Legal pages shipped; first full production transaction |
| 2026-08-10 | Monthly and annual dress rehearsal, including cancellation and refund |
| 2026-08-14 | Content freeze |
| 2026-08-15 | Code freeze; money-path fixes only |
| 2026-08-16 | Production preflight and checkout-disable rehearsal |
| 2026-08-17 | Earliest controlled full-price Club Watch beta; broad launch requires a separate Ryan decision |
| 2026-09-30 | Interim paid-tier keep/change/kill/extend decision using observed transaction, conversion, concierge, and available early-retention evidence; set the definitive D60 review date |

## Launch safety rule

> Defects on the money path abort. Defects elsewhere fix forward.

Checkout must be disabled if the wrong amount is charged, payment succeeds without access, or a
money-path endpoint returns 5xx. Existing entitlements remain in durable storage; disabling new
checkout must not revoke existing access.
