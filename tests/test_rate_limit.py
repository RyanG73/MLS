from unittest.mock import patch

from server.kv_store import InMemoryKVStore
from server.rate_limit import check_rate_limit


def test_allows_requests_under_the_limit():
    kv = InMemoryKVStore()
    for _ in range(3):
        assert check_rate_limit(kv, "user-1", max_requests=3, window_seconds=60) is True


def test_blocks_once_limit_is_hit():
    kv = InMemoryKVStore()
    for _ in range(3):
        check_rate_limit(kv, "user-1", max_requests=3, window_seconds=60)
    assert check_rate_limit(kv, "user-1", max_requests=3, window_seconds=60) is False


def test_different_keys_have_independent_limits():
    kv = InMemoryKVStore()
    for _ in range(3):
        check_rate_limit(kv, "user-1", max_requests=3, window_seconds=60)
    assert check_rate_limit(kv, "user-2", max_requests=3, window_seconds=60) is True


def test_resets_in_the_next_window():
    kv = InMemoryKVStore()
    with patch("server.rate_limit.time.time", return_value=1_000_000.0):
        for _ in range(3):
            check_rate_limit(kv, "user-1", max_requests=3, window_seconds=60)
        assert check_rate_limit(kv, "user-1", max_requests=3, window_seconds=60) is False
    with patch("server.rate_limit.time.time", return_value=1_000_100.0):  # next 60s window
        assert check_rate_limit(kv, "user-1", max_requests=3, window_seconds=60) is True
