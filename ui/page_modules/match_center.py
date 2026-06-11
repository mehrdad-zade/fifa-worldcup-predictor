from __future__ import annotations

"""Fixtures page — full WC 2026 schedule with team/group/date filters."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date

import pandas as pd
import streamlit as st

from config.fixtures import FIXTURES
from ui.data_loader import load_all_results, load_all_predictions, load_knockout_matchups


# ── Build DataFrame from shared fixture config ────────────────────────────────

def _build_df() -> pd.DataFrame:
    df = pd.DataFrame(
        FIXTURES,
        columns=["#", "_date_str", "EST", "Local", "Matchup", "Group", "Round", "Venue", "City"],
    )
    df["date"] = pd.to_datetime(df["_date_str"], format="%d-%b-%y").dt.date
    df["Date"] = df["date"].apply(lambda d: d.strftime("%d %b"))
    df["fixture_id"] = df["#"].apply(lambda n: f"wc-2026-m{n}")
    return df.drop(columns=["_date_str"])


_DF = _build_df()

_ROUND_ORDER = [
    "Group Stage",
    "Round of 32",
    "Round of 16",
    "Quarter-finals",
    "Semi-finals",
    "Third Place",
    "Final",
]

_ROUND_EMOJI = {
    "Group Stage":    "🏟️",
    "Round of 32":    "⚽",
    "Round of 16":    "⚽",
    "Quarter-finals": "🥊",
    "Semi-finals":    "🔥",
    "Third Place":    "🥉",
    "Final":          "🏆",
}

_GROUP_OPTIONS = list("ABCDEFGHIJKL") + ["Knockout"]


# ── Page ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("🗓️ Fixtures — FIFA World Cup 2026")

    results_map      = load_all_results()
    predictions_map  = load_all_predictions()
    ko_matchups      = load_knockout_matchups()

    # ── Filters ──────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 1.5, 2, 2.5])

    with col1:
        team_q = st.text_input("Search team", placeholder="e.g. Brazil, France…")

    with col2:
        group_sel = st.multiselect("Group", _GROUP_OPTIONS, placeholder="All")

    with col3:
        round_sel = st.multiselect("Round", _ROUND_ORDER, placeholder="All rounds")

    with col4:
        date_range = st.date_input(
            "Date range",
            value=(date(2026, 6, 11), date(2026, 7, 19)),
            min_value=date(2026, 6, 11),
            max_value=date(2026, 7, 19),
        )

    # ── Apply filters ─────────────────────────────────────────────────────────
    df = _DF.copy()

    # For KO rows, swap in the resolved matchup so team-name search works there too
    def _effective_matchup(row: pd.Series) -> str:
        if row["Group"] == "":
            return ko_matchups.get(row["fixture_id"], row["Matchup"])
        return row["Matchup"]

    df["EffectiveMatchup"] = df.apply(_effective_matchup, axis=1)

    if team_q.strip():
        df = df[df["EffectiveMatchup"].str.contains(team_q.strip(), case=False, na=False)]

    if group_sel:
        def _group_match(g: str) -> bool:
            if g == "":
                return "Knockout" in group_sel
            return g in group_sel
        df = df[df["Group"].apply(_group_match)]

    if round_sel:
        df = df[df["Round"].isin(round_sel)]

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        df = df[(df["date"] >= start) & (df["date"] <= end)]

    count = len(df)
    st.caption(f"{count} match{'es' if count != 1 else ''} found")

    if df.empty:
        st.info("No matches match your filters.")
        return

    # ── Display grouped by round ──────────────────────────────────────────────
    for rnd in _ROUND_ORDER:
        rnd_df = df[df["Round"] == rnd].copy()
        if rnd_df.empty:
            continue

        st.subheader(f"{_ROUND_EMOJI.get(rnd, '')} {rnd}")

        rnd_df["Result"]    = rnd_df["fixture_id"].map(results_map).fillna("")
        rnd_df["Predicted"] = rnd_df["fixture_id"].map(predictions_map).fillna("")

        if rnd == "Group Stage":
            display = rnd_df[[
                "#", "Date", "EST", "Local", "Matchup", "Group",
                "Result", "Predicted", "Venue", "City",
            ]].reset_index(drop=True)

            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "#":         st.column_config.NumberColumn("#",         width="small"),
                    "Date":      st.column_config.TextColumn("Date",       width="small"),
                    "EST":       st.column_config.TextColumn("EST",        width="small"),
                    "Local":     st.column_config.TextColumn("Local",      width="small"),
                    "Group":     st.column_config.TextColumn("Grp",        width="small"),
                    "Result":    st.column_config.TextColumn("Result",     width="small"),
                    "Predicted": st.column_config.TextColumn("Predicted",  width="small"),
                },
            )

        else:
            # Knockout round: "Group" column shows the bracket slot description
            # (e.g. "Group A Runners Up v Group B Runners Up") so the original
            # bracket position is always visible even after teams are known.
            # "Predicted Match" shows the resolved team names from the simulation.
            rnd_df["Predicted Match"] = rnd_df["fixture_id"].map(ko_matchups).fillna("TBD")
            # Bracket slot description lives in the original Matchup column
            rnd_df["Bracket"] = rnd_df["Matchup"]

            display = rnd_df[[
                "#", "Date", "EST", "Local", "Predicted Match", "Bracket",
                "Result", "Predicted", "Venue", "City",
            ]].reset_index(drop=True)

            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "#":                st.column_config.NumberColumn("#",                width="small"),
                    "Date":             st.column_config.TextColumn("Date",              width="small"),
                    "EST":              st.column_config.TextColumn("EST",               width="small"),
                    "Local":            st.column_config.TextColumn("Local",             width="small"),
                    "Predicted Match":  st.column_config.TextColumn("Predicted Match",   width="medium"),
                    "Bracket":          st.column_config.TextColumn("Group",             width="large"),
                    "Result":           st.column_config.TextColumn("Result",            width="small"),
                    "Predicted":        st.column_config.TextColumn("Predicted",         width="small"),
                },
            )
