"""XGBoost multiclass classifier (home_win=0, draw=1, away_win=2)."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder

try:
    import xgboost as xgb
    import optuna

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

from features.feature_matrix import FEATURE_COLUMNS


class XGBModel:
    def __init__(self) -> None:
        self._model = None
        self._le = LabelEncoder()
        self._fitted = False

    def fit(self, X: pd.DataFrame, y: pd.Series, n_optuna_trials: int = 50) -> "XGBModel":
        if not _AVAILABLE:
            raise ImportError("xgboost and optuna are required for training.")

        y_enc = self._le.fit_transform(y)

        def objective(trial: "optuna.Trial") -> float:
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 800),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "objective": "multi:softprob",
                "num_class": 3,
                "eval_metric": "mlogloss",
                "use_label_encoder": False,
                "random_state": 42,
            }
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            scores = []
            for train_idx, val_idx in cv.split(X, y_enc):
                m = xgb.XGBClassifier(**params)
                m.fit(X.iloc[train_idx], y_enc[train_idx],
                      eval_set=[(X.iloc[val_idx], y_enc[val_idx])],
                      verbose=False)
                scores.append(m.score(X.iloc[val_idx], y_enc[val_idx]))
            return float(np.mean(scores))

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_optuna_trials, show_progress_bar=False)

        best = study.best_params
        best.update({
            "objective": "multi:softprob",
            "num_class": 3,
            "eval_metric": "mlogloss",
            "use_label_encoder": False,
            "random_state": 42,
        })
        self._model = xgb.XGBClassifier(**best)
        self._model.fit(X, y_enc)
        self._fitted = True
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return shape (n_samples, 3) — [p_home_win, p_draw, p_away_win]."""
        if not self._fitted or self._model is None:
            return np.array([[1 / 3, 1 / 3, 1 / 3]])
        return self._model.predict_proba(X[FEATURE_COLUMNS])

    def feature_importance(self) -> dict[str, float]:
        if self._model is None:
            return {}
        return dict(zip(FEATURE_COLUMNS, self._model.feature_importances_))

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str) -> "XGBModel":
        return joblib.load(path)
