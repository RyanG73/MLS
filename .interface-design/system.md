# Entenser Interface System

## Direction

Entenser should feel like a football probability command center: dense, auditable, fast, and calm. The primary user is a committed supporter returning after a result or before kickoff. The interface should answer what changed, why it matters, and what comes next before it exposes deeper analysis. Analysts and betting-adjacent readers remain supported, but market status is secondary to club-season continuity.

## Domain Signature

Use a club-season watch tape across Club Watch, club pages, and relevant landing surfaces:

- Current season target and probability.
- What changed since the saved reference.
- Why it changed, with evidence or an explicit quiet/unsupported state.
- What comes next, including match stakes when available.
- Snapshot receipt and honest data-state label.

This is the product's signature: the model does not just quote probabilities; it keeps a supporter oriented in the club's season without requiring them to reconstruct the story.

## Palette

Keep the existing dark quant-terminal world:

- Canvas: near-black scoreboard/off-pitch surfaces.
- Structure: low-contrast chalk-line borders.
- Positive validated signal: floodlit pitch green.
- Priced edge or caution: bookmaker-slip amber.
- Relegation/danger/errors: restrained red.
- Draw/no-line/neutral states: muted gray-blue.

Avoid using green broadly for "profitable" language. In betting-adjacent contexts, green should mean validated signal or qualification only when the context is clear.

## Depth

Use borders-only and subtle surface shifts. No decorative shadows, gradient orbs, or card-on-card layouts. Page sections should be full-width or unframed; cards are for repeated items, panels, and compact tools.

Surface scale:

- Base canvas: `--ink-0`.
- Primary panels/cards: `--ink-1`.
- Panel headers and nested rows: `--ink-2`.
- Active controls and hover states: `--ink-3`.

Borders should stay quiet: `--line`, `--line-2`, `--line-3`. Focus/active borders can use floodlight green sparingly.

## Typography

Keep:

- `Archivo` for compact headings and high-emphasis numbers.
- `Inter` for body and interface text.
- `Spline Sans Mono` for probabilities, Brier values, odds, dates, and aligned numeric metrics.

Do not use hero-scale type inside cards or operational panels. Command-center hero copy can be larger, but table, card, and trust modules should stay compact and scannable.

## Spacing

Use the existing 4px base grid:

- `--s1: 4px`
- `--s2: 8px`
- `--s3: 12px`
- `--s4: 16px`
- `--s5: 24px`
- `--s6: 36px`

Keep repeated card gaps at 10-16px. Compact rows should use 7-10px vertical padding.

## Component Patterns

Command Center:

- The no-query landing page should always show value, even when odds are missing.
- Top area combines a concise promise with operational KPIs.
- Main body pairs match window/race cards with model movers/trust summaries.
- Use "no line yet" as neutral, not alarming.

Trust:

- Public-facing model governance should be called "Trust."
- First-order copy answers: can this family/league be trusted today?
- Always distinguish measured weak spots from diagnostics still missing.
- Use family-level summaries when league-specific slices do not exist yet.

Race Cards:

- Sort cross-league races by uncertainty or movement, not by league hierarchy.
- Show leader, probability, league, and a small contender set.
- Keep race cards full-width on mobile; no clipped horizontal cards.

League Tables:

- League mastheads show identity and season state, not methodology: logo, league name, country, division, projected season, next match, and average matches played per team.
- Express season progress as average team GP divided by the regular-season game total so uneven fixture counts remain honest.
- Historical model/market/naive performance belongs in the Trust tab.
- Treat the full-width ladder as the primary league decision surface.
- Keep `Pts`, `GP`, and `GD` as adjacent numeric columns immediately after the club.
- Team names use the strongest row typography; do not place metadata footnotes beneath them.
- Keep headers compact but no smaller than 10px, with enough contrast and weight to scan.
- Put supporting trajectory, projected-finish, and schedule analysis below the ladder.
- Paid table controls remain visible as muted previews for free readers, with a compact lock marker and a direct path to Club Watch.
- Explain locked table controls in a compact card that physically overlaps the disabled control column, revealed only when the column is hovered or keyboard-focused; a detached or permanently open banner is too distracting.
- Disabled previews must not mutate state; entitled and open-access readers receive the same control in its active state.

Season Trajectory:

- Use isolated team lanes on a shared 0–100% probability scale; do not overlay a full field of lines.
- Fix the horizontal domain to the actual regular season, labeled from Game 1 to the final scheduled game.
- Position snapshots by matches played, not by snapshot count or date spacing.
- Collapse multiple model snapshots between matchdays into one point.
- Preseason leagues therefore show one point at the start; live leagues stop at current season progress and never stretch to the chart edge.
- Suppress probability-point movement during preseason; label the state as a baseline because no match-driven movement exists yet.
- Rotate the movement panel through every available configured projection, with direct category controls and hover/focus pause.
- For title and relegation, show the six clubs with the highest current likelihood. For other projection categories, show the six largest absolute likelihood changes.
- During preseason, use current likelihood for every category because no match-driven movement exists yet.

