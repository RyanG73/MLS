"""Shared KV selection for local tests and production serverless functions."""
from __future__ import annotations

import os

from server.kv_store import InMemoryKVStore, KVStore
from server.upstash_kv import UpstashKVStore

_kv: KVStore | None = None


def get_kv() -> KVStore:
    global _kv
    if _kv is not None:
        return _kv
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        _kv = UpstashKVStore(url, token)
    elif os.environ.get("ENTENSER_ENV") == "production":
        raise RuntimeError(
            "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required in production")
    else:
        _kv = InMemoryKVStore()
    return _kv


def reset_kv_for_tests() -> None:
    global _kv
    _kv = InMemoryKVStore()
