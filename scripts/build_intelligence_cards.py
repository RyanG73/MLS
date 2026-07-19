#!/usr/bin/env python3
"""Render a deterministic Intelligence conversation card for visual regression."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from server.conversation_card import render_card_png
from server.intelligence_service import IntelligenceService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--template", choices=[
        "material_move", "highest_leverage", "turning_point",
        "race_comparison", "receipt",
    ], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = IntelligenceService().public_card_payload(
        args.league, args.team_id, args.template)
    payload["verification_url"] = "https://api.entenser.com/v1/public/card?id=preview"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(render_card_png(payload, payload["verification_url"]))
    args.output.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
