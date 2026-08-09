#!/usr/bin/env python3
"""Publish a durable source-health surface and alert on a dark feed.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§3.4 (and R4's "fail closed", R3's "a coverage claim is a full pass").

The problem this solves, stated exactly: `data/source_health.parquet` is
gitignored, read by no workflow, and discarded at the end of every CI run. The
division-mismatch guard, every router fallback and the plan-lapse assertion all
record there — i.e. into nothing. A feed can go dark for days and the only
evidence is warning lines in a log nobody reads, which is precisely how ESPN
403'd through three scheduled jobs on 2026-08-07 unnoticed.

Two properties worth stating because their absence caused defects:

- **Every figure is a full pass over the parquet, and names its condition.**
  `rows` counts rows returned by SUCCESSFUL fetches; `failure_rate_24h` is over
  recorded runs inside 24 hours and says how many runs that was. Nothing is
  sampled, and no field is counted for its presence when its value is what
  matters.
- **"Dark" means no successful fetch in a run that ATTEMPTED the feed.** A feed
  nobody called this run is not dark, it is unexercised — ~40% of the catalogue
  is between seasons at any moment (§8.14), and a 200 carrying zero fixtures for
  a dormant league is a success, not an outage.

Usage:
  build_source_health.py --write    # merge this run into the summary, annotate
  build_source_health.py --check    # read the summary, annotate, exit non-zero
                                    # when a feed has been dark N runs running
`--write` never fails a build: the health surface is observability, and a run
that produced good payloads must still commit them (the 2026-07-19 bug that
discarded five nights of correct data was exactly this mistake). The failing
verdict lives in `--check`, which runs after the commit step.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HEALTH_PATH = Path("data/source_health.parquet")
SUMMARY_PATH = Path("data/source_health_summary.json")

# Consecutive scheduled runs a feed may be dark before the run FAILS. One dark
# run already emits an ::error:: annotation — this is the threshold at which a
# human is made to look, not the threshold at which the problem starts.
DARK_RUNS_ALERT = 3

# How many per-run records the summary carries. Bounded so a committed file
# cannot grow without limit; 48 covers two days of hourly runs, which is more
# than the 24h window any published figure reads.
RECENT_RUNS_KEPT = 48

# Failures that must never read like a routine pre-season 404 (§3.4). Matched on
# the error text the recording site writes, so a new guard shows up here by
# writing a clear error rather than by editing this table.
NOTABLE = {
    "division_mismatch": "expected",        # football_data: "served X, expected Y"
    "wrong_competition": "declares",        # football_data_intl League filter
    "identity_mismatch": "identity mismatch",   # API-Football R1 guard
    "plan_lapse":        "plan",            # api_budget.PlanMismatch
    "stale_cache":       "served from cache",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_summary(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"feeds": {}}


def _annotate(level: str, message: str) -> None:
    """GitHub Actions annotation; a plain line anywhere else."""
    print(f"::{level}::{message}" if level in ("warning", "error") else message)


def read_run(health_path: Path = HEALTH_PATH) -> dict:
    """Full pass over this run's health parquet → per-feed counters.

    Returns {feed: {attempts, failures, rows, last_success, last_failure,
                    errors: [str]}}, plus a "" key never used. Empty when the
    parquet is absent, which is the state of a fresh runner before any fetch.
    """
    if not health_path.exists():
        return {}
    import pandas as pd
    try:
        df = pd.read_parquet(health_path)
    except Exception as exc:                      # noqa: BLE001 — observability
        _annotate("warning", f"source health: unreadable parquet ({exc})")
        return {}
    if df.empty:
        return {}
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True, errors="coerce")
    feeds: dict[str, dict] = {}
    for name, rows in df.groupby("source_name"):
        ok = rows[rows["success"].astype(bool)]
        bad = rows[~rows["success"].astype(bool)]
        feeds[str(name)] = {
            "attempts": int(len(rows)),
            "failures": int(len(bad)),
            # Rows returned by SUCCESSFUL fetches. A failed fetch's row count is
            # not evidence of coverage (a stale-cache read records both).
            "rows": int(ok["raw_count"].fillna(0).sum()),
            "last_success": _iso(ok["fetched_at"].max()) if len(ok) else None,
            "last_failure": _iso(bad["fetched_at"].max()) if len(bad) else None,
            "errors": [str(e) for e in bad["error_message"].dropna().unique()[:10]],
            "endpoints_failed": sorted({str(e) for e in bad["endpoint"].dropna()})[:10],
        }
    return feeds


def _iso(ts) -> str | None:
    return ts.isoformat() if hasattr(ts, "isoformat") and ts == ts else None


def classify_notable(feeds: dict) -> list[dict]:
    """Failures that mean something specific went wrong, not that a feed was
    briefly unreachable. These are the ones §3.4 refuses to leave as quiet as a
    routine 404."""
    out = []
    for feed, info in sorted(feeds.items()):
        for err in info.get("errors") or []:
            low = err.lower()
            for kind, needle in NOTABLE.items():
                if needle in low:
                    out.append({"kind": kind, "feed": feed, "error": err[:300]})
                    break
    return out


def merge(prior: dict, run_feeds: dict, now: datetime | None = None) -> dict:
    """Fold one run's counters into the durable summary.

    consecutive_dark_runs advances only for feeds this run ATTEMPTED and never
    succeeded on; a feed with no attempts keeps its previous count untouched,
    because "not called" is not "not answering".
    """
    now = now or _now()
    summary = {"generated": now.isoformat(),
               "feeds": dict(prior.get("feeds") or {})}
    for feed, info in run_feeds.items():
        before = dict(summary["feeds"].get(feed) or {})
        attempts, failures = info["attempts"], info["failures"]
        succeeded = attempts > failures
        dark_before = int(before.get("consecutive_dark_runs") or 0)
        if attempts == 0:
            dark = dark_before
        elif succeeded:
            dark = 0
        else:
            dark = dark_before + 1
        recent = list(before.get("recent") or [])
        recent.append({"at": now.isoformat(), "attempts": attempts,
                       "failures": failures, "rows": info["rows"]})
        recent = recent[-RECENT_RUNS_KEPT:]
        summary["feeds"][feed] = {
            "last_success": info["last_success"] or before.get("last_success"),
            "last_failure": info["last_failure"] or before.get("last_failure"),
            "attempts": attempts,
            "failures": failures,
            "rows": info["rows"],
            "consecutive_dark_runs": dark,
            "recent": recent,
            **_window_rates(recent, now),
            "errors": info["errors"],
            "endpoints_failed": info["endpoints_failed"],
        }
    summary["notable"] = classify_notable(run_feeds)
    return summary


def _window_rates(recent: list[dict], now: datetime) -> dict:
    """Failure rate over recorded runs inside 24h — and the run count it is
    over, because a rate without its n is the kind of figure that gets quoted
    as authoritative."""
    cutoff = now - timedelta(hours=24)
    window = []
    for r in recent:
        try:
            at = datetime.fromisoformat(str(r.get("at")))
        except (TypeError, ValueError):
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if at >= cutoff:
            window.append(r)
    attempts = sum(int(r.get("attempts") or 0) for r in window)
    failures = sum(int(r.get("failures") or 0) for r in window)
    return {
        "failure_rate_24h": round(failures / attempts, 4) if attempts else None,
        "failure_rate_24h_condition":
            f"failed fetches / attempted fetches over {len(window)} recorded "
            f"runs in the last 24h ({failures}/{attempts})",
    }


def dark_feeds(summary: dict, threshold: int = DARK_RUNS_ALERT) -> list[tuple[str, int]]:
    return sorted((f, int(i.get("consecutive_dark_runs") or 0))
                  for f, i in (summary.get("feeds") or {}).items()
                  if int(i.get("consecutive_dark_runs") or 0) >= threshold)


def annotate(summary: dict, threshold: int = DARK_RUNS_ALERT) -> None:
    for feed, info in sorted((summary.get("feeds") or {}).items()):
        dark = int(info.get("consecutive_dark_runs") or 0)
        if dark >= threshold:
            _annotate("error", f"source health: {feed} dark for {dark} consecutive "
                               f"runs (last success {info.get('last_success')})")
        elif dark:
            # "Alerts within one cycle": one dark run is already an error
            # annotation on the run, visible in the run UI without digging.
            _annotate("error", f"source health: {feed} answered nothing this run "
                               f"({info.get('failures')}/{info.get('attempts')} "
                               f"attempts failed; last success "
                               f"{info.get('last_success')})")
        elif info.get("failures"):
            _annotate("warning", f"source health: {feed} {info['failures']}/"
                                 f"{info['attempts']} fetches failed")
    for note in summary.get("notable") or []:
        _annotate("error", f"source health [{note['kind']}] {note['feed']}: "
                           f"{note['error']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="merge this run's parquet into the summary and annotate")
    ap.add_argument("--check", action="store_true",
                    help="annotate from the summary and fail on a persistently "
                         "dark feed")
    ap.add_argument("--health-path", type=Path, default=HEALTH_PATH)
    ap.add_argument("--summary-path", type=Path, default=SUMMARY_PATH)
    ap.add_argument("--threshold", type=int, default=DARK_RUNS_ALERT)
    args = ap.parse_args(argv)
    if not (args.write or args.check):
        ap.error("pass --write or --check")

    summary = _load_summary(args.summary_path)
    if args.write:
        summary = merge(summary, read_run(args.health_path))
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        print(f"source health: {len(summary.get('feeds') or {})} feeds → "
              f"{args.summary_path}")
    annotate(summary, args.threshold)
    if args.check:
        dark = dark_feeds(summary, args.threshold)
        if dark:
            names = ", ".join(f"{f} ({n} runs)" for f, n in dark)
            _annotate("error", f"source health: failing the run — dark feeds: {names}")
            return 1
    return 0


if __name__ == "__main__":                        # pragma: no cover
    sys.exit(main())
