import time

from server.kv_client import get_kv, reset_kv_for_tests
from server.kv_store import InMemoryKVStore


def test_set_and_get_roundtrip():
    kv = InMemoryKVStore()
    kv.set("k", "v")
    assert kv.get("k") == "v"


def test_get_missing_key_returns_none():
    kv = InMemoryKVStore()
    assert kv.get("nope") is None


def test_delete_removes_key():
    kv = InMemoryKVStore()
    kv.set("k", "v")
    kv.delete("k")
    assert kv.get("k") is None


def test_exists_reflects_presence():
    kv = InMemoryKVStore()
    assert kv.exists("k") is False
    kv.set("k", "v")
    assert kv.exists("k") is True


def test_ttl_expiry():
    kv = InMemoryKVStore()
    kv.set("k", "v", ex=1)
    assert kv.get("k") == "v"
    time.sleep(1.1)
    assert kv.get("k") is None


def test_no_ttl_never_expires():
    kv = InMemoryKVStore()
    kv.set("k", "v")
    time.sleep(0.1)
    assert kv.get("k") == "v"


def test_get_kv_returns_same_instance_across_calls():
    reset_kv_for_tests()
    a = get_kv()
    b = get_kv()
    assert a is b
    a.set("shared", "value")
    assert b.get("shared") == "value"
