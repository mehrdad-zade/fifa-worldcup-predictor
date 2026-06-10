"""
Blended ensemble: Poisson 40% + XGBoost 30% + LightGBM 30%.

Scoreline always comes from Poisson (Dixon-Coles).
W/D/L probabilities are the weighted blend.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config.settings import settings
from features.feature_matrix import build_feature_vector
from models.poisson_model import PoissonModel
from models.xgb_model import XGBModel
from models.lgbm_model import LGBMModel

_WEIGHT_POISSON = 0.40
_WEIGHT_XGB = 0.30
_WEIGHT_LGBM = 0.30

_ARTIFACTS = Path("models/artifacts")


@dataclass
class PredictionResult:
    home_team_id: int
    away_team_id: int
    stage: str
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    predicted_home: int
    predicted_away: int
    model_version: str

    def as_dict(self) -> dict:
        return {
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "stage": self.stage,
            "prob_home_win": self.prob_home_win,
            "prob_draw": self.prob_draw,
            "prob_away_win": self.prob_away_win,
            "predicted_home": self.predicted_home,
            "predicted_away": self.predicted_away,
            "model_version": self.model_version,
        }


class Ensemble:
    def __init__(self) -> None:
        self._poisson: PoissonModel | None = None
        self._xgb: XGBModel | None = None
        self._lgbm: LGBMModel | None = None
        self._loaded = False

    def load(self, version: str | None = None) -> "Ensemble":
        v = version or settings.model_version
        poisson_path = _ARTIFACTS / f"poisson_{v}.pkl"
        xgb_path = _ARTIFACTS / f"xgb_{v}.pkl"
        lgbm_path = _ARTIFACTS / f"lgbm_{v}.pkl"

        if poisson_path.exists():
            self._poisson = PoissonModel.load(str(poisson_path))
        if xgb_path.exists():
            self._xgb = XGBModel.load(str(xgb_path))
        if lgbm_path.exists():
            self._lgbm = LGBMModel.load(str(lgbm_path))

        self._loaded = True
        return self

    def predict(
        self,
        home_team_id: int,
        away_team_id: int,
        stage: str = "Group Stage",
        home_disruption: float = 0.0,
        away_disruption: float = 0.0,
    ) -> PredictionResult:
        features = build_feature_vector(
            home_team_id, away_team_id, stage, home_disruption, away_disruption
        )

        # ── Poisson ────────────────────────────────────────────
        if self._poisson is not None:
            p_pred = self._poisson.predict(home_team_id, away_team_id)
            p_probs = np.array([p_pred["prob_home_win"], p_pred["prob_draw"], p_pred["prob_away_win"]])
            pred_home = p_pred["predicted_home"]
            pred_away = p_pred["predicted_away"]
        else:
            p_probs = np.array([1 / 3, 1 / 3, 1 / 3])
            pred_home, pred_away = 1, 1

        # ── XGBoost ────────────────────────────────────────────
        if self._xgb is not None:
            xgb_probs = self._xgb.predict_proba(features)[0]
        else:
            xgb_probs = np.array([1 / 3, 1 / 3, 1 / 3])

        # ── LightGBM ───────────────────────────────────────────
        if self._lgbm is not None:
            lgbm_probs = self._lgbm.predict_proba(features)[0]
        else:
            lgbm_probs = np.array([1 / 3, 1 / 3, 1 / 3])

        blended = (
            _WEIGHT_POISSON * p_probs
            + _WEIGHT_XGB * xgb_probs
            + _WEIGHT_LGBM * lgbm_probs
        )
        blended /= blended.sum()  # renormalise

        return PredictionResult(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            stage=stage,
            prob_home_win=round(float(blended[0]), 4),
            prob_draw=round(float(blended[1]), 4),
            prob_away_win=round(float(blended[2]), 4),
            predicted_home=pred_home,
            predicted_away=pred_away,
            model_version=settings.model_version,
        )


# Module-level singleton — loaded lazily on first use
_ensemble_instance: Ensemble | None = None


def get_ensemble() -> Ensemble:
    global _ensemble_instance
    if _ensemble_instance is None:
        _ensemble_instance = Ensemble().load()
    return _ensemble_instance
