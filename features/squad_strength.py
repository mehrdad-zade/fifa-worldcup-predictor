"""
Squad Strength Index: mean(player_rating_i × fitness_i) over top 23 rostered players.

player_rating is derived from FBref SCA/GCA composite, normalised to [0, 1].
"""
import numpy as np

from db.database import query_df

_TOP_N = 23


def _compute_player_rating(sca: float, gca: float, goals: float, assists: float) -> float:
    """Weighted composite of FBref attacking contribution metrics."""
    raw = sca * 0.3 + gca * 0.5 + goals * 1.0 + assists * 0.7
    return raw  # normalised across the squad below


def get_squad_strength(team_id: int) -> float:
    """Return squad strength index ∈ [0, 1]."""
    df = query_df(
        "SELECT minutes_played, sca, gca, goals, assists, is_injured, is_suspended "
        "FROM player_stats WHERE team_id = ? ORDER BY minutes_played DESC LIMIT ?",
        (team_id, _TOP_N),
    )
    if df.empty:
        return 0.5  # neutral default

    ratings = df.apply(
        lambda r: _compute_player_rating(r["sca"], r["gca"], r["goals"], r["assists"]),
        axis=1,
    ).values

    # Normalise so max player = 1.0
    max_r = ratings.max()
    if max_r > 0:
        ratings = ratings / max_r

    # Per-player fitness (injured or suspended players penalised)
    fitnesses = np.where(
        (df["is_injured"] == 1) | (df["is_suspended"] == 1),
        0.5,  # partial availability
        1.0,
    )

    strength = float(np.mean(ratings * fitnesses))
    return round(min(1.0, max(0.0, strength)), 4)
