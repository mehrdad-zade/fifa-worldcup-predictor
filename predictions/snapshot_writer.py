from __future__ import annotations

"""
Writes predictions to:
  1. JSON snapshot file: data/snapshots/YYYY-MM-DD_v{VERSION}.json
  2. SQLite predictions table (upserted by fixture_id + model_version)

Idempotent: safe to re-run on the same day — overwrites existing snapshot
and updates existing DB rows.
"""
import json
from datetime import date
from pathlib import Path

from config.settings import settings
from db.database import execute_sql


def write_snapshot(
    daily_predictions: list[dict],
    bracket_prediction: dict,
    model_version: str | None = None,
) -> Path:
    version = model_version or settings.model_version
    today = date.today().isoformat()

    payload = {
        "meta": {
            "simulation_date": today,
            "model_version": version,
        },
        "daily_predictions": daily_predictions,
        "final_bracket_prediction": bracket_prediction,
    }

    # ── Write JSON snapshot ────────────────────────────────────
    snapshot_dir = Path(settings.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{today}_{version}.json"
    snapshot_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Upsert into SQLite ─────────────────────────────────────
    for pred in daily_predictions:
        fixture_id = pred.get("fixture_id")
        if not fixture_id:
            continue
        probs = pred.get("probabilities", {})
        score = pred.get("predicted_score", {})
        execute_sql(
            "INSERT INTO predictions "
            "(fixture_id, model_version, predicted_home, predicted_away, "
            " prob_home_win, prob_draw, prob_away_win) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(fixture_id, model_version) DO UPDATE SET "
            "predicted_home=excluded.predicted_home, predicted_away=excluded.predicted_away, "
            "prob_home_win=excluded.prob_home_win, prob_draw=excluded.prob_draw, "
            "prob_away_win=excluded.prob_away_win",
            (
                fixture_id,
                version,
                score.get("home", 0),
                score.get("away", 0),
                probs.get("home_win", 1 / 3),
                probs.get("draw", 1 / 3),
                probs.get("away_win", 1 / 3),
            ),
        )

    return snapshot_path


def load_latest_snapshot(date_str: str | None = None) -> dict | None:
    """Load the most recent snapshot for a given date (default: today)."""
    target = date_str or date.today().isoformat()
    snapshot_dir = Path(settings.snapshot_dir)
    if not snapshot_dir.exists():
        return None
    candidates = sorted(snapshot_dir.glob(f"{target}_*.json"), reverse=True)
    if not candidates:
        return None
    return json.loads(candidates[0].read_text(encoding="utf-8"))
