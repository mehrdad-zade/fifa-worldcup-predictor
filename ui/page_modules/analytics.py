"""
Analytics page: pre-tournament bracket predictions, model win probabilities,
feature importance, and (post-match) accuracy metrics.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from ui.data_loader import (
    load_evaluation_metrics,
    load_feature_importance,
    load_bracket_prediction,
)

_ROUND_LABELS = {
    "R32": "Round of 32",
    "R16": "Round of 16",
    "QF": "Quarter-Finals",
    "SF": "Semi-Finals",
    "Final": "Final",
}


def render() -> None:
    st.title("📊 Model Analytics")

    metrics_df = load_evaluation_metrics()
    importance = load_feature_importance()
    bracket = load_bracket_prediction()

    # ── Championship win-probability ───────────────────────────
    contenders = bracket.get("top_contenders", []) if bracket else []
    if contenders:
        st.subheader("Championship Win Probability")
        df_c = (
            pd.DataFrame(contenders)
            .assign(win_pct=lambda d: (d["win_probability"] * 100).round(1))
            .sort_values("win_pct", ascending=False)
        )
        st.bar_chart(df_c.set_index("team")["win_pct"], use_container_width=True)
        n_sims = bracket.get("n_simulations", 0)
        champion = bracket.get("champion", "—")
        champ_prob = bracket.get("champion_probability", 0.0)
        st.caption(
            f"Based on {n_sims:,} Monte Carlo simulations. "
            f"Predicted champion: **{champion}** ({champ_prob * 100:.1f}%)"
        )
        st.markdown("---")

    # ── Pre-tournament: Group advancement predictions ──────────
    group_qualifiers = bracket.get("group_qualifiers", {}) if bracket else {}
    if group_qualifiers:
        st.subheader("Predicted Group Stage Qualifiers")
        st.caption(
            "Teams predicted to advance from each group based on Monte Carlo simulation. "
            "Run predictions again after each matchday to update."
        )
        _render_group_qualifiers_table(group_qualifiers)
        st.markdown("---")

    # ── Pre-tournament: Full bracket round predictions ─────────
    bracket_rounds = bracket.get("bracket_rounds", {}) if bracket else {}
    if bracket_rounds:
        st.subheader("Predicted Bracket — All Rounds")
        _render_bracket_summary(bracket_rounds)
        st.markdown("---")

    # ── Feature importance ─────────────────────────────────────
    if importance:
        st.subheader("XGBoost Feature Importance")
        imp_df = (
            pd.Series(importance)
            .sort_values(ascending=False)
            .reset_index()
            .rename(columns={"index": "Feature", 0: "Importance"})
        )
        st.bar_chart(imp_df.set_index("Feature"), use_container_width=True)
        with st.expander("Raw values"):
            st.dataframe(imp_df, hide_index=True)
    else:
        st.info(
            "Feature importance will appear after model training — "
            "run `python scripts/train_models.py`",
            icon="ℹ️",
        )
    st.markdown("---")

    # ── Model configuration ────────────────────────────────────
    st.subheader("Model Configuration")
    col_w, col_f = st.columns(2)
    with col_w:
        st.markdown("**Ensemble weights**")
        st.dataframe(
            pd.DataFrame(
                [("Dixon-Coles Poisson", "40%"),
                 ("XGBoost", "30%"),
                 ("LightGBM", "30%")],
                columns=["Model", "Weight"],
            ),
            hide_index=True,
            use_container_width=True,
        )
    with col_f:
        st.markdown("**Feature vector (17 features)**")
        st.dataframe(
            pd.DataFrame(
                ["home_elo / away_elo / elo_diff",
                 "home_momentum / away_momentum",
                 "home_fitness / away_fitness",
                 "home_strength / away_strength",
                 "home_points / away_points",
                 "home_goal_diff / away_goal_diff",
                 "home_position / away_position",
                 "stage_encoded",
                 "is_neutral_venue"],
                columns=["Feature"],
            ),
            hide_index=True,
            use_container_width=True,
        )
    st.markdown("---")

    # ── Prediction accuracy (fills in as matches complete) ─────
    st.subheader("Prediction Accuracy")
    if metrics_df.empty:
        st.caption(
            "Accuracy metrics will populate here as group-stage results come in "
            "(first fixtures kick off June 11, 2026). Re-run predictions after each "
            "matchday to refresh."
        )
        return

    latest = metrics_df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Model Version", str(latest.get("model_version", "—")))
    col2.metric(
        "Avg Brier Score",
        f"{float(latest.get('avg_brier', 0)):.4f}",
        delta_color="inverse",
        help="Lower = better. Random baseline = 0.667",
    )
    col3.metric("Avg RPS", f"{float(latest.get('avg_rps', 0)):.4f}", delta_color="inverse")
    col4.metric("Matches Evaluated", str(int(metrics_df["n_matches"].sum())))

    st.markdown("---")

    stage_df = (
        metrics_df.groupby("stage")
        .agg(
            accuracy=("accuracy", "mean"),
            n_matches=("n_matches", "sum"),
            avg_brier=("avg_brier", "mean"),
        )
        .reset_index()
        .rename(columns={
            "stage": "Stage", "accuracy": "Accuracy",
            "n_matches": "Matches", "avg_brier": "Avg Brier",
        })
    )

    st.subheader("Accuracy by Stage")
    st.dataframe(stage_df, hide_index=True, use_container_width=True)

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Accuracy Over Time")
        if "evaluated_at" in metrics_df.columns:
            time_df = (
                metrics_df.groupby("evaluated_at")["accuracy"]
                .mean()
                .reset_index()
                .rename(columns={"evaluated_at": "Date", "accuracy": "Accuracy"})
            )
            st.line_chart(time_df.set_index("Date"), use_container_width=True)

    with col_right:
        st.subheader("Brier Score by Stage")
        st.bar_chart(stage_df.set_index("Stage")["Avg Brier"], use_container_width=True)


# ── Helper renderers ───────────────────────────────────────────────────────


def _render_group_qualifiers_table(group_qualifiers: dict) -> None:
    rows = []
    for gc in sorted(group_qualifiers.keys()):
        quals = group_qualifiers[gc]
        first = next((q for q in quals if q["position"] == 1), None)
        second = next((q for q in quals if q["position"] == 2), None)
        rows.append({
            "Group": gc,
            "1st (predicted)": first["team"] if first else "—",
            "Prob": f"{first['advance_prob'] * 100:.1f}%" if first else "—",
            "2nd (predicted)": second["team"] if second else "—",
            "Prob ": f"{second['advance_prob'] * 100:.1f}%" if second else "—",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_bracket_summary(bracket_rounds: dict) -> None:
    tabs = st.tabs([_ROUND_LABELS.get(r, r) for r in ("R32", "R16", "QF", "SF", "Final")])
    for tab, round_key in zip(tabs, ("R32", "R16", "QF", "SF", "Final")):
        with tab:
            matches = [
                m for m in bracket_rounds.get(round_key, [])
                if m.get("away") != "—"
            ]
            if not matches:
                st.caption("No predictions yet.")
                continue
            rows = []
            for m in matches:
                score = m.get("predicted_score", {})
                rows.append({
                    "Home": m.get("home", "TBD"),
                    "Score": f"{score.get('home', '?')}–{score.get('away', '?')}",
                    "Away": m.get("away", "TBD"),
                    "Predicted Winner": m.get("predicted_winner", "TBD"),
                    "Result": (
                        "✅" if m.get("actual_winner") and m["actual_winner"] == m.get("predicted_winner")
                        else ("❌" if m.get("actual_winner") else "⏳")
                    ),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
