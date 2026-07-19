"""
ntfy.sh push notification wrapper.

Free service, no signup. Topic configured via NTFY_TOPIC env var.
Subscribe to the topic on iOS/Android via the ntfy app to receive pushes.
"""

import os
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_NTFY_BASE_URL = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh")


def _topic() -> Optional[str]:
    return os.environ.get("NTFY_TOPIC")


def send_notification(
    title: str,
    message: str,
    priority: str = "default",
    tags: Optional[list[str]] = None,
    click_url: Optional[str] = None,
) -> bool:
    """
    Send a push to ntfy.sh.
    priority: min, low, default, high, urgent
    tags: emoji tags (e.g. ['warning', 'soccer'])
    Returns True on success.
    """
    topic = _topic()
    if not topic:
        logger.debug("NTFY_TOPIC not set; skipping notification.")
        return False

    headers = {
        "Title":    title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    if click_url:
        headers["Click"] = click_url

    try:
        resp = requests.post(
            f"{_NTFY_BASE_URL}/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("ntfy.sh send failed: %s", exc)
        return False


def notify_value_bet(home: str, away: str, outcome: str, edge_pct: float, odds: float) -> None:
    send_notification(
        title=f"⚽ Value Bet: {home} vs {away}",
        message=f"Back {outcome} @ {odds:.2f}\nEdge: +{edge_pct:.1f}%",
        priority="high",
        tags=["soccer_ball", "money_with_wings"],
    )


def notify_drift_alert(brier_recent: float, brier_baseline: float, pct_change: float) -> None:
    send_notification(
        title="⚠️ Model Drift Detected",
        message=(
            f"Recent Brier: {brier_recent:.4f}\n"
            f"Baseline:     {brier_baseline:.4f}\n"
            f"Δ: +{pct_change:.1f}% worse"
        ),
        priority="urgent",
        tags=["warning"],
    )


def notify_pipeline_failure(step: str, error: str) -> None:
    send_notification(
        title=f"🚨 MLS Pipeline Failure: {step}",
        message=error[:500],
        priority="urgent",
        tags=["x"],
    )


def notify_betting_paused(reason: str) -> None:
    send_notification(
        title="⛔ Betting Paused",
        message=reason,
        priority="urgent",
        tags=["no_entry"],
    )
