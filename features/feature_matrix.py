"""
Assembles the flat feature vector for a (home_team_id, away_team_id) match pair.

FEATURE_COLUMNS is the stability contract — any change requires retraining all
models and bumping MODEL_VERSION in .env.
"""
import pandas as pd

from features.elo import get_current_elo
from features.group_status import get_group_status
from features.momentum import get_momentum_score
from features.squad_fitness import get_squad_fitness
from features.squad_strength import get_squad_strength

FEATURE_COLUMNS = [
    "home_elo",
    "away_elo",
    "elo_diff",
    "home_momentum",
    "away_momentum",
    "home_fitness",
    "away_fitness",
    "home_strength",
    "away_strength",
    "home_points",
    "away_points",
    "home_goal_diff",
    "away_goal_diff",
    "home_position",
    "away_position",
    "stage_encoded",
    "is_neutral_venue",
]

_STAGE_MAP = {
    "Group Stage": 0,
    "R32": 1,
    "R16": 2,
    "Quarter-finals": 3,
    "Semi-finals": 4,
    "Final": 5,
}


def build_feature_vector(
    home_team_id: int,
    away_team_id: int,
    stage: str = "Group Stage",
    home_disruption: float = 0.0,
    away_disruption: float = 0.0,
) -> pd.DataFrame:
    """Return a single-row DataFrame with all features."""
    home_elo = get_current_elo(home_team_id)
    away_elo = get_current_elo(away_team_id)

    home_status = get_group_status(home_team_id)
    away_status = get_group_status(away_team_id)

    row = {
        "home_elo": home_elo,
        "away_elo": away_elo,
        "elo_diff": home_elo - away_elo,
        "home_momentum": get_momentum_score(home_team_id),
        "away_momentum": get_momentum_score(away_team_id),
        "home_fitness": get_squad_fitness(home_team_id, home_disruption),
        "away_fitness": get_squad_fitness(away_team_id, away_disruption),
        "home_strength": get_squad_strength(home_team_id),
        "away_strength": get_squad_strength(away_team_id),
        "home_points": home_status["points"],
        "away_points": away_status["points"],
        "home_goal_diff": home_status["goal_differential"],
        "away_goal_diff": away_status["goal_differential"],
        "home_position": home_status["position_in_group"],
        "away_position": away_status["position_in_group"],
        "stage_encoded": _STAGE_MAP.get(stage, 0),
        "is_neutral_venue": 1,  # All WC 2026 matches are at neutral venues
    }

    return pd.DataFrame([row], columns=FEATURE_COLUMNS)
