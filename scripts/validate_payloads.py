#!/usr/bin/env python3
"""Post-build payload validator — rejects NaN and checks required fields.

Run after every data build, before the webapp is served or published:

    python scripts/validate_payloads.py            # all webapp/data/*.js
    python scripts/validate_payloads.py epl ligue-1 # named leagues only

Exit codes:
    0  all payloads valid
    1  one or more payloads failed
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

_DATA = Path("webapp/data")

# Required top-level fields by surface type.
# Note: MLS uses a flat schema without "outlook"; European table leagues DO have it.
# The minimal contract is: all live surfaces must have league, standings, games,
# health, and generated.  Knockout competitions replace health with outlook.
_REQUIRED_LIVE = {"status", "league", "standings", "games", "health", "generated"}
_REQUIRED_KNOCKOUT = {"status", "league", "outlook", "games", "generated"}
_REQUIRED_POWER = {"status", "groups", "generated"}
_REQUIRED_PLACEHOLDER = {"status", "league"}  # "coming soon" stubs — minimal gate

# Canonical list of cross-league data files that are NOT per-league payloads
# (globals like window.TEAM_LOGOS / MODEL_SLICES, not LEAGUE_DATA/POWER_DATA).
# This is the single source of truth: tests/test_payload_contract.py and
# tests/test_fetch_league_teams.py import this set so a new cross-league file
# only has to be added here once (was duplicated + drifted through 2026-07-11).
_NON_PAYLOAD = {
    "logos.js",
    "ledger.js",
    "edge-board.js",
    "home.js",
    "search-index.js",
    "europe-map.js",
    "movers.js",
    "coefficients.js",
    "drift.js",
    "model-slices.js",
    "race-deltas.js",
    # Weekly recap (window.WEEKLY_DATA, launch plan H1) — cross-league snapshot,
    # not a per-league LEAGUE_DATA payload.
    "weekly.js",
    # Added 2026-07-14 while shipping round-5 leagues: "calendar.js" (matches
    # calendar, window.CALENDAR_DATA) landed in 3279e2a without being added
    # here, so it failed contract validation and the REGISTRY-vs-disk test as
    # an unregistered "league". Not caused by round 5 — a pre-existing gap.
    "calendar.js",
    "team-catalog.js",
}


def _load_payload(path: Path) -> dict:
    """Strip the JS assignment wrapper and parse as strict JSON.

    json.loads rejects NaN / Infinity because they are not valid JSON —
    that is intentional and is the primary contract check.
    """
    txt = path.read_text()
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", txt, re.DOTALL)
    if not m:
        raise ValueError("No JS assignment pattern found")
    return json.loads(m.group(1))


def _check_finite(obj: object, path: str = "root") -> None:
    """Recursively assert no NaN / Infinity in a JSON-parsed structure.

    json.loads normally rejects these, but this catches any that slip through
    other serialisation paths.
    """
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError(f"Non-finite value {obj!r} at {path}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_finite(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check_finite(v, f"{path}[{i}]")


def _required_fields(data: dict) -> set[str]:
    """Return the required field set for this payload's surface type."""
    # Placeholder / "coming soon" stubs — top-level status or league.status == "soon".
    if data.get("status") == "placeholder" or data.get("league", {}).get("status") == "soon":
        return _REQUIRED_PLACEHOLDER
    # Power rankings: has "groups" but no "league" key.
    if "groups" in data and "league" not in data:
        return _REQUIRED_POWER
    # Knockout competition (continental): outlook.mode == "knockout", no health block.
    if data.get("outlook", {}).get("mode") == "knockout":
        return _REQUIRED_KNOCKOUT
    # Live table league (MLS or European single-table).
    return _REQUIRED_LIVE


def _registry_data_status() -> dict[str, str]:
    """id → data_status from webapp/leagues.js (empty dict if unreadable)."""
    try:
        registry = _load_payload(Path("webapp/leagues.js"))
        return {e["id"]: e.get("data_status", "full_forecast") for e in registry}
    except Exception:
        return {}


def validate_file(path: Path, registry_ds: dict[str, str] | None = None) -> list[str]:
    """Return a list of error strings; empty means the payload is valid."""
    errors: list[str] = []
    try:
        data = _load_payload(path)
    except json.JSONDecodeError as e:
        errors.append(f"JSON parse error (likely contains NaN/Infinity): {e}")
        return errors
    except ValueError as e:
        errors.append(str(e))
        return errors

    try:
        _check_finite(data)
    except ValueError as e:
        errors.append(str(e))

    missing = _required_fields(data) - set(data)
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")

    # Data-status contract (launch plan 2026-08-17 B3): a payload's data_status
    # must agree with the registry's. Absent field == "full_forecast" on both
    # sides, so full-forecast leagues built before the field existed still pass;
    # a stale/results-only league whose payload claims otherwise fails.
    if registry_ds and data.get("status") != "placeholder":
        lid = data.get("league", {}).get("id")
        if lid and lid in registry_ds:
            payload_ds = data.get("data_status", "full_forecast")
            if payload_ds != registry_ds[lid]:
                errors.append(
                    f"data_status mismatch: payload says {payload_ds!r}, "
                    f"registry (webapp/leagues.js) says {registry_ds[lid]!r} — "
                    "update fetch_league_teams.DATA_STATUS or the "
                    "build_league_data derivation")

    # S1 stable-ID contract (docs/intelligence-hub-implementation-instructions.md
    # §4.3), MLS-only for now — see the S1 plan's Scope note for why other
    # leagues aren't checked yet.
    if data.get("status") != "placeholder" and data.get("league", {}).get("id") == "mls":
        for i, s in enumerate(data.get("standings") or []):
            if not s.get("team_id"):
                errors.append(f"standings[{i}] ({s.get('team')!r}): missing team_id "
                               "(docs/intelligence-hub-implementation-instructions.md §4.3)")
        for i, g in enumerate(data.get("games") or []):
            for field in ("home_id", "away_id", "fixture_id"):
                if not g.get(field):
                    errors.append(f"games[{i}] ({g.get('home')!r} v {g.get('away')!r}): "
                                   f"missing {field} "
                                   "(docs/intelligence-hub-implementation-instructions.md §4.3)")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if args:
        paths = [_DATA / f"{lid}.js" for lid in args]
    else:
        paths = [p for p in sorted(_DATA.glob("*.js"))
                 if p.name not in _NON_PAYLOAD]

    if not paths:
        print("No payload files found.", file=sys.stderr)
        return 1

    registry_ds = _registry_data_status()
    failures: list[tuple[str, list[str]]] = []
    for path in paths:
        if not path.exists():
            failures.append((path.name, [f"File not found: {path}"]))
            print(f"  MISS {path.name}")
            continue
        errs = validate_file(path, registry_ds)
        if errs:
            failures.append((path.name, errs))
            for e in errs:
                print(f"  FAIL {path.name}: {e}")
        else:
            print(f"  ok   {path.name}")

    total = len(paths)
    if failures:
        print(f"\n{len(failures)}/{total} payload(s) failed validation.")
        return 1
    print(f"\nAll {total} payload(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
