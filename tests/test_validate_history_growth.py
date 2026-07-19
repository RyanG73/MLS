import pandas as pd

from scripts import validate_history_growth as vhg


def test_check_no_shrinkage_passes_when_nothing_committed_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(vhg, "committed_row_count", lambda rel_path: None)
    monkeypatch.setattr(vhg, "ACCRUAL_FILES", [tmp_path / "hist.parquet"])
    pd.DataFrame({"a": [1, 2]}).to_parquet(tmp_path / "hist.parquet")
    assert vhg.check_no_shrinkage() == []


def test_check_no_shrinkage_passes_when_row_count_grows(tmp_path, monkeypatch):
    monkeypatch.setattr(vhg, "committed_row_count", lambda rel_path: 2)
    monkeypatch.setattr(vhg, "ACCRUAL_FILES", [tmp_path / "hist.parquet"])
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(tmp_path / "hist.parquet")
    assert vhg.check_no_shrinkage() == []


def test_check_no_shrinkage_flags_a_shrink(tmp_path, monkeypatch):
    monkeypatch.setattr(vhg, "committed_row_count", lambda rel_path: 10)
    monkeypatch.setattr(vhg, "ACCRUAL_FILES", [tmp_path / "hist.parquet"])
    pd.DataFrame({"a": [1, 2]}).to_parquet(tmp_path / "hist.parquet")
    errors = vhg.check_no_shrinkage()
    assert len(errors) == 1 and "SHRANK" in errors[0]


def test_check_trajectory_season_bounds_flags_stale_season_point(monkeypatch):
    monkeypatch.setattr(vhg, "registry_ids", lambda: {"epl"})

    def fake_read(path):
        path = str(path)
        if path.endswith("data/epl.js"):
            return {"season": 2026}
        if "drift-traj" in path:
            return {"teams": {"Alpha": [{"date": "2025-08-01", "season": 2025, "elo": 1400}]}}
        return None

    monkeypatch.setattr(vhg, "read_js_payload", fake_read)
    errors = vhg.check_trajectory_season_bounds()
    assert len(errors) == 1 and "2025" in errors[0]


def test_check_trajectory_season_bounds_passes_when_seasons_match(monkeypatch):
    monkeypatch.setattr(vhg, "registry_ids", lambda: {"epl"})

    def fake_read(path):
        path = str(path)
        if path.endswith("data/epl.js"):
            return {"season": 2026}
        if "drift-traj" in path:
            return {"teams": {"Alpha": [{"date": "2026-08-01", "season": 2026, "elo": 1500}]}}
        return None

    monkeypatch.setattr(vhg, "read_js_payload", fake_read)
    assert vhg.check_trajectory_season_bounds() == []


def test_check_trajectory_season_bounds_skips_when_current_season_unknown(monkeypatch):
    monkeypatch.setattr(vhg, "registry_ids", lambda: {"epl"})
    monkeypatch.setattr(vhg, "read_js_payload", lambda path: None)
    assert vhg.check_trajectory_season_bounds() == []
