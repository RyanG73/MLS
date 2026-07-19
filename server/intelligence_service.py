"""Read/filter private team artifacts and execute supported intelligence intents."""
from __future__ import annotations

import base64
import csv
import gzip
import io
import json
import re
from pathlib import Path

from scripts.intelligence.simulation import run_simulation
from scripts.payload_utils import read_js_payload
from server.config import intelligence_root

_SAFE_ID = re.compile(r"^[A-Za-z0-9:_-]+$")


class ArtifactNotFound(Exception):
    pass


class StaleScenario(Exception):
    pass


class IntelligenceService:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or intelligence_root())

    @staticmethod
    def _safe(value: str) -> str:
        if not value or not _SAFE_ID.fullmatch(value):
            raise ValueError("invalid identifier")
        return value

    def get_team(self, league_id: str, team_id: str, feature_id: int | None = None) -> dict:
        league_id, team_id = self._safe(league_id), self._safe(team_id)
        path = self.root / league_id / f"{team_id.replace(':', '_')}.json"
        try:
            record = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            from server.kv_client import get_kv
            raw = get_kv().get(f"intel:artifact:{league_id}:{team_id}")
            if raw is None:
                raise ArtifactNotFound(f"no intelligence artifact for {league_id}/{team_id}")
            try:
                if raw.startswith("gz:"):
                    decoded = gzip.decompress(base64.b64decode(raw[3:])).decode()
                    record = json.loads(decoded)
                else:
                    record = json.loads(raw)
            except (ValueError, json.JSONDecodeError, OSError) as exc:
                raise ArtifactNotFound(
                    f"invalid intelligence artifact for {league_id}/{team_id}") from exc
        if feature_id is None:
            return record
        key = str(int(feature_id))
        if key not in record["features"]:
            raise ValueError("feature_id must be between 1 and 26")
        return {
            "schema_version": record["schema_version"],
            "league_id": league_id,
            "team_id": team_id,
            "team": record["team"],
            "snapshot_id": record["snapshot_id"],
            "generated": record["generated"],
            "calendar_mode": record["calendar_mode"],
            "feature": record["features"][key],
        }

    def _snapshot(self, league_id: str) -> dict:
        from scripts.archive_intelligence_state import build_snapshot
        payload = read_js_payload(Path("webapp/data") / f"{league_id}.js")
        if not isinstance(payload, dict):
            raise ArtifactNotFound(f"no current payload for {league_id}")
        return build_snapshot(payload, league_id=league_id)

    def run_scenario(self, league_id: str, team_id: str, payload: dict) -> dict:
        record = self.get_team(league_id, team_id)
        snapshot = self._snapshot(league_id)
        requested_snapshot = payload.get("snapshot_id")
        if requested_snapshot and requested_snapshot != snapshot["snapshot_id"]:
            raise StaleScenario(
                f"scenario snapshot {requested_snapshot} is stale; current is {snapshot['snapshot_id']}")
        assumptions = payload.get("assumptions") or {}
        n = min(max(int(payload.get("n") or 2000), 200), 5000)
        seed = int(payload.get("seed") or snapshot["replay_seed"])
        results = run_simulation(snapshot, forced=assumptions, n=n, seed=seed)
        target = payload.get("target_metric") or record["target_metric"]
        subject = results[team_id]
        rivals = record["features"]["9"]["data"]["rivals"] if record["features"]["9"]["data"] else []
        return {
            "schema_version": 1,
            "snapshot_id": snapshot["snapshot_id"],
            "simulation_version": snapshot["simulation_version"],
            "seed": seed,
            "n": n,
            "assumptions": assumptions,
            "target_metric": target,
            "baseline": record["features"]["5"]["data"]["baseline"],
            "scenario": subject,
            "nearest_rivals": [
                {"team_id": rival["team_id"], "team": rival["team"],
                 "scenario": results.get(rival["team_id"])}
                for rival in rivals[:3] if rival["team_id"] in results
            ],
        }

    def ask(self, league_id: str, team_id: str, payload: dict) -> dict:
        record = self.get_team(league_id, team_id)
        requested = payload.get("intent")
        question = str(payload.get("question") or "").strip().casefold()
        if not requested:
            catalog = [
                ("why_changed", ("why", "changed", "move")),
                ("next_high_impact_match", ("next match", "important match", "leverage")),
                ("rival_importance", ("rival", "threat", "race")),
                ("path_to_target", ("path", "reach", "qualify", "avoid")),
                ("schedule_difficulty", ("schedule", "run-in", "fixtures")),
                ("historical_comparison", ("history", "before", "analog", "past")),
                ("receipt_lookup", ("receipt", "prediction", "said")),
                ("scenario", ("what if", "scenario")),
            ]
            requested = next((intent for intent, phrases in catalog
                              if any(phrase in question for phrase in phrases)), "current_state")
        mapping = {
            "current_state": "1", "why_changed": "3", "next_high_impact_match": "4",
            "rival_importance": "9", "path_to_target": "6",
            "schedule_difficulty": "13", "historical_comparison": "24",
            "receipt_lookup": "18", "scenario": "5",
        }
        if requested not in mapping:
            return {
                "status": "unsupported",
                "intent": requested,
                "supported_intents": list(mapping),
                "suggested_follow_ups": ["current_state", "next_high_impact_match"],
            }
        feature = record["features"][mapping[requested]]
        return {
            "status": feature["status"],
            "intent": requested,
            "parameters": {"league_id": league_id, "team_id": team_id,
                           "target_metric": record["target_metric"]},
            "result": feature["data"],
            "snapshot_id": record["snapshot_id"],
            "evidence_ids": self._evidence_ids(feature["data"]),
            "suggested_follow_ups": self._follow_ups(requested),
        }

    @staticmethod
    def _evidence_ids(value) -> list[str]:
        found = set()
        def walk(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if key == "evidence_ids" and isinstance(child, list):
                        found.update(str(entry) for entry in child)
                    else:
                        walk(child)
            elif isinstance(item, list):
                for child in item:
                    walk(child)
        walk(value)
        return sorted(found)

    @staticmethod
    def _follow_ups(intent: str) -> list[str]:
        options = {
            "current_state": ["why_changed", "next_high_impact_match"],
            "why_changed": ["receipt_lookup", "scenario"],
            "next_high_impact_match": ["scenario", "path_to_target"],
            "rival_importance": ["path_to_target", "schedule_difficulty"],
        }
        return options.get(intent, ["current_state", "next_high_impact_match"])

    def creator_export(self, league_id: str, team_id: str, format_name: str,
                       template: str = "highest_leverage") -> tuple[str, bytes]:
        record = self.get_team(league_id, team_id)
        citation = f"Entenser Intelligence Hub, generated {record['generated']}"
        public = {
            "team": record["team"], "league": record["league_name"],
            "season_id": record["season_id"], "generated": record["generated"],
            "snapshot_id": record["snapshot_id"], "target_metric": record["target_metric"],
            "brief": record["features"]["1"]["data"],
            "leverage": record["features"]["4"]["data"],
            "race_context": record["features"]["9"]["data"],
            "receipts": record["features"]["18"]["data"],
            "source": "Entenser market-blind forecast pipeline",
            "citation": citation,
            "methodology": "https://entenser.com/methodology",
        }
        if format_name == "json":
            return "application/json", json.dumps(public, indent=2, allow_nan=False).encode()
        if format_name == "png":
            from server.conversation_card import render_card_png
            card = self.public_card_payload(league_id, team_id, template)
            verification = f"https://api.entenser.com/v1/public/card?preview={record['snapshot_id']}"
            return "image/png", render_card_png(card, verification)
        if format_name != "csv":
            raise ValueError("format must be csv, json, or png")
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow([
            "team", "league", "metric", "value", "generated", "snapshot_id",
            "source", "methodology", "citation",
        ])
        brief = public["brief"]
        writer.writerow([
            record["team"], record["league_name"], record["target_metric"],
            brief.get("current_pct"), record["generated"], record["snapshot_id"],
            public["source"], public["methodology"], citation,
        ])
        return "text/csv", stream.getvalue().encode()

    def public_card_payload(self, league_id: str, team_id: str,
                            template: str) -> dict:
        record = self.get_team(league_id, team_id)
        allowed = set(record["features"]["20"]["data"]["approved_templates"])
        if template not in allowed:
            raise ValueError("unsupported conversation-card template")
        feature_key = {
            "material_move": "3", "highest_leverage": "4", "turning_point": "17",
            "race_comparison": "9", "receipt": "18",
        }[template]
        source = record["features"][feature_key]
        return {
            "schema_version": 1, "public_safe": True, "template": template,
            "team": record["team"], "league": record["league_name"],
            "generated": record["generated"], "snapshot_id": record["snapshot_id"],
            "insight": source["data"], "evidence_ids": self._evidence_ids(source["data"]),
        }
