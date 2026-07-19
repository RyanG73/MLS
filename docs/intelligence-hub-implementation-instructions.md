# Entenser Intelligence Hub - Implementation Instructions

**Date:** 2026-07-18  
**Status:** Implementation specification  
**Audience:** Product and engineering  
**Related:** `docs/product-roadmap-2026-07.md`, `docs/CURRENT_STATE.md`,
`docs/projection-drift-tracking.md`

## 1. Product contract

The Intelligence Hub is not a collection of premium charts. It is a personal
monitor that answers four questions for a supporter:

1. What changed for my team?
2. Why did it change?
3. What matters next?
4. What evidence supports that conclusion?

The free product answers **"What does the model think now?"** The Intelligence
Hub answers **"What changed for my clubs, why, what should I watch next, and can
you tell me before I remember to check?"**

The recurring paid loop is:

```text
new result or forecast -> material change detected -> evidence assembled
-> personalized explanation -> hub, alert, or weekly briefing
-> user explores the next consequential scenario
```

Every feature in this document must strengthen that loop. A feature that only
adds another number, chart, or generic news feed does not meet the product bar.

### 1.1 Calendar-mode contract

The Hub must not assume every week is a matchweek. Classify each competition into
one of five operating modes and adapt the experience without requiring manual
editorial work:

| Mode | User question | Hub emphasis |
|---|---|---|
| Active matchweek | What changed? | Events, explanations, alerts, leverage |
| Short lull | What should I watch next? | Team thesis, model watchpoints, scenarios |
| International or scheduled break | What have we learned? | Expectation review, historical context, schedule outlook |
| Offseason | What is changing underneath the forecast? | Report card, priors, promoted teams, modeled input changes |
| Preseason | What should I believe before matches begin? | Baseline forecast, uncertainty, journal checkpoint |

Silence is preferable to fake urgency. Engagement goals must be phase-appropriate:
high-frequency event delivery during active play, one substantial review during a
break, and event-driven or monthly updates during the offseason. Never send an
empty weekly email merely to preserve cadence.

## 2. Non-negotiable rules

1. **One fact, one answer.** The hub, email, alert, Ask Entenser response, export,
   and share card must read from the same computed event and evidence records.
2. **No invented explanations.** All numerical and causal language must be
   generated from structured calculations. An LLM may eventually translate a
   user question into a supported intent, but it may not create figures, causes,
   or unsupported football analysis.
3. **Label attribution honestly.** The current `race-deltas.js` cause values
   (`result`, `model`, and `refresh`) identify the class of change; they do not
   yet prove how many percentage points came from the user's result, rival
   results, or schedule. Do not present those values as a decomposition.
4. **Preserve the free-floor ratchet.** Current public forecasts, match
   probabilities, public grading, and current-season public trajectories remain
   free. Paid value comes from monitoring, personalization, proactive delivery,
   new analyses, private multi-season depth, saved work, and creator tools.
5. **Public trust stays public.** Model health, methodology, aggregate grading,
   and honest misses cannot become subscriber-only. Intel can add personalized
   filtering and historical depth on top.
6. **Private means access-controlled.** A file is not private merely because it
   sits outside `webapp/`. If the repository is publicly readable, private
   archives must not be committed there. Store them in an access-controlled
   deployment artifact or object store approved in the roadmap cost table.
7. **No localStorage security theater.** The current `IntelStore` flag is useful
   for a mockup only. It is not an entitlement system and must never protect
   paid data.
8. **Respect route status.** `live`, `preseason`, `completed`, results-only, and
   historical leagues support different features. Unsupported analyses must
   render a precise unavailable state rather than fabricated or stale output.
9. **Reproducible simulations.** Saved scenarios, explanations, emails, and
   receipts must carry the input snapshot, model configuration, simulation
   version, seed, and run count that produced them.
10. **Do not confuse uncertainty types.** Monte Carlo sampling error, future
    match uncertainty, model uncertainty, and data quality are different. Never
    call a simulation percentile a confidence band unless its coverage has been
    statistically validated.

## 3. Existing assets and known gaps

### Assets to reuse

| Existing asset | Intelligence Hub use |
|---|---|
| `FavStore` in `webapp/index.html` | Local team and league selection; migration source when accounts launch |
| `runSim` / `runSimTable` | Existing what-if behavior; extract into a shared, testable simulation module |
| `leverageScore` | UI heuristic only; useful as a temporary fallback, not the final impact calculation |
| `data/odds_history.parquet` | Current-season team trajectory source |
| `data/match_prob_history.parquet` | Immutable pre-match probabilities and receipt source |
| `webapp/data/drift-traj/<league>.js` | Free current-season trajectory view |
| `webapp/data/movers.js` | Broad movement candidates |
| `webapp/data/race-deltas.js` | Coarse change-class candidates |
| `webapp/data/weekly.js` | Generic recap inputs and public trust receipt |
| `webapp/data/model-slices.js` | Calibration and model-quality context |
| `webapp/data/edge-board.js` | Market-consensus comparison, subject to quiet-middle policy |
| `scripts/build_share_cards.py` | Rendering pattern for evidence-backed conversation cards |
| `scripts/build_static_pages.py` | Public share and archive page pattern |
| `?league=intel` | Demand-test UI prototype only |
| `?league=account` | Preference and favorites prototype only |

### Gaps that block truthful implementation

- No canonical intelligence-event record shared by all delivery surfaces.
- No stable cross-season `team_id` emitted in every payload.
- No archived simulation-state snapshot that can reproduce an old forecast.
- No quantitative decomposition of forecast movement.
- No true fixture impact calculation for the user's target metric.
- No authenticated account, server-side preference store, or entitlement check.
- No private data delivery path.
- No notification deduplication, frequency cap, unsubscribe processing, or send
  ledger.
- No distinction in the current Intel mockup between sample values and live
  values.
- No validated model-uncertainty interval, despite the prototype's
  "confidence bands" wording.
- No competition calendar-mode classifier or quiet-period composition rules.
- No versioned Team Thesis, model-watchpoint, historical-analog, or personal
  forecast-journal records.

## 4. Target architecture

### 4.1 Data flow

```text
league builders
  -> validated league payloads
  -> archive forecast + match + compact simulation state
  -> build canonical intelligence events and evidence
  -> build per-team intelligence snapshots
  -> public-safe payloads OR entitlement-gated private artifacts
  -> hub / alerts / weekly / Ask / exports / conversation cards
```

The nightly build remains the source of truth. Serverless functions should
mostly authenticate, filter, and deliver precomputed results. They should not
fit models or run every league simulation on each request.

Interactive scenarios may run in the browser from the current league state.
Any scenario that is saved, emailed, shared as a receipt, or used by Ask
Entenser must be persisted with reproducibility metadata.

### 4.2 New modules

Use these names unless implementation reveals a strong reason to change them:

