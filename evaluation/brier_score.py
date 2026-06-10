"""
Multi-class Brier score computation.

BS = (p_hw - o_hw)^2 + (p_d - o_d)^2 + (p_aw - o_aw)^2

A perfect prediction gives BS = 0. Random guessing gives BS = 2/3 ≈ 0.667.
A good football model should achieve BS ≈ 0.18 for group stage.
"""
import pandas as pd


def compute_brier(
    prob_home_win: float,
    prob_draw: float,
    prob_away_win: float,
    actual_outcome: str,  # "home_win", "draw", or "away_win"
) -> float:
    outcomes = {"home_win": 0, "draw": 0, "away_win": 0}
    if actual_outcome in outcomes:
        outcomes[actual_outcome] = 1

    bs = (
        (prob_home_win - outcomes["home_win"]) ** 2
        + (prob_draw - outcomes["draw"]) ** 2
        + (prob_away_win - outcomes["away_win"]) ** 2
    )
    return round(float(bs), 6)


def batch_brier(df: pd.DataFrame) -> pd.Series:
    """
    df must have columns: prob_home_win, prob_draw, prob_away_win, actual_outcome.
    Returns a Series of Brier scores indexed like df.
    """
    return df.apply(
        lambda r: compute_brier(
            r["prob_home_win"], r["prob_draw"], r["prob_away_win"], r["actual_outcome"]
        ),
        axis=1,
    )
