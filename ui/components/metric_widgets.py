"""Reusable metric summary widgets for the Analytics page."""
import streamlit as st


def render_model_summary(version: str, brier: float, rps: float, accuracy: float, n: int) -> None:
    cols = st.columns(4)
    cols[0].metric("Model", version)
    cols[1].metric("Brier Score", f"{brier:.4f}", help="Lower = better. Random ≈ 0.667")
    cols[2].metric("Accuracy", f"{accuracy*100:.1f}%")
    cols[3].metric("Matches", str(n))


def render_brier_gauge(brier: float) -> None:
    """Display Brier score with a colour-coded status."""
    if brier < 0.20:
        label, color = "Excellent", "#2ecc71"
    elif brier < 0.30:
        label, color = "Good", "#f39c12"
    elif brier < 0.40:
        label, color = "Fair", "#e67e22"
    else:
        label, color = "Poor", "#e74c3c"

    st.markdown(
        f"<div style='text-align:center; padding:12px; border-radius:8px; "
        f"background:{color}22; border:1px solid {color}'>"
        f"<span style='font-size:2em; font-weight:bold; color:{color}'>{brier:.4f}</span><br/>"
        f"<span style='color:{color}'>{label}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