| Path | Responsibility |
|---|---|
| `scripts/intelligence/schema.py` | Shared event, evidence, state, and preference schema constants |
| `scripts/archive_intelligence_state.py` | Compact reproducible snapshot of standings, fixtures, probability matrix, rules, and configuration |
| `scripts/build_intelligence_events.py` | Change detection, materiality, event classification, attribution, turning points, and receipts |
| `scripts/build_team_intelligence.py` | Per-team brief, race context, leverage, schedule, confidence, and comparison artifacts |
| `scripts/build_personalized_briefing.py` | Deterministic user-specific weekly assembly |
| `scripts/send_intelligence_notifications.py` | Alert selection, deduplication, caps, sending, and send ledger |
| `scripts/build_intelligence_cards.py` | Public-safe share images and card metadata |
| `webapp/intelligence.js` | Hub state, rendering, question intents, scenarios, and analytics |
| `webapp/intelligence.css` | Hub-specific styles, moved out of the existing monolith |
| `webapp/sim-engine.js` | Extracted deterministic simulation engine used by league and Intel views |
| `api/intel/*.py` | Authenticated read/filter endpoints; exact split can follow Vercel conventions |
| `api/auth/*.py` | Magic-link issue/verify and signed access token refresh |
| `api/stripe/webhook.py` | Stripe entitlement lifecycle |
| `server/intel_auth.py` | Token verification and entitlement middleware |
| `server/intel_store.py` | Preferences, saved scenarios, seen cursors, and send state |

First refactor the current Intel-specific code out of `webapp/index.html` without
changing behavior. Do not use the Hub project as permission to rewrite unrelated
league pages or site chrome.

### 4.3 Stable identifiers

Before building events, introduce identifiers that survive display-name changes:

- `team_id`: canonical club identifier, stable across seasons and divisions.
- `league_id`: existing registry ID.
- `season_id`: explicit competition season, never inferred only from snapshot
  date.
- `fixture_id`: deterministic identifier based on source ID where available;
  otherwise a versioned hash of competition, season, kickoff, home team ID, and
  away team ID.
- `snapshot_id`: league, season, generated timestamp, configuration ID, and
  simulation version.
- `event_id`: stable hash of event type, team, target metric, effective time,
  and evidence references.

Continue carrying display names for rendering, but never join history on names
once IDs exist.

### 4.4 Canonical intelligence-event contract

Store the durable event archive in Parquet and compile JSON for delivery. At
minimum, every event contains:

```json
{
  "schema_version": 1,
  "event_id": "...",
  "generated_at": "2026-07-18T11:00:00Z",
  "effective_at": "2026-07-18T02:00:00Z",
  "snapshot_before_id": "...",
  "snapshot_after_id": "...",
  "league_id": "mls",
  "season_id": "2026",
  "team_id": "...",
  "event_type": "forecast_move",
  "target_metric": "playoff",
  "before_pct": 62.0,
  "after_pct": 39.0,
  "delta_pp": -23.0,
  "materiality_score": 0.91,
  "cause_class": "results",
  "attribution": [
    {"kind": "own_result", "delta_pp": -11.2, "evidence_ids": ["fixture:..."]},
    {"kind": "rival_results", "delta_pp": -7.1, "evidence_ids": ["fixture:..."]},
    {"kind": "schedule_or_state", "delta_pp": -4.4, "evidence_ids": ["state:..."]},
    {"kind": "residual", "delta_pp": -0.3, "evidence_ids": []}
  ],
  "confidence": {
    "status": "supported",
    "data_freshness": "current",
    "attribution_quality": "counterfactual",
    "notes": []
  },
  "config_id": "...",
  "simulation_version": "...",
  "public_safe": true
}
```

All generated prose must be a deterministic rendering of this record and its
linked evidence. Store template IDs and versions with rendered messages so old
receipts can be reconstructed.

### 4.5 Materiality

Do not treat every nightly delta as intelligence. Compute a materiality score
from:

- absolute probability movement;
- threshold crossing, such as 25%, 50%, or 75%;
- change in projected rank or target status;
- fixture impact relative to remaining season uncertainty;
- whether a real result arrived;
- whether the event affects a pinned team or its closest rivals;
- data freshness and model health;
- user threshold and notification frequency settings.

Suppress fan-facing events caused only by harmless build churn. Model-update
events may appear in the audit timeline, but do not send them as football news.
If a configuration change creates a large movement, label it explicitly.

### 4.6 Forecast-movement attribution

The required product promise needs more than the current coarse `cause` field.
Implement attribution in two stages:

1. **Evidence attribution:** identify all own-team results, rival results,
   schedule/source changes, and model/config changes between snapshots.
2. **Counterfactual attribution:** replay the archived pre-change simulation
   state with event groups applied separately. For interacting events, use a
   small Shapley decomposition over the event groups or another order-neutral
   method. Keep an explicit residual.

Acceptance requirements:

- attribution components sum to the observed movement within 0.5 percentage
  points, including residual;
- the calculation uses the same simulation version and deterministic seed;
- if replay is impossible, downgrade to `observational` and say "changed after"
  rather than "caused by";
- source refresh and config change never masquerade as match impact.

### 4.7 Simulation state and reproducibility

Archive a compact state after every successful league build:

- standings and competition rules;
- remaining fixtures and fixture IDs;
- H/D/A probability matrix;
- team-strength inputs needed by the client simulator;
- season target definitions;
- simulation count, seed, version, and uncertainty settings;
- model/config ID and payload generated timestamp;
- source status and freshness.

Do not archive decorative UI fields. Compress snapshots and deduplicate unchanged
large arrays when practical. Add a replay test that reconstructs the published
target probabilities within a documented tolerance.

### 4.8 Authentication, preferences, and entitlements

Replace `IntelStore.unlocked()` with a signed, expiring token verified by every
paid endpoint. The client may cache entitlement state for presentation, but the
server is authoritative.

Store the minimum user record needed:

```json
{
  "user_id": "...",
  "email": "...",
  "plan": "free|trial|intel|creator|canceled",
  "teams": [{"team_id": "...", "league_id": "..."}],
  "leagues": ["mls"],
  "targets": [{"team_id": "...", "metric": "playoff"}],
  "notifications": {"weekly": true, "material_change": true},
  "threshold_pp": 5,
  "timezone": "America/New_York",
  "last_seen_event_id_by_team": {},
  "unsubscribe_state": {}
}
```

On first authenticated use, offer to merge existing `FavStore` and `AcctStore`
state. Never overwrite server preferences silently. Provide export and deletion.

### 4.9 Public versus paid delivery

