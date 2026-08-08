"""Unit tests for data_pipeline.http.espn_get."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from data_pipeline.http import espn_get


def test_espn_get_returns_parsed_json_on_success():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"events": [{"id": "999"}]}
    with patch("data_pipeline.http.requests.get", return_value=mock_resp):
        result = espn_get("https://example.com/api", {"limit": 5})
    assert result == {"events": [{"id": "999"}]}


def test_espn_get_raises_on_network_error():
    with patch("data_pipeline.http.requests.get", side_effect=ConnectionError("timeout")):
        with pytest.raises(Exception):
            espn_get("https://example.com/api")


def test_espn_get_passes_params_and_headers():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    with patch("data_pipeline.http.requests.get", return_value=mock_resp) as mock_get:
        espn_get("https://example.com/api", {"season": 2026}, timeout=15)
    mock_get.assert_called_once_with(
        "https://example.com/api",
        params={"season": 2026},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=15,
    )


def test_espn_get_raises_on_http_error():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    with patch("data_pipeline.http.requests.get", return_value=mock_resp):
        with pytest.raises(requests.HTTPError):
            espn_get("https://example.com/api")


# ── rate-limit retry (2026-08-07) ────────────────────────────────────────────
# ESPN answers a rate limit with 403 rather than 429, and then refuses every
# endpoint rather than just the one that crossed the line. Without a retry the
# pipeline turned that into "season not refreshed" and carried on: the Leagues
# Cup match cache held only 2024 while a live 2026 tournament published a
# forecast with 0 of 54 results, and the scheduled fast refresh failed outright.


def _resp(status, payload=None):
    """A response mock whose status_code is a real int, so membership of
    _RETRY_STATUS behaves rather than silently matching a MagicMock."""
    m = MagicMock()
    m.status_code = status
    m.reason = "Forbidden" if status == 403 else "OK"
    m.url = "https://example.com/api"
    m.headers = {}
    m.json.return_value = payload if payload is not None else {}
    if status >= 400:
        m.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return m


# `attempts` is passed explicitly throughout: conftest sets the module default
# to 1 for the session so the few tests that reach ESPN for real do not pay the
# backoff ladder, and these tests must exercise retries regardless of it.


def test_espn_get_retries_403_then_succeeds():
    calls = [_resp(403), _resp(403), _resp(200, {"events": [1]})]
    with patch("data_pipeline.http.requests.get", side_effect=calls) as get, \
         patch("data_pipeline.http.time.sleep"):
        assert espn_get("https://example.com/api", attempts=4) == {"events": [1]}
    assert get.call_count == 3, "a 403 must be retried, not surfaced"


def test_espn_get_does_not_retry_404():
    """404 is a slug that does not exist and 400 a date window ESPN dislikes.
    Both are deterministic; retrying only slows the build to the same answer."""
    with patch("data_pipeline.http.requests.get", return_value=_resp(404)) as get, \
         patch("data_pipeline.http.time.sleep"):
        with pytest.raises(requests.HTTPError):
            espn_get("https://example.com/api", attempts=4)
    assert get.call_count == 1


def test_espn_get_gives_up_after_max_attempts_and_raises():
    with patch("data_pipeline.http.requests.get", return_value=_resp(403)) as get, \
         patch("data_pipeline.http.time.sleep"):
        with pytest.raises(requests.HTTPError):
            espn_get("https://example.com/api", attempts=3)
    assert get.call_count == 3, "must stop, so a dead source cannot hang a build"


def test_espn_get_honours_retry_after_header():
    limited = _resp(429)
    limited.headers = {"Retry-After": "7"}
    with patch("data_pipeline.http.requests.get",
               side_effect=[limited, _resp(200, {"ok": True})]), \
         patch("data_pipeline.http.time.sleep") as sleep:
        assert espn_get("https://example.com/api", attempts=4) == {"ok": True}
    waits = [c.args[0] for c in sleep.call_args_list if c.args and c.args[0] >= 1]
    assert 7 in waits, f"Retry-After ignored; slept {waits}"


def test_breaker_opens_after_repeated_refusals_and_then_stops_requesting():
    """Retrying is right for a transient limit and harmful for a sustained one.
    ESPN blocks by IP across every endpoint, so once it refuses, each further
    call costs four requests to learn nothing — and extends our own block."""
    from data_pipeline import http

    http.reset_breaker()
    with patch("data_pipeline.http.requests.get", return_value=_resp(403)) as get, \
         patch("data_pipeline.http.time.sleep"):
        for _ in range(http._BREAKER_THRESHOLD):
            with pytest.raises(requests.HTTPError):
                espn_get("https://example.com/api", attempts=1)
        calls_before = get.call_count
        # Breaker is now open: further calls must not touch the network at all.
        for _ in range(10):
            with pytest.raises(http.RateLimited):
                espn_get("https://example.com/api", attempts=4)
        assert get.call_count == calls_before, (
            f"{get.call_count - calls_before} requests issued while the breaker "
            f"was open — the point is to stop asking")


def test_breaker_reopens_the_gate_after_the_cooldown():
    from data_pipeline import http

    http.reset_breaker()
    with patch("data_pipeline.http.requests.get", return_value=_resp(403)), \
         patch("data_pipeline.http.time.sleep"):
        for _ in range(http._BREAKER_THRESHOLD):
            with pytest.raises(requests.HTTPError):
                espn_get("https://example.com/api", attempts=1)
    # Pretend the cooldown has elapsed; one probe must be allowed through.
    http._breaker_opened_at -= http._BREAKER_COOLDOWN + 1
    with patch("data_pipeline.http.requests.get",
               return_value=_resp(200, {"ok": True})) as get:
        assert espn_get("https://example.com/api", attempts=1) == {"ok": True}
    assert get.call_count == 1


def test_a_success_closes_the_breaker():
    """A single good answer means the host is serving again; the failure count
    must not carry over and trip the breaker on unrelated later calls."""
    from data_pipeline import http

    http.reset_breaker()
    seq = [_resp(403)] * (http._BREAKER_THRESHOLD - 1) + [_resp(200, {"ok": True})]
    with patch("data_pipeline.http.requests.get", side_effect=seq), \
         patch("data_pipeline.http.time.sleep"):
        for _ in range(http._BREAKER_THRESHOLD - 1):
            with pytest.raises(requests.HTTPError):
                espn_get("https://example.com/api", attempts=1)
        assert espn_get("https://example.com/api", attempts=1) == {"ok": True}
    assert http._consecutive_failures == 0


def test_a_404_does_not_count_toward_the_breaker():
    """A missing slug is not the host refusing us. Counting deterministic 4xx
    would open the breaker on a config typo and hide a real outage behind it."""
    from data_pipeline import http

    http.reset_breaker()
    with patch("data_pipeline.http.requests.get", return_value=_resp(404)):
        for _ in range(http._BREAKER_THRESHOLD + 2):
            with pytest.raises(requests.HTTPError):
                espn_get("https://example.com/api", attempts=1)
    assert http._consecutive_failures == 0, "404s must not trip the breaker"


def test_espn_get_retries_transient_connection_errors():
    with patch("data_pipeline.http.requests.get",
               side_effect=[requests.ConnectionError("reset"),
                            _resp(200, {"ok": True})]) as get, \
         patch("data_pipeline.http.time.sleep"):
        assert espn_get("https://example.com/api", attempts=4) == {"ok": True}
    assert get.call_count == 2
