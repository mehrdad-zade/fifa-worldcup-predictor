"""
Match Center page: today's scheduled matches + full group standings with
predicted qualifier badges.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date

import streamlit as st
import pandas as pd

from ui.data_loader import (
    load_todays_fixtures,
    load_todays_predictions,
    load_group_standings,
    load_bracket_prediction,
)
from ui.components.match_card import render_match_card

_GROUPS = list("ABCDEFGHIJKL")


def render() -> None:
    st.title(f"⚽ Match Center — {date.today().strftime('%B %d, %Y')}")

    col_title, col_toggle = st.columns([4, 1])
    with col_toggle:
        auto_refresh = st.toggle("Live", value=False, help="Auto-refresh every 60s")

    fixtures = load_todays_fixtures()
    predictions = load_todays_predictions()
    pred_map = {p["fixture_id"]: p for p in predictions}

    if not fixtures.empty:
        cols = st.columns(3)
        for i, (_, row) in enumerate(fixtures.iterrows()):
            fixture_id = str(row["fixture_id"])
            pred = pred_map.get(fixture_id, {})
            with cols[i % 3]:
                render_match_card(row.to_dict(), pred)
        st.markdown("---")
    else:
        st.info("No matches scheduled today — first fixtures kick off June 11, 2026.")

    _render_group_tables()

    if auto_refresh:
        import time
        time.sleep(60)
        st.cache_data.clear()
        st.rerun()


def _render_group_tables() -> None:
    st.subheader("Group Standings")
    st.caption("✓ = Predicted to advance to the next round (from bracket simulation)")

    standings = load_group_standings()
    bracket = load_bracket_prediction()

    # Build a set of predicted qualifier IDs per group
    group_qualifiers: dict[str, dict] = {}
    if bracket:
        for gc, quals in bracket.get("group_qualifiers", {}).items():
            group_qualifiers[gc] = {q["team_id"]: q["position"] for q in quals}

    # Determine groups to display: use standings groups if available, else A-L
    if not standings.empty:
        available_groups = sorted(standings["group_code"].dropna().unique())
    else:
        available_groups = [g for g in _GROUPS if g in group_qualifiers]

    if not available_groups:
        st.caption("No team data yet. Run the ingestion pipeline to populate group standings.")
        return

    # Display in rows of 2
    for row_start in range(0, len(available_groups), 2):
        row_groups = available_groups[row_start : row_start + 2]
        cols = st.columns(len(row_groups))
        for col, gc in zip(cols, row_groups):
            with col:
                _render_group_card(gc, standings, group_qualifiers.get(gc, {}))


def _render_group_card(
    gc: str,
    standings: pd.DataFrame,
    predicted_ids: dict[int, int],
) -> None:
    st.markdown(f"**Group {gc}**")

    if not standings.empty and "group_code" in standings.columns:
        group_df = standings[standings["group_code"] == gc].copy()
    else:
        group_df = pd.DataFrame()

    if group_df.empty:
        # No DB data — show predicted qualifiers only
        if predicted_ids:
            for tid, pos in sorted(predicted_ids.items(), key=lambda x: x[1]):
                st.caption(f"  {pos}. (team_id {tid})")
        else:
            st.caption("No data")
        return

    # Compute GD and add predicted-advance column
    group_df = group_df.copy()
    group_df["gd"] = group_df["gf"] - group_df["ga"]

    if predicted_ids:
        group_df["Adv"] = group_df["team_id"].apply(
            lambda tid: f"✓{predicted_ids.get(int(tid), '')}" if int(tid) in predicted_ids else ""
        )
    else:
        group_df["Adv"] = ""

    display_df = (
        group_df[["team", "played", "points", "gd", "gf", "ga", "Adv"]]
        .rename(columns={
            "team": "Team",
            "played": "P",
            "points": "Pts",
            "gd": "GD",
            "gf": "GF",
            "ga": "GA",
        })
        .reset_index(drop=True)
    )

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Adv": st.column_config.TextColumn("→", width="small"),
        },
    )

    # Caption showing predicted qualifiers by name
    if predicted_ids:
        qualifier_names = (
            group_df[group_df["team_id"].apply(lambda t: int(t) in predicted_ids)]
            .sort_values("team_id", key=lambda s: s.apply(lambda t: predicted_ids.get(int(t), 99)))
            ["team"]
            .tolist()
        )
        if qualifier_names:
            st.caption("→ " + "  ·  ".join(qualifier_names))
