"""Shared KV store singleton. Every api/*.py handler and server/*.py caller
should go through get_kv() rather than constructing its own store — a real
deployment swaps the single InMemoryKVStore() here for a shared Upstash
Redis client; nothing else needs to change. Without this, each api/*.py
module instantiating its own store would silently NOT share state with any
other endpoint (e.g. a user created by api/auth/callback.py would be
invisible to api/intel/me.py) — a real bug this singleton exists to
prevent.
"""
from __future__ import annotations

from server.kv_store import InMemoryKVStore, KVStore

_kv: KVStore | None = None


def get_kv() -> KVStore:
    global _kv
    if _kv is None:
        _kv = InMemoryKVStore()
    return _kv


def reset_kv_for_tests() -> None:
    """Test-only: force a fresh store so tests don't leak state into each other."""
    global _kv
    _kv = InMemoryKVStore()
