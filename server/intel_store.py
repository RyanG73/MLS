#!/usr/bin/env python3
"""S5: user preference/entitlement record store (docs/intelligence-hub-
implementation-instructions.md §4.8, §5 S5).

Backed by the KVStore abstraction (server/kv_store.py) — one JSON blob per
user_id, matching the roadmap's "no database server" decision (a KV store,
not a relational schema).
"""
from __future__ import annotations

import json

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
}


def _key(user_id: str) -> str:
    return f"user:{user_id}"


def get_or_create_user(kv: KVStore, user_id: str, email: str) -> dict:
    raw = kv.get(_key(user_id))
    if raw is not None:
        return json.loads(raw)
    record = {"user_id": user_id, "email": email, **json.loads(json.dumps(DEFAULT_RECORD))}
    kv.set(_key(user_id), json.dumps(record))
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
