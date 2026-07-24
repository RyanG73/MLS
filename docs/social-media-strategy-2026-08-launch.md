# Entenser social media strategy - August 2026 launch

**Date:** 2026-07-18  
**Launch target:** Monday 2026-08-17  
**Primary job:** turn Entenser from an invisible product into a measured habit loop for soccer fans, without weakening the trust position by sounding like a betting-picks account.

This strategy builds on:

- `docs/launch-announcements.md` for launch-post drafts.
- `docs/superpowers/plans/2026-08-17-public-launch.md` for launch workstreams and metrics.
- `docs/competitive-intelligence-2026-07-combined.md` for positioning and audience evidence.
- `docs/product-roadmap-2026-07.md` for the post-launch free habit loop and supporter waitlist gates.

## 1. Strategic position

**One-line social promise:** Independent football forecasts across dozens of competitions. No bookmaker odds in the model. Every forecast graded in public.

**What social should sell:**

- A weekly reason to check the model: what moved, what got closer, what the model got wrong.
- A trust story: Entenser shows misses, calibration, and market comparison instead of pretending to be magic.
- A utility story: free league pages, weekly recaps, after-the-World-Cup guide, open CSVs.
- A feedback request: fans who know a league can help identify where the numbers feel wrong.

**What social should not sell:**

- "Picks," "locks," "profit," "edge," "beat the book," or "value bets."
- A 56-league boast without data-status nuance.
- A paid tier before the waitlist gate is measured.
- A founder vanity story unless the audience is technical and wants implementation detail.

## 2. Launch goals and metrics

Primary launch goal: **weekly returning forecast users** from social-referred forecast routes.

Secondary goals:

- Email signups from social-referred sessions.
- Supporter waitlist joins from social-referred returning users.
- Search lift from social: branded queries, league-page impressions, links, and mentions.
- Qualitative feedback: league-specific corrections, product confusion, trust objections.

Use consistent UTMs on every link:

```text
utm_source=<platform>
utm_medium=social
utm_campaign=launch_2026_08
utm_content=<post_or_community>
```

Examples:

```text
https://entenser.com/leagues/mls/?utm_source=reddit&utm_medium=social&utm_campaign=launch_2026_08&utm_content=r_mls_launch
https://entenser.com/weekly/?utm_source=bluesky&utm_medium=social&utm_campaign=launch_2026_08&utm_content=weekly_receipt_2026_08_18
```

Decision gates:

- Keep a channel if it produces returning users or high-quality feedback, not just likes.
- Do not spend on paid social until GA4/GSC are live and at least two organic posts show a measurable click or signup signal.
- Build paid supporter features only under the existing roadmap gate: waitlist joins >= 2% of returning users and >= 150 absolute.

## 3. Audience segments

| Segment | Why they care | Best surfaces | Core message |
|---|---|---|---|
| MLS/NWSL/USL fans | Post-World-Cup interest, underserved projections, domestic league fit | Reddit, Bluesky, X, Threads/Instagram | "Here is the race picture after the World Cup, and the model grades itself." |
| Analytics/data fans | Transparent methodology, open CSVs, model-vs-market comparison | Hacker News, Reddit analytics subs, Bluesky, X | "A static, market-blind soccer model with public calibration and downloadable data." |
| Club/league obsessives | Title/relegation/playoff odds and weekly movement | X, Bluesky, Reddit niche subs | "Your league has a live race page and weekly movers." |
| Journalists/bloggers/newsletter writers | Quotable numbers and reusable links | X, Bluesky, direct replies, email | "Here is a clean number and a source page you can cite." |
| New US soccer fans | Need a next-step guide after the World Cup | Threads/Instagram, Reddit, X/Bluesky | "Finished the World Cup? Here are MLS, NWSL, Liga MX, USL, and Leagues Cup races to follow." |

## 4. Channel strategy

### Reddit - primary feedback and launch channel

