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
import os
import random
import threading
import time

import requests
import urllib3

urllib3.disable_warnings()

logger = logging.getLogger("espn_http")

# ESPN admits a request on the FIRST token of its User-Agent: a recognised HTTP
# client (curl/*, python-requests/*, urllib3/*, okhttp/*, Go-http-client/*) is
# served and everything else — browser strings included — gets 403. "Mozilla/5.0"
# sat here from the start and stopped working on 2026-08-21, which read exactly
# like the IP rate limit described below and was NOT one: measured 2026-08-23,
# one IP, five trials per agent run in both orders, the split by agent was total
# and the version inside the token was never checked. The table is in
# tests/test_http.py so the next person does not have to re-measure it.
#
# Built from requests' own agent rather than typed, so it cannot drift from the
# client actually making the call. The suffix is free at the filter and says who
# is calling — honesty and availability point the same way here.
_UA_SUFFIX = "(+https://entenser.com)"


def espn_user_agent(client: str | None = None) -> str:
    """The User-Agent ESPN will serve, for a caller using `client`.

    Pass the caller's REAL client token (urllib, httpx, ...) — leading with a
    token that does not match the library making the call is the browser lie in
    a new costume, and the next filter change catches it. Defaults to requests,
    which is what every adapter in this module uses.
    """
    return f"{client or requests.utils.default_user_agent()} {_UA_SUFFIX}"


_HDR = {"User-Agent": espn_user_agent()}

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

# ── circuit breaker ──────────────────────────────────────────────────────────
# Retrying is right for a transient limit and actively harmful for a sustained
# one. ESPN blocks by IP across every endpoint, so once it is refusing, every
# subsequent request in the run is doomed — and with the retry ladder each one
# costs FOUR requests instead of one. Measured on the 2026-08-08 rebuild: 560
# ESPN attempts, of which a large share were retries against a host that had
# already made its answer clear.
#
# After `_BREAKER_THRESHOLD` consecutive rate-limit failures the breaker opens
# and calls fail immediately without touching the network, for `_BREAKER_COOLDOWN`
# seconds. That does two things at once: it stops the build wasting minutes on
# certain failures, and it stops us extending our own block. Any success closes
# it — a single probe after the cooldown is enough to recover.
_BREAKER_THRESHOLD = 5
_BREAKER_COOLDOWN = 120.0

_consecutive_failures = 0
_breaker_opened_at = 0.0


class RateLimited(requests.RequestException):
    """Raised while the breaker is open, so callers treat it as a transport
    failure and keep their existing "season not refreshed" semantics rather
    than mistaking it for an empty result."""


def _breaker_is_open() -> bool:
    global _consecutive_failures
    with _lock:
        if _consecutive_failures < _BREAKER_THRESHOLD:
            return False
        if time.monotonic() - _breaker_opened_at >= _BREAKER_COOLDOWN:
            _consecutive_failures = 0        # cooldown served — allow one probe
            return False
        return True


def _note_outcome(ok: bool) -> None:
    global _consecutive_failures, _breaker_opened_at
    with _lock:
        if ok:
            _consecutive_failures = 0
        else:
            _consecutive_failures += 1
            if _consecutive_failures == _BREAKER_THRESHOLD:
                _breaker_opened_at = time.monotonic()
                logger.warning(
                    "ESPN circuit breaker OPEN after %d consecutive rate-limit "
                    "failures — skipping requests for %.0fs",
                    _BREAKER_THRESHOLD, _BREAKER_COOLDOWN)


def reset_breaker() -> None:
    """Clear breaker state. For tests and for a caller that knows the situation
    changed (a new run, a different host)."""
    global _consecutive_failures, _breaker_opened_at
    with _lock:
        _consecutive_failures, _breaker_opened_at = 0, 0.0


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


# ── fault injection (spec 2026-08-09 §3.6) ───────────────────────────────────
# The router's whole value is that a dark ESPN degrades instead of failing, and
# nothing exercises that path when ESPN is answering — so it rots quietly the
# first time an adapter changes. `ENTENSER_BLOCK_ESPN=1` blackholes every ESPN
# request at this layer, which is the one chokepoint every adapter goes through.
#
# Deliberately an explicit env var rather than a config default: this must be
# impossible to enable by accident, and a run with it set must be a run someone
# asked for. The raised error is a RequestException subclass, so every caller
# takes the transport-failure branch it already has for a 403 storm.
_BLOCK_ENV = "ENTENSER_BLOCK_ESPN"


class Blackholed(requests.RequestException):
    """Raised for every ESPN request while the fault-injection drill is on."""


def espn_is_blocked() -> bool:
    return os.environ.get(_BLOCK_ENV, "").strip() not in ("", "0", "false", "False")


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
    if espn_is_blocked():
        # Checked before the breaker and before any sleep: the drill wants the
        # failure the caller would see, not four backoffs on the way to it.
        raise Blackholed(
            f"ESPN blackholed by {_BLOCK_ENV} (fault-injection drill): {url}")
    if _breaker_is_open():
        raise RateLimited(
            f"ESPN circuit breaker open — skipping {url} without a request. "
            f"{_BREAKER_THRESHOLD}+ consecutive rate-limit failures; retrying "
            f"now would extend the block rather than shorten it.")
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
                _note_outcome(True)           # host is answering — close the breaker
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

    # Attempts spent. Count it ONCE per call, not once per attempt: the breaker
    # measures how many distinct requests the host has refused, not how hard we
    # tried on any one of them.
    _note_outcome(False)
    raise last
