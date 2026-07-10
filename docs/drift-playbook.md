# Drift-Tracking Playbook

*2026-07-10 · how to read the numbers scripts/build_drift_report.py produces, and what to do about them*

This is the operator's guide. For the *design rationale* (why these four metrics, what was considered and deferred), see [docs/projection-drift-tracking.md](projection-drift-tracking.md). This document assumes that's already been read once and answers a narrower question: **you're looking at the dashboard or the raw data — now what?**

---

## 1. What's accruing, where, and when

| File | Written by | Cadence | Contents |
|---|---|---|---|
| `data/odds_history.parquet` | `scripts/archive_odds_snapshot.py` | every `build_all.sh` run | one row per (league, team, build date): ELO, proj_pts, every outcome-odds column, next-match probs, `n_played`, `config_id`, `code_rev` |
| `data/match_prob_history.parquet` | same script | same | one row per (league, fixture, build date): full pH/pD/pA + market odds + days-to-kickoff for **every** upcoming match, not just each team's next one |
| `webapp/data/drift.js` | `scripts/build_drift_report.py` | every `build_all.sh` run | the churn index, config-change markers, kickoff funnel — small (~4KB), loaded on every page |
| `webapp/data/drift-traj/<league>.js` | same script | same | per-team time series for one league, loaded only when that league's Model Health tab is opened |

**Where this runs:** all four scripts are now wired into `scripts/build_all.sh`, which runs after every league rebuild, gated behind `scripts/validate_payloads.py`. `build_all.sh` is scheduled via `scripts/com.mls.buildall.plist` (launchd, 6am daily). **This wiring did not exist before 2026-07-10** — `odds_history.parquet` had only accrued on whatever days someone happened to run the archiver by hand. Check it's actually running:

```bash
tail -5 data/odds_history.parquet  # or:
python3 -c "import pandas as pd; d=pd.read_parquet('data/odds_history.parquet'); print(d['snapshot_date'].max())"
```

If the max date is more than a day old, `build_all.sh` isn't running on schedule — check `launchctl list | grep mls` and the plist's `Hour`/`Minute`.

---

## 2. The ramp-up period — what to expect for the first ~1-2 weeks

Two columns are brand new as of 2026-07-10: `n_played` and `config_id`. Every snapshot **before** that date has them as `null`. The churn index requires two *consecutive* snapshots with a matching, non-null `n_played` — so:

- **For the first day or two**, every league will show `insufficient_history` for churn. This is correct, not a bug — there's only one snapshot with the new column populated.
- **Once there are 2+ new-style snapshots**, in-season leagues (matches happening) will mostly show `insufficient_history` too, because `n_played` legitimately changes between most consecutive builds during an active season. That's fine — churn is specifically about *quiet* periods (no news, but the odds moved anyway), which by definition are the minority of build-pairs in-season.
- **Preseason / off-season leagues** (0 matches played, unchanged for weeks) are where churn will actually compute early and often — watch those first if you want to sanity-check the metric.
- **The kickoff funnel** needs a match to be quoted while upcoming AND later show up as played — it will be empty until the first archived quote's fixture actually happens (days, not weeks).
- **Trajectories** are cosmetic (a sparkline) and populate immediately, just short.

Rule of thumb: **don't draw conclusions from churn or the funnel until you have ~2-4 weeks of accrual.** Trust the mechanism, not early readings.

---

## 3. Reading the Model Health "Projection stability" card

Open any league → **Model Health** tab → **Projection stability** card.

- **"Build-to-build churn (window)"** — the mean absolute percentage-point move across every team/outcome pair between the two most recent quiet builds (see §2 for when this is available). A number under ~1pp is normal float noise from the Monte-Carlo sim reseeding. **>1.5pp triggers the ⚠ alert marker.**
  - *If you see the alert:* click through to §4 below (Runbook).
  - *If it says "insufficient history":* read §2 — this is almost always expected, not broken.
- **Individual mover chips** — up to 5 team/outcome pairs that moved >0.05pp inside that window. If the index is high but there's ONE big mover and everything else is flat, that's a single-team data problem (roster feed, name-mapping break), not a systemic one.
- **"Model config last changed"** — the date the champion's `run_id` (from `experiments/champion.json`) last changed. **Any drift dated after this is expected** — a new model naturally reprices everything once. Drift on a day with NO marker nearby is the suspicious case.
- **Kickoff funnel** — 3-way Brier of the quoted probability at each days-to-kickoff bucket, scored against the eventual result. Read left to right (7d+ → 0-1d): **it should generally fall** (get better) as kickoff approaches — that's the model correctly incorporating late injury news, form, etc. If it's flat, the late-window inputs (availability, last-5 form) aren't adding value close to kickoff. If it *rises*, something is actively making late predictions worse — investigate the features that update closest to kickoff first.
- **Trend line for the biggest movers** — a compact "last 5 points" readout for whichever teams appear in the mover chips, so you can eyeball whether a move was a one-day blip or a sustained trend before digging into the raw parquet.

