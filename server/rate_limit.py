#!/usr/bin/env python3
"""S5: KV-backed rate limiting (docs/intelligence-hub-implementation-
instructions.md §5 S5 "rate limits"; §9 security tests: "Rate limiting on
auth, Ask, scenario, and export endpoints.")

Fixed-window counter: the simplest correct approach for a KV store with
TTL, adequate for this scope (a sliding-window/token-bucket refinement is
straightforward follow-on work if fixed-window's edge-of-window burst
behavior ever matters in practice).
"""
from __future__ import annotations

import time

from server.kv_store import KVStore


def check_rate_limit(kv: KVStore, key: str, max_requests: int, window_seconds: int) -> bool:
    """Returns True if the request is allowed (and records it), False if
    `key` has already hit `max_requests` within the current window."""
    window = int(time.time()) // window_seconds
    counter_key = f"ratelimit:{key}:{window}"
    current = kv.get(counter_key)
    count = int(current) if current is not None else 0
    if count >= max_requests:
        return False
    kv.set(counter_key, str(count + 1), ex=window_seconds)
    return True
