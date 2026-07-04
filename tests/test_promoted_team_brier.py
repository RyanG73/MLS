import scripts.eval.promoted_team_brier as ptb


def _fake_evaluate_pair(results):
    def _fn(tier2_lid, tier1_lid):
        return results[f"{tier2_lid}_to_{tier1_lid}"]
    return _fn


def test_pooled_summary_weights_by_match_count(monkeypatch):
    results = {
        "championship_to_epl": {"pair": "championship_to_epl", "n_matches": 100,
                                "brier_tier_bridge": 0.60},
        "serie-b_to_serie-a": {"pair": "serie-b_to_serie-a", "n_matches": 300,
                               "brier_tier_bridge": 0.65},
    }
    monkeypatch.setattr(ptb, "evaluate_pair", _fake_evaluate_pair(results))
    out = ptb.pooled_summary(pairs=[("championship", "epl"), ("serie-b", "serie-a")])
    # weighted mean: (100*0.60 + 300*0.65) / 400 = 0.6375
    assert out["n_matches"] == 400
    assert round(out["pooled_brier"], 4) == 0.6375
    assert out["exceeds_naive"] is False  # below 2/3 = 0.6667


def test_pooled_summary_flags_when_above_naive(monkeypatch):
    results = {
        "championship_to_epl": {"pair": "championship_to_epl", "n_matches": 50,
                                "brier_tier_bridge": 0.70},
    }
    monkeypatch.setattr(ptb, "evaluate_pair", _fake_evaluate_pair(results))
    out = ptb.pooled_summary(pairs=[("championship", "epl")])
    assert out["pooled_brier"] == 0.70
    assert out["exceeds_naive"] is True


def test_pooled_summary_handles_no_matches(monkeypatch):
    results = {
        "championship_to_epl": {"pair": "championship_to_epl", "n_matches": 0,
                                "brier_tier_bridge": None},
    }
    monkeypatch.setattr(ptb, "evaluate_pair", _fake_evaluate_pair(results))
    out = ptb.pooled_summary(pairs=[("championship", "epl")])
    assert out["n_matches"] == 0
    assert out["pooled_brier"] is None
    assert out["exceeds_naive"] is False
