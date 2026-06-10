"""
Cached data access layer for Streamlit pages.
All functions use @st.cache_data(ttl=300) — a 5-minute cache.
No direct DB access should happen in page files.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import settings
from db.database import query_df
from predictions.snapshot_writer import load_latest_snapshot


@st.cache_data(ttl=300)
def load_todays_fixtures() -> pd.DataFrame:
    today = date.today().isoformat()
    return query_df(
        """
        SELECT
            f.fixture_id, f.stage, f.match_date, f.venue,
            ht.name AS home_team, at.name AS away_team,
            f.home_team_id, f.away_team_id,
            r.home_score, r.away_score, r.status
        FROM fixtures f
        JOIN teams ht ON f.home_team_id = ht.team_id
        JOIN teams at ON f.away_team_id = at.team_id
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE DATE(f.match_date) = ?
        ORDER BY f.match_date
        """,
        (today,),
    )


@st.cache_data(ttl=300)
def load_todays_predictions() -> list[dict]:
    snapshot = load_latest_snapshot()
    if snapshot:
        return snapshot.get("daily_predictions", [])
    return []


@st.cache_data(ttl=300)
def load_bracket_prediction() -> dict:
    snapshot = load_latest_snapshot()
    if snapshot:
        return snapshot.get("final_bracket_prediction", {})
    return {}


@st.cache_data(ttl=600)
def load_evaluation_metrics() -> pd.DataFrame:
    return query_df(
        """
        SELECT
            el.model_version,
            f.stage,
            AVG(el.brier_score) AS avg_brier,
            AVG(el.rps)         AS avg_rps,
            AVG(el.outcome_correct) AS accuracy,
            COUNT(*)            AS n_matches,
            el.evaluated_at
        FROM evaluation_log el
        JOIN fixtures f ON el.fixture_id = f.fixture_id
        GROUP BY el.model_version, f.stage
        ORDER BY el.evaluated_at DESC
        """
    )


@st.cache_data(ttl=600)
def load_feature_importance() -> dict[str, float]:
    """Load feature importance from the most recent XGBoost artifact."""
    from pathlib import Path
    import joblib

    artifacts = Path("models/artifacts")
    xgb_files = sorted(artifacts.glob("xgb_*.pkl"), reverse=True)
    if not xgb_files:
        return {}
    try:
        model = joblib.load(str(xgb_files[0]))
        return model.feature_importance()
    except Exception:
        return {}


@st.cache_data(ttl=60)
def load_live_scores() -> pd.DataFrame:
    """Fetch live scores — short TTL for in-match refresh."""
    from db.database import query_df
    return query_df(
        """
        SELECT f.fixture_id, ht.name AS home_team, at.name AS away_team,
               r.home_score, r.away_score, r.status, f.match_date
        FROM fixtures f
        JOIN teams ht ON f.home_team_id = ht.team_id
        JOIN teams at ON f.away_team_id = at.team_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE r.status NOT IN ('FT', 'AET', 'PEN')
        ORDER BY f.match_date
        """
    )


@st.cache_data(ttl=3600)
def load_all_teams() -> pd.DataFrame:
    return query_df(
        "SELECT team_id, name, group_code, confederation FROM teams ORDER BY group_code, name"
    )


@st.cache_data(ttl=3600)
def load_group_standings() -> pd.DataFrame:
    return query_df(
        """
        SELECT
            t.group_code,
            t.name       AS team,
            t.team_id,
            COALESCE(SUM(CASE
                WHEN f.home_team_id = t.team_id AND r.home_score > r.away_score THEN 3
                WHEN f.away_team_id = t.team_id AND r.away_score > r.home_score THEN 3
                WHEN r.home_score = r.away_score THEN 1
                ELSE 0
            END), 0)     AS points,
            COALESCE(SUM(CASE WHEN f.home_team_id = t.team_id THEN r.home_score
                              WHEN f.away_team_id = t.team_id THEN r.away_score
                              ELSE 0 END), 0) AS gf,
            COALESCE(SUM(CASE WHEN f.home_team_id = t.team_id THEN r.away_score
                              WHEN f.away_team_id = t.team_id THEN r.home_score
                              ELSE 0 END), 0) AS ga,
            COUNT(DISTINCT CASE WHEN (f.home_team_id = t.team_id OR f.away_team_id = t.team_id)
                                     AND r.fixture_id IS NOT NULL THEN f.fixture_id END) AS played
        FROM teams t
        LEFT JOIN fixtures f ON (f.home_team_id = t.team_id OR f.away_team_id = t.team_id)
                                 AND f.stage = 'Group Stage'
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        GROUP BY t.team_id, t.name, t.group_code
        ORDER BY t.group_code, points DESC, (gf - ga) DESC
        """
    )
