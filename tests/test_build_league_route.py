"""build_league_data source routing — registry-resolved frames with provenance.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md §6.1/§6.2.
"""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def isolated_health(tmp_path, monkeypatch):
    from data_pipeline import source_health
    monkeypatch.setattr(source_health, "_HEALTH_PATH",
                        tmp_path / "source_health.parquet")


def _sentinel() -> pd.DataFrame:
    return pd.DataFrame({"match_id": ["m1"]})


def test_routed_frame_default_uses_primary_and_publishes_it(monkeypatch):
    """No registry entry: exactly one load, from cfg['source'], and the
    provenance names it — today's behavior plus visibility."""
    from scripts import build_league_data as bld
    calls = []

    def fake_load(lid, source, asa_key=None):
        calls.append((lid, source, asa_key))
        return _sentinel()

    monkeypatch.setattr(bld, "_load_frame", fake_load)
    frame, prov = bld._routed_frame("epl", {"source": "understat"})
    assert calls == [("epl", "understat", None)]
    assert prov == {"fixtures": "understat"}
    assert len(frame) == 1


def test_routed_frame_falls_back_and_provenance_shows_it(monkeypatch, isolated_health):
    from scripts import build_league_data as bld
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "epl",
                        {"fixtures": ["api_football", "understat"]})

    def fake_load(lid, source, asa_key=None):
        if source == "api_football":
            raise RuntimeError("dark")
        return _sentinel()

    monkeypatch.setattr(bld, "_load_frame", fake_load)
    frame, prov = bld._routed_frame("epl", {"source": "understat"})
    assert prov == {"fixtures": "understat"}


def test_routed_frame_passes_asa_key_through(monkeypatch):
    from scripts import build_league_data as bld
    seen = {}

    def fake_load(lid, source, asa_key=None):
        seen["asa_key"] = asa_key
        return _sentinel()

    monkeypatch.setattr(bld, "_load_frame", fake_load)
    bld._routed_frame("nwsl", {"source": "asa", "asa_key": "nwsl"})
    assert seen["asa_key"] == "nwsl"
