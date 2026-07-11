# Entenser Interface System

## Direction

Entenser should feel like a football probability command center: dense, auditable, fast, and calm. The primary user is a serious bettor, analyst, fantasy player, or data-curious fan checking what changed before a matchday or preseason decision. The interface should lead with probability movement, model trust, race fragility, and market-line status rather than generic dashboard decoration.

## Domain Signature

Use a trust tape pattern across landing and league pages:

- Upcoming match context.
- Season-race uncertainty.
- Projection movement.
- Model-family weak spots.
- Data and market availability.

This is the product's signature: the model does not just quote probabilities; it explains whether today's probabilities are stable enough to trust.

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

Match Rows:

- Keep compact probability bars.
- Show model favorite or edge status, but suppress draw-side betting recommendations until draw calibration clears.
- Expected scorelines and raw inputs belong behind expansion, not in the default scan.

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

"Market-blind football probabilities, explained and audited."

Avoid:

- "Guaranteed edge."
- "Picks" as the main product promise.
- Profit claims without paper ledger and CLV evidence.

Preferred framing:

- "Model-market disagreement."
- "No line yet."
- "Thin sample."
- "Known weak spot."
- "Diagnostics pending."