| Surface | Access rule |
|---|---|
| Current league tables, forecasts, match probabilities | Free |
| Current-season trajectory charts already in public payloads | Free |
| Aggregate model health and grading | Free |
| Generic weekly recap | Free when sending is explicitly approved |
| Personalized team brief and "since last visit" feed | Intel |
| Material-change and threshold alerts | Intel |
| Advanced leverage, path, and rival analysis | Intel |
| Team Thesis, model watchpoints, and personalized break/offseason mode | Intel |
| Multi-season time machine, historical analogs, and searchable personalized receipts | Intel |
| Personal Forecast Journal | Intel; private by default |
| Consensus/market comparison | Intel, login-only, quiet-middle rules |
| Public-safe conversation card URL | Publicly viewable; creation may require Intel |
| Bulk exports and creator packaging | Creator or separately gated Intel benefit |

Do not ship paid JSON under `webapp/data/`; browser-visible static files cannot be
protected by CSS, route guards, or obfuscated names.

## 5. Shared implementation sequence

Complete these foundations before feature work diverges:

### S0. Protect the historical flywheel — **done 2026-07-18**

- Finish roadmap actions F-1 through F-5. **Done.**
- Add `data/match_prob_history.parquet` to every relevant workflow commit step. **Done.**
- Add the private multi-season trajectory archive. **Scope adjustment:**
  `data/odds_history.parquet` already accrues every snapshot indefinitely and is
  already committed, so it already serves as the private multi-season archive —
  a second file would have duplicated those rows. The real gap was on the public
  side (see next item), which is what actually got fixed.
- Archive race-delta and weekly records instead of overwriting the only copy. **Done**
  (`data/race_deltas_history.parquet`, `data/weekly-archive/<date>.json`), plus
  the public trajectory files (`webapp/data/drift-traj/<league>.js`) are now
  season-bounded so a rollover can't leak prior-season rows.
- Add growth, deduplication, active-season, and accidental-publication tests. **Done**
  (`scripts/validate_history_growth.py`, wired into both refresh workflows before
  the commit step).

See `docs/PROJECT_HISTORY.md` "Intelligence Hub S0" for the full outcome summary.

### S1. Add stable IDs and season fields — **done 2026-07-18, MLS pilot only**

- Emit IDs from all league builders and normalize existing records during read.
  **Done for MLS**; other leagues deferred — see below.
- Backfill aliases carefully; do not invent cross-season identity where clubs
  cannot be matched confidently. **N/A for this pass** — MLS's `team_id` reuses
  ASA's own existing stable identifier rather than inventing new cross-season
  identity, so there was nothing to backfill or alias.
- Extend `validate_payloads.py` and archive tests. **Done** — `validate_payloads.py`
  gates the MLS payload on `team_id`/`home_id`/`away_id`/`fixture_id` presence;
  both new IDs are additive columns in `data/odds_history.parquet` and
  `data/match_prob_history.parquet`.

**Scoped to the MLS pilot league only.** `league_id` and `season_id` already
satisfied this section as-is (both explicit, source-derived, never inferred from
a snapshot date) — no changes were needed. `team_id` and `fixture_id` are real
for MLS now; generalizing to the other leagues in the registry is separate
follow-on work, since each sources team names from a different upstream
(football-data.co.uk, API-Football, ESPN-only) with no equivalent stable-ID
field yet — not a mechanical repeat of this pass. See `docs/PROJECT_HISTORY.md`
"Intelligence Hub S1" for the full outcome summary.

### S2. Extract and version simulation behavior — **done 2026-07-18**

- Move common browser simulation logic into `webapp/sim-engine.js`. **Done** —
  both `runSim` (MLS) and `runSimTable` (all single-table leagues) ported, not
  just one format; the duplicated code already existed side by side in the
  same file, so unifying only one would have defeated the point.
- Preserve current league-page behavior with characterization tests before adding
  Intel calculations. **Done** — Node-based characterization tests (no npm/jest;
  the repo has no JS build tooling, so these use only Node's built-in `assert`,
  wrapped by a pytest shim) plus live browser verification against the real
  running site for both league formats. No Intel-specific calculations were
  added in this pass.
- Add a deterministic PRNG and explicit seed. **Done** — a seeded PRNG
  (mulberry32) threaded through *every* random draw in both formats, including
  the MLS playoff bracket and the promotion-playoff bracket, so a seeded run
  is fully reproducible end-to-end; an unseeded call preserves today's
  behavior exactly (a fresh seed drawn each time).
- Return simulation metadata and Monte Carlo standard error with each result.
  **Done** — additive `_meta` (engine version/n/seed) and per-metric `_se`
  fields on both `runSim` and `runSimTable` output.

See `docs/PROJECT_HISTORY.md` "Intelligence Hub S2" for the full outcome summary.

### S3. Archive reproducible simulation states — **done 2026-07-18, MLS pilot only**

- Implement `archive_intelligence_state.py`. **Done** — extracts standings,
  `sim.pmatrix`/team order, upcoming fixtures (by S1 `fixture_id`), rules, and
  provenance; a replay test against the real MLS payload confirms the
  archived state reconstructs 6 of 7 published targets within a documented,
  investigated tolerance (`cup` excluded — needs the MLS playoff bracket,
  which stays client-page-specific).
- Run it after payload validation and before building intelligence events.
  **Done** — wired into `refresh-daily.yml` after `validate_payloads.py` and
  `validate_history_growth.py`.
- Fail closed when required inputs are missing; do not archive a partial state as
  healthy. **Done** — `MissingRequiredInput`, unit-tested for every required field.

**Compliance note:** this repo is public (confirmed via `gh repo view`), and
rule 6 above prohibits committing private archives to a public repo, so
`data/intelligence_snapshots/` is gitignored rather than committed — the
archiver runs and validates on every build regardless, but durable storage
awaits S5's access-controlled infrastructure. See `docs/PROJECT_HISTORY.md`
"Intelligence Hub S3" for the full outcome summary, including a real
methodology gap (server-side "strength-uncertainty widening") this work
uncovered in the pre-existing browser what-if simulator.

### S4. Build canonical intelligence events — **done 2026-07-18, MLS pilot only**

- Start with movement, threshold-crossing, result, model-change, and data-health
  events. **Done** — all five implemented in `scripts/build_intelligence_events.py`.
- Add evidence links and attribution quality. **Done, observational only** —
  `attribution_quality` is `"observational"` or `"unavailable"`, never
  `"counterfactual"` (that needs S3's archived states to accrue enough
  history to replay against, which is separate follow-on work).
- Append to a durable archive with stable deduplication keys. **Done** —
  `data/intelligence_events.parquet`, deduped on `event_id`.
- Compile current per-team snapshots for fast API delivery. **Done** —
  `data/intelligence_events_latest.json`, recomputed from the full archive
  each run.

**Architecture note:** deliberately reads `data/odds_history.parquet` /
`data/match_prob_history.parquet` (S0/S1, already public) rather than S3's
`data/intelligence_snapshots/` (private, gitignored, empty on every fresh CI
checkout). This keeps the event archive itself derived only from already-
public data, so — unlike S3 — it's committed to the repo, giving it real
persistence across CI runs. See `docs/PROJECT_HISTORY.md` "Intelligence Hub
S4" for the full outcome summary.

