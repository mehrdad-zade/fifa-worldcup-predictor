"""
Momentum Score: weighted sum of recent trophy wins, decaying exponentially with time.

momentum = Σ multiplier_i × exp(-days_since_i / 180)

Multipliers:
  WC             = 3.0
  Continental    = 2.5   (Euros, Copa América, AFCON, etc.)
  NationsLeague  = 1.5
  Friendly       = 0.3
"""
import math
from datetime import date

from db.database import query_df

_HALF_LIFE_DAYS = 180.0

_MULTIPLIERS = {
    "WC": 3.0,
    "Continental": 2.5,
    "NationsLeague": 1.5,
    "Friendly": 0.3,
}


def get_momentum_score(team_id: int, reference_date: date | None = None) -> float:
    if reference_date is None:
        reference_date = date.today()

    df = query_df(
        "SELECT tournament_type, importance_multiplier, won_date "
        "FROM trophy_events WHERE team_id = ?",
        (team_id,),
    )
    if df.empty:
        return 0.0

    score = 0.0
    for _, row in df.iterrows():
        try:
            won = date.fromisoformat(str(row["won_date"]))
        except ValueError:
            continue
        days_since = (reference_date - won).days
        if days_since < 0:
            continue
        multiplier = float(row.get("importance_multiplier") or
                           _MULTIPLIERS.get(str(row["tournament_type"]), 1.0))
        score += multiplier * math.exp(-days_since / _HALF_LIFE_DAYS)

    return round(score, 4)


def add_trophy_event(
    team_id: int,
    tournament_name: str,
    tournament_type: str,
    won_date: str,
) -> None:
    from db.database import execute_sql

    multiplier = _MULTIPLIERS.get(tournament_type, 1.0)
    execute_sql(
        "INSERT INTO trophy_events (team_id, tournament_name, tournament_type, won_date, importance_multiplier) "
        "VALUES (?, ?, ?, ?, ?)",
        (team_id, tournament_name, tournament_type, won_date, multiplier),
    )
