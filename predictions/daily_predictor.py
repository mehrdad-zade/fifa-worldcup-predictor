from __future__ import annotations

"""
Daily Mode: given two team IDs and a stage, returns a full prediction dict
including W/D/L probabilities and expected scoreline.
"""
from datetime import date

from db.database import query_df, query_one
from models.ensemble import get_ensemble, PredictionResult
from pipeline.claude_news import get_team_news


def predict_match(
    home_team_id: int,
    away_team_id: int,
    stage: str = "Group Stage",
    match_date: str | None = None,
    use_news: bool = True,
) -> dict:
    """Return a full prediction dict for a single fixture."""
    if match_date is None:
        match_date = date.today().isoformat()

    home_disruption = 0.0
    away_disruption = 0.0

    if use_news:
        home_name = _team_name(home_team_id)
        away_name = _team_name(away_team_id)
        if home_name:
            news = get_team_news(home_team_id, home_name, match_date)
            home_disruption = float(news.get("disruption_severity", 0.0))
        if away_name:
            news = get_team_news(away_team_id, away_name, match_date)
            away_disruption = float(news.get("disruption_severity", 0.0))

    result: PredictionResult = get_ensemble().predict(
        home_team_id, away_team_id, stage, home_disruption, away_disruption
    )

    home_name = _team_name(home_team_id) or str(home_team_id)
    away_name = _team_name(away_team_id) or str(away_team_id)

    return {
        "fixture_id": f"manual-{home_team_id}-{away_team_id}-{match_date}",
        "stage": stage,
        "home_team": home_name,
        "away_team": away_name,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "predicted_score": {
            "home": result.predicted_home,
            "away": result.predicted_away,
        },
        "probabilities": {
            "home_win": result.prob_home_win,
            "draw": result.prob_draw,
            "away_win": result.prob_away_win,
        },
        "model_version": result.model_version,
        "actual_score": None,
    }


def predict_todays_matches(use_news: bool = True) -> list[dict]:
    """Return predictions for all fixtures scheduled today."""
    today = date.today().isoformat()
    df = query_df(
        "SELECT fixture_id, home_team_id, away_team_id, stage, match_date "
        "FROM fixtures WHERE DATE(match_date) = ? ORDER BY match_date",
        (today,),
    )
    if df.empty:
        return []

    predictions = []
    for _, row in df.iterrows():
        pred = predict_match(
            int(row["home_team_id"]),
            int(row["away_team_id"]),
            str(row["stage"]),
            today,
            use_news=use_news,
        )
        pred["fixture_id"] = str(row["fixture_id"])
        predictions.append(pred)

    return predictions


def _team_name(team_id: int) -> str | None:
    row = query_one("SELECT name FROM teams WHERE team_id = ?", (team_id,))
    return str(row["name"]) if row else None