### S5. Build secure delivery — **done 2026-07-18, code + mocked tests only**

- Implement magic-link auth, token verification, Stripe entitlements, preference
  storage, and rate limits. **Done** — `server/intel_auth.py`, `server/intel_store.py`,
  `server/rate_limit.py`, `server/stripe_webhook.py`.
- Add a single entitlement middleware used by all Intel endpoints. **Done** —
  `require_entitlement()`, demonstrated by the one representative endpoint
  this pass builds (`api/intel/me.py`); further Intel endpoints reuse it as
  they're built.
- Ensure expired, canceled, and trial users receive correct states. **Done** —
  the middleware always re-checks the *current* plan from a live lookup,
  never a token's embedded plan claim, so a canceled subscription is
  correctly rejected even with a still-valid access token.

**Scope confirmed with the user before starting:** code and mocked tests
only — no Vercel project, Stripe account, Resend account, or Upstash Redis
instance exists or was created by this work. Every module is written
against clean interfaces (`KVStore`, `MagicLinkSender`) with in-memory/
recording test doubles; swapping in real Upstash Redis / Resend / Stripe
later is a small, isolated change, not a rewrite. See
`docs/PROJECT_HISTORY.md` "Intelligence Hub S5" for the full outcome
summary.

### S6. Replace the mockup with live data progressively

- Keep the current Intel screen as a labeled preview while no live endpoint exists.
- Remove every hard-coded percentage before labeling a panel live.
- Replace panels one at a time and display a `sample`, `live`, `thin history`, or
  `unavailable` state.

### S7. Add delivery controls and observability

- Maintain an alert send ledger with event ID, recipient, template version,
  provider ID, and delivery status.
- Add deduplication, frequency caps, retries, and provider webhook processing.
- Track hub activation, brief opens, scenario completion, alert click-through,
  and 30/90-day retention without logging sensitive question text by default.

### S8. Run a shadow period

- Generate events, briefs, and alerts without sending for at least two full
  matchweeks.
- Review false positives, source-refresh events, decomposition residuals, and
  repeated notifications.
- Require owner sign-off before enabling scheduled email sends.

## 6. Feature implementation instructions

### 1. Team Intelligence Brief

**User outcome:** Understand the team's season state in under one minute.

**Build:**

- Lead with one target appropriate to the team and competition: title, top-N,
  playoffs, promotion, or relegation. Allow the user to pin a different target.
- Show current probability, seven-day change, projected finish/points, model
  freshness, the largest evidence-backed driver, and the highest-impact next
  fixture.
- Add a one-sentence deterministic summary assembled from event records. Avoid
  generic form commentary.
- Include links into Why It Changed, Match Leverage Radar, and Scenario Explorer.
- During a short lull or scheduled break, replace the matchweek lead with the
  current Team Thesis, the most important unresolved question, and the next
  evidence that could change the forecast.
- During offseason and preseason, lead with the next-season baseline, changes
  since the prior final forecast, and the current uncertainty state.
- Build the result in `build_team_intelligence.py`; the API should filter and
  return it rather than recompute it.

**Acceptance:**

- Every number resolves to a snapshot or event ID.
- The selected target is valid for the league's rules and status.
- A results-only or completed league receives an explicit reduced brief.
- Mode transitions are driven by schedule/status evidence and do not require a
  manual deployment.
- The brief fits without horizontal overflow at 375px and does not shift while
  asynchronous sections load.

### 2. Since You Last Checked Feed

**User outcome:** See only new, meaningful information.

**Build:**

- Store a per-team last-seen event cursor locally for anonymous previews and in
  the user preference store for authenticated members.
- Return events after the cursor, sorted by materiality and then time.
- Group multiple events from the same build into one story when they explain the
  same movement.
- Include `Mark all seen` and per-team seen behavior. Opening one card must not
  mark unrelated team events seen.
- On a new device, initialize from the server cursor. On first use, show the most
  material seven-day events rather than the entire archive.
- When no material event exists, do not manufacture a feed card. Render a
  `What the model is watching` state from Feature 23 and link to the current Team
  Thesis, upcoming leverage, or the relevant break/offseason view.

**Acceptance:**

- Refreshing does not resurrect seen events.
- Duplicate build retries do not create duplicate cards.
- Model/config updates are labeled and excluded from football-result language.
- A quiet period produces a useful watch state without incrementing the unseen
  event count.
- Cursor merge behavior is covered by tests for multiple devices.

### 3. Why It Changed

**User outcome:** Explain a forecast movement with quantified evidence.

**Build:**

- Render the canonical event's before, after, total delta, attribution bars, and
  linked evidence.
- Separate own result, rival results, schedule/state, model update, and residual.
- Show attribution quality: `counterfactual`, `observational`, or `unavailable`.
- For each match evidence item, show the pre-match probability and result so the
  user can understand whether it was surprising.
- Use cautious language when attribution is observational.

**Acceptance:**

- Components reconcile to the total movement within 0.5 percentage points.
- No explanation is emitted without evidence references.
- A source refresh cannot be described as a football cause.
- Snapshot replay and attribution tests cover single-result, multiple-result,
  model-change, and mixed-event windows.

### 4. Match Leverage Radar

**User outcome:** Know which upcoming match can move the team's season most.

**Build:**

- Evaluate every relevant upcoming fixture by forcing H/D/A outcomes against the
  same archived simulation state.
- Include the user's own fixtures and rival fixtures that materially affect the
  chosen target.
- Define displayed leverage as the range between the best and worst conditional
  target probabilities. Also compute expected movement using baseline H/D/A
  probabilities.
- Cache the top fixtures per team and metric nightly. Recompute interactively only
  when the user changes target or scenario assumptions.
- Replace or clearly distinguish the current UI `leverageScore`, which is a
  sorting heuristic rather than a probability-impact calculation.

**Acceptance:**

- Outcome labels are from the watched team's perspective where appropriate.
- Re-running with the same state and seed reproduces values within tolerance.
- Fixtures with missing forecasts are excluded with an explained coverage note.
- A rival fixture can outrank the user's own fixture when the calculation supports
  it.

### 5. Scenario Explorer

**User outcome:** Test a small set of future results and see the season respond.

**Build:**

- Support forcing H/D/A for multiple future fixtures, undo/redo, reset, and a
  clear count of active assumptions.
- Use the extracted simulation engine; do not maintain separate league and Intel
  implementations.
- Show baseline versus scenario for the user's target, projected rank/points, and
  the nearest rivals.
- Encode free current-session scenarios in a versioned URL. Saved cross-device
  scenarios require authentication and store snapshot/version metadata.
- Warn when the scenario was created from an old snapshot and offer to rebase it.
- Show Monte Carlo noise or suppress changes smaller than the simulation's
  reliable display precision.

