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
    "notifications": {
        "weekly": True,
        "material_change": True,
        "match_morning": False,
        "quiet": False,
        "paused": False,
    },
    "threshold_pp": 5,
    "timezone": "UTC",
    "last_seen_event_id_by_team": {},
    "unsubscribe_state": {},
    "saved_scenarios": [],
    "creator_workspaces": [],
    "journal_entries": [],
    "alert_state": {"bounced": False, "last_sent_at_by_team": {}},
    "analytics_consent": False,
    "club_watch_sample": None,
    "subscription_lifecycle": {},
    "customer_evidence": [],
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


def set_stripe_customer(kv: KVStore, user_id: str, customer_id: str) -> dict:
    """Link a user to their Stripe customer, and index the reverse direction.

    The reverse index is what makes Stripe the recoverable source of truth: it
    lets an entitlement be rebuilt from a Stripe object that only knows the
    customer id, and it is required to open a hosted billing portal session.
    """
    kv.set(f"stripe_customer:{customer_id}", user_id)
    return update_preferences(kv, user_id, stripe_customer_id=customer_id)


def user_for_stripe_customer(kv: KVStore, customer_id: str) -> str | None:
    """Resolve a Stripe customer id back to our user, via the reverse index.

    Refund and charge events carry a customer but no metadata, so this is the
    only link back to an entitlement -- and the same lookup is what makes an
    entitlement rebuildable from Stripe if the KV store is ever lost.
    """
    if not customer_id:
        return None
    return kv.get(f"stripe_customer:{customer_id}")


def get_stripe_customer(kv: KVStore, user_id: str) -> str | None:
    raw = kv.get(_key(user_id))
    if raw is None:
        return None
    return json.loads(raw).get("stripe_customer_id")


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
    record = export_user_data(kv, user_id) or {}
    customer_id = record.get("stripe_customer_id")
    if customer_id:
        kv.delete(f"stripe_customer:{customer_id}")
    for token_hash in kv.members(f"refresh_tokens:{user_id}"):
        kv.delete(f"refresh:{token_hash}")
    kv.delete(f"refresh_tokens:{user_id}")
    for key in kv.members("send_ledger:index"):
        try:
            delivery = json.loads(kv.get(key) or "{}")
        except (TypeError, ValueError):
            continue
        if delivery.get("user_id") == user_id:
            if delivery.get("provider_id"):
                kv.delete(f"provider_send:{delivery['provider_id']}")
            kv.delete(key)
    for key in kv.members("growth_events:index"):
        try:
            event = json.loads(kv.get(key) or "{}")
        except (TypeError, ValueError):
            continue
        if event.get("user_id") == user_id:
            kv.delete(key)
    for event in (
        "registration_complete", "sample_update_view", "activation",
        "checkout_start", "purchase", "renewal", "cancellation_requested",
        "expiration", "refund", "failed_payment", "payment_recovered",
        "pause", "reactivation", "material_change_explanation_viewed",
        "match_stakes_viewed", "since_last_visit_viewed", "scenario_run",
        "scenario_saved", "return_visit", "notification_setting_change",
        "cancellation_reason_submitted", "support_request_categorized",
        "testimonial_consented",
    ):
        kv.delete(f"growth_last:{user_id}:{event}")
    kv.delete(f"dunning:{user_id}")
    kv.delete(f"refunded:{user_id}")
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


def _normalise_teams(value, plan: str) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("teams must be a list")
    limit = 1 if plan == "free" else 10
    if len(value) > limit:
        raise ValueError(
            "free accounts can follow one synced club"
            if plan == "free" else f"at most {limit} clubs may be followed")
    out, seen = [], set()
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("each followed club must be an object")
        league_id = str(row.get("league_id") or "").strip()
        team_id = str(row.get("team_id") or "").strip()
        if not league_id or not team_id:
            raise ValueError("followed clubs require league_id and team_id")
        key = (league_id, team_id)
        if key in seen:
            continue
        seen.add(key)
        clean = {"league_id": league_id, "team_id": team_id}
        if row.get("team"):
            clean["team"] = str(row["team"])[:120]
        out.append(clean)
    return out