---

## 4. Runbook — when the churn alert fires

1. **Check the config marker first.** If today's date matches (or is right after) a config-change marker, this is expected — a new champion reprices the board. No action needed; note it and move on.
2. **Check the mover chips.** One team, one outcome key, a big jump → look at that team's `elo_history` and recent match results in the Teams tab. Common causes: a roster/injury-availability data glitch, a name-mapping break that silently zeroed out a feature, or a genuinely surprising real-world event (managerial change, a key transfer) that's legitimately supposed to move the odds — check the News tab for that club before assuming it's a bug.
3. **Many teams, similar magnitude, same league** → look at league-wide inputs: did the ELO K/home-advantage/regress constants change? Did a data source (Understat, football-data, ASA) have a gap or a schema change that day? Check `scripts/validate_payloads.py` output from that day's build log.
4. **Many teams, many leagues, same day** → this is almost certainly a config/champion change that didn't get recorded as a marker (a code path other than `experiments/champion.json` changed model behavior — e.g. an ELO constant hardcoded in `build_league_data.py`, not gated by the promotion process). Check `git log` around that date for changes to `scripts/build_league_data.py`, `scripts/build_dashboard_data.py`, or `models/research_model.py`.
5. **Can't explain it after the above** → pull the raw rows and diff by hand (see §5). If it's real noise from the Monte-Carlo reseeding (the sim re-runs at build time; a different random seed will move small-sample outcome tails slightly), that's expected up to a couple pp on long-tail metrics (spoon odds, deep playoff brackets) — the 1.5pp threshold has margin built in for this, but a borderline case is worth a second look at whether `--sims` count dropped.

---

## 5. Manual inspection (when the card isn't enough)

```python
import pandas as pd
h = pd.read_parquet("data/odds_history.parquet")

# a team's full title/playoff/promoted/... history over time
h[h.team == "Arsenal"].sort_values("snapshot_date")[["snapshot_date", "elo", "title", "ucl"]]

# every (date, config_id) combination recorded — NOT deduped to just the
# change points (that's what drift.js's config_markers already gives you)
h[["snapshot_date", "config_id"]].dropna().drop_duplicates().sort_values("snapshot_date")

# raw churn for a specific league/date-pair (what the card summarizes)
g = h[h.league == "epl"].sort_values("snapshot_date")
prev, cur = g[g.snapshot_date == "2026-07-09"], g[g.snapshot_date == "2026-07-10"]
merged = prev.merge(cur, on="team", suffixes=("_prev", "_cur"))
merged["title_delta"] = merged.title_cur - merged.title_prev
merged.sort_values("title_delta", key=abs, ascending=False)[["team", "title_delta"]].head(10)

m = pd.read_parquet("data/match_prob_history.parquet")
# how one match's quote moved as kickoff approached
m[(m.home == "Arsenal") & (m.away == "Chelsea")].sort_values("days_to_kickoff", ascending=False)
```

You can also read `webapp/data/drift.js` directly — it's plain JSON after the `window.DRIFT_DATA = ` prefix.

---

## 6. Recommended review cadence

- **Passive:** the Projection stability card is on every league's Model Health tab — glance at it whenever you're already there.
- **Weekly (once ~2 weeks of history exist):** skim the churn index across leagues; anything alerting deserves the runbook.
- **Monthly:** review the kickoff funnel once it has real settled-match volume — this is the number that tells you whether late-arriving inputs (availability, hot/cold form) are pulling their weight.
- **On every champion promotion** (`scripts/promotion_gate.py` run): expect and ignore a repricing spike across every league on that date — it should show up as a `config_markers` entry automatically; verify it does.

---

## 7. What's NOT implemented yet (from the original design)

- **Rolling 90-day calibration drift** (reliability curve trending away from the diagonal over time) — needs real accrual first; revisit once a month of history exists, per the original design doc's phasing.
- **Automated alerting** — `scripts/notify.py::notify_drift_alert(brier_recent, brier_baseline, pct_change)` already exists and is wired to ntfy.sh, but nothing calls it today (confirmed 2026-07-10: zero callers in the codebase). Wiring `build_drift_report.py`'s `alerts` list (churn leagues over threshold) to a notify call is the natural next step — the signature doesn't quite match (it's Brier-framed, this is odds-churn-framed), so either adapt the call or add a small `notify_churn_alert()` sibling function rather than force-fitting the existing one.
- **Per-league-family calibration slices** — currently only MLS has a champion-report-backed trust block (`D.trust`); the live phase-Brier card added in round 3 covers every league from raw game data as an interim measure.

None of these block using what's here today — they extend it once there's enough history to make them meaningful.
