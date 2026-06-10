"""
Squad Fitness Score: 0.0 (exhausted/injured) → 1.0 (fully fit).

Formula:
  fitness = 1.0 - min(1.0, normalized_minutes × 0.4 + injuries × 0.05 + suspensions × 0.08)

normalized_minutes = (mean club minutes in last 30 days) / MAX_MINUTES_THRESHOLD
"""
from db.database import query_df

_MAX_MINUTES = 2700.0  # ~30 matches × 90 min — normalisation ceiling


def get_squad_fitness(team_id: int, disruption_severity: float = 0.0) -> float:
    """Return fitness score ∈ [0, 1] for a team's squad."""
    df = query_df(
        "SELECT minutes_played, is_injured, is_suspended FROM player_stats WHERE team_id = ?",
        (team_id,),
    )
    if df.empty:
        return max(0.0, 1.0 - disruption_severity)

    mean_minutes = float(df["minutes_played"].mean())
    injuries = int(df["is_injured"].sum())
    suspensions = int(df["is_suspended"].sum())

    normalized = min(1.0, mean_minutes / _MAX_MINUTES)
    penalty = normalized * 0.4 + injuries * 0.05 + suspensions * 0.08 + disruption_severity * 0.3
    return round(max(0.0, 1.0 - min(1.0, penalty)), 4)
