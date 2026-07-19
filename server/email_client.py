"""Resend email adapter plus development sender selection."""
from __future__ import annotations

import hashlib
import html
import os

import requests

from server.intel_auth import RecordingSender


class ResendSender:
    API_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_address: str, timeout: float = 8.0) -> None:
        self.api_key = api_key
        self.from_address = from_address
        self.timeout = timeout

    def send_message(self, *, to: str, subject: str, html_body: str,
                     text_body: str, idempotency_key: str) -> str:
        response = requests.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key[:256],
            },
            json={
                "from": self.from_address,
                "to": [to],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        provider_id = response.json().get("id")
        if not provider_id:
            raise RuntimeError("Resend response did not contain an email id")
        return provider_id

    def send(self, email: str, magic_link_url: str) -> None:
        escaped = html.escape(magic_link_url, quote=True)
        key = "magic-" + hashlib.sha256(magic_link_url.encode()).hexdigest()
        self.send_message(
            to=email,
            subject="Sign in to Entenser",
            html_body=f'<p><a href="{escaped}">Sign in to Entenser</a></p>'
                      '<p>This link expires in 15 minutes and can be used once.</p>',
            text_body=(f"Sign in to Entenser: {magic_link_url}\n"
                       "This link expires in 15 minutes and can be used once."),
            idempotency_key=key,
        )


_sender = None


def get_magic_link_sender():
    global _sender
    if _sender is not None:
        return _sender
    api_key = os.environ.get("RESEND_API_KEY")
    from_address = os.environ.get("RESEND_FROM_EMAIL") or os.environ.get("RESEND_FROM")
    if api_key and from_address:
        _sender = ResendSender(api_key, from_address)
    elif os.environ.get("ENTENSER_ENV") == "production":
        raise RuntimeError("RESEND_API_KEY and RESEND_FROM_EMAIL are required in production")
    else:
        _sender = RecordingSender()
    return _sender
