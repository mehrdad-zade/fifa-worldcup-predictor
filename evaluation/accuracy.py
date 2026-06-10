"""
Outcome accuracy and Ranked Probability Score (RPS) computation.

RPS accounts for the ordinal structure of outcomes (home_win > draw > away_win).
Lower RPS = better calibration.
"""
import numpy as np
import pandas as pd

_OUTCOME_ORDER = {"home_win": 0, "draw": 1, "away_win": 2}


def compute_accuracy(df: pd.DataFrame) -> dict:
    """
    df must have columns: prob_home_win, prob_draw, prob_away_win, actual_outcome.
    Returns dict with overall accuracy, per-stage breakdown (if 'stage' column present).
    """
    if df.empty:
        return {"overall_accuracy": None, "n_matches": 0}

    predicted = df.apply(
        lambda r: max(
            ["home_win", "draw", "away_win"],
            key=lambda o: r[f"prob_{o.replace('_', '_')}" if o == "draw" else f"prob_{o}"],
        ),
        axis=1,
    )
    # Simpler version: argmax of the three probability columns
    prob_cols = ["prob_home_win", "prob_draw", "prob_away_win"]
    label_map = {0: "home_win", 1: "draw", 2: "away_win"}
    predicted = df[prob_cols].idxmax(axis=1).map(
        {"prob_home_win": "home_win", "prob_draw": "draw", "prob_away_win": "away_win"}
    )
    correct = (predicted == df["actual_outcome"]).astype(int)

    result: dict = {
        "overall_accuracy": round(float(correct.mean()), 4),
        "n_matches": len(df),
        "rps": round(float(compute_rps(df).mean()), 4),
    }

    if "stage" in df.columns:
        result["by_stage"] = (
            df.assign(correct=correct)
            .groupby("stage")["correct"]
            .agg(["mean", "count"])
            .rename(columns={"mean": "accuracy", "count": "n_matches"})
            .round(4)
            .to_dict("index")
        )

    return result


def compute_rps(df: pd.DataFrame) -> pd.Series:
    """
    Ranked Probability Score per row.
    Outcomes ordered: home_win (0) < draw (1) < away_win (2).
    """
    def _rps_row(row: pd.Series) -> float:
        probs = np.array([row["prob_home_win"], row["prob_draw"], row["prob_away_win"]])
        actual_idx = _OUTCOME_ORDER.get(str(row["actual_outcome"]), 1)
        outcomes = np.zeros(3)
        outcomes[actual_idx] = 1.0

        cum_probs = np.cumsum(probs)
        cum_actual = np.cumsum(outcomes)
        return float(np.mean((cum_probs[:-1] - cum_actual[:-1]) ** 2))

    return df.apply(_rps_row, axis=1)
