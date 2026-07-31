"""Single Vercel Python function that routes the versioned HTTP API."""
from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from api.account import data as account_data
from api.account import feedback as account_feedback
from api.auth import callback, logout, refresh, request
from api.billing import checkout, portal as billing_portal
from api.intel import (
    analytics, ask, briefing, cards, events, export, journal, me, preferences, sample, scenario, team, workspaces,
)
from api.admin import open_access as admin_open_access
from api.admin import pricing as admin_pricing
from api.admin import checkout as admin_checkout
from api.admin import delivery as admin_delivery
from api.admin import growth as admin_growth
from api.admin import intelligence_artifacts as admin_intelligence_artifacts
from api.pub import card as public_card
from api.pub import config as public_config
from api.pub import subscribe as public_subscribe
from api.pub import unsubscribe as public_unsubscribe
from api.resend import webhook as resend_webhook
from api.stripe import webhook as stripe_webhook
from server.http_headers import Headers


def _query(path: str) -> dict:
    parsed = parse_qs(urlparse(path).query, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _dispatch(method: str, path: str, headers: dict, body: bytes):
    route = urlparse(path).path
    for prefix in ("/v1", "/api"):
        if route.startswith(prefix + "/"):
            route = route[len(prefix):]
            break
    query = _query(path)
    if route == "/api" and query.get("path"):
        route = "/" + query.pop("path").lstrip("/")
    if route == "/auth/request":
        return request.handle(method, headers, body)
    if route == "/auth/callback":
        return callback.handle(method, headers, query)
    if route == "/auth/refresh":
        return refresh.handle(method, headers, body)
    if route == "/auth/logout":
        return logout.handle(method, headers, body)
    if route == "/billing/checkout":
        return checkout.handle(method, headers, body)
    if route == "/billing/portal":
        return billing_portal.handle(method, headers, body)
    if route == "/stripe/webhook":
        return stripe_webhook.handle(method, headers, body)
    if route == "/resend/webhook":
        return resend_webhook.handle(method, headers, body)
    if route == "/intel/me":
        return me.handle(method, headers)
    if route == "/intel/analytics":
        return analytics.handle(method, headers, body)
    if route == "/intel/team":
        return team.handle(method, headers, query)
    if route == "/intel/sample":
        return sample.handle(method, headers, query)
    if route == "/intel/preferences":
        return preferences.handle(method, headers, body)
    if route == "/intel/scenario":
        return scenario.handle(method, headers, body)
    if route == "/intel/ask":
        return ask.handle(method, headers, body)
    if route == "/intel/events":
        return events.handle(method, headers, query, body)
    if route == "/intel/briefing":
        return briefing.handle(method, headers, query)
    if route == "/intel/journal":
        return journal.handle(method, headers, query, body)
    if route == "/intel/export":
        return export.handle(method, headers, query)
    if route == "/intel/workspaces":
        return workspaces.handle(method, headers, query, body)
    if route == "/intel/cards":
        return cards.handle(method, headers, body)
    if route == "/account/data":
        return account_data.handle(method, headers, body)
    if route == "/account/feedback":
        return account_feedback.handle(method, headers, body)
    if route == "/public/config":
        return public_config.handle(method, headers)
    if route in ("/admin/open-access", "/admin/open_access"):
        return admin_open_access.handle(method, headers, body)
    if route == "/admin/pricing":
        return admin_pricing.handle(method, headers, body)
    if route == "/admin/checkout":
        return admin_checkout.handle(method, headers, body)
    if route == "/admin/delivery":
        return admin_delivery.handle(method, headers, body)
    if route == "/admin/growth":
        return admin_growth.handle(method, headers)
    if route == "/admin/intelligence-artifacts":
        return admin_intelligence_artifacts.handle(method, headers, body)
    if route == "/public/card":
        return public_card.handle(method, headers, query)
    if route == "/public/unsubscribe":
        return public_unsubscribe.handle(method, headers, query)
    if route == "/public/subscribe":
        return public_subscribe.handle(method, headers, body)
    return 404, {"Content-Type": "application/json"}, b'{"error":"not found"}'


def _allowed_origin(origin: str) -> str | None:
    configured = {value.strip() for value in os.environ.get(
        "ALLOWED_ORIGINS", "https://entenser.com,http://localhost:8000,http://127.0.0.1:8000"
    ).split(",") if value.strip()}
    return origin if origin in configured else None


class handler(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        headers = Headers(self.headers.items())
        try:
            status, response_headers, payload = _dispatch(
                self.command, self.path, headers, body)
        except RuntimeError:
            status, response_headers, payload = (
                503, {"Content-Type": "application/json"},
                b'{"error":"service configuration unavailable"}')
        if not any(key.lower() == "content-type" for key in response_headers):
            response_headers["Content-Type"] = "application/json"
        if not any(key.lower() == "content-length" for key in response_headers):
            response_headers["Content-Length"] = str(len(payload))
        origin = _allowed_origin(self.headers.get("Origin", ""))
        self.send_response(status)
        for key, value in response_headers.items():
            self.send_header(key, value)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PATCH(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def do_OPTIONS(self):
        origin = _allowed_origin(self.headers.get("Origin", ""))
        self.send_response(204)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
            self.send_header("Vary", "Origin")
        self.end_headers()

    def log_message(self, format, *args):
        return
