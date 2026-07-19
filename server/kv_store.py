"""Minimal key-value store abstraction for S5 (docs/intelligence-hub-
implementation-instructions.md §4.2, §5 S5).

The roadmap (docs/product-roadmap-2026-07.md) commits to "no database
server" — Upstash Redis (a managed KV store) is the intended production
backend. This module defines the interface every auth/entitlement/
preference module here is written against, plus an in-memory
implementation for tests — so none of this code needs a real Redis
connection to be correct, and swapping in a real client later is a
one-file change, not a rewrite.
"""
from __future__ import annotations

import time
from typing import Protocol


class KVStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ex: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def add_to_set(self, key: str, value: str) -> None: ...
    def members(self, key: str) -> set[str]: ...
    def increment(self, key: str, ex: int | None = None) -> int: ...


class InMemoryKVStore:
    """Dict-backed KVStore for tests. Honors `ex` (seconds-to-live) via a
    wall-clock expiry check on read — not a background sweep, matching how
    a real TTL-backed store behaves from the caller's perspective."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str) -> str | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.time() >= expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        expires_at = time.time() + ex if ex is not None else None
        self._data[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def add_to_set(self, key: str, value: str) -> None:
        raw = self.get(key)
        values = set(raw.split("\n")) if raw else set()
        values.add(value)
        self.set(key, "\n".join(sorted(values)))

    def members(self, key: str) -> set[str]:
        raw = self.get(key)
        return set(raw.split("\n")) if raw else set()

    def increment(self, key: str, ex: int | None = None) -> int:
        value = int(self.get(key) or 0) + 1
        self.set(key, str(value), ex=ex)
        return value
