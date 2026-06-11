from __future__ import annotations

"""
Seeds Elo ratings from historical WC results stored in the DB.
Run once after initial data ingestion to prime the Elo system.

Usage: python scripts/backfill_elo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import execute_sql, query_df
from features.elo import update_elo_after_match, apply_trophy_bonus, _DEFAULT_ELO


_HISTORICAL_TROPHY_EVENTS = [
    # (team_name, tournament_name, tournament_type, won_date, multiplier)
    ("Argentina", "FIFA World Cup 2022", "WC", "2022-12-18", 3.0),
    ("France",    "UEFA Euro 2020",      "Continental", "2021-07-11", 2.5),
    ("Italy",     "UEFA Euro 2020",      "Continental", "2021-07-11", 2.5),
    ("Argentina", "Copa America 2021",   "Continental", "2021-07-10", 2.5),
    ("Spain",     "UEFA Nations League 2021", "NationsLeague", "2021-10-10", 1.5),
    ("Argentina", "Copa America 2024",   "Continental", "2024-07-15", 2.5),
    ("Spain",     "UEFA Euro 2024",      "Continental", "2024-07-14", 2.5),
    ("France",    "UEFA Nations League 2024", "NationsLeague", "2024-06-09", 1.5),
]


def _team_id_by_name(name: str) -> int | None:
    from db.database import query_one
    row = query_one("SELECT team_id FROM teams WHERE name = ?", (name,))
    return int(row["team_id"]) if row else None


def main() -> None:
    # Initial Elo seeds and trophy bonuses are handled by scripts/seed_fixtures.py.
    # This script only adds incremental updates from completed WC 2026 match results.
    df = query_df("""
        SELECT f.fixture_id, f.home_team_id, f.away_team_id,
               f.match_date, f.stage, r.home_score, r.away_score
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        ORDER BY f.match_date ASC
    """)

    if df.empty:
        print("No completed match results yet — nothing to backfill.")
        return

    print(f"Updating Elo from {len(df)} completed match(es)...")
    for _, row in df.iterrows():
        is_friendly = str(row["stage"]).lower() in ("friendly", "international friendly")
        update_elo_after_match(
            int(row["home_team_id"]),
            int(row["away_team_id"]),
            int(row["home_score"]),
            int(row["away_score"]),
            str(row["match_date"])[:10],
            is_friendly=is_friendly,
            reason=f"{row['stage']}: {row['fixture_id']}",
        )

    print("Elo update complete.")


if __name__ == "__main__":
    main()
