#!/usr/bin/env python3
"""Add the published global-ELO contract to every built domestic payload.

This is a cheap, deterministic post-build migration: it does not fetch data or
rerun a model. Future league builds call the same helper before writing, while
this script upgrades the already-committed payload set in one pass.
"""
from __future__ import annotations

from pathlib import Path

from scripts.payload_utils import (
    apply_global_elo_scale,
    read_js_payload,
    write_js_payload,
)

DATA_DIR = Path("webapp/data")


def apply_all(data_dir: Path = DATA_DIR) -> int:
    changed = 0
    for path in sorted(data_dir.glob("*.js")):
        data = read_js_payload(path)
        if not isinstance(data, dict):
            continue
        league_id = (data.get("league") or {}).get("id")
        if not league_id or not data.get("standings"):
            continue
        apply_global_elo_scale(data, league_id)
        write_js_payload(path, "LEAGUE_DATA", data)
        changed += 1
    return changed


def main() -> None:
    changed = apply_all()
    print(f"[global-elo] updated {changed} domestic league payloads")


if __name__ == "__main__":
    main()
