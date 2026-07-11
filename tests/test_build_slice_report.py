import json
import re

from scripts import build_slice_report


def test_family_payload_includes_measured_mls_slices():
    spec = next(f for f in build_slice_report.FAMILIES if f["id"] == "mls")
    payload = build_slice_report._family_payload(spec)

    assert payload["id"] == "mls"
    assert payload["model_brier"] is not None
    assert payload["confidence"]
    assert payload["worst_home_teams"]
    assert not payload["worst_home_teams"][0]["team"].startswith("0KP")
    assert "mls" in payload["leagues"]
    assert payload["forward_summary"]["matches"]["total"] > 0
    assert "mls" in payload["league_diagnostics"]
    assert "underdog_calibration" in payload
    assert "historical_market_disagreement" in payload


def test_current_diagnostics_bins_underdogs_and_value_gaps():
    payload = {
        "league": {"name": "Test League"},
        "games": [
            {"home": "A", "away": "B", "pH": 0.62, "pD": 0.22, "pA": 0.16,
             "lam": 2.1, "mu": 0.8, "result": "H", "mkt_home": 0.55, "mkt_away": 0.20},
            {"home": "C", "away": "D", "pH": 0.34, "pD": 0.33, "pA": 0.33,
             "lam": 1.0, "mu": 0.9, "result": None},
            {"home": "E", "away": "F", "pH": 0.24, "pD": 0.31, "pA": 0.45,
             "lam": 1.2, "mu": 1.1, "result": "A", "mkt_home": 0.14, "mkt_away": 0.50},
        ],
        "standings": [
            {"team": "A", "proj_rank": 2.0},
            {"team": "B", "proj_rank": 15.0},
        ],
        "squad_value": {
            "A": {"league_rank": 10},
            "B": {"league_rank": 2},
        },
    }

    diag = build_slice_report._league_current_diagnostics("test", payload)

    assert diag["matches"] == {"total": 3, "upcoming": 1, "played": 2, "market": 2}
    assert any(row["bucket"] == ">60%" and row["played_n"] == 1 for row in diag["favorite_bins"])
    assert any(row["bucket"] == "30%+" for row in diag["draw_bins"])
    assert any(row["bucket"] == "low total" for row in diag["total_goals_draw"])
    assert diag["underdogs"]["model_count"] == 2
    assert diag["underdogs"]["disagreement_count"] == 1
    assert diag["market_disagreement"]["status"] == "ok"
    assert any(row["bucket"] == "4 to 8pp" for row in diag["market_disagreement"]["by_edge"])
    assert diag["market_disagreement"]["market_underdogs"]["n"] == 2
    assert diag["value_rank_gaps"][0]["team"] == "B"


def test_aggregate_forward_includes_draw_total_and_market_buckets():
    league_diags = {
        "a": {
            "matches": {"total": 3, "upcoming": 1, "played": 2, "market": 2},
            "underdogs": {"model_count": 2, "upcoming_count": 1, "market_count": 1, "disagreement_count": 1},
            "draw_bins": [{"bucket": "30%+", "n": 2}],
            "total_goals_draw": [
                {"bucket": "low total", "n": 2, "played_n": 2, "mean_total": 2.1,
                 "mean_draw_prob": 0.31, "draw_hit_rate": 0.5}
            ],
            "market_disagreement": {
                "by_edge": [
                    {"bucket": "8pp+", "n": 2, "mean_model_prob": 0.35,
                     "mean_market_prob": 0.25, "mean_edge_pp": 10.0, "hit_rate": 0.5}
                ],
                "market_underdogs": {"n": 2, "hit_rate": 0.5},
                "disagreement_underdogs": {"n": 1, "hit_rate": 1.0},
            },
            "value_rank_gaps": [],
            "league": "a",
            "league_name": "A",
        }
    }

    summary = build_slice_report._aggregate_forward(league_diags)

    assert summary["total_goals_draw"][0]["bucket"] == "low total"
    assert summary["market_disagreement"]["status"] == "ok"
    assert summary["market_disagreement"]["by_edge"][0]["bucket"] == "8pp+"
    assert summary["market_disagreement"]["disagreement_underdogs"]["hit_rate"] == 1.0


def test_main_writes_valid_js_payload(tmp_path, monkeypatch):
    out = tmp_path / "model-slices.js"
    monkeypatch.setattr(build_slice_report, "OUT", out)

    assert build_slice_report.main() == 0
    text = out.read_text()
    match = re.match(r"window\.MODEL_SLICES\s*=\s*(.*);\s*$", text)
    assert match
    data = json.loads(match.group(1))
    assert data["status"] == "ok"
    assert data["league_family"]["epl"] == "eur_big5"
    assert any(f["id"] == "eur_tiers" for f in data["families"])


def test_eur_tiers_can_surface_promoted_relegated_windows():
    spec = next(f for f in build_slice_report.FAMILIES if f["id"] == "eur_tiers")
    payload = build_slice_report._family_payload(spec)

    assert "promoted_relegated_windows" in payload
