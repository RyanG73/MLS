"""Contract test for scripts/build_weekly_recap.py (launch plan H1)."""
from __future__ import annotations

import json

from scripts import build_weekly_recap as wr


def test_recap_payload_shape(tmp_path, monkeypatch):
    monkeypatch.chdir(wr.Path(__file__).resolve().parent.parent)
    monkeypatch.setattr(wr, "DATA", wr.Path("webapp/data"))
    names = wr._league_names()
    assert names, "registry should resolve league names"

    movers = wr._movers(names)
    assert set(movers) == {"risers", "fallers", "window_label"}
    for r in movers["risers"]:
        assert r["delta"] > 0
    for f in movers["fallers"]:
        assert f["delta"] < 0

    hm = wr._hits_and_misses(names)
    assert hm["n_hits"] <= hm["n_calls"]
    if hm["n_calls"]:
        assert 0 <= hm["hit_rate"] <= 100
    for m in hm["misses"]:
        assert m["fav_pct"] >= wr.MISS_CONF * 100
        assert {"league_name", "home", "away", "score", "outcome"} <= set(m)

    headline = wr._headline(movers, wr._fragile_races())
    assert isinstance(headline, str) and headline


def test_main_writes_dated_archive_copy(tmp_path, monkeypatch):
    monkeypatch.chdir(wr.Path(__file__).resolve().parent.parent)
    monkeypatch.setattr(wr, "DATA", tmp_path / "webdata")   # no payloads → degrades to empty defaults
    monkeypatch.setattr(wr, "WEEKLY_ARCHIVE_DIR", tmp_path / "archive")
    wr.main()
    files = list((tmp_path / "archive").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["status"] == "ok"
    assert saved["week_label"]
