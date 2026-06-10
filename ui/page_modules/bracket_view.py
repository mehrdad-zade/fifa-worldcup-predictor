"""
Bracket View: complete WC 2026 tournament prediction from group stage through Final.

Layout:
  1. Summary (champion, runner-up, simulation count)
  2. Group Stage — all round-robin matches per group with predicted scores,
     predicted final standings, and who advances to R32
  3. Knockout rounds R32 → R16 → QF → SF → Final — every match listed with
     predicted score and predicted winner; result badge fills in live
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from ui.data_loader import (
    load_bracket_prediction,
    load_group_stage_matches,
    load_predicted_standings,
)

_ROUND_LABELS = {
    "R32":   "Round of 32",
    "R16":   "Round of 16",
    "QF":    "Quarter-Finals",
    "SF":    "Semi-Finals",
    "Final": "Final",
}


def render() -> None:
    st.title("🏆 Tournament Bracket")

    bracket = load_bracket_prediction()
    if not bracket:
        st.info(
            "No bracket prediction available yet. "
            "Run `python scripts/generate_predictions.py --no-news` to generate predictions."
        )
        return

    # ── 1. Summary ─────────────────────────────────────────────
    champion   = bracket.get("champion", "TBD")
    champ_prob = bracket.get("champion_probability", 0.0)
    runner_up  = bracket.get("runner_up", "TBD")
    n_sims     = bracket.get("n_simulations", 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Predicted Champion",  champion,  f"{champ_prob * 100:.1f}% probability")
    c2.metric("Predicted Runner-up", runner_up)
    c3.metric("Monte Carlo Simulations", f"{n_sims:,}")
    st.markdown("---")

    # ── 2. Group Stage ──────────────────────────────────────────
    group_matches   = load_group_stage_matches()
    pred_standings  = load_predicted_standings()
    group_qualifiers = bracket.get("group_qualifiers", {})

    if group_matches or pred_standings:
        st.subheader("Group Stage — Predicted Matches & Standings")
        st.caption(
            "Scores are model predictions. Top 2 from each group (✓) advance to the Round of 32. "
            "8 best 3rd-place teams also advance."
        )
        _render_group_stage(group_matches, pred_standings, group_qualifiers)
        st.markdown("---")

    # ── 3. Knockout rounds ──────────────────────────────────────
    bracket_rounds = bracket.get("bracket_rounds", {})
    for round_key in ("R32", "R16", "QF", "SF", "Final"):
        matches = [m for m in bracket_rounds.get(round_key, []) if m.get("away") != "—"]
        if not matches:
            continue
        st.subheader(_ROUND_LABELS[round_key])
        if round_key == "Final":
            _render_final(matches[0])
        else:
            _render_knockout_table(matches)
        st.markdown("---")


# ── Group stage renderers ───────────────────────────────────────────────────


def _render_group_stage(
    group_matches: dict,
    pred_standings: dict,
    group_qualifiers: dict,
) -> None:
    groups = sorted(set(list(group_matches.keys()) + list(pred_standings.keys())))
    if not groups:
        st.caption("No group data available.")
        return

    for row_start in range(0, len(groups), 2):
        row_groups = groups[row_start : row_start + 2]
        cols = st.columns(len(row_groups))
        for col, gc in zip(cols, row_groups):
            with col:
                _render_group_card(
                    gc,
                    group_matches.get(gc, []),
                    pred_standings.get(gc, []),
                    {q["team_id"] for q in group_qualifiers.get(gc, [])},
                )


def _render_group_card(
    gc: str,
    matches: list[dict],
    standings: list[dict],
    qualifier_ids: set,
) -> None:
    st.markdown(f"#### Group {gc}")

    # ── Predicted standings ───────────────────────────────
    if standings:
        rows = []
        for t in standings:
            adv = "✓" if t["team_id"] in qualifier_ids else ""
            rows.append({
                "":     adv,
                "Team": t["team"],
                "Pts":  t["pts"],
                "W":    t["w"],
                "D":    t["d"],
                "L":    t["l"],
                "GD":   t["gd"],
                "GF":   t["gf"],
                "GA":   t["ga"],
            })
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            column_config={"": st.column_config.TextColumn("→", width="small")},
        )

    # ── Match list ────────────────────────────────────────
    if matches:
        match_rows = []
        for m in matches:
            hs = m.get("home_score", "?")
            as_ = m.get("away_score", "?")
            winner = m.get("predicted_winner", "")
            actual_h = m.get("actual_home_score")
            actual_a = m.get("actual_away_score")
            if actual_h is not None and actual_a is not None:
                score_str = f"{actual_h}–{actual_a} (actual)"
                predicted_correct = (
                    (actual_h > actual_a and winner == m["home"]) or
                    (actual_a > actual_h and winner == m["away"]) or
                    (actual_h == actual_a and winner == "Draw")
                )
                status = "✅" if predicted_correct else "❌"
            else:
                score_str = f"{hs}–{as_}"
                status = "⏳"
            match_rows.append({
                "Home":    m.get("home", ""),
                "Score":   score_str,
                "Away":    m.get("away", ""),
                "Winner":  winner,
                "":        status,
            })
        st.dataframe(
            pd.DataFrame(match_rows),
            hide_index=True,
            use_container_width=True,
            column_config={"": st.column_config.TextColumn(" ", width="small")},
        )


# ── Knockout round renderers ────────────────────────────────────────────────


def _render_knockout_table(matches: list[dict]) -> None:
    rows = []
    for m in matches:
        score = m.get("predicted_score", {})
        h = score.get("home", "?")
        a = score.get("away", "?")
        actual = m.get("actual_winner")
        predicted = m.get("predicted_winner", "TBD")
        if actual:
            status = "✅" if actual == predicted else "❌"
        else:
            status = "⏳"
        rows.append({
            "Home":             m.get("home", "TBD"),
            "Score":            f"{h}–{a}",
            "Away":             m.get("away", "TBD"),
            "Predicted Winner": predicted,
            "Actual Winner":    actual or "—",
            "":                 status,
        })
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={"": st.column_config.TextColumn(" ", width="small")},
    )


def _render_final(match: dict) -> None:
    score = match.get("predicted_score", {})
    home = match.get("home", "TBD")
    away = match.get("away", "TBD")
    winner = match.get("predicted_winner", "TBD")
    h_goals = score.get("home", "?")
    a_goals = score.get("away", "?")
    actual = match.get("actual_winner")

    st.markdown("")
    _, mid, _ = st.columns([1, 4, 1])
    with mid:
        with st.container(border=True):
            left, centre, right = st.columns([4, 2, 4])
            with left:
                flag = "🏆 " if winner == home and not actual else ""
                st.markdown(f"### {flag}{home}")
            with centre:
                st.markdown(
                    f"<div style='text-align:center;font-size:1.8em;font-weight:bold'>"
                    f"{h_goals}–{a_goals}</div>",
                    unsafe_allow_html=True,
                )
            with right:
                flag = "🏆 " if winner == away and not actual else ""
                st.markdown(f"### {flag}{away}")
            if actual:
                result_icon = "✅" if actual == winner else "❌"
                st.markdown(
                    f"<div style='text-align:center'>{result_icon} <b>{actual}</b> wins the World Cup</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div style='text-align:center'>⏳ Predicted champion: <b>{winner}</b></div>",
                    unsafe_allow_html=True,
                )
