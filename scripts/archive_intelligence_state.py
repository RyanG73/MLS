#!/usr/bin/env python3
"""S3: archive a compact, reproducible simulation-state snapshot after each
successful league build (docs/intelligence-hub-implementation-instructions.md
§4.7, §5 S3).

Reads the already-built, already-validated MLS payload (webapp/data/mls.js)
and extracts exactly what a later replay needs to reconstruct the published
target probabilities: team-strength inputs (the sim.pmatrix + team order the
client simulator reads), current standings (points/goal-diff/conference),
remaining fixtures (by stable fixture_id, not display order — S1), season-
format rules, and provenance (config/code revision, generation timestamp).
Decorative UI fields (crests, colors, weather, venue) are never archived.

Fails closed: if any required input is missing, this exits non-zero and
writes NOTHING rather than archiving a partial/misleading snapshot as
healthy.

COMPLIANCE NOTE: per docs/intelligence-hub-implementation-instructions.md
rule 6, private archives must not be committed to a publicly readable
repository — this one is public. data/intelligence_snapshots/ is gitignored;
this script still runs on every build (fail-closed validation + a
replay-testable local artifact), but durable committed persistence is
deferred to S5's access-controlled storage.

Run after scripts/validate_payloads.py and scripts/validate_history_growth.py,
before any future intelligence-event builder (S4).

Usage:
    python scripts/archive_intelligence_state.py            # MLS only, for now
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import make_snapshot_id, read_js_payload  # noqa: E402

PAYLOAD_PATH = Path("webapp/data/mls.js")
SNAPSHOT_DIR = Path("data/intelligence_snapshots/mls")
SIMULATION_VERSION = "v1"  # matches webapp/sim-engine.js ENGINE_VERSION


class MissingRequiredInput(Exception):
    """Raised when the payload lacks a field this archive cannot honestly represent."""


def _require(payload: dict, path: str, predicate=lambda v: bool(v)):
    """Walk a dotted path in payload; raise if missing or fails `predicate`."""
    cur = payload
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise MissingRequiredInput(f"missing required field: {path}")
        cur = cur[part]
    if not predicate(cur):
        raise MissingRequiredInput(f"required field is empty/invalid: {path}")
    return cur


def build_snapshot(payload: dict) -> dict:
    """Extract the reproducibility-relevant subset of `payload`. Raises
    MissingRequiredInput (fail closed) if anything required is absent."""
    league_id = _require(payload, "league.id")
    season = _require(payload, "season", lambda v: v is not None)
    generated = _require(payload, "generated")
    config_id = _require(payload, "provenance.champion_run")
    code_rev = payload.get("provenance", {}).get("git_commit")
    n_sims = _require(payload, "n_sims")
    playoff_slots = _require(payload, "playoff_slots")
    hfa_slots = _require(payload, "hfa_slots")
    standings = _require(payload, "standings", lambda v: isinstance(v, list) and len(v) > 0)
    sim_teams = _require(payload, "sim.teams", lambda v: isinstance(v, list) and len(v) > 0)
    pmatrix = _require(payload, "sim.pmatrix", lambda v: isinstance(v, list) and len(v) > 0)

    by_name = {s["team"]: s for s in standings}
    teams = []
    for name in sim_teams:
        s = by_name.get(name)
        if s is None:
            raise MissingRequiredInput(f"sim.teams entry {name!r} has no matching standings row")
        teams.append({
            "team": name, "team_id": s.get("team_id"), "conf": s.get("conf"),
            "pts": s.get("pts"), "gd": s.get("gd"),
            "published": {k: s.get(k) for k in
                          ("proj_pts", "playoff", "hfa", "shield", "spoon", "conf_win", "cup")},
        })

    fixtures = []
    for g in payload.get("games") or []:
        if g.get("result") is not None:
            continue
        if not g.get("fixture_id") or not g.get("home_id") or not g.get("away_id"):
            continue  # S1 IDs not backfilled on this row yet — skip rather than
                      # archive a fixture that can't be joined back to a team_id
        fixtures.append({
            "fixture_id": g["fixture_id"], "home_id": g["home_id"], "away_id": g["away_id"],
            "date": g.get("date"), "pH": g.get("pH"), "pD": g.get("pD"), "pA": g.get("pA"),
        })

    snapshot_id = make_snapshot_id(league_id, season, generated, config_id, SIMULATION_VERSION)
    replay_seed = int(snapshot_id.split(":", 1)[1][:8], 16)  # deterministic from the id itself

    return {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "league_id": league_id, "season": season, "generated": generated,
        "config_id": config_id, "code_rev": code_rev,
        "simulation_version": SIMULATION_VERSION,
        "n_sims": n_sims, "replay_seed": replay_seed,
        "rules": {"playoff_slots": playoff_slots, "hfa_slots": hfa_slots},
        "teams": teams,
        "pmatrix": pmatrix,
        "fixtures": fixtures,
    }


def _latest_snapshot(snapshot_dir: Path) -> dict | None:
    """Most recently WRITTEN snapshot in `snapshot_dir` (by file mtime — the
    hash-based filenames are not lexicographically time-ordered)."""
    if not snapshot_dir.exists():
        return None
    files = sorted(snapshot_dir.glob("*.json.gz"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    with gzip.open(files[-1], "rt", encoding="utf-8") as f:
        return json.load(f)


def write_snapshot(snapshot: dict, snapshot_dir: Path = SNAPSHOT_DIR) -> tuple[Path, bool]:
    """Write `snapshot`, gzip-compressed, deduplicating an unchanged pmatrix
    against the immediately previous snapshot (a large array that rarely
    changes build-to-build — e.g. two consecutive preseason builds with no
    new results). Returns (path, deduped)."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    prev = _latest_snapshot(snapshot_dir)
    to_write = dict(snapshot)
    deduped = prev is not None and prev.get("pmatrix") == snapshot["pmatrix"]
    if deduped:
        to_write["pmatrix"] = {"$ref": prev["snapshot_id"]}
    out_path = snapshot_dir / f"{snapshot['snapshot_id'].replace(':', '_')}.json.gz"
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        json.dump(to_write, f, separators=(",", ":"))
    return out_path, deduped


def main() -> int:
    if not PAYLOAD_PATH.exists():
        print(f"[archive-intelligence-state] {PAYLOAD_PATH} does not exist — nothing to archive",
              file=sys.stderr)
        return 1
    payload = read_js_payload(PAYLOAD_PATH)
    if payload is None:
        print(f"[archive-intelligence-state] {PAYLOAD_PATH} did not parse — nothing to archive",
              file=sys.stderr)
        return 1
    try:
        snapshot = build_snapshot(payload)
    except MissingRequiredInput as e:
        print(f"[archive-intelligence-state] FAILED CLOSED: {e}", file=sys.stderr)
        return 1
    out_path, deduped = write_snapshot(snapshot)
    note = " (pmatrix deduplicated)" if deduped else ""
    print(f"[archive-intelligence-state] wrote {out_path} "
          f"({len(snapshot['teams'])} teams, {len(snapshot['fixtures'])} fixtures){note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
