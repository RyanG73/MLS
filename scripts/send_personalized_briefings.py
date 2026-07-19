#!/usr/bin/env python3
"""Send adaptive personalized briefings; defaults to shadow mode."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os

from scripts.build_personalized_briefing import build_user_briefing
from server.email_client import get_magic_link_sender
from server.intel_store import export_user_data
from server.kv_client import get_kv
from server.send_ledger import already_sent, record_delivery, retry_allowed
from server.unsubscribe import issue_unsubscribe_token

TEMPLATE_VERSION = "personalized-briefing-v1"
MIN_DAYS = {
    "active_matchweek": 6,
    "short_lull": 10,
    "scheduled_break": 14,
    "offseason": 28,
    "preseason": 21,
}


def _cadence_allows(kv, user_id: str, modes: set[str]) -> bool:
    raw = kv.get(f"briefing:last:{user_id}")
    if raw is None:
        return True
    last = dt.datetime.fromisoformat(json.loads(raw)["sent_at"])
    wait = min(MIN_DAYS.get(mode, 14) for mode in modes) if modes else 14
    return dt.datetime.now(dt.timezone.utc) - last >= dt.timedelta(days=wait)


def _render(user: dict, briefing: dict) -> tuple[str, str, str]:
    html_rows, text_rows = [], []
    for row in briefing["teams"]:
        pulse = row["briefing"]["sections"]["team_pulse"]
        summary = pulse["summary"]
        html_rows.append(
            f"<h2>{html.escape(row['team'])}</h2><p>{html.escape(summary)}</p>")
        text_rows.append(f"{row['team']}\n{summary}")
    token = issue_unsubscribe_token(user["user_id"], "weekly")
    base = os.environ.get("PUBLIC_API_URL", "https://api.entenser.com/v1").rstrip("/")
    url = f"{base}/public/unsubscribe?token={token}"
    subject = "Your Entenser team briefing"
    return (
        subject,
        "<h1>Your team briefing</h1>" + "".join(html_rows)
        + f'<p><a href="{html.escape(url, quote=True)}">Unsubscribe</a></p>',
        "Your team briefing\n\n" + "\n\n".join(text_rows)
        + f"\n\nUnsubscribe: {url}",
    )


def process_user(user_id: str, send: bool) -> dict:
    kv = get_kv()
    user = export_user_data(kv, user_id)
    if user is None or user.get("plan") not in {"trial", "intel", "creator"}:
        return {"status": "skipped", "reason": "not entitled"}
    if not user.get("notifications", {}).get("weekly", False):
        return {"status": "skipped", "reason": "briefing disabled"}
    if (user.get("unsubscribe_state", {}).get("weekly")
            or user.get("alert_state", {}).get("bounced")):
        return {"status": "skipped", "reason": "suppressed"}
    briefing = build_user_briefing(user_id)
    if not briefing["should_send"]:
        return {"status": "skipped", "reason": briefing["skip_reason"]}
    modes = {row["calendar_mode"]["mode"] for row in briefing["teams"]}
    if not _cadence_allows(kv, user_id, modes):
        return {"status": "skipped", "reason": "adaptive cadence cap"}
    event_ids = sorted({
        row["briefing"]["sections"]["team_pulse"]["snapshot_id"]
        for row in briefing["teams"]
    })
    team_ids = [row["team_id"] for row in briefing["teams"]]
    if already_sent(kv, user_id, event_ids, TEMPLATE_VERSION, include_shadow=not send):
        return {"status": "skipped", "reason": "deduplicated"}
    if not retry_allowed(kv, user_id, event_ids, TEMPLATE_VERSION):
        return {"status": "skipped", "reason": "retry limit reached"}
    if not send:
        record_delivery(
            kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
            template_version=TEMPLATE_VERSION, status="shadow")
        return {"status": "shadow", "teams": len(team_ids)}
    sender = get_magic_link_sender()
    if not hasattr(sender, "send_message"):
        return {"status": "failed", "reason": "real email provider is not configured"}
    subject, html_body, text_body = _render(user, briefing)
    try:
        provider_id = sender.send_message(
            to=user["email"], subject=subject, html_body=html_body,
            text_body=text_body,
            idempotency_key=f"briefing-{user_id}-{'-'.join(event_ids)}",
        )
    except Exception as exc:
        record_delivery(
            kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
            template_version=TEMPLATE_VERSION, status="failed",
            error_code=type(exc).__name__)
        return {"status": "failed", "reason": type(exc).__name__}
    record_delivery(
        kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
        template_version=TEMPLATE_VERSION, status="sent", provider_id=provider_id)
    kv.set(f"briefing:last:{user_id}", json.dumps({
        "sent_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "modes": sorted(modes),
        "provider_id": provider_id,
    }, separators=(",", ":")))
    return {"status": "sent", "teams": len(team_ids)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--user")
    args = parser.parse_args()
    if args.send and (
        os.environ.get("INTELLIGENCE_SENDS_ENABLED") != "true"
        or os.environ.get("INTELLIGENCE_SENDS_OWNER_APPROVED") != "true"
    ):
        print("[briefings] live sends blocked by kill switch or owner approval")
        return 2
    kv = get_kv()
    user_ids = [args.user] if args.user else sorted(kv.members("users:index"))
    counts = {}
    for user_id in user_ids:
        result = process_user(user_id, args.send)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    print(
        f"[briefings] mode={'send' if args.send else 'shadow'} "
        f"users={len(user_ids)} {counts}")
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
