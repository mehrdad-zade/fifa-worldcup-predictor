"""
Bracket View page: Plotly-based knockout bracket tree showing predicted
advancement probabilities. Node colour: green > 70%, yellow 40-70%, red < 40%.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from ui.data_loader import load_bracket_prediction, load_all_teams


def render() -> None:
    st.title("🏆 Tournament Bracket")

    bracket = load_bracket_prediction()
    if not bracket:
        st.info("No bracket prediction available yet. Run the ingestion pipeline and predictions first.")
        return

    champion = bracket.get("champion", "TBD")
    champ_prob = bracket.get("champion_probability", 0.0)
    runner_up = bracket.get("runner_up", "TBD")

    # ── Summary row ────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("Predicted Champion", champion, f"{champ_prob*100:.1f}% probability")
    c2.metric("Predicted Runner-up", runner_up)
    c3.metric("Simulations", f"{bracket.get('n_simulations', 0):,}")

    st.markdown("---")

    # ── Top contenders bar chart ───────────────────────────────
    contenders = bracket.get("top_contenders", [])
    if contenders:
        st.subheader("Win Probability — Top 8 Contenders")
        df_c = pd.DataFrame(contenders)
        df_c["win_pct"] = (df_c["win_probability"] * 100).round(1)
        st.bar_chart(df_c.set_index("team")["win_pct"], use_container_width=True)

    st.markdown("---")

    # ── TBD Knockout slots ─────────────────────────────────────
    knockouts = bracket.get("tbd_knockouts", [])
    if knockouts:
        st.subheader("Predicted Knockout Bracket")
        _render_bracket_table(knockouts)

    # ── Plotly bracket figure ──────────────────────────────────
    fig = _build_bracket_figure(contenders)
    if fig:
        st.subheader("Visual Bracket")
        st.plotly_chart(fig, use_container_width=True)


def _render_bracket_table(knockouts: list[dict]) -> None:
    rows = []
    for ko in knockouts:
        home = ko.get("resolved_home") or ko.get("placeholder_home", "TBD")
        away = ko.get("resolved_away") or ko.get("placeholder_away", "TBD")
        winner = ko.get("predicted_winner", "TBD")
        actual = ko.get("actual_winner") or "—"
        score = ko.get("predicted_score", {})
        score_str = f"{score.get('home', '?')}–{score.get('away', '?')}"
        status = "✅" if actual != "—" and actual == winner else ("❌" if actual != "—" else "⏳")
        rows.append({
            "Match": ko.get("match_code", ""),
            "Stage": ko.get("stage", ""),
            "Home": home,
            "Away": away,
            "Pred. Score": score_str,
            "Pred. Winner": winner,
            "Actual": actual,
            "": status,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _build_bracket_figure(contenders: list[dict]) -> go.Figure | None:
    if not contenders:
        return None

    teams = [c["team"] for c in contenders[:8]]
    probs = [c["win_probability"] for c in contenders[:8]]

    colors = [
        "#2ecc71" if p >= 0.7 else ("#f39c12" if p >= 0.4 else "#e74c3c")
        for p in probs
    ]

    fig = go.Figure(go.Bar(
        x=teams,
        y=[p * 100 for p in probs],
        marker_color=colors,
        text=[f"{p*100:.1f}%" for p in probs],
        textposition="outside",
    ))
    fig.update_layout(
        title="Championship Win Probability (%)",
        yaxis_title="Probability (%)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=40),
        height=380,
    )
    return fig
