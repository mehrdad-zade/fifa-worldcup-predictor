"""
Analytics page: model accuracy over time, per-stage breakdown,
and feature importance from XGBoost / LightGBM.
"""
import streamlit as st
import pandas as pd

from ui.data_loader import load_evaluation_metrics, load_feature_importance


def render() -> None:
    st.title("📊 Model Analytics")

    metrics_df = load_evaluation_metrics()
    importance = load_feature_importance()

    if metrics_df.empty:
        st.info("No evaluation data yet. Complete matches need to be logged before analytics appear.")
        st.caption("Run: `python scripts/run_evaluation.py` after results come in.")
        return

    # ── Overall metrics ────────────────────────────────────────
    latest = metrics_df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Model Version", str(latest.get("model_version", "—")))
    col2.metric("Avg Brier Score", f"{float(latest.get('avg_brier', 0)):.4f}",
                delta_color="inverse", help="Lower = better. Random = 0.667")
    col3.metric("Avg RPS", f"{float(latest.get('avg_rps', 0)):.4f}",
                delta_color="inverse")
    col4.metric("Matches Evaluated", str(int(metrics_df["n_matches"].sum())))

    st.markdown("---")

    # ── Accuracy by stage ──────────────────────────────────────
    st.subheader("Accuracy by Stage")
    stage_df = (
        metrics_df.groupby("stage")
        .agg(accuracy=("accuracy", "mean"), n_matches=("n_matches", "sum"), avg_brier=("avg_brier", "mean"))
        .reset_index()
        .rename(columns={"stage": "Stage", "accuracy": "Accuracy", "n_matches": "Matches", "avg_brier": "Avg Brier"})
    )
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
        brier_df = stage_df.set_index("Stage")["Avg Brier"]
        st.bar_chart(brier_df, use_container_width=True)

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
        with st.expander("Raw importance values"):
            st.dataframe(imp_df, hide_index=True)
    else:
        st.caption("Feature importance will appear after model training (`scripts/train_models.py`).")
