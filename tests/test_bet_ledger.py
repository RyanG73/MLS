import pandas as pd

from scripts.bet_ledger import (candidate_bets, log_bets, settle_bets,
                                ledger_summary)


def _payload():
    return {
        "status": "live",
        "generated": "2026-07-03 12:00 UTC",
        "games": [
            # upcoming, market attached, home edge 61-49=12% → bet
            {"date": "2026-07-05", "home": "Alpha", "away": "Beta",
             "pH": 0.61, "pD": 0.22, "pA": 0.17, "result": None,
             "mkt_home": 0.49, "mkt_draw": 0.27, "mkt_away": 0.24},
            # upcoming, DRAW edge 12% but draw-side is suppressed (A11 rule)
            {"date": "2026-07-06", "home": "Gamma", "away": "Delta",
             "pH": 0.30, "pD": 0.40, "pA": 0.30, "result": None,
             "mkt_home": 0.36, "mkt_draw": 0.28, "mkt_away": 0.36},
            # upcoming, no market odds → skipped
            {"date": "2026-07-07", "home": "Eps", "away": "Zeta",
             "pH": 0.70, "pD": 0.20, "pA": 0.10, "result": None},
            # played → not a candidate
            {"date": "2026-06-01", "home": "Beta", "away": "Alpha",
             "pH": 0.5, "pD": 0.3, "pA": 0.2, "result": "H",
             "mkt_home": 0.30, "mkt_draw": 0.30, "mkt_away": 0.40},
        ],
    }


def test_candidates_edge_threshold_and_draw_suppression():
    bets = candidate_bets("epl", _payload(), thresh=8.0)
    assert len(bets) == 1
    b = bets[0]
    assert b["side"] == "H" and b["home"] == "Alpha"
    assert round(b["edge_pct"], 1) == 12.0
    assert b["units"] > 0
    assert b["dec_odds"] == round(1 / 0.49, 3)  # fair (de-vigged) odds


def test_log_once_dedup(tmp_path):
    out = tmp_path / "ledger.parquet"
    bets = candidate_bets("epl", _payload())
    log_bets(bets, out)
    log_bets(bets, out)  # second build recommends the same bet → no reprice
    df = pd.read_parquet(out)
    assert len(df) == 1


def test_settlement_math(tmp_path):
    out = tmp_path / "ledger.parquet"
    log_bets(candidate_bets("epl", _payload()), out)
    # the match decides: home win → bet won
    results = {("epl", "2026-07-05", "Alpha", "Beta"): "H"}
    settle_bets(out, results)
    df = pd.read_parquet(out)
    r = df.iloc[0]
    assert r["result"] == "H" and bool(r["won"])
    # pnl = units * (dec_odds − 1) on a win
    assert abs(r["pnl"] - r["units"] * (r["dec_odds"] - 1)) < 1e-9
    # settling again must not double-settle
    settle_bets(out, results)
    assert len(pd.read_parquet(out)) == 1


def test_summary_and_drawdown(tmp_path):
    df = pd.DataFrame([
        {"league": "epl", "units": 1.0, "won": True,  "pnl": 1.0, "result": "H", "clv_pp": None},
        {"league": "epl", "units": 1.0, "won": False, "pnl": -1.0, "result": "A", "clv_pp": None},
        {"league": "epl", "units": 1.0, "won": False, "pnl": -1.0, "result": "A", "clv_pp": None},
        {"league": "epl", "units": 1.0, "won": None,  "pnl": None, "result": None, "clv_pp": None},
    ])
    s = ledger_summary(df)
    assert s["n_bets"] == 4 and s["n_settled"] == 3
    assert s["units_pnl"] == -1.0
    assert round(s["hit_rate"], 3) == round(1 / 3, 3)
    # cum pnl: +1, 0, −1 → peak 1, trough −1 → max drawdown 2
    assert s["max_drawdown"] == 2.0