**Acceptance:**

- Reset reproduces the baseline.
- URL decoding validates fixture IDs, season, league, and outcome values.
- Stale or removed fixtures fail safely.
- Simulation behavior matches existing league what-if behavior before rollout.

### 6. Path to the Goal

**User outcome:** See realistic routes to a chosen season objective.

**Build:**

- Let the user select a target and threshold, such as `playoff >= 70%` or
  `relegation <= 20%`.
- Search combinations among the highest-leverage upcoming own and rival fixtures.
  Use a bounded beam search, not exhaustive enumeration.
- Return up to three distinct paths: shortest, most probable, and a rival-dependent
  alternative.
- Each path must list assumptions, approximate joint likelihood, resulting target
  probability, and snapshot time.
- Do not describe a path as sufficient or required unless every remaining outcome
  has been mathematically enumerated under the competition rules.

**Acceptance:**

- Every displayed path can be opened in Scenario Explorer and reproduces its
  result.
- The search has strict time and fixture-count bounds.
- Impossible targets return a useful explanation, not an empty spinner.
- Conditional and approximate language is explicit.

### 7. Smart Alerts

**User outcome:** Learn about consequential changes without receiving noise.

**Build:**

- Support material-move, threshold-crossing, clinch/elimination, and critical-match
  alerts. Market-consensus alerts remain off by default and follow quiet-middle
  rules.
- Default to conservative thresholds and a maximum of one non-urgent alert per
  team per 24 hours.
- Group related team and rival events into one message.
- Never send pure refresh/churn events. Suppress during unhealthy pipeline states.
- Include before/after, why, what matters next, data timestamp, and a deep link.
- Implement one-click unsubscribe, per-category controls, bounce handling, and a
  send ledger before the first live send.

**Acceptance:**

- Re-running the job cannot resend the same event to the same user.
- Trial, canceled, unsubscribed, and bounced recipients are handled correctly.
- Shadow-mode fixtures prove rate caps and grouping.
- Every email figure matches the linked hub event.

### 8. Personalized Weekly Briefing

**User outcome:** Arrive at the weekend knowing the important story around each
followed team.

**Build:**

- Assemble from canonical events, leverage records, turning points, and public
  receipts. Do not personalize by merely filtering the generic weekly payload.
- Recommended sections: team pulse, what changed, why, match to watch, rival watch,
  one model receipt, and scenario prompt.
- Rank followed teams by materiality while guaranteeing at least a concise row for
  every followed team with active forecasts.
- Use adaptive cadence: weekly during active play, one substantive report during a
  scheduled break, and event-driven or at most monthly communication during the
  offseason. Preseason gets a baseline edition when a valid schedule and forecast
  exist.
- Skip the send when there is no material personalized content and no scheduled
  phase report. A skipped send is a healthy outcome, not a pipeline failure.
- Produce HTML and plain-text versions from the same structured brief.
- Archive the rendered template version and event IDs used in every send.

**Acceptance:**

- Zero-followed-team users receive the generic edition only if they subscribed to
  it.
- No section repeats the same event under different wording.
- Cadence selection is deterministic from the competition mode and send ledger;
  users following multiple calendars receive one grouped message, not one email
  per league.
- Snapshot dates and deep links survive email forwarding.
- Owner approval remains a hard gate before scheduling sends.

### 9. Race Context

**User outcome:** Understand who actually threatens or helps the team's objective.

**Build:**

- Identify relevant rivals by target-probability proximity and counterfactual
  sensitivity, not only table position.
- Show the top threats, opportunities, probability gap, remaining head-to-heads,
  and the rival result with the largest expected effect.
- Distinguish direct competitors from schedule dependencies.
- Recompute context for each supported target because title rivals and relegation
  rivals are different sets.

**Acceptance:**

- Every rival has an evidence-backed inclusion reason.
- Race context updates after results and target changes.
- Split-table, conference, playoff, and promotion formats use their actual rules.
- The section degrades cleanly when no meaningful rival exists.

### 10. Expectation Versus Performance

**User outcome:** Distinguish strong underlying performance from fortunate or
unfortunate results.

**Build:**

- Freeze the latest valid pre-kickoff model snapshot for each completed match.
- Compute expected points as `3 * P(win) + P(draw)` and compare with actual points
  over season, last five, and last ten where sample size permits.
- Add xG-based context only for leagues with validated xG coverage. Label goals-only
  leagues accordingly.
- Show direction and magnitude without declaring luck as a fact. Use wording such
  as "results are running ahead of pre-match expectation."
- Separate model expectation from market expectation when both are displayed.

**Acceptance:**

- No post-match probability is used as a pre-match expectation.
- Voids, postponed matches, and duplicate fixtures are excluded correctly.
- Small samples carry a warning.
- Calculations are unit-tested against hand-worked match examples.

### 11. Forecast Time Machine

**User outcome:** See what the model believed at any point and what changed next.

**Build:**

- Keep the existing current-season public trajectory free.
- Add event annotations for matches, config changes, threshold crossings, and
  turning points.
- Serve private multi-season trajectories and match-level history only through an
  entitlement-gated endpoint.
- Support season and metric selection, compare mode, and links to immutable
  receipts.
- Downsample only for rendering; preserve full-resolution downloadable history in
  the private archive.

**Acceptance:**

- Public trajectory payloads contain only the active season.
- Private history is not browser-discoverable without authorization.
- Season boundaries, promoted/relegated division changes, and team aliases render
  correctly.
- Config markers are visible and explained.

### 12. Consensus Disagreement

**User outcome:** Know where Entenser's view differs materially from a credible
external benchmark.

**Build:**

- Use normalized no-vig market probabilities already captured by the system as the
  first benchmark. Do not scrape competitor forecasts without permission.
- Show model probability, consensus probability, gap, timestamp, book/source
  coverage, and historical calibration context.
- Use neutral language: "more optimistic than consensus," not "the market is
  wrong" or "value bet."
- Keep this feature login-only, out of SEO, announcements, and public share cards
  under the quiet-middle policy.
- Preserve the standing rule that low-skill outright categories are not promoted
  before the validated season-progress gate.

**Acceptance:**

- Stale or single-source consensus is clearly labeled or suppressed.
- Market timestamps and normalization method are available.
- No betting recommendation is generated.
- Licensing and responsible-gambling review is complete before launch.

### 13. Schedule Difficulty Outlook

**User outcome:** Understand how the remaining fixture list changes the race.

**Build:**

- Compute opponent strength, home/away mix, rest, travel, and congestion only where
  those inputs are available and validated.
- Report relative difficulty against the league and selected rivals, not an opaque
  universal score.
- Show the hardest run, easiest run, and how much schedule contributes to current
  target probability.
- Prefer model-implied fixture probabilities over a hand-built strength formula.

**Acceptance:**

