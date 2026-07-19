#!/usr/bin/env python3
"""S5: user preference/entitlement record store (docs/intelligence-hub-
implementation-instructions.md §4.8, §5 S5).

Backed by the KVStore abstraction (server/kv_store.py) — one JSON blob per
user_id, matching the roadmap's "no database server" decision (a KV store,
not a relational schema).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid

from server.kv_store import KVStore

DEFAULT_RECORD = {
    "plan": "free",
    "teams": [],
    "leagues": [],
    "targets": [],
    "notifications": {"weekly": True, "material_change": True},
    "threshold_pp": 5,
    "timezone": "UTC",
    "last_seen_event_id_by_team": {},
    "unsubscribe_state": {},
    "saved_scenarios": [],
    "creator_workspaces": [],
    "journal_entries": [],
    "alert_state": {"bounced": False, "last_sent_at_by_team": {}},
    "analytics_consent": False,
}


def _key(user_id: str) -> str:
    return f"user:{user_id}"


def get_or_create_user(kv: KVStore, user_id: str, email: str) -> dict:
    raw = kv.get(_key(user_id))
    if raw is not None:
        kv.add_to_set("users:index", user_id)
        return json.loads(raw)
    record = {"user_id": user_id, "email": email, **json.loads(json.dumps(DEFAULT_RECORD))}
    kv.set(_key(user_id), json.dumps(record))
    kv.add_to_set("users:index", user_id)
    return record


def update_preferences(kv: KVStore, user_id: str, **updates) -> dict:
    """Merge `updates` into the user's existing record (never a blind
    overwrite of the whole record) and persist it."""
    raw = kv.get(_key(user_id))
    if raw is None:
        raise KeyError(f"no user record for {user_id!r}")
    record = json.loads(raw)
    record.update(updates)
    kv.set(_key(user_id), json.dumps(record))
    return record


def set_plan(kv: KVStore, user_id: str, plan: str) -> dict:
    return update_preferences(kv, user_id, plan=plan)


def get_plan(kv: KVStore, user_id: str) -> str:
    """The authoritative current plan lookup intel_auth.require_entitlement
    calls on every request — never a cached/token-embedded value."""
    raw = kv.get(_key(user_id))
    if raw is None:
        return "free"
    return json.loads(raw).get("plan", "free")


def export_user_data(kv: KVStore, user_id: str) -> dict | None:
    """docs/intelligence-hub-implementation-instructions.md §4.8: "Provide
    export and deletion." Returns the full record, or None if the user
    doesn't exist."""
    raw = kv.get(_key(user_id))
    return json.loads(raw) if raw is not None else None


def delete_user_data(kv: KVStore, user_id: str) -> None:
    kv.delete(_key(user_id))
    # The immutable index may retain a tombstone; jobs skip missing records.


def merge_client_state(server_record: dict, fav_leagues: list[str], fav_teams: list[dict]) -> dict:
    """docs/intelligence-hub-implementation-instructions.md §4.8: "On first
    authenticated use, offer to merge existing FavStore and AcctStore
    state. Never overwrite server preferences silently." Additive only:
    unions leagues/teams into whatever the server already has, never
    replaces or drops an existing entry."""
    merged = dict(server_record)
    merged["leagues"] = sorted(set(server_record.get("leagues", [])) | set(fav_leagues))
    existing_team_ids = {t["team_id"] for t in server_record.get("teams", [])}
    merged_teams = list(server_record.get("teams", []))
    for t in fav_teams:
        if t["team_id"] not in existing_team_ids:
            merged_teams.append(t)
            existing_team_ids.add(t["team_id"])
    merged["teams"] = merged_teams
    return merged


_ALLOWED_PREFERENCE_KEYS = {
    "teams", "leagues", "targets", "notifications", "threshold_pp", "timezone",
    "last_seen_event_id_by_team", "unsubscribe_state", "analytics_consent",
}


def update_public_preferences(kv: KVStore, user_id: str, updates: dict) -> dict:
    unknown = set(updates) - _ALLOWED_PREFERENCE_KEYS
    if unknown:
        raise ValueError(f"unsupported preference fields: {sorted(unknown)}")
    return update_preferences(kv, user_id, **updates)