Role: first high-signal audience, not a broadcast channel.

Use:

- r/MLS and r/NWSL first, because the product fit is strongest and the communities are specific.
- r/soccer only after niche posts have produced useful feedback and you can show that this is a serious free tool, not link spam.
- Analytics communities later with an open-data/calibration angle.

Rules:

- Be a participant for 1-2 weeks before launch. Comment on normal threads without linking Entenser.
- Never reuse the same post body across communities.
- Disclose ownership in the first line.
- Lead with the community benefit, then the link.
- Stay in the thread for the first 2 hours after posting.

Launch content already exists in `docs/launch-announcements.md`; use those as the base, then rewrite per community.

### Bluesky - public notebook and soccer conversation

Role: daily lightweight distribution and relationship building with soccer/data people.

Use:

- Post one concise "model changed its mind" item on most matchdays.
- Reply to analysts, league writers, and club fans when a probability is directly relevant.
- Share weekly recap links with a plain-English lead.
- Use threads sparingly; single posts with one strong number should be the default.

Tone:

- Matter-of-fact, curious, and open to being wrong.
- "The model has Vancouver at 43% for the Shield; tell me why that is too high/low" beats "our model predicts Vancouver."

### X - journalist discovery and real-time soccer graph

Role: broadcast plus replies around live conversation.

Use:

- Same core assets as Bluesky, but with more matchday timing.
- Reply under relevant journalist/fan-account posts only when the number adds context.
- Pin the launch thread for 2-3 weeks.

Do not:

- Chase gambling accounts or betting-intent hashtags.
- Auto-post every league movement.

### Hacker News - one technical launch spike

Role: technical feedback, credibility, and backlinks.

Use:

- One `Show HN` post when the product is fully tryable without login.
- Lead with architecture, model honesty, static-site pipeline, public calibration, and open data.
- Be available for technical questions for the full day.

Do not:

- Post a newsletter, waitlist, or fundraiser as the main asset.
- Ask friends to upvote or comment.

### Threads / Instagram - visual proof, not a launch dependency

Role: secondary consumer reach once reusable cards exist.

Use:

- 3-slide carousels: "closest races," "biggest movers," "the receipt."
- Reels only if they are native 9:16 clips: chart, one number, one sentence, CTA.
- Keep copy non-technical and club/league-led.

Do not:

- Spend serious production time before GA4 proves social traffic converts.
- Use generic stock soccer imagery. Use Entenser charts, league tables, and real race cards.

### TikTok / YouTube Shorts - optional experiment

Role: top-of-funnel test, not core launch work.

Use only if one lightweight template can produce 3-5 clips per week:

- 20-35 seconds, vertical 9:16, chart on screen, captions, one question.
- Format: "The Premier League relegation race changed this week. Here is who moved and why."
- Repurpose the same export for TikTok, YouTube Shorts, and Reels.

Kill if:

- It consumes more than 90 minutes/week before there is evidence of returning users or email signups.

### LinkedIn - low priority

Role: occasional technical/product credibility, especially for the static data-product architecture.

Use:

- One launch post after HN or alongside it.
- One post about the static dashboard and daily rebuild pipeline.

Do not:

- Treat LinkedIn as a soccer fan acquisition channel.

## 5. Content pillars

| Pillar | Cadence | Link target | Example hook |
|---|---:|---|---|
| The Receipt | Weekly, Monday or Tuesday | `/weekly/` | "The model was >=60% on 8 calls this week. 6 hit. Here are the 2 misses." |
| Biggest Movers | 2-3x/week during active matchweeks | `/weekly/` or league page | "Rochdale's promotion odds jumped 27 points this week." |
| Closest Races | Weekly plus matchday | league page | "MLS Cup is basically a three-team race right now: Vancouver 23%, Nashville next, Miami next." |
| Model vs market, carefully | Weekly only if useful | relevant league or match page | "This is not a pick. It is where an odds-blind model disagrees most with the market this weekend." |
| How it works | 1x/week pre-launch, then occasional | `/?league=about` | "Why 'no bookmaker odds in the model' matters." |
| After the World Cup | Heavy pre-launch and launch week | `/after-the-world-cup/` | "Finished the World Cup and want club soccer stakes immediately? Start here." |
| Open data | 1x/week to technical audiences | `/open-data/` | "Every current league table is downloadable as CSV with attribution." |

