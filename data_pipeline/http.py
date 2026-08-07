"""Shared HTTP helpers for ESPN API adapters.

urllib3.disable_warnings() is called once at import time so that
InsecureRequestWarning is suppressed in every adapter that imports this
module — no adapter needs its own suppress call.

Every ESPN adapter in the pipeline goes through `espn_get`, so the throttle and
retry below are the pipeline's only rate-limit defence and are deliberately
placed here rather than in any one caller.
"""
from __future__ import annotations

import logging
import random
import threading
import time

import requests
import urllib3

urllib3.disable_warnings()

logger = logging.getLogger("espn_http")

_HDR = {"User-Agent": "Mozilla/5.0"}

# ESPN rate-limits by IP and answers with 403 — not 429 — once tripped, and it
# then refuses EVERY endpoint, not just the one that crossed the line. Measured
# 2026-08-07: `concacaf.leagues.cup/scoreboard` returned 200, and within a
# minute of a handful of further calls that same URL and `uefa.champions` (which
# had also just returned 200) were both 403. So a 403 here is a back-off signal,
# not an authorisation verdict, and must be retried rather than surfaced.
#
# The cost of not doing this was silent and site-wide: espn_get had no retry,
# _fetch turned the failure into "season not refreshed", and the Leagues Cup
# match cache sat at 77 rows from 2024 while a live 2026 tournament published a
# forecast with 0 of 54 results. The scheduled fast refresh was failing outright
# for the same reason (403 on bol.1, runs 31221990714 and 31218282187).
#
# 400 and 404 are NOT retried: ESPN returns 400 for a date window it dislikes
# (see espn_continental._fetch) and 404 for a slug that does not exist. Both are
# deterministic, and retrying them only slows a build down on its way to the
# same answer.
_RETRY_STATUS = frozenset({403, 408, 429, 500, 502, 503, 504})

_MAX_ATTEMPTS = 4
_BASE_DELAY = 2.0          # seconds; doubles per attempt
_MAX_DELAY = 30.0
_MIN_INTERVAL = 0.35       # floor between consecutive requests, process-wide

_last_request = 0.0
_lock = threading.Lock()


def _throttle() -> None:
    """Keep a floor between consecutive ESPN requests.

    Cheaper than backing off after the fact: the build loops over ~70 leagues
    and several continental competitions back to back, which is exactly the
    burst shape that trips the limit. Callers that already sleep are unaffected
    — this only ever adds the remainder.
    """
    global _last_request
    with _lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _retry_after(response: requests.Response, fallback: float) -> float:
    """Honour Retry-After when present, else the caller's backoff."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return fallback
    try:
        return min(float(raw), _MAX_DELAY)
    except ValueError:                      # HTTP-date form; not worth parsing
        return fallback


def espn_get(url: str, params: dict | None = None, timeout: int = 30,
             attempts: int | None = None) -> dict:
    """GET an ESPN API endpoint and return parsed JSON.

    Retries rate-limit and transient server statuses with exponential backoff
    and jitter; raises on anything else, and re-raises the last error once the
    attempts are spent. Raises requests.RequestException on HTTP error or
    network failure, so existing callers keep their current contract.

    `attempts` resolves from the module default at CALL time rather than as a
    default argument, so tests can turn retries off by setting _MAX_ATTEMPTS.
    A few tests reach ESPN for real, and against a rate-limited host each one
    would otherwise pay the full backoff ladder — that took the suite from 75s
    to 9m41s before this was made overridable.
    """
    attempts = attempts if attempts is not None else _MAX_ATTEMPTS
    last: Exception | None = None
    for attempt in range(attempts):
        _throttle()
        try:
            r = requests.get(url, params=params, headers=_HDR,
                             verify=False, timeout=timeout)
        except requests.RequestException as e:
            last = e                          # connection reset / timeout
        else:
            if r.status_code not in _RETRY_STATUS:
                r.raise_for_status()          # 400/404 and friends surface now
                return r.json()
            last = requests.HTTPError(
                f"{r.status_code} {r.reason} for url: {r.url}", response=r)

        if attempt == attempts - 1:
            break
        # Jitter so a loop over many leagues does not retry in lockstep and
        # rebuild the very burst that tripped the limit.
        delay = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY) * (0.5 + random.random())
        if isinstance(last, requests.HTTPError) and last.response is not None:
            delay = _retry_after(last.response, delay)
        logger.info("ESPN %s — retrying in %.1fs (attempt %d/%d)",
                    last, delay, attempt + 1, attempts)
        time.sleep(delay)

    raise last