def set_seen_cursor(kv: KVStore, user_id: str, team_id: str, event_id: str) -> dict:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    cursors = dict(record.get("last_seen_event_id_by_team") or {})
    cursors[team_id] = event_id
    return update_preferences(kv, user_id, last_seen_event_id_by_team=cursors)


def save_scenario(kv: KVStore, user_id: str, scenario: dict) -> dict:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    required = {"league_id", "team_id", "snapshot_id", "simulation_version", "seed", "assumptions"}
    if not required.issubset(scenario):
        raise ValueError(f"scenario missing fields: {sorted(required - set(scenario))}")
    assumptions = scenario["assumptions"]
    if not isinstance(assumptions, dict) or any(value not in {"H", "D", "A"} for value in assumptions.values()):
        raise ValueError("scenario assumptions must map fixture IDs to H/D/A")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    value = {**scenario, "scenario_id": scenario.get("scenario_id") or str(uuid.uuid4()),
             "saved_at": now, "updated_at": now}
    saved = [row for row in record.get("saved_scenarios", [])
             if row.get("scenario_id") != value["scenario_id"]]
    saved.append(value)
    update_preferences(kv, user_id, saved_scenarios=saved[-50:])
    return value


def save_creator_workspace(kv: KVStore, user_id: str, workspace: dict) -> dict:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    required = {"league_id", "team_id"}
    if not required.issubset(workspace):
        raise ValueError(f"workspace missing fields: {sorted(required - set(workspace))}")
    allowed = {"workspace_id", "name", "league_id", "team_id", "target_metric",
               "rival_team_id", "date_from", "date_to", "card_template"}
    unknown = set(workspace) - allowed
    if unknown:
        raise ValueError(f"unsupported workspace fields: {sorted(unknown)}")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    value = {key: workspace.get(key) for key in allowed if workspace.get(key) is not None}
    value["workspace_id"] = value.get("workspace_id") or str(uuid.uuid4())
    value["name"] = str(value.get("name") or "Creator workspace")[:80]
    value["updated_at"] = now
    rows = [row for row in record.get("creator_workspaces", [])
            if row.get("workspace_id") != value["workspace_id"]]
    rows.append(value)
    update_preferences(kv, user_id, creator_workspaces=rows[-20:])
    return value


def delete_creator_workspace(kv: KVStore, user_id: str, workspace_id: str) -> None:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    rows = [row for row in record.get("creator_workspaces", [])
            if row.get("workspace_id") != workspace_id]
    update_preferences(kv, user_id, creator_workspaces=rows)


def append_journal_entry(kv: KVStore, user_id: str, entry: dict) -> dict:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    required = {"league_id", "team_id", "season_id", "target_metric",
                "target_probability", "confidence"}
    if not required.issubset(entry):
        raise ValueError(f"journal entry missing fields: {sorted(required - set(entry))}")
    probability = float(entry["target_probability"])
    if not 0 <= probability <= 100:
        raise ValueError("target_probability must be between 0 and 100")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    logical_id = entry.get("logical_id") or str(uuid.uuid4())
    existing = [row for row in record.get("journal_entries", [])
                if row.get("logical_id") == logical_id]
    version = max((int(row.get("version", 0)) for row in existing), default=0) + 1
    frozen = {
        "journal_entry_id": f"journal:{hashlib.sha256(f'{user_id}|{logical_id}|{version}|{now}'.encode()).hexdigest()[:20]}",
        "logical_id": logical_id,
        "version": version,
        "created_at": now,
        "private": True,
        "league_id": entry["league_id"],
        "team_id": entry["team_id"],
        "season_id": str(entry["season_id"]),
        "target_metric": entry["target_metric"],
        "target_probability": probability,
        "predicted_finish": entry.get("predicted_finish"),
        "confidence": entry["confidence"],
        "private_notes": entry.get("private_notes", ""),
        "model_snapshot_id": entry.get("model_snapshot_id"),
    }
    entries = list(record.get("journal_entries", []))
    entries.append(frozen)
    update_preferences(kv, user_id, journal_entries=entries)
    return frozen


def delete_journal_entry(kv: KVStore, user_id: str, journal_entry_id: str) -> None:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    entries = [row for row in record.get("journal_entries", [])
               if row.get("journal_entry_id") != journal_entry_id]
    update_preferences(kv, user_id, journal_entries=entries)