## 6. Launch timeline

### Now to July 26: account setup and social warm-up

- Claim/clean handles on X, Bluesky, Threads/Instagram, YouTube, TikTok, LinkedIn.
- Bio: "Independent football forecasts. No bookmaker odds in the model. Every forecast graded in public."
- Link in bio: homepage until launch week, then `/after-the-world-cup/` or `/weekly/` depending on post.
- Follow 100-150 relevant accounts: MLS/NWSL/USL writers, soccer analytics people, data journalists, club bloggers.
- Comment daily in r/MLS, r/NWSL, and soccer/data threads without dropping links.
- Build 3 reusable visual templates: square card, 9:16 vertical card, link-preview crop.

### July 27 to August 9: soft proof

- Post 3-4 no-hype examples on Bluesky/X using live weekly/mover numbers.
- Share one open-data or methodology post to a technical audience without calling it a launch.
- Privately ask 5-10 soccer/data people for feedback on the league pages.
- Record common objections and turn them into copy: "How is this different from Opta/FotMob/Forebet?"

### August 10 to August 16: freeze and queue

- Freeze launch copy on August 14 after the final QA pass.
- Refresh all launch post links with UTMs.
- Choose the first Reddit community based on where the account has real participation: r/MLS or r/NWSL.
- Prepare a launch-day response sheet:
  - "Does it beat the market?"
  - "Where do the numbers come from?"
  - "Is this for betting?"
  - "Why is my league results-only/historical?"
  - "Can I download the data?"

### Launch week: August 17 to August 23

Day 1, Monday August 17:

- Post first Reddit launch in r/MLS or r/NWSL.
- Post X/Bluesky launch thread.
- Stay active for replies for 2 hours immediately after posting and again that evening.

Day 2-3:

- Post `Show HN` if the first wave did not expose blocking product issues.
- Post the other US-soccer Reddit community if Day 1 went well.
- Share one "what feedback changed" note on Bluesky/X.

Day 4-5:

- Data-forward post for analytics communities: open CSVs, calibration, static architecture.
- Start targeted replies to journalists/bloggers with league-specific numbers.

Later that week:

- Consider r/soccer only if the niche launches generated real engagement and no major trust confusion.
- Publish the first post-launch "The Receipt" social card.

## 7. Weekly operating rhythm after launch

This should fit inside about 45 minutes/day and one 90-minute weekly production block.

Monday:

- Publish "The Receipt" and biggest movers.
- Reply to weekend conversations.
- Log top objections and feature requests.

Tuesday/Wednesday:

- One league-specific race post.
- One technical/method post every other week.

Thursday/Friday:

- Matchday leverage post for the weekend.
- Optional model-vs-market post with strict non-betting framing.

Saturday/Sunday:

- Minimal posting. Reply when a live result materially changes a race.

Weekly production block:

- Pull top movers and closest races from `/weekly/`.
- Create 3 cards:
  - one square card for X/Bluesky/Threads
  - one 9:16 vertical card for Reels/Shorts/TikTok
  - one Reddit-safe text version with no image dependency
- Review GA4/GSC/source metrics.

## 8. Creative templates

### Square card

Use for X, Bluesky, Threads, and link previews.

Structure:

- Header: league + race
- Main number: team probability and change
- Context: "No bookmaker odds in the model. Updated daily."
- Footer: entenser.com

Example:

```text
NWSL Shield race
Washington Spirit 41%
Gotham and Portland chasing

Entenser - independent forecasts, graded in public
```

