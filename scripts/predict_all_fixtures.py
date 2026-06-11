"""
Generates and stores predictions for every group-stage fixture in the DB.

Knockout fixtures are skipped (team IDs are NULL until group stage resolves).
Predictions are upserted into the predictions table so it is safe to re-run.

Usage:
  python scripts/predict_all_fixtures.py
  python scripts/predict_all_fixtures.py --force   # re-predict even if already present
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from db.database import execute_sql, query_df
from models.ensemble import get_ensemble


def predict_all(force: bool = False) -> int:
    """Predict all fixtures with known home/away teams; return count written."""
    sql = """
        SELECT fixture_id, home_team_id, away_team_id, stage
        FROM fixtures
        WHERE home_team_id IS NOT NULL AND away_team_id IS NOT NULL
        ORDER BY match_date
    """
    if not force:
        sql = """
            SELECT f.fixture_id, f.home_team_id, f.away_team_id, f.stage
            FROM fixtures f
            LEFT JOIN predictions p
              ON f.fixture_id = p.fixture_id AND p.model_version = ?
            WHERE f.home_team_id IS NOT NULL
              AND f.away_team_id IS NOT NULL
              AND p.fixture_id IS NULL
            ORDER BY f.match_date
        """

    df = query_df(sql) if force else query_df(sql, (settings.model_version,))
    if df.empty:
        return 0

    ensemble = get_ensemble()
    version = settings.model_version
    count = 0

    for _, row in df.iterrows():
        try:
            result = ensemble.predict(
                int(row["home_team_id"]),
                int(row["away_team_id"]),
                str(row["stage"]),
            )
            execute_sql(
                "INSERT INTO predictions "
                "(fixture_id, model_version, predicted_home, predicted_away, "
                " prob_home_win, prob_draw, prob_away_win) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(fixture_id, model_version) DO UPDATE SET "
                "predicted_home=excluded.predicted_home, "
                "predicted_away=excluded.predicted_away, "
                "prob_home_win=excluded.prob_home_win, "
                "prob_draw=excluded.prob_draw, "
                "prob_away_win=excluded.prob_away_win",
                (
                    str(row["fixture_id"]),
                    version,
                    result.predicted_home,
                    result.predicted_away,
                    result.prob_home_win,
                    result.prob_draw,
                    result.prob_away_win,
                ),
            )
            count += 1
        except Exception as exc:
            print(f"  WARN: prediction failed for {row['fixture_id']}: {exc}")

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict all WC 2026 fixtures")
    parser.add_argument("--force", action="store_true",
                        help="Re-predict fixtures that already have predictions")
    args = parser.parse_args()

    print("Generating predictions for all fixtures...")
    n = predict_all(force=args.force)
    print(f"  {n} prediction(s) written (model: {settings.model_version})")


if __name__ == "__main__":
    main()
