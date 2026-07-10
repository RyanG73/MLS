"""Drift-tracking report (docs/projection-drift-tracking.md step 2)."""
import pandas as pd
import pytest

from scripts.build_drift_report import (
    compute_churn, compute_config_markers, compute_kickoff_funnel,
    compute_trajectories, write_trajectory_files,
)


def _hist_rows(rows):
    """rows: list of dicts with league/team/snapshot_date/n_played/config_id +
    any _ODDS_KEYS columns; missing odds keys default to None."""
    from scripts.archive_odds_snapshot import _ODDS_KEYS
    out = []
    for r in rows:
        row = {k: None for k in _ODDS_KEYS}
        row.update(elo=1500, proj_pts=50.0, config_id="cfg-1")
        row.update(r)
        out.append(row)
    return pd.DataFrame(out)


# ── compute_churn ─────────────────────────────────────────────────────────────

def test_churn_zero_when_odds_unchanged_between_no_new_match_builds():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 5, "title": 10.0},
    ])
    out = compute_churn(hist)
    assert out["epl"]["status"] == "ok"
    assert out["epl"]["index_pp"] == 0.0
    assert out["epl"]["alert"] is False


def test_churn_flags_alert_above_threshold():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 5, "title": 25.0},
    ])
    out = compute_churn(hist)
    assert out["epl"]["index_pp"] == 15.0
    assert out["epl"]["alert"] is True
    assert out["epl"]["top_movers"][0] == {"team": "Alpha", "key": "title", "delta": 15.0}


def test_churn_skips_pairs_where_matches_were_played():
    # only pair available has DIFFERENT n_played → real information response,
    # not churn — must report insufficient_history rather than a fake number
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 6, "title": 40.0},
    ])
    out = compute_churn(hist)
    assert out["epl"]["status"] == "insufficient_history"


def test_churn_picks_the_latest_qualifying_pair_not_the_first():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-06-30", "n_played": 4, "title": 5.0},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},  # match played
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 5, "title": 10.0},  # no match
    ])
    out = compute_churn(hist)
    assert out["epl"]["window"] == "2026-07-01→2026-07-02"
    assert out["epl"]["index_pp"] == 0.0


def test_churn_ignores_subnoise_moves_in_top_movers_but_counts_in_index():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.00},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 5, "title": 10.02},
    ])
    out = compute_churn(hist)
    assert out["epl"]["top_movers"] == []          # below the 0.05pp mover threshold
    assert out["epl"]["index_pp"] == pytest.approx(0.02, abs=1e-6)


def test_churn_multiple_leagues_independent():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 5, "title": 10.0},
        {"league": "mls", "team": "Beta", "snapshot_date": "2026-07-01", "n_played": 3, "cup": 20.0},
        {"league": "mls", "team": "Beta", "snapshot_date": "2026-07-02", "n_played": 3, "cup": 30.0},
    ])
    out = compute_churn(hist)
    assert out["epl"]["index_pp"] == 0.0
    assert out["mls"]["index_pp"] == 10.0


# ── compute_trajectories ──────────────────────────────────────────────────────

def test_trajectories_grouped_and_sorted():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 5, "title": 12.0},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},
    ])
    out = compute_trajectories(hist)
    series = out["epl"]["Alpha"]
    assert [s["date"] for s in series] == ["2026-07-01", "2026-07-02"]
    assert series[0]["title"] == 10.0 and series[1]["title"] == 12.0


def test_trajectories_nan_becomes_none_json_safe():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5},
    ])
    out = compute_trajectories(hist)
    assert out["epl"]["Alpha"][0]["title"] is None


def test_trajectories_caps_to_max_points():
    import scripts.build_drift_report as bdr
    rows = [{"league": "epl", "team": "Alpha", "snapshot_date": f"2026-01-{d:02d}",
             "n_played": 1, "title": float(d)} for d in range(1, 32)]
    hist = _hist_rows(rows)
    orig = bdr._TRAJ_MAX_POINTS
    bdr._TRAJ_MAX_POINTS = 5
    try:
        out = compute_trajectories(hist)
        assert len(out["epl"]["Alpha"]) == 5
        assert out["epl"]["Alpha"][-1]["date"] == "2026-01-31"   # keeps the tail
    finally:
        bdr._TRAJ_MAX_POINTS = orig


