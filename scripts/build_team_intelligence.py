#!/usr/bin/env python3
"""Compile all private per-team Intelligence Hub artifacts."""
from __future__ import annotations

import argparse
import json

from scripts.intelligence.builder import build_all


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leverage-sims", type=int, default=400)
    args = parser.parse_args()
    manifest = build_all(leverage_n=args.leverage_sims)
    failures = {league: row for league, row in manifest["leagues"].items()
                if row["status"] != "ok"}
    print(json.dumps({
        "leagues": len(manifest["leagues"]),
        "teams": sum(row["team_count"] for row in manifest["leagues"].values()),
        "failures": failures,
    }, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