Run difficulty:

- Opening/upcoming-run charts should rely on team identity, bar length, opponent ELO, and the shared toughest/easiest legend.
- Do not append opponent-monogram chips; their density and abbreviations make the chart harder to scan.

Match Rows:

- Match projections open on the viewer's current local date. Past results are reached through backward calendar navigation, not a separate Played filter.
- Keep the match filter row to the team selector and result count; do not add status, hit/miss, edge, or leverage pill groups beside it.
- On desktop, the date control opens a compact month calendar with direct day selection and previous/next month navigation. Dates without matches remain selectable and resolve to an honest empty state.
- Do not place the league-wide Model vs. Market analysis panel in Match Projections; detailed evaluation belongs in Trust.
- Keep compact probability bars.
- Show model favorite or edge status, but suppress draw-side betting recommendations until draw calibration clears.
- Venue and weather may sit behind expansion. Proprietary model inputs are not exposed in public match or team views.

Team Dashboards:

- Show one selected club at a time; never lead with a grid of every club's ELO history.
- Selection priority is explicit navigation/deep link, then a favorite in that league, then the current championship-projection leader.
- Use a custom searchable/scannable team dropdown that keeps club crests and current ELO visible.
- Lead with the selected club's identity and ELO history. Do not show trophy counts or trophy markers until trophy data is reliable enough to be a product feature.
- Place three dotted league-relative references directly on the ELO chart: league average, the top-quartile threshold, and the bottom-quartile threshold.
- Pair Season Outlook and Season Trajectory as equal-height cards on desktop; stack them on narrow screens.
- Render headline projection probabilities as horizontal bars instead of a dense stat list.
- Keep squad value inside Season Outlook: one total plus plain, aligned attack, midfield, defense, and goalkeeper value lines. Do not use progress bars for the positional split, and do not surface player rows, rank, age, or a separate squad card.
- Use the same fixed-season trajectory language as the league table: Game 1 to the final scheduled game, with snapshots positioned by matches played and preseason represented by one starting dot per projection.
- Plot every projection category configured as a league-table column in the team Season Trajectory card. Reuse the table's category colors and include a compact legend with current values; the shared 0–100% axis makes unlike outcomes directly comparable.
- Keep club news full-width immediately below the Outlook/Trajectory pair.
- Replace separate upcoming/recent cards with one full-season fixture ledger. Keep rows neutral and put the semantic tone only on the pre-match win value: green when the selected club exceeds 50%, amber when neither side exceeds 50%, and red when the opponent exceeds 50%. Use a sufficiently dark tinted badge to remain legible on the dark panel.
- Fixture rows pair the selected club's pre-match win probability with a compact result marker: green W, amber T, red L, or a muted dash when unplayed.
- Random matchup odds belong only in the internal `intel` route, whose customer-facing name is Club Watch.

Club Watch:

- Customer-facing name is always “Club Watch”; `intel` remains an internal route, entitlement, and storage alias only.
- Signed-out intent is club-first. Preserve the selected club through magic-link registration.
- A free account can follow one server-backed club and receives one complete, frozen sample update.
- Show the sample before the paid continuation. Never make the first signed-in screen a generic pricing wall.
- Paid continuation is continuous monitoring, supported causes, match stakes, continuity across visits, saved scenarios, and up to ten clubs.
- Current public forecasts, club pages, the current one-match what-if, and the saved sample remain free.
- Checkout is disabled when a verified amount or any production prerequisite is missing. Never use “see price at checkout.”
- Notification controls may be previewed and saved, but alerts and briefings must be labeled unavailable until the shadow-run reliability gate and owner approval are complete.
- Account identity, plan, followed clubs, notification preferences, export, deletion, and billing are server-authoritative. Browser favorites remain explicitly local unless the user chooses to import them.

Model Weak Spots:

- Surface weak spots with human-readable club names, not internal IDs.
- Prefer concrete language: low-confidence favorites, draw-heavy balanced matches, promoted/relegated priors, thin markets, volatile roster-reset teams.
- Missing diagnostics should be explicit chips or notes, not hidden.

## Mobile

Mobile should preserve complete cards and readable text:

- Summary/race cards stack full-width.
- Tables may scroll horizontally, but cards and headers should not clip.
- Header model status should collapse to compact trust language.
- Use stable dimensions for fixed-format rows and KPI cards so content does not resize the layout.

## Copy Rules

Lead with:

"What changed, why it matters, and what comes next for your club."

Avoid:

- "Guaranteed edge."
- "Picks" as the main product promise.
- Profit claims without paper ledger and CLV evidence.

Preferred framing:

- "Current answer stays free."
- "Keep this club on watch."
- "No supported cause yet."
- "First saved sample."
- "Model-market disagreement."
- "No line yet."
- "Thin sample."
- "Known weak spot."
- "Diagnostics pending."
