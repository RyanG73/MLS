from scripts.promotion_gate import evaluate_gate


def _report(run_id, avg_brier):
    return {
        "run_id": run_id,
        "avg_brier": avg_brier,
        "max_decile_cal_error": 0.02,
        "per_season": {"2024": avg_brier},
        "coverage_by_season": {"2024": 100},
        "slices": {
            "by_season": {"2024": {"n": 100, "brier_sum": avg_brier}},
            "by_confidence": {"40-50%": {"n": 100, "brier_sum": avg_brier}},
            "underdog_calibration": {"significant": {"n": 42}},
            "draw_reliability": [{"bin": "0.25", "n": 100}],
        },
    }


def test_gate_reports_trust_diagnostics_advisory():
    champion = _report("champion", 0.64)
    challenger = _report("challenger", 0.639)

    _, checks = evaluate_gate(champion, challenger)
    by_name = {name: detail for name, _, detail in checks}

    assert "trust_diagnostics" in by_name
    assert "underdogs n=42" in by_name["trust_diagnostics"]
