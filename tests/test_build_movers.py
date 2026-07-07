import pandas as pd

from scripts.build_movers import compute_movers


def _hist(rows):
    return pd.DataFrame(rows, columns=["league", "team", "snapshot_date",
                                       "title", "releg"])


def test_two_snapshots_yield_signed_deltas():
    df = _hist([
        ("epl", "Arsenal",  "2026-07-01", 45.0, 0.0),
        ("epl", "Arsenal",  "2026-07-07", 51.0, 0.0),
        ("epl", "Tottenham", "2026-07-01", 1.0, 36.0),
        ("epl", "Tottenham", "2026-07-07", 1.0, 30.0),
    ])
    movers = compute_movers(df, min_delta=1.0)
    m = {(x["team"], x["metric"]): x for x in movers}
    assert m[("Arsenal", "title")]["delta"] == 6.0
    assert m[("Arsenal", "title")]["prev"] == 45.0
    assert m[("Tottenham", "releg")]["delta"] == -6.0
    # sub-threshold moves (title 1.0 → 1.0) are excluded
    assert ("Tottenham", "title") not in m


def test_single_snapshot_league_is_excluded():
    df = _hist([
        ("epl", "Arsenal", "2026-07-01", 45.0, 0.0),
        ("nwsl", "Gotham", "2026-07-01", 12.0, 0.0),
        ("nwsl", "Gotham", "2026-07-07", 15.0, 0.0),
    ])
    movers = compute_movers(df, min_delta=1.0)
    teams = {x["team"] for x in movers}
    assert teams == {"Gotham"}


def test_top_n_ranked_by_magnitude():
    rows = []
    for i in range(30):
        rows.append(("epl", f"T{i}", "2026-07-01", 10.0, 0.0))
        rows.append(("epl", f"T{i}", "2026-07-07", 10.0 + i, 0.0))
    movers = compute_movers(_hist(rows), min_delta=1.0, top_n=5)
    assert len(movers) == 5
    assert movers[0]["delta"] == 29.0   # biggest magnitude first