### Vertical video/card

Use for Reels, Shorts, TikTok.

Structure:

1. First 2 seconds: "The MLS Cup race moved again."
2. Middle: 3 team odds or one mover chart.
3. End: "Full forecast: entenser.com/leagues/mls/"

Keep all important text inside the central safe area and use captions.

### Text-only community post

Use for Reddit and HN.

Structure:

- Disclosure.
- Why this is useful to the community.
- One or two concrete numbers.
- Link.
- Honest limitation.
- Ask for feedback.

## 9. Community response playbook

**"Does it beat the market?"**

No. Sharp markets are still better on aggregate. Entenser's value is that the model is independent of bookmaker odds and grades itself publicly, so you can inspect where it is right, wrong, and different.

**"Is this betting advice?"**

No. Do not frame it as picks. The public product is a forecast and transparency tool.

**"How is this different from Opta?"**

Opta's public supercomputer uses betting-market odds as an input and does not publish the same calibration ledger. Entenser is market-blind and shows misses.

**"Why is my league not fully forecast?"**

Some leagues have current fixtures and full simulations; some are results-only or historical because reliable fixture/data coverage is not available yet. The site labels that rather than pretending every league has the same data quality.

**"The model is wrong about my team."**

Good. Ask why. League-specific fan knowledge is useful signal. Request the concrete reason: injuries, transfers, tactical changes, source-data issue, or fixture-context miss.

## 10. Paid social policy

Do not buy launch-day reach.

Run a small paid test only after all are true:

- GA4/GSC are live and social UTMs are visible.
- Organic posts identify at least two hooks that earn clicks or email signups.
- The target page has a clear next action: email signup, favorite teams, or waitlist.

First test budget: $500-$1,000 total, split across at most two platforms.

Recommended tests:

- Reddit interest/community targeting around MLS/NWSL/Liga MX, optimized for email signup.
- X/Meta retest of the best organic race-card creative, optimized for landing-page views and email signup.

Stop if:

- Email signup rate is below 1% from paid social sessions.
- Bounce/engagement is materially worse than organic social.
- Comments pull the product into betting-picks framing.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Looks like spam | One community at a time, custom copy, prior participation, ownership disclosure. |
| Betting-frame drift | Ban picks/profit language; repeat "not betting advice"; keep edge language quiet. |
| Founder time gets consumed | 45-minute daily cap; kill short-form video if it takes more than 90 minutes/week. |
| Engagement without retention | Judge channels by returning users, email, waitlist, and feedback quality. |
| Trust damage from data gaps | Mention data-status labels plainly when relevant. |
| Overposting | One strong number beats five generic links. |

## 12. Minimum viable launch checklist

- [ ] Handles claimed and bios aligned.
- [ ] GA4/GSC live.
- [ ] UTMs prepared for every launch link.
- [ ] Three visual templates created.
- [ ] First Reddit community chosen based on actual participation.
- [ ] Launch drafts refreshed against latest payload numbers.
- [ ] Response sheet ready.
- [ ] Owner blocks two reply windows on August 17.
- [ ] Launch-week metrics sheet created.

## 13. Sources checked

- Reddit spam/self-promotion guidance: https://support.reddithelp.com/hc/en-us/articles/360043504051-Spam
- Hacker News Show HN guidelines: https://news.ycombinator.com/showhn.html
- Instagram creator best-practices hub: https://about.fb.com/news/2024/10/best-practices-education-hub-creators-instagram/
- Instagram recommendation eligibility: https://www.facebook.com/help/instagram/653964212890722
- TikTok creative best practices: https://ads.tiktok.com/help/article/creative-best-practices
- TikTok conversion creative guidance: https://ads.tiktok.com/business/en-US/blog/creative-that-drives-conversions
- YouTube Shorts creator guidance: https://support.google.com/youtube/answer/10059070
- Bluesky community guidelines: https://bsky.social/about/support/community-guidelines
