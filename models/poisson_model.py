"""
Dixon-Coles bivariate Poisson model for predicting match scorelines.

Parameters: attack (α_i), defense (β_i), home advantage (γ), low-score correction (ρ).
Returns a 15×15 score probability matrix from which W/D/L probs and expected
scoreline are derived.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import joblib
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

_MAX_GOALS = 15


def _tau(x: int, y: int, mu: float, nu: float, rho: float) -> float:
    """Dixon-Coles low-score correction factor."""
    if x == 0 and y == 0:
        return 1.0 - mu * nu * rho
    if x == 0 and y == 1:
        return 1.0 + mu * rho
    if x == 1 and y == 0:
        return 1.0 + nu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(home_lambda: float, away_lambda: float, rho: float = -0.1) -> np.ndarray:
    """Return a MAX_GOALS × MAX_GOALS matrix of P(home=i, away=j)."""
    mat = np.zeros((_MAX_GOALS, _MAX_GOALS))
    for i in range(_MAX_GOALS):
        for j in range(_MAX_GOALS):
            mat[i, j] = (
                poisson.pmf(i, home_lambda)
                * poisson.pmf(j, away_lambda)
                * _tau(i, j, home_lambda, away_lambda, rho)
            )
    # Renormalise to sum to 1
    total = mat.sum()
    if total > 0:
        mat /= total
    return mat


def probabilities_from_matrix(mat: np.ndarray) -> tuple[float, float, float]:
    """Return (p_home_win, p_draw, p_away_win) from a score matrix."""
    home_win = np.tril(mat, -1).sum()
    draw = np.trace(mat)
    away_win = np.triu(mat, 1).sum()
    total = home_win + draw + away_win
    return home_win / total, draw / total, away_win / total


def expected_scoreline(mat: np.ndarray) -> tuple[int, int]:
    """Return (home_goals, away_goals) at the argmax of the score matrix."""
    idx = np.unravel_index(np.argmax(mat), mat.shape)
    return int(idx[0]), int(idx[1])


class PoissonModel:
    """Fitted Dixon-Coles Poisson model."""

    def __init__(self) -> None:
        self.team_ids: list[int] = []
        self.attack: dict[int, float] = {}
        self.defense: dict[int, float] = {}
        self.home_advantage: float = 0.0
        self.rho: float = -0.1
        self._fitted = False

    def fit(self, matches: list[dict]) -> "PoissonModel":
        """
        Fit on a list of match dicts with keys:
          home_team_id, away_team_id, home_score, away_score
        """
        team_ids = sorted({m["home_team_id"] for m in matches} |
                          {m["away_team_id"] for m in matches})
        self.team_ids = team_ids
        n = len(team_ids)
        idx = {t: i for i, t in enumerate(team_ids)}

        def neg_log_likelihood(params: np.ndarray) -> float:
            attack = params[:n]
            defense = params[n : 2 * n]
            gamma = params[2 * n]
            rho = params[2 * n + 1]
            ll = 0.0
            for m in matches:
                hi, ai = idx[m["home_team_id"]], idx[m["away_team_id"]]
                mu = np.exp(attack[hi] - defense[ai] + gamma)
                nu = np.exp(attack[ai] - defense[hi])
                hs, as_ = int(m["home_score"]), int(m["away_score"])
                tau = _tau(hs, as_, mu, nu, rho)
                if tau <= 0:
                    return 1e10
                ll += (
                    poisson.logpmf(hs, mu)
                    + poisson.logpmf(as_, nu)
                    + np.log(max(tau, 1e-10))
                )
            return -ll

        x0 = np.zeros(2 * n + 2)
        x0[2 * n] = 0.1  # slight home advantage start
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = minimize(neg_log_likelihood, x0, method="L-BFGS-B",
                              options={"maxiter": 500, "ftol": 1e-8})

        params = result.x
        for i, t in enumerate(team_ids):
            self.attack[t] = params[i]
            self.defense[t] = params[n + i]
        self.home_advantage = params[2 * n]
        self.rho = float(np.clip(params[2 * n + 1], -0.5, 0.5))
        self._fitted = True
        return self

    def predict(self, home_id: int, away_id: int) -> dict:
        """Return prediction dict with score matrix, probs, and expected scoreline."""
        if not self._fitted:
            raise RuntimeError("Model not fitted — call fit() first.")

        home_attack = self.attack.get(home_id, 0.0)
        home_defense = self.defense.get(home_id, 0.0)
        away_attack = self.attack.get(away_id, 0.0)
        away_defense = self.defense.get(away_id, 0.0)

        home_lambda = np.exp(home_attack - away_defense + self.home_advantage)
        away_lambda = np.exp(away_attack - home_defense)

        mat = score_matrix(max(home_lambda, 0.1), max(away_lambda, 0.1), self.rho)
        hw, d, aw = probabilities_from_matrix(mat)
        es_h, es_a = expected_scoreline(mat)

        return {
            "prob_home_win": round(float(hw), 4),
            "prob_draw": round(float(d), 4),
            "prob_away_win": round(float(aw), 4),
            "predicted_home": es_h,
            "predicted_away": es_a,
        }

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str) -> "PoissonModel":
        return joblib.load(path)
