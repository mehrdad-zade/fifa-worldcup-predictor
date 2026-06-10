"""Tests for daily_predictor module."""
import pytest
from predictions.daily_predictor import predict_match


def test_predict_match_returns_expected_keys(seed_teams):
    result = predict_match(1, 2, stage="Group Stage", use_news=False)
    assert "fixture_id" in result
    assert "stage" in result
    assert "predicted_score" in result
    assert "probabilities" in result
    probs = result["probabilities"]
    assert "home_win" in probs
    assert "draw" in probs
    assert "away_win" in probs


def test_predict_match_probs_sum_to_one(seed_teams):
    result = predict_match(1, 2, use_news=False)
    probs = result["probabilities"]
    total = probs["home_win"] + probs["draw"] + probs["away_win"]
    assert abs(total - 1.0) < 1e-4


def test_predict_match_actual_score_is_null(seed_teams):
    result = predict_match(1, 2, use_news=False)
    assert result["actual_score"] is None


def test_predict_match_includes_team_names(seed_teams):
    result = predict_match(1, 2, use_news=False)
    assert result["home_team"] == "Spain"
    assert result["away_team"] == "Germany"
