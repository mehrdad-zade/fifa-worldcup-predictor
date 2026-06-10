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

# Per-team feature cache: populated on first use, valid until explicitly cleared.
# Eliminates repeated DB queries during Monte Carlo simulation (10k runs × 80 matches
# would otherwise fire ~8M queries against the same immutable data).
_TEAM_FEAT_CACHE: dict[int, dict] = {}


def clear_feature_cache() -> None:
    """Invalidate the per-team cache — call after data ingestion."""
    _TEAM_FEAT_CACHE.clear()


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


def _team_features(team_id: int) -> dict:
    """Return cached per-team features (no disruption adjustment)."""
    if team_id not in _TEAM_FEAT_CACHE:
        status = get_group_status(team_id)
        _TEAM_FEAT_CACHE[team_id] = {
            "elo": get_current_elo(team_id),
            "momentum": get_momentum_score(team_id),
            "fitness_base": get_squad_fitness(team_id, 0.0),
            "strength": get_squad_strength(team_id),
            "points": status["points"],
            "goal_diff": status["goal_differential"],
            "position": status["position_in_group"],
        }
    return _TEAM_FEAT_CACHE[team_id]


def build_feature_vector(
    home_team_id: int,
    away_team_id: int,
    stage: str = "Group Stage",
    home_disruption: float = 0.0,
    away_disruption: float = 0.0,
) -> pd.DataFrame:
    """Return a single-row DataFrame with all features."""
    h = _team_features(home_team_id)
    a = _team_features(away_team_id)

    # Apply disruption on top of cached base fitness
    home_fitness = max(0.0, h["fitness_base"] - home_disruption * 0.3)
    away_fitness = max(0.0, a["fitness_base"] - away_disruption * 0.3)

    row = {
        "home_elo": h["elo"],
        "away_elo": a["elo"],
        "elo_diff": h["elo"] - a["elo"],
        "home_momentum": h["momentum"],
        "away_momentum": a["momentum"],
        "home_fitness": home_fitness,
        "away_fitness": away_fitness,
        "home_strength": h["strength"],
        "away_strength": a["strength"],
        "home_points": h["points"],
        "away_points": a["points"],
        "home_goal_diff": h["goal_diff"],
        "away_goal_diff": a["goal_diff"],
        "home_position": h["position"],
        "away_position": a["position"],
        "stage_encoded": _STAGE_MAP.get(stage, 0),
        "is_neutral_venue": 1,
    }

    return pd.DataFrame([row], columns=FEATURE_COLUMNS)
