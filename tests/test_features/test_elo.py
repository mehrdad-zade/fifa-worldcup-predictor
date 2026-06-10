"""Tests for Elo rating system."""
import pytest
from features.elo import (
    get_current_elo,
    update_elo_after_match,
    apply_trophy_bonus,
    _DEFAULT_ELO,
)


def test_default_elo_for_unknown_team(seed_teams):
    elo = get_current_elo(9999)
    assert elo == _DEFAULT_ELO


def test_winner_elo_increases(seed_teams):
    update_elo_after_match(1, 2, 2, 0, "2026-06-11")
    assert get_current_elo(1) > _DEFAULT_ELO
    assert get_current_elo(2) < _DEFAULT_ELO


def test_draw_adjusts_based_on_elo_diff(seed_teams):
    # Equal teams drawing: no change
    update_elo_after_match(1, 2, 1, 1, "2026-06-11")
    # After a draw between equal teams, changes should be near zero
    delta = abs(get_current_elo(1) - _DEFAULT_ELO)
    assert delta < 5.0


def test_trophy_bonus_positive(seed_teams):
    elo_before = get_current_elo(1)
    new_elo = apply_trophy_bonus(1, "WC", "2026-07-19", 3.0)
    assert new_elo > elo_before
    assert new_elo == elo_before + 50.0 * 3.0


def test_elo_conserved_on_draw_equal_teams(seed_teams):
    """Sum of both teams' Elo should be roughly conserved on a draw."""
    elo1_before = get_current_elo(1)
    elo2_before = get_current_elo(2)
    update_elo_after_match(1, 2, 1, 1, "2026-06-12")
    elo1_after = get_current_elo(1)
    elo2_after = get_current_elo(2)
    assert abs((elo1_after + elo2_after) - (elo1_before + elo2_before)) < 1.0
