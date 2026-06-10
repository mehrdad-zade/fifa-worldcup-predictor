"""
Runs full evaluation: joins predictions × results, computes Brier + RPS + accuracy,
writes to evaluation_log, prints a markdown table.
"""
from __future__ import annotations

import pandas as pd

from config.settings import settings
from db.database import execute_sql, query_df
from evaluation.brier_score import batch_brier
from evaluation.accuracy import compute_accuracy, compute_rps


def _actual_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home_win"
    if home_score < away_score:
        return "away_win"
    return "draw"


def run_evaluation(model_version: str | None = None) -> dict:
    version = model_version or settings.model_version

    df = query_df(
        """
        SELECT
            p.fixture_id,
            p.model_version,
            p.prob_home_win,
            p.prob_draw,
            p.prob_away_win,
            r.home_score,
            r.away_score,
            f.stage
        FROM predictions p
        JOIN fixtures f ON p.fixture_id = f.fixture_id
        JOIN results r ON p.fixture_id = r.fixture_id
        WHERE p.model_version = ? AND r.home_score IS NOT NULL
        """,
        (version,),
    )

    if df.empty:
        print(f"No completed matches found for model version '{version}'.")
        return {}

    df["actual_outcome"] = df.apply(
        lambda r: _actual_outcome(int(r["home_score"]), int(r["away_score"])), axis=1
    )
    df["brier_score"] = batch_brier(df)
    df["rps"] = compute_rps(df)
    metrics = compute_accuracy(df)

    # ── Write to evaluation_log ────────────────────────────────
    for _, row in df.iterrows():
        execute_sql(
            "INSERT OR REPLACE INTO evaluation_log "
            "(model_version, fixture_id, brier_score, rps, outcome_correct) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                version,
                row["fixture_id"],
                row["brier_score"],
                row["rps"],
                int(1 if _actual_outcome(int(row["home_score"]), int(row["away_score"]))
                    == max(["home_win", "draw", "away_win"],
                           key=lambda o: row[f"prob_{o}" if o != "home_win" else "prob_home_win"]) else 0),
            ),
        )

    # ── Print markdown table ───────────────────────────────────
    print(f"\n## Evaluation: {version} ({len(df)} matches)\n")
    print(f"| Metric | Value |")
    print(f"|--------|-------|")
    print(f"| Overall Accuracy | {metrics.get('overall_accuracy', 'N/A')} |")
    print(f"| Mean Brier Score | {df['brier_score'].mean():.4f} |")
    print(f"| Mean RPS         | {metrics.get('rps', 'N/A')} |")
    print(f"| Matches Evaluated| {metrics.get('n_matches', 0)} |")

    if "by_stage" in metrics:
        print(f"\n### By Stage\n")
        print(f"| Stage | Accuracy | N |")
        print(f"|-------|----------|---|")
        for stage, vals in metrics["by_stage"].items():
            print(f"| {stage} | {vals['accuracy']} | {vals['n_matches']} |")

    return metrics