- Difficulty updates when fixtures, venues, or team strengths change.
- Postponed and unscheduled fixtures are handled explicitly.
- Cross-league scores are not compared unless calibrated onto the same scale.
- Users can inspect the fixtures behind every summary.

### 14. Critical Date Calendar

**User outcome:** Know when the season is likely to turn.

**Build:**

- Start with fixture-derived dates: high-leverage matches, head-to-heads, congested
  runs, possible clinch/elimination windows, and competition-stage transitions.
- Add transfer windows, international breaks, or other external dates only after a
  licensed and maintained calendar source is approved.
- Provide calendar and agenda views in the user's timezone.
- Allow an event to be added to a personal calendar only through an explicit user
  action.

**Acceptance:**

- Every generated date cites its fixture or rules evidence.
- Kickoff changes update the calendar without duplicating events.
- Dates with insufficient schedule publication are labeled tentative.
- Timezone and daylight-saving behavior is tested.

### 15. Model Confidence and Fragility

**User outcome:** Understand how much weight to place on the forecast and how
easily it can move.

**Build:**

- Present separate indicators for data freshness, source coverage, historical
  calibration, projection stability/churn, season progress, and scenario fragility.
- Define fragility as sensitivity to plausible near-term results, using leverage
  calculations. A forecast can be 55% and stable or 55% and highly fragile.
- Use `model-slices.js`, `drift.js`, source-health data, and season-outcome
  validation to support labels.
- Remove "confidence band" language from live UI unless an ensemble/bootstrap
  interval is implemented and its empirical coverage is validated.

**Acceptance:**

- The UI never collapses the indicators into an unexplained pseudo-precision
  score.
- Poor freshness or coverage lowers the displayed confidence state.
- Model changes and unexplained churn are visible.
- Labels have documented thresholds and tests.

### 16. Ask Entenser

**User outcome:** Ask natural questions without learning the product's navigation.

**Build:**

- Implement a finite intent catalog first: current state, why changed, scenario,
  next high-impact match, rival importance, path to target, schedule difficulty,
  historical comparison, and receipt lookup.
- Prefer suggested questions and structured controls. A natural-language parser may
  map text to an intent and entities, but calculation functions supply all answers.
- Return an answer object containing intent, parameters, result data, snapshot ID,
  evidence IDs, and suggested follow-ups before rendering prose.
- Reject unsupported questions plainly and offer the nearest supported intents.
- Do not send raw private question text to analytics or third-party models by
  default.

**Acceptance:**

- Golden tests cover paraphrases, ambiguous teams, missing seasons, and unsupported
  requests.
- Every numerical statement has evidence and snapshot metadata.
- The same intent returns the same answer as the corresponding hub panel.
- Prompt injection cannot grant data access or change entitlement checks.

### 17. Turning-Point Detection

**User outcome:** Identify the moments that most altered the team's season.

**Build:**

- Rank result-driven intelligence events by absolute target-probability movement.
- Separate own-team turning points from rival-driven turning points.
- Exclude pure config and refresh movements from the football turning-point list,
  while retaining them in the audit timeline.
- Allow metric and season selection. Annotate the time-machine chart.

**Acceptance:**

- Every turning point opens its Why It Changed record and receipt evidence.
- Ties and clustered same-day results are grouped coherently.
- Ranking is reproducible from the event archive.
- The feature works with fewer than five events without padding the list.

### 18. Prediction Receipts

**User outcome:** Verify what the model said before the outcome was known.

**Build:**

- Preserve an immutable pre-kickoff snapshot selected by a documented cutoff rule.
- Store H/D/A probabilities, season-target probabilities when relevant, config ID,
  generated time, source freshness, eventual result, and scoring outcome.
- Keep aggregate and current public grading free. Intel adds team-filtered search,
  multi-season history, and links from personalized events.
- Never rewrite old predictions after a model update. Corrections append a labeled
  correction record.

**Acceptance:**

- Receipts are timestamped before kickoff.
- A rebuild after the result cannot alter the frozen prediction.
- Postponements and kickoff changes select the correct cutoff snapshot.
- Public hit/miss summaries reconcile with underlying receipts.

### 19. Rival Comparison Mode

**User outcome:** Compare the user's team with the rival that matters to the chosen
objective.

**Build:**

- Support manual rival choice and a recommended rival from Race Context.
- Compare target probability, projected points/rank, trajectory, remaining schedule,
  expected-versus-actual performance, model confidence, and mutual dependencies.
- Highlight direct fixtures and the next external result most likely to change the
  gap.
- Keep visual scales identical between teams.

**Acceptance:**

- Comparisons only use compatible metrics and competition rules.
- Missing xG or market data does not block the rest of the comparison.
- Deep links preserve both teams, target, season, and snapshot.
- Mobile layout remains readable without side-by-side text compression.

### 20. Conversation Cards

**User outcome:** Share a defensible insight rather than a context-free percentage.

**Build:**

- Generate cards from approved event types: material move, highest-leverage match,
  turning point, race comparison, or receipt.
- Include team/league, insight, before/after or impact number, data date, Entenser
  branding, and a short public verification URL.
- Use `build_share_cards.py` patterns for server-generated assets. A client preview
  may use Canvas, but the canonical shared asset must be deterministic and tested.
- Strip private preferences and paid-only archive details from the public card
  payload. The verification page may show the public-safe evidence and upsell the
  deeper hub.

**Acceptance:**

- Every card has a public-safe evidence record.
- Long team names fit at required social dimensions.
- Card values match the linked verification page.
- Generated assets pass visual regression checks at all supported templates.

### 21. Creator Mode

**User outcome:** Give podcasters, newsletter writers, fan accounts, and beat
reporters publication-ready research with provenance.

**Build:**

- Add a workspace for selecting teams, metrics, date ranges, comparisons, and card
  templates.
- Export chart images, public-safe tables, CSV where licensed, and a concise set of
  evidence-backed briefing notes.
- Include source, generated timestamp, methodology link, and suggested citation in
  every export.
- Support saved workspaces and reusable presets only after authenticated persistence
  is stable.
- Treat API, embeds, and high-volume exports as a separate pricing/licensing decision,
  not an automatic $5.99 entitlement.

**Acceptance:**

- Creator output never contains unsupported prose or private user data.
- Exported numbers reconcile with the hub and receipts.
- Data-source licenses permit every included field and use case.
- Rate limits and file-size limits protect the solo-operated backend.


### 22. Team Thesis

**User outcome:** Retain a clear, evidence-backed understanding of what the model
currently believes about the team even when no recent match has moved the forecast.

**Build:**

- Maintain a versioned thesis containing the team's primary strength, primary
  weakness, sustainability assessment, current season expectation, largest
  unresolved uncertainty, and the evidence supporting each statement.
- Generate thesis claims from structured model inputs, expectation-versus-
  performance records, schedule context, confidence state, and canonical events.
  Do not add generic football commentary to fill space.
