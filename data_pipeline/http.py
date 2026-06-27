"""Shared HTTP helpers for ESPN API adapters.

urllib3.disable_warnings() is called once at import time so that
InsecureRequestWarning is suppressed in every adapter that imports this
module — no adapter needs its own suppress call.
"""
from __future__ import annotations

import requests
import urllib3

urllib3.disable_warnings()

_HDR = {"User-Agent": "Mozilla/5.0"}


def espn_get(url: str, params: dict | None = None, timeout: int = 30) -> dict:
    """GET an ESPN API endpoint and return parsed JSON.

    Raises requests.RequestException on HTTP error or network failure.
    Callers that need retry logic should wrap this in a loop.
    """
    r = requests.get(url, params=params, headers=_HDR, verify=False, timeout=timeout)
    r.raise_for_status()
    return r.json()
