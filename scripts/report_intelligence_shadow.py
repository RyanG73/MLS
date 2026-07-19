#!/usr/bin/env python3
"""Summarize shadow deliveries and event-quality risks for owner review."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from server.kv_client import get_kv


def main() -> int:
    kv = get_kv()
    deliveries = []
    for key in sorted(kv.members("send_ledger:index")):
        raw = kv.get(key)
        if raw:
            deliveries.append(json.loads(raw))
    statuses = Counter(row.get("status", "unknown") for row in deliveries)
    templates = Counter(row.get("template_version", "unknown") for row in deliveries)
    attempts = Counter(int(row.get("attempts", 0)) for row in deliveries)

    event_path = Path("data/intelligence_events.parquet")
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

    report = {
        "delivery_count": len(deliveries),
        "statuses": dict(statuses),
        "templates": dict(templates),
        "attempts": dict(attempts),
        "event_quality": dict(event_stats),
        "owner_signoff_ready": False,
        "note": "Set owner_signoff_ready only after two complete matchweeks are reviewed.",
    }
    Path("output").mkdir(exist_ok=True)
    Path("output/intelligence-shadow-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
