#!/usr/bin/env python3
"""Summarize shadow deliveries and event-quality risks for owner review."""
from __future__ import annotations

import json
from collections import Counter
import datetime as dt
from pathlib import Path

from server.kv_client import get_kv


def build_report(kv, event_path: Path = Path("data/intelligence_events.parquet")) -> dict:
    deliveries = []
    for key in sorted(kv.members("send_ledger:index")):
        raw = kv.get(key)
        if raw:
            deliveries.append(json.loads(raw))
    statuses = Counter(row.get("status", "unknown") for row in deliveries)
    templates = Counter(row.get("template_version", "unknown") for row in deliveries)
    attempts = Counter(int(row.get("attempts", 0)) for row in deliveries)

    event_stats = Counter()
    if event_path.exists():
        import pandas as pd
        events = pd.read_parquet(event_path)
        if not events.empty:
            event_stats["events"] = len(events)
            event_stats["refresh"] = int((events["cause_class"] == "refresh").sum())
            event_stats["model"] = int((events["cause_class"] == "model").sum())
            event_stats["unavailable_attribution"] = int(
                (events["attribution_quality"] == "unavailable").sum())
            if "residual_pp" in events:
                event_stats["residual_over_0_5pp"] = int(
                    (events["residual_pp"].abs() > 0.5).sum())

    shadow = [row for row in deliveries if row.get("status") == "shadow"]
    reviewed = [row for row in shadow if row.get("reviewed_at")]
    worth_sending = sum(row.get("worth_sending") is True for row in reviewed)
    defects = Counter(
        defect for row in reviewed for defect in (row.get("defects") or []))
    iso_weeks = set()
    for row in shadow:
        try:
            moment = dt.datetime.fromisoformat(
                row.get("created_at") or row.get("updated_at"))
        except (TypeError, ValueError):
            continue
        iso = moment.isocalendar()
        iso_weeks.add(f"{iso.year}-W{iso.week:02d}")
    quiet_suppressions = sum(
        row.get("status") == "suppressed"
        and "quiet" in str(row.get("reason") or "").lower()
        for row in deliveries
    )
    worth_rate = worth_sending / len(reviewed) if reviewed else None
    critical_defects = sum(
        defects[name] for name in
        ("wrong_team", "wrong_outcome", "wrong_price", "duplicate"))
    checks = {
        "at_least_50_reviewed": len(reviewed) >= 50,
        "at_least_80pct_worth_sending": (
            worth_rate is not None and worth_rate >= 0.80),
        "zero_critical_defects": critical_defects == 0,
        "two_iso_weeks_observed": len(iso_weeks) >= 2,
        "quiet_suppression_observed": quiet_suppressions > 0,
    }
    return {
        "delivery_count": len(deliveries),
        "statuses": dict(statuses),
        "templates": dict(templates),
        "attempts": dict(attempts),
        "event_quality": dict(event_stats),
        "shadow_review": {
            "candidate_count": len(shadow),
            "reviewed_count": len(reviewed),
            "worth_sending_count": worth_sending,
            "worth_sending_rate": worth_rate,
            "defects": dict(defects),
            "critical_defect_count": critical_defects,
            "observed_iso_weeks": sorted(iso_weeks),
            "quiet_suppression_count": quiet_suppressions,
            "automated_checks": checks,
            "automated_thresholds_met": all(checks.values()),
        },
        "owner_signoff_ready": False,
        "note": (
            "Owner signoff remains manual after confirming two complete "
            "matchweeks, one quiet-mode cycle, provider delivery success, "
            "and every automated check."
        ),
    }


def main() -> int:
    report = build_report(get_kv())
    Path("output").mkdir(exist_ok=True)
    Path("output/intelligence-shadow-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
