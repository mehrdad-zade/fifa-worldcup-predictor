"""Tests for ensemble prediction (models not fitted — uses fallback probs)."""
import pytest
from models.ensemble import Ensemble, PredictionResult


def test_ensemble_predict_returns_valid_probs():
    ensemble = Ensemble()  # no models loaded — uses uniform 1/3 fallback
    result = ensemble.predict(1, 2, "Group Stage")
    assert isinstance(result, PredictionResult)
    total = result.prob_home_win + result.prob_draw + result.prob_away_win
    assert abs(total - 1.0) < 1e-5


def test_ensemble_predict_different_teams_same_probs_when_no_models():
    """Without fitted models, predictions are symmetric."""
    e = Ensemble()
    r1 = e.predict(1, 2)
    r2 = e.predict(3, 4)
    # Both should be 1/3 each since no model is loaded
    assert abs(r1.prob_home_win - r2.prob_home_win) < 1e-5


def test_prediction_result_as_dict():
    e = Ensemble()
    result = e.predict(1, 2, "Final")
    d = result.as_dict()
    assert "prob_home_win" in d
    assert "predicted_home" in d
    assert d["stage"] == "Final"


def test_ensemble_probs_sum_to_one_after_blend():
    e = Ensemble()
    result = e.predict(5, 6, "R16")
    total = result.prob_home_win + result.prob_draw + result.prob_away_win
    assert abs(total - 1.0) < 1e-4
