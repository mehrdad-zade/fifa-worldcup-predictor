"""
Elo rating tracker for WC 2026 teams.

K=40 for competitive matches (WC qualifying, tournaments).
K=20 for friendlies.
Trophy bonus: +50 * importance_multiplier added to winner's Elo.
"""
from datetime import date

from db.database import execute_sql, query_df, query_one

_DEFAULT_ELO = 1500.0

_K_COMPETITIVE = 40.0
_K_FRIENDLY = 20.0
_TROPHY_BONUS_BASE = 50.0


def get_current_elo(team_id: int) -> float:
    row = query_one(
        "SELECT elo_rating FROM elo_history "
        "WHERE team_id = ? ORDER BY effective_date DESC, id DESC LIMIT 1",
        (team_id,),
    )
    return float(row["elo_rating"]) if row else _DEFAULT_ELO


def update_elo_after_match(
    home_id: int,
    away_id: int,
    home_score: int,
    away_score: int,
    match_date: str,
    is_friendly: bool = False,
    reason: str = "",
) -> tuple[float, float]:
    """Update Elo for both teams after a match; return new (home_elo, away_elo)."""
    home_elo = get_current_elo(home_id)
    away_elo = get_current_elo(away_id)
    k = _K_FRIENDLY if is_friendly else _K_COMPETITIVE

    expected_home = 1.0 / (1.0 + 10.0 ** ((away_elo - home_elo) / 400.0))
    expected_away = 1.0 - expected_home

    if home_score > away_score:
        actual_home, actual_away = 1.0, 0.0
    elif home_score < away_score:
        actual_home, actual_away = 0.0, 1.0
    else:
        actual_home = actual_away = 0.5

    new_home = home_elo + k * (actual_home - expected_home)
    new_away = away_elo + k * (actual_away - expected_away)

    _save_elo(home_id, new_home, match_date, reason or f"match vs {away_id}")
    _save_elo(away_id, new_away, match_date, reason or f"match vs {home_id}")

    return new_home, new_away


def apply_trophy_bonus(team_id: int, tournament_type: str, won_date: str, multiplier: float) -> float:
    """Add a one-off trophy bonus to a team's Elo."""
    current = get_current_elo(team_id)
    bonus = _TROPHY_BONUS_BASE * multiplier
    new_elo = current + bonus
    _save_elo(team_id, new_elo, won_date, f"trophy bonus: {tournament_type} (×{multiplier})")
    return new_elo


def _save_elo(team_id: int, elo: float, effective_date: str, reason: str) -> None:
    execute_sql(
        "INSERT INTO elo_history (team_id, elo_rating, effective_date, reason) VALUES (?, ?, ?, ?)",
        (team_id, round(elo, 2), effective_date, reason),
    )


