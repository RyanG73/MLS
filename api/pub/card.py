"""Public-safe card verification page, JSON record, and canonical PNG."""
from __future__ import annotations

import json
import re

from server.api_support import ApiError, guarded, response
from server.conversation_card import render_card_png, render_verification_html
from server.kv_client import get_kv

_CARD_ID = re.compile(r"^[a-f0-9]{20}$")


def handle(method: str, headers: dict, query: dict):
    def run():
        if method != "GET":
            raise ApiError(405, "method not allowed")
        card_id = query.get("id", "")
        if not _CARD_ID.fullmatch(card_id):
            raise ApiError(400, "invalid card id")
        raw = get_kv().get(f"public_card:{card_id}")
        if raw is None:
            raise ApiError(404, "card not found")
        payload = json.loads(raw)
        if payload.get("public_safe") is not True:
            raise ApiError(404, "card not public")
        api_base = query.get("_base", "")
        image_url = api_base or f"/v1/public/card?id={card_id}&format=png"
        format_name = query.get("format", "html")
        if format_name == "png":
            png = render_card_png(payload, f"/v1/public/card?id={card_id}")
            return 200, {
                "Content-Type": "image/png",
                "Cache-Control": "public, max-age=31536000, immutable",
                "Content-Length": str(len(png)),
            }, png
        if format_name == "json":
            return response(200, payload, {"Cache-Control": "public, max-age=300"})
        if format_name != "html":
            raise ApiError(400, "format must be html, json, or png")
        page = render_verification_html(payload, image_url)
        return 200, {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=300",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'",
            "Content-Length": str(len(page)),
        }, page
    return guarded(run)
