from __future__ import annotations

import json

import pytest

from api.admin import intelligence_artifacts
from api.index import _dispatch
from scripts import publish_intelligence_artifacts as publisher
from server.http_headers import Headers
from server.kv_client import get_kv, reset_kv_for_tests


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    reset_kv_for_tests()
    monkeypatch.setenv("INTELLIGENCE_PUBLISH_TOKEN", "publish-secret")
    yield
    reset_kv_for_tests()


def _call(records, token="publish-secret"):
    return intelligence_artifacts.handle(
        "POST",
        Headers({"x-intelligence-publish-token": token}),
        json.dumps({"records": records}).encode(),
    )


def test_rejects_missing_or_wrong_publisher_secret():
    status, _, _ = _call([{"key": "intel:artifact:mls:atl", "value": "gz:eA=="}], "wrong")
    assert status == 401


def test_publishes_only_strict_artifact_keys_and_values():
    records = [
        {"key": "intel:artifact:mls:v1:a256353b6911", "value": "gz:eA=="},
        {"key": "intel:artifact:manifest", "value": '{"leagues":{}}'},
    ]
    status, _, body = _call(records)
    assert status == 200
    assert json.loads(body) == {"published": 2}
    assert get_kv().get("intel:artifact:mls:v1:a256353b6911") == "gz:eA=="
    assert get_kv().get("intel:artifact:manifest") == '{"leagues":{}}'


def test_versioned_api_route_reaches_publisher():
    status, _, body = _dispatch(
        "POST",
        "/v1/admin/intelligence-artifacts",
        Headers({"x-intelligence-publish-token": "publish-secret"}),
        json.dumps({"records": [
            {"key": "intel:artifact:mls:atl", "value": "gz:eA=="},
        ]}).encode(),
    )
    assert status == 200
    assert json.loads(body) == {"published": 1}


@pytest.mark.parametrize("record", [
    {"key": "other:key", "value": "gz:eA=="},
    {"key": "intel:artifact:mls:atl", "value": "not-compressed"},
    {"key": "intel:artifact:manifest", "value": "gz:eA=="},
    {"key": "intel:artifact:mls:atl", "value": "gz:eA==", "extra": True},
])
def test_rejects_invalid_records_without_writing(record):
    status, _, _ = _call([record])
    assert status == 400
    assert get_kv().get("intel:artifact:mls:atl") is None


def test_rejects_oversized_batches():
    records = [
        {"key": f"intel:artifact:mls:t{i}", "value": "gz:eA=="}
        for i in range(intelligence_artifacts.MAX_RECORDS + 1)
    ]
    status, _, _ = _call(records)
    assert status == 400


def test_publisher_relays_team_records_before_manifest(tmp_path, monkeypatch):
    league_dir = tmp_path / "mls"
    league_dir.mkdir()
    (league_dir / "atl.json").write_text(json.dumps({"team_id": "atl"}))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "leagues": {"mls": {"status": "ok", "files": ["atl.json"]}},
    }))
    relayed = []
    monkeypatch.setenv("INTELLIGENCE_PUBLISH_TOKEN", "publish-secret")
    monkeypatch.setattr(
        publisher,
        "_publish_via_api",
        lambda endpoint, token, records: relayed.append((endpoint, token, records)),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["publish_intelligence_artifacts.py", "--root", str(tmp_path),
         "--endpoint", "https://api.example/v1/admin/intelligence-artifacts"],
    )

    assert publisher.main() == 0
    assert relayed[0][2][0]["key"] == "intel:artifact:mls:atl"
    assert relayed[0][2][0]["value"].startswith("gz:")
    assert relayed[-1][2][0]["key"] == "intel:artifact:manifest"
