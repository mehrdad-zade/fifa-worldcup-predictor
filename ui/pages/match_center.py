"""
Match Center page: today's scheduled matches with predicted vs actual scores.
Auto-refreshes live scores every 60 seconds when matches are in progress.
"""
from datetime import date

import streamlit as st
import pandas as pd

from ui.data_loader import load_todays_fixtures, load_todays_predictions, load_group_standings
from ui.components.match_card import render_match_card


def render() -> None:
    st.title(f"⚽ Match Center — {date.today().strftime('%B %d, %Y')}")

    # ── Auto-refresh toggle ────────────────────────────────────
    col_title, col_toggle = st.columns([4, 1])
    with col_toggle:
        auto_refresh = st.toggle("Live", value=False, help="Auto-refresh every 60s")

    fixtures = load_todays_fixtures()
    predictions = load_todays_predictions()
    pred_map = {p["fixture_id"]: p for p in predictions}

    if fixtures.empty:
        st.info("No matches scheduled today. Check back closer to kick-off!")
        _render_group_tables()
        return

    # ── Match grid (3 columns) ─────────────────────────────────
    cols = st.columns(3)
    for i, (_, row) in enumerate(fixtures.iterrows()):
        fixture_id = str(row["fixture_id"])
        pred = pred_map.get(fixture_id, {})
        with cols[i % 3]:
            render_match_card(row.to_dict(), pred)

    st.markdown("---")
    _render_group_tables()

    if auto_refresh:
        import time
        time.sleep(60)
        st.cache_data.clear()
        st.rerun()


def _render_group_tables() -> None:
    st.subheader("Group Standings")
    standings = load_group_standings()
    if standings.empty:
        st.caption("No group stage results yet.")
        return

    groups = sorted(standings["group_code"].unique())
    cols = st.columns(min(len(groups), 4))
    for i, gc in enumerate(groups):
        with cols[i % 4]:
            group_df = (
                standings[standings["group_code"] == gc]
                [["team", "points", "gf", "ga", "played"]]
                .assign(gd=lambda d: d["gf"] - d["ga"])
                .rename(columns={"team": "Team", "points": "Pts", "gf": "GF",
                                 "ga": "GA", "gd": "GD", "played": "P"})
                .reset_index(drop=True)
            )
            st.markdown(f"**Group {gc}**")
            st.dataframe(group_df, hide_index=True, use_container_width=True)
