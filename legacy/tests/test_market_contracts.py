import pytest

from data_pipeline.odds_client import normalize_outcome
from market.clv_tracker import evaluate_match
from market.kelly import full_kelly, vig_adjusted_prob


def test_normalize_odds_outcomes_to_internal_contract():
    event = {"home_team": "Columbus Crew", "away_team": "Inter Miami CF"}

    assert normalize_outcome("Columbus Crew", event) == "home"
    assert normalize_outcome("Inter Miami CF", event) == "away"
    assert normalize_outcome("Draw", event) == "draw"
    assert normalize_outcome("Unmapped", event) is None


def test_vig_adjusted_probabilities_sum_to_one():
    probs = vig_adjusted_prob(2.2, 3.4, 3.1)
    total = probs["home"] + probs["draw"] + probs["away"]
    assert total == pytest.approx(1.0)


def test_full_kelly_returns_zero_for_negative_ev():
    assert full_kelly(0.30, 2.0) == 0.0


def test_evaluate_match_uses_deterministic_bet_id_and_positive_clv():
    model_probs = {"prob_home": 0.60, "prob_draw": 0.20, "prob_away": 0.20}
    opening = {"home": 2.4, "draw": 3.4, "away": 3.0}
    closing = {"home": 2.0, "draw": 3.5, "away": 4.0}

    first = evaluate_match("abc123", model_probs, opening, closing, edge_threshold_pct=0)
    second = evaluate_match("abc123", model_probs, opening, closing, edge_threshold_pct=0)

    home_bet = next(b for b in first if b["outcome_backed"] == "home")
    home_bet_again = next(b for b in second if b["outcome_backed"] == "home")
    assert home_bet["bet_id"] == home_bet_again["bet_id"]
    assert home_bet["clv"] > 0
