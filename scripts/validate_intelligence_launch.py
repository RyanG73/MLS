#!/usr/bin/env python3
"""Fail the build when private Intelligence artifacts violate launch contracts."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from scripts.intelligence.schema import FEATURES, FEATURE_STATES
from scripts.payload_utils import read_js_payload
from server.intelligence_service import IntelligenceService

EXPECTED_FEATURES = {str(value) for value in FEATURES}


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_record(record: dict, path: Path) -> list[str]:
    errors = []
    prefix = str(path)
    if record.get("feature_count") != 26 or set(record.get("features", {})) != EXPECTED_FEATURES:
        errors.append(f"{prefix}: does not contain exactly features 1-26")
    for required in ("league_id", "season_id", "team_id", "snapshot_id", "generated"):
        if not record.get(required):
            errors.append(f"{prefix}: missing {required}")
    for feature_id, feature in record.get("features", {}).items():
        if feature.get("feature_id") != int(feature_id):
            errors.append(f"{prefix}: feature {feature_id} identity mismatch")
        if feature.get("status") not in FEATURE_STATES:
            errors.append(f"{prefix}: feature {feature_id} has invalid state")
    for item in _walk(record):
        if isinstance(item, str) and (
            item in {"fixture:None", "snapshot:None", "event:None"}
            or item.endswith(":null")
        ):
            errors.append(f"{prefix}: null evidence identity {item}")
            break
    scenario = (record.get("features", {}).get("5", {}).get("data") or {})
    for required in ("snapshot_id", "simulation_version", "seed", "n"):
        if scenario and scenario.get(required) is None:
            errors.append(f"{prefix}: scenario missing {required}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/team_intelligence"))
    args = parser.parse_args()
    manifest_path = args.root / "manifest.json"
    if not manifest_path.exists():
        print("[validate-intelligence] manifest missing", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text())
    errors = []
    states = Counter()
    records = 0
    expected_catalog = set()
    for league_id, league in manifest.get("leagues", {}).items():
        if league.get("status") != "ok":
            errors.append(f"{league_id}: build status {league.get('status')}: {league.get('reason')}")
            continue
        for filename in league.get("files", []):
            path = args.root / league_id / filename
            if not path.exists():
                errors.append(f"{path}: manifest file missing")
                continue
            record = json.loads(path.read_text())
            records += 1
            expected_catalog.add((record.get("league_id"), record.get("team_id")))
            states.update(value["status"] for value in record.get("features", {}).values())
            errors.extend(validate_record(record, path))
            if records == 1:
                service = IntelligenceService(args.root)
                for template in record["features"]["20"]["data"].get("approved_templates", []):
                    payload = service.public_card_payload(
                        record["league_id"], record["team_id"], template)
                    serialized = json.dumps(payload)
                    for forbidden in ("email", "private_notes", "journal_entries",
                                      "saved_scenarios", "creator_workspaces"):
                        if f'"{forbidden}"' in serialized:
                            errors.append(f"{path}: public card leaked {forbidden}")
    if records == 0:
        errors.append("no team records were validated")
    catalog = read_js_payload("webapp/data/team-catalog.js") or {}
    catalog_pairs = {
        (league.get("league_id"), team.get("team_id"))
        for league in catalog.get("leagues", [])
        for team in league.get("teams", [])
    }
    if catalog_pairs != expected_catalog:
        errors.append(
            "team catalog coverage mismatch: "
            f"catalog={len(catalog_pairs)} artifacts={len(expected_catalog)}")
    if errors:
        print("[validate-intelligence] FAILED", file=sys.stderr)
        for error in errors[:100]:
            print(f"  - {error}", file=sys.stderr)
        if len(errors) > 100:
            print(f"  - and {len(errors) - 100} more", file=sys.stderr)
        return 1
    print(f"[validate-intelligence] ok leagues={len(manifest['leagues'])} teams={records} states={dict(states)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
