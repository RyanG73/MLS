#!/usr/bin/env python3
"""Select and send intelligence alerts; defaults to dry-run shadow mode."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import os

from server.email_client import get_magic_link_sender
from server.intel_store import export_user_data, update_preferences
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.kv_client import get_kv
from server.send_ledger import (
    already_sent, record_delivery, retry_allowed, within_team_cap,
)
from server.unsubscribe import issue_unsubscribe_token

TEMPLATE_VERSION = "material-alert-v1"


def candidates_for_user(user: dict) -> list[dict]:
    service = IntelligenceService()
    selected = []
    threshold = float(user.get("threshold_pp", 5))
    sent_by_team = (user.get("alert_state") or {}).get("last_sent_at_by_team") or {}
    for favorite in user.get("teams", []):
        team_id = favorite.get("team_id")
        if within_team_cap(sent_by_team.get(team_id)):
            continue
        try:
            record = service.get_team(favorite["league_id"], team_id)
        except ArtifactNotFound:
            continue
        events = (record["features"]["7"]["data"] or {}).get("candidates") or []
        events = [event for event in events
                  if abs(event.get("delta_pp") or 0) >= threshold
                  or event.get("event_type") == "threshold_crossing"]
        if events:
            selected.append({"record": record, "events": events[:3]})
    return selected


def render_alert(user: dict, groups: list[dict]) -> tuple[str, str, str]:
    rows_html, rows_text = [], []
    for group in groups:
        record, event = group["record"], group["events"][0]
        target = event.get("target_metric") or record["target_metric"]
        before, after = event.get("before_pct"), event.get("after_pct")
        line = (f"{record['team']}: {target} moved from {before:.1f}% to {after:.1f}%."
                if before is not None and after is not None
                else f"{record['team']}: a material {target} update is available.")
        rows_html.append(f"<li>{html.escape(line)}</li>")
        rows_text.append(f"- {line}")
    token = issue_unsubscribe_token(user["user_id"], "material_change")
    base = os.environ.get("PUBLIC_API_URL", "https://api.entenser.com/v1").rstrip("/")
    unsubscribe = f"{base}/public/unsubscribe?token={token}"
    subject = "What changed for your teams"
    html_body = ("<h1>What changed</h1><ul>" + "".join(rows_html)
                 + f'</ul><p><a href="{html.escape(unsubscribe, quote=True)}">'
                   "Unsubscribe from material-change alerts</a></p>")
    text_body = ("What changed\n\n" + "\n".join(rows_text)
                 + f"\n\nUnsubscribe: {unsubscribe}")
    return subject, html_body, text_body


def process_user(user_id: str, send: bool) -> dict:
    kv = get_kv()
    user = export_user_data(kv, user_id)
    if user is None or user.get("plan") not in {"trial", "intel", "creator"}:
        return {"status": "skipped", "reason": "not entitled"}
    if not user.get("notifications", {}).get("material_change", False):
        return {"status": "skipped", "reason": "notifications disabled"}
    if user.get("unsubscribe_state", {}).get("material_change"):
        return {"status": "skipped", "reason": "unsubscribed"}
    if user.get("alert_state", {}).get("bounced"):
        return {"status": "skipped", "reason": "bounced"}
    groups = candidates_for_user(user)
    if not groups:
        return {"status": "skipped", "reason": "no uncapped material events"}
    event_ids = sorted({event["event_id"] for group in groups for event in group["events"]})
    if already_sent(kv, user_id, event_ids, TEMPLATE_VERSION, include_shadow=not send):
        return {"status": "skipped", "reason": "deduplicated"}
    if not retry_allowed(kv, user_id, event_ids, TEMPLATE_VERSION):
        return {"status": "skipped", "reason": "retry limit reached"}
    team_ids = [group["record"]["team_id"] for group in groups]
    if not send:
        record_delivery(kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
                        template_version=TEMPLATE_VERSION, status="shadow")
        return {"status": "shadow", "teams": len(team_ids), "events": len(event_ids)}
    sender = get_magic_link_sender()
    if not hasattr(sender, "send_message"):
        return {"status": "failed", "reason": "real email provider is not configured"}
    subject, html_body, text_body = render_alert(user, groups)
    try:
        provider_id = sender.send_message(
            to=user["email"], subject=subject, html_body=html_body,
            text_body=text_body,
            idempotency_key=delivery_key(user_id, event_ids, TEMPLATE_VERSION),
        )
    except Exception as exc:
        record_delivery(kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
                        template_version=TEMPLATE_VERSION, status="failed",
                        error_code=type(exc).__name__)
        return {"status": "failed", "reason": type(exc).__name__}
    record_delivery(kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
                    template_version=TEMPLATE_VERSION, status="sent",
                    provider_id=provider_id)
    state = dict(user.get("alert_state") or {})
    sent = dict(state.get("last_sent_at_by_team") or {})
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for team_id in team_ids:
        sent[team_id] = now
    state["last_sent_at_by_team"] = sent
    update_preferences(kv, user_id, alert_state=state)
    return {"status": "sent", "teams": len(team_ids), "events": len(event_ids)}


def delivery_key(user_id: str, event_ids: list[str], template_version: str) -> str:
    from server.send_ledger import delivery_key as key
    return key(user_id, event_ids, template_version)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--user")
    args = parser.parse_args()
    live = args.send
    if live and (os.environ.get("INTELLIGENCE_SENDS_ENABLED") != "true"
                 or os.environ.get("INTELLIGENCE_SENDS_OWNER_APPROVED") != "true"):
        print("[notifications] live sends blocked by kill switch or owner approval")
        return 2
    kv = get_kv()
    user_ids = [args.user] if args.user else sorted(kv.members("users:index"))
    counts = {}
    for user_id in user_ids:
        result = process_user(user_id, live)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    print(f"[notifications] mode={'send' if live else 'shadow'} users={len(user_ids)} {counts}")
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
