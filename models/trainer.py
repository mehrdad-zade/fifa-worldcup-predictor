"""
Training pipeline: loads historical match data from SQLite, builds feature
matrices, trains Poisson + XGBoost + LightGBM, saves artifacts.

Called from scripts/train_models.py.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from config.settings import settings
from db.database import query_df
from features.feature_matrix import build_feature_vector, FEATURE_COLUMNS
from models.poisson_model import PoissonModel
from models.xgb_model import XGBModel
from models.lgbm_model import LGBMModel

_ARTIFACTS = Path("models/artifacts")


def load_historical_matches() -> tuple[pd.DataFrame, pd.Series, list[dict]]:
    """Load completed fixtures + results from DB as (X, y, raw_matches)."""
    sql = """
        SELECT
            f.fixture_id, f.home_team_id, f.away_team_id, f.stage,
            r.home_score, r.away_score
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE r.home_score IS NOT NULL
    """
    df = query_df(sql)
    if df.empty:
        return pd.DataFrame(), pd.Series(dtype=str), []

    rows = []
    labels = []
    raw_matches = []
    for _, row in df.iterrows():
        ht, at = int(row["home_team_id"]), int(row["away_team_id"])
        hs, as_ = int(row["home_score"]), int(row["away_score"])
        raw_matches.append({"home_team_id": ht, "away_team_id": at,
                             "home_score": hs, "away_score": as_})
        features = build_feature_vector(ht, at, str(row["stage"]))
        rows.append(features.iloc[0])
        if hs > as_:
            labels.append("home_win")
        elif hs < as_:
            labels.append("away_win")
        else:
            labels.append("draw")

    X = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    y = pd.Series(labels, name="outcome")
    return X, y, raw_matches


def train_all(version: str | None = None, n_optuna_trials: int = 50) -> None:
    version = version or settings.model_version
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print("Loading training data from DB...")
    X, y, raw_matches = load_historical_matches()
    if X.empty:
        print("No training data found. Run ingestion pipeline first.")
        return

    print(f"Training on {len(X)} matches...")

    # ── Poisson ────────────────────────────────────────────────
    print("Fitting Poisson model...")
    poisson = PoissonModel()
    poisson.fit(raw_matches)
    poisson.save(str(_ARTIFACTS / f"poisson_{version}.pkl"))
    print(f"  Saved poisson_{version}.pkl")

    # ── XGBoost ────────────────────────────────────────────────
    print(f"Training XGBoost (Optuna {n_optuna_trials} trials)...")
    xgb_model = XGBModel()
    xgb_model.fit(X, y, n_optuna_trials=n_optuna_trials)
    xgb_model.save(str(_ARTIFACTS / f"xgb_{version}.pkl"))
    print(f"  Saved xgb_{version}.pkl")
    importances = xgb_model.feature_importance()
    top5 = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"  Top-5 features: {top5}")

    # ── LightGBM ───────────────────────────────────────────────
    print(f"Training LightGBM (Optuna {n_optuna_trials} trials)...")
    lgbm_model = LGBMModel()
    lgbm_model.fit(X, y, n_optuna_trials=n_optuna_trials)
    lgbm_model.save(str(_ARTIFACTS / f"lgbm_{version}.pkl"))
    print(f"  Saved lgbm_{version}.pkl")

    print(f"\nAll models saved to {_ARTIFACTS}/")
