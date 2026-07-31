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
from server.send_ledger import (
    already_sent, record_delivery, record_delivery_outcome, retry_allowed,
)
from server.unsubscribe import issue_unsubscribe_token

TEMPLATE_VERSION = "personalized-briefing-v2"
MIN_DAYS = {
    "active_matchweek": 6,
    "short_lull": 10,
    "scheduled_break": 14,
    "offseason": 28,
    "preseason": 21,
}


def _cadence_allows(kv, user_id: str, modes: set[str],
                    prematch_due: bool = False) -> bool:
    if prematch_due:
        return True
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
        stake = row["briefing"]["sections"].get("prematch_stakes")
        stake_html, stake_text = "", ""
        if stake and stake.get("delivery_date") == briefing["local_date"]:
            baseline = stake.get("baseline_pct")
            baseline_text = (
                "Unavailable" if baseline is None else f"{baseline:.1f}%")
            outcome_html = []
            outcome_text = []
            for outcome in stake.get("outcomes", []):
                pct = outcome.get("pct")
                delta = outcome.get("delta_pp")
                pct_text = "Unavailable" if pct is None else f"{pct:.1f}%"
                delta_text = "" if delta is None else f" ({delta:+.1f}pp)"
                outcome_html.append(
                    f"<li><strong>{html.escape(outcome['label'])}:</strong> "
                    f"{pct_text}{delta_text}</li>")
                outcome_text.append(
                    f"{outcome['label']}: {pct_text}{delta_text}")
            target = str(stake.get("target_label") or stake.get(
                "target_metric") or "target").replace("_", " ")
            stake_html = (
                f"<h3>What’s at stake: {html.escape(stake['home'])} vs "
                f"{html.escape(stake['away'])}</h3>"
                f"<p>Scenario baseline for {html.escape(target)}: "
                f"{baseline_text}</p><ul>"
                + "".join(outcome_html) + "</ul>"
            )
            stake_text = (
                f"\nWhat’s at stake: {stake['home']} vs {stake['away']}\n"
                f"Scenario baseline for {target}: {baseline_text}\n"
                + "\n".join(outcome_text)
            )
        html_rows.append(
            f"<h2>{html.escape(row['team'])}</h2><p>{html.escape(summary)}</p>"
            f"<p><small>Forecast as of {html.escape(row['generated'])} · "
            f"Snapshot {html.escape(row['snapshot_id'])}</small></p>"
            + stake_html)
        text_rows.append(
            f"{row['team']}\n{summary}\nForecast as of {row['generated']} · "
            f"Snapshot {row['snapshot_id']}" + stake_text)
    token = issue_unsubscribe_token(user["user_id"], "weekly")
    base = os.environ.get("PUBLIC_API_URL", "https://api.entenser.com/v1").rstrip("/")
    url = f"{base}/public/unsubscribe?token={token}"
    subject = "Your Entenser Club Watch briefing"
    return (
        subject,
        "<h1>Your Club Watch briefing</h1>" + "".join(html_rows)
        + f'<p><a href="{html.escape(url, quote=True)}">Unsubscribe</a></p>',
        "Your Club Watch briefing\n\n" + "\n\n".join(text_rows)
        + f"\n\nUnsubscribe: {url}",
    )


def process_user(user_id: str, send: bool) -> dict:
    kv = get_kv()
    user = export_user_data(kv, user_id)
    if user is None or user.get("plan") not in {"trial", "intel", "creator"}:
        return {"status": "skipped", "reason": "not entitled"}
    followed_ids = [row.get("team_id") for row in user.get("teams", [])
                    if row.get("team_id")]
    def suppressed(reason: str) -> dict:
        record_delivery_outcome(
            kv, user_id=user_id, team_ids=followed_ids, event_ids=[],
            template_version=TEMPLATE_VERSION, status="suppressed",
            reason=reason)
        return {"status": "skipped", "reason": reason}
    if user.get("notifications", {}).get("paused"):
        return suppressed("delivery paused")
    if user.get("notifications", {}).get("quiet"):
        return suppressed("quiet mode")
    notifications = user.get("notifications", {})
    if not (notifications.get("weekly", False)
            or notifications.get("match_morning", False)):
        return suppressed("briefing disabled")
    if (user.get("unsubscribe_state", {}).get("weekly")
            or user.get("alert_state", {}).get("bounced")):
        return suppressed("unsubscribed or bounced")
    briefing = build_user_briefing(user_id)
    if not briefing["should_send"]:
        return {"status": "skipped", "reason": briefing["skip_reason"]}
    if briefing["prematch_due"] and not notifications.get(
            "match_morning", False):
        briefing["prematch_due"] = False
        briefing["due_fixture_ids"] = []
        for row in briefing["teams"]:
            (row.get("briefing") or {}).get("sections", {}).pop(
                "prematch_stakes", None)
    if not notifications.get("weekly", False) and not briefing["prematch_due"]:
        return {"status": "skipped", "reason": "match morning not due"}
    modes = {row["calendar_mode"]["mode"] for row in briefing["teams"]}
    if not _cadence_allows(
            kv, user_id, modes, prematch_due=briefing["prematch_due"]):
        return suppressed("adaptive cadence cap")
    event_ids = sorted({
        row["briefing"]["sections"]["team_pulse"]["snapshot_id"]
        for row in briefing["teams"]
    } | set(briefing["due_fixture_ids"]))
    team_ids = [row["team_id"] for row in briefing["teams"]]
    if already_sent(kv, user_id, event_ids, TEMPLATE_VERSION, include_shadow=not send):
        record_delivery_outcome(
            kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
            template_version=TEMPLATE_VERSION, status="duplicated",
            reason="deduplicated")
        return {"status": "skipped", "reason": "deduplicated"}
    if not retry_allowed(kv, user_id, event_ids, TEMPLATE_VERSION):
        record_delivery_outcome(
            kv, user_id=user_id, team_ids=team_ids, event_ids=event_ids,
            template_version=TEMPLATE_VERSION, status="suppressed",
            reason="retry limit reached")
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