def test_trajectory_files_written_for_leagues_with_data(tmp_path, monkeypatch):
    import json
    import scripts.build_drift_report as bdr

    monkeypatch.setattr(bdr, "TRAJ_DIR", tmp_path)
    monkeypatch.setattr(bdr, "registry_ids", lambda: set())  # isolate from the real registry
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},
        {"league": "mls", "team": "Beta", "snapshot_date": "2026-07-01", "n_played": 3, "cup": 20.0},
    ])
    n = write_trajectory_files(compute_trajectories(hist), "2026-07-10 00:00 UTC")
    assert n == 2
    epl_file = json.loads((tmp_path / "epl.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
    assert epl_file["league"] == "epl"
    assert epl_file["teams"]["Alpha"][0]["title"] == 10.0
    assert (tmp_path / "mls.js").exists()


def test_trajectory_files_written_for_every_registry_league_even_without_data(tmp_path, monkeypatch):
    """A league that's never been archived (a 'soon' placeholder, or added
    since the last run) still gets a file — an empty one beats a 404."""
    import json
    import scripts.build_drift_report as bdr

    monkeypatch.setattr(bdr, "TRAJ_DIR", tmp_path)
    monkeypatch.setattr(bdr, "registry_ids", lambda: {"epl", "canadian-pl"})
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "title": 10.0},
    ])
    n = write_trajectory_files(compute_trajectories(hist), "2026-07-10 00:00 UTC")
    assert n == 2
    stub = json.loads((tmp_path / "canadian-pl.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
    assert stub == {"league": "canadian-pl", "generated": "2026-07-10 00:00 UTC", "teams": {}}


# ── compute_config_markers ────────────────────────────────────────────────────

def test_config_markers_one_per_change_not_per_row():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "config_id": "cfg-1"},
        {"league": "mls", "team": "Beta", "snapshot_date": "2026-07-01", "n_played": 3, "config_id": "cfg-1"},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-02", "n_played": 5, "config_id": "cfg-1"},
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-03", "n_played": 5, "config_id": "cfg-2"},
    ])
    markers = compute_config_markers(hist)
    assert markers == [{"date": "2026-07-01", "config_id": "cfg-1"},
                       {"date": "2026-07-03", "config_id": "cfg-2"}]


def test_config_markers_empty_without_config_id_column_values():
    hist = _hist_rows([
        {"league": "epl", "team": "Alpha", "snapshot_date": "2026-07-01", "n_played": 5, "config_id": None},
    ])
    assert compute_config_markers(hist) == []


# ── compute_kickoff_funnel ─────────────────────────────────────────────────────

def test_kickoff_funnel_insufficient_history_when_no_match_hist():
    out = compute_kickoff_funnel(None, {})
    assert out["status"] == "insufficient_history"


def test_kickoff_funnel_insufficient_history_when_nothing_settled_yet():
    match_hist = pd.DataFrame([{
        "league": "epl", "home": "Alpha", "away": "Beta", "date": "2026-07-05",
        "snapshot_date": "2026-07-03", "pH": 0.6, "pD": 0.2, "pA": 0.2,
        "days_to_kickoff": 2,
    }])
    payloads = {"epl": {"games": [
        {"home": "Alpha", "away": "Beta", "date": "2026-07-05", "result": None},
    ]}}
    out = compute_kickoff_funnel(match_hist, payloads)
    assert out["status"] == "insufficient_history"


def test_kickoff_funnel_computes_brier_by_bucket_once_settled():
    match_hist = pd.DataFrame([
        {"league": "epl", "home": "Alpha", "away": "Beta", "date": "2026-07-05",
         "snapshot_date": "2026-06-28", "pH": 0.5, "pD": 0.3, "pA": 0.2,
         "days_to_kickoff": 7},
        {"league": "epl", "home": "Alpha", "away": "Beta", "date": "2026-07-05",
         "snapshot_date": "2026-07-04", "pH": 0.7, "pD": 0.2, "pA": 0.1,
         "days_to_kickoff": 1},
    ])
    payloads = {"epl": {"games": [
        {"home": "Alpha", "away": "Beta", "date": "2026-07-05", "result": "H"},
    ]}}
    out = compute_kickoff_funnel(match_hist, payloads)
    assert out["status"] == "ok"
    assert out["n_matched"] == 2
    by_label = {b["label"]: b for b in out["buckets"]}
    # the 1-day-out quote (0.7) should score a lower (better) Brier than the
    # 7-day-out quote (0.5) against the actual home win
    assert by_label["0-1d"]["brier"] < by_label["7d+"]["brier"]


def test_kickoff_funnel_ignores_rows_for_unplayed_or_different_fixtures():
    match_hist = pd.DataFrame([
        {"league": "epl", "home": "Alpha", "away": "Gamma", "date": "2026-07-05",
         "snapshot_date": "2026-07-04", "pH": 0.5, "pD": 0.3, "pA": 0.2,
         "days_to_kickoff": 1},
    ])
    payloads = {"epl": {"games": [
        {"home": "Alpha", "away": "Beta", "date": "2026-07-05", "result": "H"},
    ]}}
    out = compute_kickoff_funnel(match_hist, payloads)
    assert out["status"] == "insufficient_history"