def _normalise_notifications(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("notifications must be an object")
    allowed = {"weekly", "material_change", "match_morning", "quiet", "paused"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unsupported notification fields: {sorted(unknown)}")
    if any(not isinstance(flag, bool) for flag in value.values()):
        raise ValueError("notification values must be booleans")
    return value


def update_public_preferences(
    kv: KVStore, user_id: str, updates: dict, plan: str = "free",
) -> dict:
    unknown = set(updates) - _ALLOWED_PREFERENCE_KEYS
    if unknown:
        raise ValueError(f"unsupported preference fields: {sorted(unknown)}")
    updates = dict(updates)
    if "teams" in updates:
        updates["teams"] = _normalise_teams(updates["teams"], plan)
        record = export_user_data(kv, user_id)
        sample = (record or {}).get("club_watch_sample")
        if plan == "free" and sample:
            sample_identity = (
                str(sample.get("league_id") or ""),
                str(sample.get("team_id") or ""),
            )
            requested_identity = (
                str(updates["teams"][0].get("league_id") or ""),
                str(updates["teams"][0].get("team_id") or ""),
            ) if updates["teams"] else ("", "")
            if requested_identity != sample_identity:
                sample_label = sample.get("team") or sample_identity[1]
                raise ValueError(
                    "Your free Club Watch sample is already assigned to "
                    f"{sample_label}. Upgrade to follow another club.")
    if "notifications" in updates:
        updates["notifications"] = _normalise_notifications(
            updates["notifications"])
    return update_preferences(kv, user_id, **updates)


def get_or_create_club_watch_sample(
    kv: KVStore, user_id: str, league_id: str, team_id: str, builder,
) -> dict:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    existing = record.get("club_watch_sample")
    if existing:
        if (
            existing.get("league_id") != league_id
            or existing.get("team_id") != team_id
        ):
            sample_label = existing.get("team") or existing.get("team_id")
            raise ValueError(
                "Your free Club Watch sample is already assigned to "
                f"{sample_label}. Upgrade to follow another club.")
        return existing
    sample = builder()
    if sample.get("league_id") != league_id or sample.get("team_id") != team_id:
        raise ValueError("sample identity did not match the followed club")
    update_preferences(kv, user_id, club_watch_sample=sample)
    return sample


def update_subscription_lifecycle(kv: KVStore, user_id: str, **updates) -> dict:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    lifecycle = dict(record.get("subscription_lifecycle") or {})
    lifecycle.update({key: value for key, value in updates.items()
                      if value is not None})
    return update_preferences(kv, user_id, subscription_lifecycle=lifecycle)


CANCELLATION_REASON_CATEGORIES = {
    "too_expensive", "not_using_enough", "seasonal_pause",
    "forecasts_not_useful", "notifications", "missing_club_or_league",
    "technical_problem", "switched_product", "other",
}

SUPPORT_CATEGORIES = {
    "account_access", "billing", "refund", "data_quality", "wrong_club",
    "forecast_question", "notification", "privacy", "feature_request", "other",
}

TESTIMONIAL_CATEGORIES = {
    "saved_time", "understood_change", "prepared_for_match",
    "followed_race", "trusted_forecast", "other",
}


def append_customer_evidence(
    kv: KVStore,
    user_id: str,
    *,
    kind: str,
    category: str,
    message: str,
    contact_consent: bool = False,
    publication_consent: bool = False,
) -> dict:
    """Persist categorized evidence with explicit contact/publication consent.

    Private message text stays in the user's exportable and deletable account
    record. Aggregate growth events receive only category and consent state.
    """
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    categories = {
        "cancellation": CANCELLATION_REASON_CATEGORIES,
        "support": SUPPORT_CATEGORIES,
        "testimonial": TESTIMONIAL_CATEGORIES,
    }
    if kind not in categories:
        raise ValueError("kind must be cancellation, support, or testimonial")
    if category not in categories[kind]:
        raise ValueError(f"unsupported {kind} category")
    clean_message = str(message or "").strip()
    if not clean_message:
        raise ValueError("message is required")
    if len(clean_message) > 2000:
        raise ValueError("message must be at most 2000 characters")
    if not isinstance(contact_consent, bool) or not isinstance(
        publication_consent, bool
    ):
        raise ValueError("consent values must be booleans")
    if kind == "testimonial" and not publication_consent:
        raise ValueError(
            "testimonial capture requires explicit publication consent")
    if kind != "testimonial" and publication_consent:
        raise ValueError(
            "publication consent is accepted only for testimonials")

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    evidence = {
        "evidence_id": f"evidence:{uuid.uuid4()}",
        "kind": kind,
        "category": category,
        "message": clean_message,
        "contact_consent": contact_consent,
        "publication_consent": publication_consent,
        "consent_version": "customer-evidence-v1",
        "created_at": now,
    }
    rows = list(record.get("customer_evidence") or [])
    rows.append(evidence)
    update_preferences(kv, user_id, customer_evidence=rows[-100:])
    return evidence


def event_cursor_key(league_id: str, team_id: str) -> str:
    """League-qualified cursor key.

    Team ids deliberately survive competition changes and name collisions can
    exist across countries. A bare team id therefore cannot safely identify
    one event stream; the league-qualified key can.
    """
    return f"{league_id}:{team_id}"


def set_seen_cursor(kv: KVStore, user_id: str, team_id: str, event_id: str,
                    league_id: str | None = None) -> dict:
    record = export_user_data(kv, user_id)
    if record is None:
        raise KeyError(user_id)
    cursors = dict(record.get("last_seen_event_id_by_team") or {})
    cursors[event_cursor_key(league_id, team_id) if league_id else team_id] = event_id
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