- Update the thesis only when a claim, evidence set, or confidence state changes
  materially. Preserve the previous version and a structured change reason.
- Show `What changed in the thesis` when a new version replaces the old one.
- Use the thesis as the quiet-period lead in the Team Intelligence Brief and as
  context for Ask Entenser answers.

**Acceptance:**

- Every claim resolves to evidence IDs and a documented deterministic rule.
- An unchanged thesis retains its original effective date and does not create a
  fake new event.
- Missing xG, roster, or availability data removes only the affected claim.
- Thesis changes can be reconstructed and compared across the season.

### 23. What Would Change the Model's Mind?

**User outcome:** Know what future evidence would materially alter the team's
forecast before that evidence arrives.

**Build:**

- For the selected target, calculate the smallest plausible near-term result sets
  that cross a meaningful threshold or move the forecast by the user's configured
  amount.
- Include own fixtures, high-impact rival fixtures, and measurable performance or
  strength assumptions only when the production model actually consumes them.
- Produce watchpoints such as `two wins from the next three`, `a loss in the direct
  rival fixture`, or `the next three-match away run`. Every watchpoint opens a
  reproducible Scenario Explorer state.
- Rank watchpoints by imminence, plausibility, and forecast impact. Keep no more
  than three active watchpoints per team and target.
- Do not imply that a result guarantees a season outcome. State the conditional
  forecast and snapshot on which the watchpoint is based.
- Power the quiet state in Since You Last Checked with these watchpoints rather
  than low-materiality events.

**Acceptance:**

- Every result-based watchpoint reproduces in Scenario Explorer within simulation
  tolerance.
- Unsupported player, manager, or tactical claims are never generated.
- Watchpoints expire or rebase after the underlying fixture or snapshot changes.
- Impossible or highly implausible thresholds return a clear explanation.

### 24. Historical Analogs and Club Baselines

**User outcome:** Understand the current season in the context of relevant past
teams and the club's own history.

**Build:**

- Compare the current team with prior seasons using season progress, points,
  projected target probability, team strength, expected-versus-actual performance,
  promoted status, and league family where available.
- Provide two views: the club's own historical baseline and a small set of similar
  teams from comparable competitions.
- Publish the matching dimensions, distance method, sample size, and outcome rate.
  Do not present a colorful anecdote as a statistically representative analog.
- Prevent future leakage: analog matching at a historical checkpoint may use only
  information that existed by that checkpoint.
- Keep current-season public history free; multi-season analog search uses the
  private archive and is entitlement-gated.

**Acceptance:**

- Every analog can be opened at the exact historical checkpoint used for matching.
- Selection is deterministic and covered by fixtures with known nearest matches.
- Sparse or structurally incompatible samples are labeled or suppressed.
- Outcome summaries disclose sample size and never imply causation.

### 25. Break and Offseason Intelligence Mode

**User outcome:** Receive a useful, appropriately paced product when the competition
is paused, completed, or preparing for a new season.

**Build:**

- Add a calendar-mode classifier using competition status, published fixtures,
  days since last match, days to next match, and known competition-stage rules.
- During scheduled breaks, assemble a state-of-the-team review: Team Thesis,
  performance versus expectation, unresolved question, remaining schedule, rival
  comparison, and what to watch when play resumes.
- During offseason, show the final forecast report card, first valid next-season
  prior, promoted/relegated-team strength adjustments, schedule-publication
  changes, and an offseason change ledger.
- The offseason ledger separates `observed development`, `model input changed`,
  and `forecast impact calculated`. Do not attach numerical impact to a transfer,
  manager change, or roster report unless the production model consumes a
  validated input representing it.
- Add transfer windows, international breaks, and roster events only from approved,
  maintained, and license-compatible sources.
- Automatically return to active-matchweek mode when live competition resumes.

**Acceptance:**

- Mode classification is deterministic and tested for calendar-year, split-season,
  winter-break, tournament, completed, and unpublished-schedule competitions.
- No active league is left in offseason mode after a valid fixture/result arrives.
- Offseason forecast changes distinguish data, model, and competition-structure
  causes.
- Email cadence follows the calendar-mode contract and never creates empty weekly
  editions.

### 26. Personal Forecast Journal

**User outcome:** Record personal beliefs, compare them with Entenser, and learn
where the user's judgment is strong or systematically biased.

**Build:**

- Let users record predicted finish, target-probability estimate, confidence, and
  private notes at preseason and optional monthly checkpoints.
- Timestamp and freeze each checkpoint. Later edits create a new version rather
  than rewriting the original belief.
- Compare the user's probabilities with Entenser and eventual outcomes using proper
  scoring and calibration summaries after enough observations exist.
- Show changes in the user's view beside changes in the model without framing the
  exercise as a competition the model must win.
- Keep journal entries private by default. Require an explicit action to create a
  public-safe share card from an entry.
- Include journal data in account export and deletion behavior.

**Acceptance:**

- A checkpoint cannot be backdated or silently edited after the relevant event.
- Scoring uses the probability recorded before the outcome was known.
- Small samples do not receive a misleading skill rank or definitive bias label.
- Private notes never appear in analytics, emails, exports, or share cards unless
  explicitly selected by the user.


## 7. Feature dependencies and release order

| Release | Features | Required foundation | Purpose |
|---|---|---|---|
| Foundation | none visible | S0-S8 | Make every later claim reproducible and secure |
| MVP 1 | 1, 2, 3, 4, 22, 23, 25 | Events, evidence, team brief, leverage, calendar mode | Establish active and quiet-period value together |
| MVP 2 | 5, 7, 8 | Shared simulator, auth, preferences, delivery controls | Create recurrence and proactive value |
| Depth 1 | 9, 10, 11, 13, 15, 17, 18, 19, 24, 26 | Accrued history, receipts, race calculations, user checkpoints | Make the hub analytically and personally defensible |
| Depth 2 | 6, 14, 16 | Stable scenarios, calendar inputs, intent service | Add planning and interrogation |
| Distribution | 20 | Public-safe evidence and image pipeline | Let paid insight travel publicly |
| Professional | 21 | Export licensing, rate limits, saved workspaces | Serve creators without bloating the supporter tier |

Do not implement in numerical order merely because the features are numbered.
Feature 3 depends on state archival and attribution; Feature 7 depends on delivery
safety; Feature 16 depends on most calculation services already existing. Features
22, 23, and 25 belong in MVP 1: shipping the event-heavy experience without the
quiet-calendar behavior would leave the central engagement risk unresolved.

## 8. Milestone plan

### Milestone A - Data integrity and live prototype

- Finish history protection and stable IDs.
- Extract/version the simulator.
- Create state and event archives.
- Replace the Team Brief, Since Last Checked, Why It Changed, Leverage, Team
  Thesis, and model-watchpoint demo panels with live data for one pilot league.
