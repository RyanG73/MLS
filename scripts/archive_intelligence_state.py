#!/usr/bin/env python3
"""Archive compact, reproducible simulation states for every forecast league.

Private snapshots are written beneath data/intelligence_snapshots/ (gitignored).
The archive is the single reproducibility source for scenarios, leverage,
attribution, receipts, watchpoints, and saved user work.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import (  # noqa: E402
    canonical_team_id,
    make_fixture_id,
    make_snapshot_id,
    read_js_payload,
)

PAYLOAD_DIR = Path("webapp/data")
SNAPSHOT_ROOT = Path("data/intelligence_snapshots")
SNAPSHOT_DIR = SNAPSHOT_ROOT / "mls"  # backwards-compatible test/default path
SIMULATION_VERSION = "v1"
TARGET_KEYS = (
    "title", "playoff", "playoffs", "shield", "cup", "hfa", "spoon",
    "conf_win", "ucl", "europa", "conf", "releg", "promo", "promoted",
    "liguilla", "premiers", "finals", "continental",
)


class MissingRequiredInput(Exception):
    """Raised when a payload cannot be represented truthfully."""


def _require(payload: dict, path: str, predicate=lambda value: bool(value)):
    cur = payload
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise MissingRequiredInput(f"missing required field: {path}")
        cur = cur[part]
    if not predicate(cur):
        raise MissingRequiredInput(f"required field is empty/invalid: {path}")
    return cur


def _champion_config_id() -> str | None:
    try:
        return json.loads(Path("experiments/champion.json").read_text()).get("run_id")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _target_rules(payload: dict) -> list[dict]:
    outlook = payload.get("outlook") or {}
    if outlook.get("mode") == "mls":
        return [
            {"key": "playoff", "per_conf_top": payload.get("playoff_slots")},
            {"key": "hfa", "per_conf_top": payload.get("hfa_slots")},
            {"key": "shield", "top": 1},
            {"key": "spoon", "bottom": 1},
        ]
    return [dict(rule) for rule in (outlook.get("columns") or [])
            if isinstance(rule, dict) and rule.get("key")]


def build_snapshot(payload: dict, league_id: str | None = None) -> dict:
    """Extract the simulation-relevant subset of a league payload."""
    league_id = league_id or _require(payload, "league.id")
    season = _require(payload, "season", lambda value: value is not None)
    generated = _require(payload, "generated")
    provenance = payload.get("provenance") or {}
    config_id = provenance.get("champion_run")
    if not config_id and (provenance.get("model_file") or provenance.get("data_source")):
        config_id = _champion_config_id()
    if not config_id:
        raise MissingRequiredInput("missing required field: provenance.champion_run")
    code_rev = provenance.get("git_commit")
    n_sims = _require(payload, "n_sims", lambda value: isinstance(value, int) and value > 0)
    standings = _require(payload, "standings", lambda value: isinstance(value, list) and bool(value))
    sim_teams = _require(payload, "sim.teams", lambda value: isinstance(value, list) and bool(value))
    pmatrix = _require(payload, "sim.pmatrix", lambda value: isinstance(value, list) and bool(value))

    by_name = {row.get("team"): row for row in standings if row.get("team")}
    teams = []
    team_id_by_name: dict[str, str] = {}
    for name in sim_teams:
        row = by_name.get(name)
        if row is None:
            raise MissingRequiredInput(f"sim.teams entry {name!r} has no matching standings row")
        team_id = canonical_team_id(name, row.get("team_id"))
        team_id_by_name[name] = team_id
        published = {"proj_pts": row.get("proj_pts"), "proj_rank": row.get("proj_rank")}
        published.update({key: row.get(key) for key in TARGET_KEYS if key in row})
        teams.append({
            "team": name,
            "team_id": team_id,
            "conf": row.get("conf") if isinstance(row.get("conf"), str) else None,
            "pts": row.get("pts"),
            "gd": row.get("gd"),
            "gp": row.get("gp"),
            "elo": row.get("elo"),
            "published": published,
        })

    fixtures = []
    for game in payload.get("games") or []:
        if game.get("result") is not None:
            continue
        home, away, date = game.get("home"), game.get("away"), game.get("date")
        if home not in team_id_by_name or away not in team_id_by_name or not date:
            continue
        probs = (game.get("pH"), game.get("pD"), game.get("pA"))
        if not all(isinstance(value, (int, float)) for value in probs):
            continue
        home_id = canonical_team_id(home, game.get("home_id") or team_id_by_name[home])
        away_id = canonical_team_id(away, game.get("away_id") or team_id_by_name[away])
        fixture_id = game.get("fixture_id") or make_fixture_id(
            league_id, season, date, home_id, away_id)
        fixtures.append({
            "fixture_id": fixture_id,
            "home_id": home_id,
            "away_id": away_id,
            "home": home,
            "away": away,
            "date": date,
            "ko": game.get("ko"),
            "pH": float(probs[0]),
            "pD": float(probs[1]),
            "pA": float(probs[2]),
        })

    snapshot_id = make_snapshot_id(
        league_id, season, generated, config_id, SIMULATION_VERSION)
    replay_seed = int(snapshot_id.split(":", 1)[1][:8], 16)
    outlook = payload.get("outlook") or {}
    source_health = payload.get("health") or {}
    return {
        "schema_version": 2,
        "snapshot_id": snapshot_id,
        "league_id": league_id,
        "league_name": (payload.get("league") or {}).get("name", league_id),
        "season": season,
        "season_id": str(season),
        "generated": generated,
        "status": payload.get("status"),
        "data_status": payload.get("data_status"),
        "config_id": config_id,
        "code_rev": code_rev,
        "simulation_version": SIMULATION_VERSION,
        "n_sims": n_sims,
        "replay_seed": replay_seed,
        "rules": {
            "mode": outlook.get("mode"),
            "playoff_slots": payload.get("playoff_slots"),
            "hfa_slots": payload.get("hfa_slots"),
            "targets": _target_rules(payload),
            "description": outlook.get("rules"),
        },
        "source": {
            "provenance": provenance,
            "health": source_health,
            "freshness": "current",
        },
        "teams": teams,
        "pmatrix": pmatrix,
        "fixtures": fixtures,
    }


def _latest_snapshot(snapshot_dir: Path) -> dict | None:
    if not snapshot_dir.exists():
        return None
    files = sorted(snapshot_dir.glob("*.json.gz"), key=lambda path: path.stat().st_mtime)
    if not files:
        return None
    with gzip.open(files[-1], "rt", encoding="utf-8") as handle:
        return json.load(handle)


def write_snapshot(snapshot: dict, snapshot_dir: Path = SNAPSHOT_DIR) -> tuple[Path, bool]:
    """Write a compressed snapshot and reference an unchanged prior matrix."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    previous = _latest_snapshot(snapshot_dir)
    to_write = dict(snapshot)
    deduped = previous is not None and previous.get("pmatrix") == snapshot["pmatrix"]
    if deduped:
        to_write["pmatrix"] = {"$ref": previous["snapshot_id"]}
    out_path = snapshot_dir / f"{snapshot['snapshot_id'].replace(':', '_')}.json.gz"
    with gzip.open(out_path, "wt", encoding="utf-8") as handle:
        json.dump(to_write, handle, separators=(",", ":"))
    return out_path, deduped


