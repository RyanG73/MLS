import pandas as pd

from scripts.archive_odds_snapshot import append_snapshot, snapshot_rows


def _payload(generated="2026-07-03 12:00 UTC"):
    return {
        "status": "live",
        "generated": generated,
        "standings": [
            {"team": "Alpha", "elo": 1550, "title": 0.4, "ucl": 0.8,
             "releg": 0.0, "proj_pts": 78.2},
            {"team": "Beta", "elo": 1440, "title": 0.01, "ucl": 0.05,
             "releg": 0.42, "proj_pts": 41.0},
        ],
        "games": [
            {"id": "g1", "home": "Alpha", "away": "Beta", "date": "2026-07-05",
             "pH": 0.61, "pD": 0.22, "pA": 0.17, "result": None},
            {"id": "g0", "home": "Beta", "away": "Alpha", "date": "2026-06-01",
             "pH": 0.3, "pD": 0.3, "pA": 0.4, "result": "H"},
        ],
    }


def test_snapshot_rows_shape():
    rows = snapshot_rows("epl", _payload())
    assert len(rows) == 2
    a = next(r for r in rows if r["team"] == "Alpha")
    assert a["league"] == "epl"
    assert a["snapshot_date"] == "2026-07-03"
    assert a["title"] == 0.4 and a["releg"] == 0.0 and a["elo"] == 1550
    # next upcoming match probs from the team's perspective flags
    assert a["nm_id"] == "g1" and a["nm_is_home"] is True
    assert a["nm_ph"] == 0.61
    # market probs not in payloads yet → archived as None
    assert a["nm_mh"] is None


def test_same_build_appends_once(tmp_path):
    out = tmp_path / "hist.parquet"
    rows = snapshot_rows("epl", _payload())
    append_snapshot(rows, out)
    append_snapshot(rows, out)
    df = pd.read_parquet(out)
    assert len(df) == 2  # deduped on league+team+snapshot_date


def test_second_date_appends_new_rows(tmp_path):
    out = tmp_path / "hist.parquet"
    append_snapshot(snapshot_rows("epl", _payload()), out)
    append_snapshot(snapshot_rows(
        "epl", _payload(generated="2026-07-04 12:00 UTC")), out)
    df = pd.read_parquet(out)
    assert len(df) == 4
    assert set(df["snapshot_date"]) == {"2026-07-03", "2026-07-04"}