- Implement calendar-mode classification for that pilot and test both active and
  quiet-period rendering.
- Keep all other panels visibly labeled as previews.

**Exit:** one team in one league can be reconstructed from archived input through
hub explanation with no hard-coded data, and the same team has a useful quiet state
when no material event exists.

### Milestone B - Multi-league Intel MVP

- Generalize features 1-5, 22, 23, and 25 across all full-forecast leagues.
- Add auth, preferences, entitlements, and safe private delivery.
- Run alert and adaptive briefing shadow mode.
- Add instrumentation and operational dashboards.

**Exit:** a trial user can follow teams, receive a correct personalized hub, run a
scenario, see exactly why a material change occurred, and still receive a useful
team thesis and watchpoints during a lull.

### Milestone C - Paid recurrence

- Enable features 7 and 8 after explicit send approval.
- Add deduplication, frequency caps, provider webhooks, and unsubscribe operations.
- Measure alert usefulness, briefing clicks, and four-week returning use.

**Exit:** at least two matchweeks and one quiet-mode cycle run without duplicate,
stale, empty, misleading, or unexplained notifications.

### Milestone D - Analytical depth

- Add features 9-15, 17-19, 24, and 26 as history becomes sufficient.
- Validate every league-format and calendar-mode branch.
- Add multi-season time machine and historical analogs only after privacy,
  future-leakage, and season-boundary tests pass.

**Exit:** every analytical claim has evidence, coverage state, and a reproducible
calculation.

### Milestone E - Interrogation and creator tools

- Add Ask Entenser over the established intent functions.
- Add conversation cards and public verification pages.
- Pilot Creator Mode with a small number of actual creators before deciding API,
  embed, or higher-tier pricing.

**Exit:** creators can publish an Entenser insight and readers can verify it without
needing access to the creator's private account.

## 9. Testing requirements

### Unit tests

- Stable IDs and fixture deduplication.
- Materiality and threshold crossing.
- Attribution reconciliation and residual handling.
- Leverage and path calculations on hand-built small leagues.
- Expected-points calculations.
- Receipt cutoff selection.
- Intent parsing and answer objects.
- Preference merging and entitlement states.
- Alert grouping, caps, deduplication, and unsubscribe logic.
- Calendar-mode classification across competition formats.
- Team Thesis claim selection and versioning.
- Model-watchpoint generation, expiry, and scenario reproduction.
- Historical-analog matching without future leakage.
- Forecast-journal immutability, scoring, and small-sample behavior.

### Contract tests

- Versioned event, evidence, team brief, thesis, watchpoint, calendar-mode,
  scenario, receipt, analog, and journal schemas.
- `public_safe` enforcement.
- No private history under `webapp/`.
- Every generated sentence's referenced fields exist.
- All league status variants return a supported or explicit unavailable state.

### Replay tests

- Archived simulation state reproduces published baseline probabilities.
- Saved scenarios reproduce after reload using the stored version and seed.
- Time-machine points reconcile with trajectory and event archives.
- Weekly and alert figures reconcile with linked hub events.
- Result-based watchpoints reproduce their conditional forecast.
- Historical analogs open at the exact checkpoint used by the matcher.

### Browser tests

- Desktop and 375px mobile Hub layouts.
- Anonymous preview, trial, paid, expired, canceled, and offline states.
- Favorite migration and cross-device seen cursors.
- Scenario URL sharing, stale scenario handling, and reset.
- Keyboard navigation, focus order, reduced motion, and screen-reader labels.
- Long club, league, and translated metric names.
- Active, short-lull, scheduled-break, offseason, and preseason Hub composition.
- Forecast Journal checkpoint creation, versioning, export, deletion, and private
  default behavior.

### Visual tests

- Conversation cards at every supported social dimension.
- Time-machine and comparison charts with sparse, dense, and missing data.
- No text overlap or layout shift in loading/error states.
- Confidence/fragility indicators remain understandable without color alone.
- Team Thesis, model-watchpoint, analog, and quiet-feed states with sparse and
  missing data.

### Security and privacy tests

- Paid endpoints reject missing, forged, expired, and wrong-user tokens.
- Object-store or bundled private paths cannot be fetched directly.
- Stripe webhook signature and replay protection.
- Rate limiting on auth, Ask, scenario, and export endpoints.
- User export/delete and unsubscribe behavior.
- Logs exclude access tokens, full email addresses, raw private questions, and
  private Forecast Journal notes.

## 10. Operational requirements

- Add a build manifest listing every input snapshot, output artifact, schema
  version, row count, health state, and competition calendar mode.
- Treat an intentionally skipped quiet-period briefing as healthy while alerting
  on a missing scheduled phase report.
- Treat zero-row archive writes during an active season as a build failure.
- Alert the owner on archive shrinkage, attribution residual spikes, stale state,
  send failure rate, and unauthorized private-artifact requests.
- Keep a kill switch for all sends independent of the website deployment.
- Make every notification job runnable in `--dry-run` and `--user` modes.
- Document recovery for a bad model build: pause sends, mark affected events,
  rebuild from the last healthy state, append corrections, and never rewrite
  receipts silently.

## 11. Analytics and decision gates

Track outcomes rather than panel views alone:

- activation: user follows a team and opens its brief;
- comprehension: user expands Why It Changed;
- anticipation: user opens leverage or runs a scenario;
- recurrence: user returns after an alert or briefing;
- trust: user opens evidence or a receipt;
- advocacy: user creates or shares a conversation card;
- quiet-period value: user opens a Team Thesis, watchpoint, or historical analog;
- reflection: user records and later revisits a Forecast Journal checkpoint;
- creator value: creator exports and publishes repeatedly;
- retention: 30-day and 90-day paid retention by activated feature and calendar
  mode.

Do not infer willingness to pay from clicks on locked cards alone. The strongest
pre-launch evidence is repeated use of the live free preview, alert/briefing opt-in,
and waitlist conversion attributed to the specific live feature. Do not use daily
visits as the universal engagement target: compare healthy behavior within active,
break, offseason, and preseason cohorts.

## 12. Definition of done

The full Intelligence Hub program is complete only when:

1. All 26 features ship with the behavior above. Until then, unshipped panels
   carry an explicit unavailable/coming-later state and no mock figure appears
   as live; a labeled preview does not count as implementation.
2. The same event produces matching numbers in the Hub, email, Ask answer, export,
   receipt, and share card.
3. Paid data is protected by server-side authorization.
4. Public forecasts and trust surfaces remain free.
5. Every explanation is evidence-backed and every historical claim is reproducible.
6. Alerts and weekly email have passed shadow mode and explicit owner approval.
7. All league formats, route statuses, and calendar modes degrade honestly.
8. Archive growth, privacy boundaries, entitlement behavior, and notification
   safety are enforced in CI.
9. Browser and visual checks pass on desktop and mobile.
10. Operational recovery and kill-switch procedures are documented and tested.