def archive_all(payload_dir: Path = PAYLOAD_DIR,
                snapshot_root: Path = SNAPSHOT_ROOT) -> tuple[list[Path], list[str]]:
    written: list[Path] = []
    skipped: list[str] = []
    for payload_path in sorted(payload_dir.glob("*.js")):
        payload = read_js_payload(payload_path)
        if not isinstance(payload, dict) or not payload.get("standings"):
            continue
        league_id = (payload.get("league") or {}).get("id") or payload_path.stem
        if payload.get("data_status") in {"results_only", "historical"}:
            skipped.append(f"{league_id}: unsupported data_status")
            continue
        if not payload.get("sim") or payload.get("season") is None:
            skipped.append(f"{league_id}: no reproducible simulation state")
            continue
        try:
            snapshot = build_snapshot(payload, league_id=league_id)
            path, _ = write_snapshot(snapshot, snapshot_root / league_id)
            written.append(path)
        except MissingRequiredInput as exc:
            skipped.append(f"{league_id}: {exc}")
    return written, skipped


def main() -> int:
    written, skipped = archive_all()
    for reason in skipped:
        print(f"[archive-intelligence-state] skip {reason}", file=sys.stderr)
    print(f"[archive-intelligence-state] wrote {len(written)} league snapshots")
    if not written:
        print("[archive-intelligence-state] no reproducible forecast payloads", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
