import pandas as pd

from scripts.build_edge_board import collect_rows, next_kickoffs

NOW = pd.Timestamp("2026-07-03T12:00", tz="UTC")


def _live(games, mode="table"):
    return {"status": "live", "generated": "2026-07-03 12:00 UTC",
            "league": {"name": "Test League"}, "outlook": {"mode": mode},
            "games": games}


def test_priced_row_gets_best_bet_above_threshold():
    payloads = {
        "epl": _live([
            {"date": "2026-07-04", "home": "Alpha", "away": "Beta", "result": None,
             "pH": 0.61, "pD": 0.22, "pA": 0.17,
             "mkt_home": 0.49, "mkt_draw": 0.27, "mkt_away": 0.24},
        ]),
    }
    priced, no_line = collect_rows(payloads, now=NOW)
    assert len(priced) == 1 and not no_line
    assert priced[0]["bet"]["side"] == "H"
    assert round(priced[0]["bet"]["edge_pct"], 1) == 12.0


def test_draw_side_never_recommended():
    payloads = {
        "epl": _live([
            {"date": "2026-07-04", "home": "Gamma", "away": "Delta", "result": None,
             "pH": 0.30, "pD": 0.40, "pA": 0.30,
             "mkt_home": 0.36, "mkt_draw": 0.28, "mkt_away": 0.36},
        ]),
    }
    priced, _ = collect_rows(payloads, now=NOW)
    assert priced[0]["bet"] is None  # 12% draw edge exists but is suppressed (A11)


def test_no_market_odds_goes_to_no_line_bucket():
    payloads = {
        "epl": _live([
            {"date": "2026-07-04", "home": "Eps", "away": "Zeta", "result": None,
             "pH": 0.70, "pD": 0.20, "pA": 0.10},
        ]),
    }
    priced, no_line = collect_rows(payloads, now=NOW)
    assert not priced and len(no_line) == 1
    assert no_line[0]["bet"] is None and no_line[0]["has_market"] is False


def test_window_excludes_far_future_and_played_matches():
    payloads = {
        "epl": _live([
            {"date": "2026-07-04", "home": "A", "away": "B", "result": None,
             "pH": 0.5, "pD": 0.3, "pA": 0.2},          # inside window
            {"date": "2026-08-01", "home": "C", "away": "D", "result": None,
             "pH": 0.5, "pD": 0.3, "pA": 0.2},          # outside 48h window
            {"date": "2026-07-04", "home": "E", "away": "F", "result": "H",
             "pH": 0.5, "pD": 0.3, "pA": 0.2},          # already played
        ]),
    }
    priced, no_line = collect_rows(payloads, now=NOW)
    assert len(priced) + len(no_line) == 1


def test_knockout_and_non_live_payloads_excluded():
    payloads = {
        "ucl": _live([{"date": "2026-07-04", "home": "A", "away": "B", "result": None,
                       "pH": 0.5, "pD": 0.3, "pA": 0.2}], mode="knockout"),
        "epl": {**_live([{"date": "2026-07-04", "home": "C", "away": "D", "result": None,
                          "pH": 0.5, "pD": 0.3, "pA": 0.2}]), "status": "preseason"},
    }
    priced, no_line = collect_rows(payloads, now=NOW)
    assert not priced and not no_line


def test_priced_rows_sorted_by_edge_descending():
    payloads = {
        "epl": _live([
            {"date": "2026-07-04", "home": "Small", "away": "X", "result": None,
             "pH": 0.55, "pD": 0.25, "pA": 0.20,
             "mkt_home": 0.47, "mkt_draw": 0.28, "mkt_away": 0.25},   # 8% edge
            {"date": "2026-07-04", "home": "Big", "away": "Y", "result": None,
             "pH": 0.65, "pD": 0.20, "pA": 0.15,
             "mkt_home": 0.45, "mkt_draw": 0.30, "mkt_away": 0.25},   # 20% edge
        ]),
    }
    priced, _ = collect_rows(payloads, now=NOW)
    assert [r["home"] for r in priced] == ["Big", "Small"]


def test_next_kickoffs_fallback_is_edge_agnostic_and_sorted():
    payloads = {
        "epl": _live([
            {"date": "2026-07-10", "home": "Late", "away": "X", "result": None,
             "pH": 0.5, "pD": 0.3, "pA": 0.2},
            {"date": "2026-07-04", "home": "Early", "away": "Y", "result": None,
             "pH": 0.5, "pD": 0.3, "pA": 0.2},
        ]),
    }
    nk = next_kickoffs(payloads, n=8)
    assert [r["home"] for r in nk] == ["Early", "Late"]
