"""Connectionless Upstash Redis REST adapter."""
from __future__ import annotations

import requests


class UpstashKVStore:
    def __init__(self, url: str, token: str, timeout: float = 5.0) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _command(self, *parts):
        response = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            json=list(parts),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(f"Upstash command failed: {payload['error']}")
        return payload.get("result")

    def get(self, key: str) -> str | None:
        value = self._command("GET", key)
        return None if value is None else str(value)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        command = ["SET", key, value]
        if ex is not None:
            command.extend(["EX", int(ex)])
        self._command(*command)

    def delete(self, key: str) -> None:
        self._command("DEL", key)

    def exists(self, key: str) -> bool:
        return bool(self._command("EXISTS", key))

    def add_to_set(self, key: str, value: str) -> None:
        self._command("SADD", key, value)

    def members(self, key: str) -> set[str]:
        return set(self._command("SMEMBERS", key) or [])

    def increment(self, key: str, ex: int | None = None) -> int:
        value = int(self._command("INCR", key))
        if ex is not None and value == 1:
            self._command("EXPIRE", key, int(ex))
        return value
