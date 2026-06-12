import hashlib

from models.stacking_ensemble import StackingEnsemble


def test_store_predictions_uses_deterministic_prediction_id(monkeypatch):
    calls = []

    def fake_execute(sql, params):
        calls.append((sql, params))

    monkeypatch.setattr("models.stacking_ensemble.db_utils.execute", fake_execute)

    ensemble = StackingEnsemble()
    probs = {
        "prob_home": 0.5,
        "prob_draw": 0.25,
        "prob_away": 0.25,
        "prob_over": 0.55,
        "prob_under": 0.45,
    }
    ensemble.store_predictions("match1", "ensemble", probs, "abc")

    expected = hashlib.md5("match1_ensemble".encode()).hexdigest()[:20]
    assert calls[0][1][0] == expected
    assert "ON CONFLICT (prediction_id) DO UPDATE" in calls[0][0]
