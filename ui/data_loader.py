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


@st.cache_data(ttl=300)
def load_group_stage_matches() -> dict[str, list[dict]]:
    """Return {group_code: [match_dict, ...]} with predicted scores per group match."""
    snapshot = load_latest_snapshot()
    if snapshot:
        return snapshot.get("final_bracket_prediction", {}).get("group_stage_matches", {})
    return {}


@st.cache_data(ttl=300)
def load_predicted_standings() -> dict[str, list[dict]]:
    """Return {group_code: [team_standing_dict, ...]} sorted by predicted position."""
    snapshot = load_latest_snapshot()
    if snapshot:
        return snapshot.get("final_bracket_prediction", {}).get("predicted_standings", {})
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


@st.cache_data(ttl=300)
def load_all_results() -> dict[str, str]:
    """Return {fixture_id: 'H-A'} for every completed match in the DB."""
    df = query_df("SELECT fixture_id, home_score, away_score FROM results")
    if df.empty:
        return {}
    return {
        row["fixture_id"]: f"{int(row['home_score'])}-{int(row['away_score'])}"
        for _, row in df.iterrows()
    }


@st.cache_data(ttl=300)
def load_all_prediction_probs() -> dict[str, dict]:
    """Return {fixture_id: {hw, d, aw}} using the most recent prediction per fixture."""
    df = query_df(
        """
        SELECT p.fixture_id, p.prob_home_win, p.prob_draw, p.prob_away_win
        FROM predictions p
        JOIN (
            SELECT fixture_id, MAX(created_at) AS latest
            FROM predictions
            GROUP BY fixture_id
        ) lp ON p.fixture_id = lp.fixture_id AND p.created_at = lp.latest
        """
    )
    if df.empty:
        return {}
    return {
        row["fixture_id"]: {
            "hw": float(row["prob_home_win"]),
            "d": float(row["prob_draw"]),
            "aw": float(row["prob_away_win"]),
        }
        for _, row in df.iterrows()
    }


@st.cache_data(ttl=300)
def load_all_predictions() -> dict[str, str]:
    """Return {fixture_id: 'H-A'} using the most recently created prediction per fixture."""
    df = query_df(
        """
        SELECT p.fixture_id, p.predicted_home, p.predicted_away
        FROM predictions p
        JOIN (
            SELECT fixture_id, MAX(created_at) AS latest
            FROM predictions
            GROUP BY fixture_id
        ) lp ON p.fixture_id = lp.fixture_id AND p.created_at = lp.latest
        """
    )
    if df.empty:
        return {}
    return {
        row["fixture_id"]: f"{int(row['predicted_home'])}-{int(row['predicted_away'])}"
        for _, row in df.iterrows()
    }


@st.cache_data(ttl=300)
def load_knockout_matchups() -> dict[str, str]:
    """Return {fixture_id: 'TeamA v TeamB'} for every KO fixture with resolved teams."""
    df = query_df("""
        SELECT f.fixture_id, t1.name AS home, t2.name AS away
        FROM fixtures f
        JOIN teams t1 ON f.home_team_id = t1.team_id
        JOIN teams t2 ON f.away_team_id = t2.team_id
        WHERE f.stage != 'Group Stage'
    """)
    if df.empty:
        return {}
    return {
        row["fixture_id"]: f"{row['home']} v {row['away']}"
        for _, row in df.iterrows()
    }


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
