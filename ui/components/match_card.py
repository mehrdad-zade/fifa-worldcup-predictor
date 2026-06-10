"""Reusable match prediction card component."""
import streamlit as st


def render_match_card(fixture: dict, prediction: dict) -> None:
    """Render a single match card with prediction and actual score."""
    home = fixture.get("home_team", "Home")
    away = fixture.get("away_team", "Away")
    stage = fixture.get("stage", "")
    match_time = str(fixture.get("match_date", ""))[-8:-3]  # HH:MM

    pred_score = prediction.get("predicted_score", {})
    probs = prediction.get("probabilities", {})
    actual_home = fixture.get("home_score")
    actual_away = fixture.get("away_score")
    status = fixture.get("status", "")

    # Determine result badge
    badge = ""
    if actual_home is not None and actual_away is not None and probs:
        pred_home_score = pred_score.get("home", 0)
        pred_away_score = pred_score.get("away", 0)
        pred_outcome = "home_win" if pred_home_score > pred_away_score else (
            "draw" if pred_home_score == pred_away_score else "away_win"
        )
        actual_outcome = "home_win" if actual_home > actual_away else (
            "draw" if actual_home == actual_away else "away_win"
        )
        badge = "✅" if pred_outcome == actual_outcome else "❌"

    with st.container(border=True):
        # Header
        cols = st.columns([3, 1, 3])
        with cols[0]:
            st.markdown(f"**{home}**")
        with cols[1]:
            if actual_home is not None:
                st.markdown(
                    f"<div style='text-align:center; font-size:1.3em; font-weight:bold'>"
                    f"{actual_home}–{actual_away}</div>",
                    unsafe_allow_html=True,
                )
            elif pred_score:
                st.markdown(
                    f"<div style='text-align:center; color:#888'>"
                    f"~{pred_score.get('home', '?')}–{pred_score.get('away', '?')}</div>",
                    unsafe_allow_html=True,
                )
        with cols[2]:
            st.markdown(f"<div style='text-align:right'><b>{away}</b></div>", unsafe_allow_html=True)

        if badge:
            st.markdown(f"<div style='text-align:center'>{badge}</div>", unsafe_allow_html=True)

        # Probability bars
        if probs:
            hw = probs.get("home_win", 0)
            d = probs.get("draw", 0)
            aw = probs.get("away_win", 0)
            bar_html = (
                f"<div style='display:flex; height:8px; border-radius:4px; overflow:hidden; margin-top:6px'>"
                f"<div style='width:{hw*100:.0f}%; background:#2ecc71'></div>"
                f"<div style='width:{d*100:.0f}%; background:#f39c12'></div>"
                f"<div style='width:{aw*100:.0f}%; background:#e74c3c'></div>"
                f"</div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.75em; color:#888'>"
                f"<span>{hw*100:.0f}%</span><span>Draw {d*100:.0f}%</span><span>{aw*100:.0f}%</span>"
                f"</div>"
            )
            st.markdown(bar_html, unsafe_allow_html=True)

        # Footer metadata
        st.caption(f"{stage} · {match_time} UTC · {status or 'Upcoming'}")
