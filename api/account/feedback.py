"""Authenticated, consent-aware customer evidence capture."""
from __future__ import annotations

from server.api_support import ApiError, account_user, body_json, guarded, response
from server.growth_events import record_event
from server.intel_store import append_customer_evidence, export_user_data
from server.kv_client import get_kv


def _safe(row: dict) -> dict:
    return {
        key: row.get(key)
        for key in (
            "evidence_id", "kind", "category", "message", "contact_consent",
            "publication_consent", "consent_version", "created_at",
        )
    }


def handle(method: str, headers: dict, body: bytes = b"{}"):
    def run():
        user_id = account_user(headers)
        if method == "GET":
            record = export_user_data(get_kv(), user_id)
            if record is None:
                raise ApiError(404, "user not found")
            return response(
                200, {"items": [_safe(row) for row in
                                record.get("customer_evidence") or []]})
        if method == "POST":
            payload = body_json(body)
            try:
                evidence = append_customer_evidence(
                    get_kv(),
                    user_id,
                    kind=str(payload.get("kind") or ""),
                    category=str(payload.get("category") or ""),
                    message=str(payload.get("message") or ""),
                    contact_consent=payload.get("contact_consent", False),
                    publication_consent=payload.get(
                        "publication_consent", False),
                )
            except KeyError as exc:
                raise ApiError(404, "user not found") from exc
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            event = {
                "cancellation": "cancellation_reason_submitted",
                "support": "support_request_categorized",
                "testimonial": "testimonial_consented",
            }[evidence["kind"]]
            consent_level = (
                "publication"
                if evidence["publication_consent"]
                else "contact"
                if evidence["contact_consent"]
                else "none"
            )
            record_event(
                get_kv(),
                event,
                event_id=f"{event}:{evidence['evidence_id']}",
                user_id=user_id,
                properties={
                    "reason": evidence["category"],
                    "consent_level": consent_level,
                    "surface": "account",
                },
            )
            return response(201, _safe(evidence))
        raise ApiError(405, "method not allowed")
    return guarded(run)
