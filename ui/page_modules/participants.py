from __future__ import annotations

"""Participants page — team cards + team detail view with squad & news."""
import sys
import unicodedata
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from config.team_profiles import TEAM_PROFILES, TEAM_GROUP
from db.database import query_df

# ── Helpers ───────────────────────────────────────────────────────────────────

_PLACE_LABEL = {1: "🥇", 2: "🥈", 3: "🥉"}
_MEDAL_COLOR = {1: "#FFD700", 2: "#C0C0C0", 3: "#CD7F32"}


def _top3_summary(top3: list[tuple[int, int]]) -> str:
    if not top3:
        return "—"
    parts = []
    for year, place in sorted(top3):
        icon = _PLACE_LABEL.get(place, "")
        parts.append(f"{icon} {year}")
    return "  ·  ".join(parts)


def _top3_count(top3: list[tuple[int, int]]) -> int:
    return len(top3)


def _load_news(team_name: str) -> list[dict]:
    """Pull cached Claude news items for a team (empty list if none).

    claude_news_cache stores a JSON blob in response_json keyed by team_id.
    We parse each blob and return a flat list of news items.
    """
    import json
    df = query_df(
        """
        SELECT c.response_json, c.created_at
        FROM claude_news_cache c
        JOIN teams t ON c.team_id = t.team_id
        WHERE t.name = ?
        ORDER BY c.created_at DESC
        LIMIT 5
        """,
        (team_name,),
    )
    if df.empty:
        return []
    items: list[dict] = []
    for _, row in df.iterrows():
        try:
            data = json.loads(row["response_json"])
            # The Claude response may be a list of news dicts or a single dict
            if isinstance(data, list):
                for entry in data:
                    entry.setdefault("fetched_at", row["created_at"])
                    items.append(entry)
            elif isinstance(data, dict):
                data.setdefault("fetched_at", row["created_at"])
                items.append(data)
        except (json.JSONDecodeError, TypeError):
            items.append({"headline": "News item", "summary": str(row["response_json"])[:200],
                          "fetched_at": row["created_at"]})
    return items


def _load_player_stats(team_name: str) -> pd.DataFrame:
    """Load player stats from DB joined to teams; empty DF if not yet ingested."""
    df = query_df(
        """
        SELECT ps.player_name, ps.position, ps.club,
               ps.goals, ps.assists, ps.minutes_played,
               CASE WHEN ps.is_injured   = 1 THEN '🤕' ELSE '' END AS injured,
               CASE WHEN ps.is_suspended = 1 THEN '🟥' ELSE '' END AS suspended
        FROM player_stats ps
        JOIN teams t ON ps.team_id = t.team_id
        WHERE t.name = ?
        ORDER BY ps.goals DESC, ps.assists DESC
        """,
        (team_name,),
    )
    return df


# ── Session state helpers ─────────────────────────────────────────────────────

def _select_team(name: str) -> None:
    st.session_state["participants_selected"] = name


def _clear_team() -> None:
    st.session_state["participants_selected"] = None


# ── Team card ─────────────────────────────────────────────────────────────────

def _render_card(name: str, profile: dict, group: str) -> None:
    top3 = profile["top3"]
    n_top3 = _top3_count(top3)
    rank = profile["fifa_rank"]

    with st.container(border=True):
        # Header row: flag + name + rank badge
        h_col, r_col = st.columns([4, 1])
        with h_col:
            st.markdown(
                f"### {profile['flag']} {name}",
                unsafe_allow_html=False,
            )
        with r_col:
            st.markdown(
                f"<div style='text-align:right; padding-top:10px;'>"
                f"<span style='background:#1a1a2e;color:white;"
                f"padding:4px 10px;border-radius:12px;font-size:13px;'>"
                f"#{rank}</span></div>",
                unsafe_allow_html=True,
            )

        # Stats grid
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Group:** {group}")
            st.markdown(f"**Coach:** {profile['coach']}")
            st.markdown(f"**WC Appearances:** {profile['wc_appearances']}")
        with c2:
            st.markdown(f"**Knockout Stage:** {profile['group_stage_adv']}×")
            st.markdown(f"**Top-3 Finishes:** {n_top3}×")
            if top3:
                st.markdown(f"<span style='font-size:12px;color:#888;'>"
                            f"{_top3_summary(top3)}</span>",
                            unsafe_allow_html=True)

        # Detail button
        st.button(
            "View Squad & News",
            key=f"card_{name}",
            use_container_width=True,
            on_click=_select_team,
            args=(name,),
        )


# ── Team detail view ──────────────────────────────────────────────────────────

def _render_detail(name: str) -> None:
    profile = TEAM_PROFILES[name]
    group = TEAM_GROUP.get(name, "?")
    top3 = profile["top3"]

    # Back button
    st.button("← Back to all teams", on_click=_clear_team)
    st.divider()

    # Header
    st.markdown(
        f"# {profile['flag']} {name}",
        unsafe_allow_html=False,
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("FIFA Rank", f"#{profile['fifa_rank']}")
    m2.metric("WC Group", group)
    m3.metric("WC Appearances", profile["wc_appearances"])
    m4.metric("Knockout Stages", f"{profile['group_stage_adv']}×")
    m5.metric("Top-3 Finishes", f"{_top3_count(top3)}×")

    if top3:
        labels = "  ·  ".join(
            f"{_PLACE_LABEL.get(p,'')}{p}{'st' if p==1 else 'nd' if p==2 else 'rd'} {y}"
            for y, p in sorted(top3)
        )
        st.caption(f"**Honours:** {labels}")

    st.markdown(f"**Head Coach:** {profile['coach']}")
    st.divider()

    # ── Squad ─────────────────────────────────────────────────────────────────
    tab_squad, tab_news = st.tabs(["🧑‍💼 Squad", "📰 Today's News"])

    with tab_squad:
        st.subheader("Squad")

        # Try DB player stats first (populated by FBref ingestion)
        db_df = _load_player_stats(name)
        if not db_df.empty:
            st.dataframe(
                db_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "player_name":    st.column_config.TextColumn("Player",    width="large"),
                    "position":       st.column_config.TextColumn("Pos",       width="small"),
                    "club":           st.column_config.TextColumn("Club",      width="medium"),
                    "goals":          st.column_config.NumberColumn("⚽ Goals", width="small"),
                    "assists":        st.column_config.NumberColumn("🎯 Assists",width="small"),
                    "minutes_played": st.column_config.NumberColumn("Mins",    width="small"),
                    "injured":        st.column_config.TextColumn("",          width="small"),
                    "suspended":      st.column_config.TextColumn("",          width="small"),
                },
            )
        else:
            # Fall back to profile data
            players = profile.get("players", [])
            if players:
                squad_df = pd.DataFrame(players, columns=["Player", "Position", "Rating"])
                # Position sort order
                pos_order = {"GK": 0, "CB": 1, "RB": 2, "LB": 3,
                             "CDM": 4, "CM": 5, "CAM": 6,
                             "RW": 7, "LW": 8, "ST": 9}
                squad_df["_sort"] = squad_df["Position"].map(
                    lambda p: pos_order.get(p, 99)
                )
                squad_df = squad_df.sort_values("_sort").drop(columns=["_sort"])
                squad_df["Rating"] = squad_df["Rating"].apply(
                    lambda r: f"{'⭐' if r >= 88 else ''}{r}"
                )
                st.dataframe(
                    squad_df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Player":   st.column_config.TextColumn("Player",   width="large"),
                        "Position": st.column_config.TextColumn("Pos",      width="small"),
                        "Rating":   st.column_config.TextColumn("Rating",   width="small"),
                    },
                )
            else:
                st.info("Squad data not available.")

    # ── News ──────────────────────────────────────────────────────────────────
    with tab_news:
        st.subheader(f"Latest News — {name}")
        news = _load_news(name)
        if news:
            for item in news:
                with st.container(border=True):
                    headline = (item.get("headline") or item.get("title")
                                or item.get("event") or "News update")
                    st.markdown(f"**{headline}**")
                    summary = item.get("summary") or item.get("description") or item.get("details")
                    if summary:
                        st.write(summary)
                    url = item.get("source_url") or item.get("url")
                    ts  = str(item.get("fetched_at", ""))[:10]
                    if url:
                        st.caption(f"[Source]({url})  ·  {ts}")
                    elif ts:
                        st.caption(ts)
        else:
            st.info(
                "No news in the cache yet. Run the ingestion pipeline with "
                "an `ANTHROPIC_API_KEY` to fetch live news summaries."
            )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.title("🌍 Participants — FIFA World Cup 2026")

    # Initialise session state
    if "participants_selected" not in st.session_state:
        st.session_state["participants_selected"] = None

    selected = st.session_state["participants_selected"]

    # ── Team detail view ───────────────────────────────────────────────────────
    if selected and selected in TEAM_PROFILES:
        _render_detail(selected)
        return

    # ── Card grid ──────────────────────────────────────────────────────────────
    st.caption("48 qualified teams · ordered by FIFA ranking · click a card to view squad & news")

    search = st.text_input(
        "",
        placeholder="🔍  Search team name, coach or player…",
        label_visibility="collapsed",
    )

    # Sort all teams by FIFA rank
    all_teams = sorted(TEAM_PROFILES.items(), key=lambda kv: kv[1]["fifa_rank"])

    # Filter by search query (accent-insensitive)
    def _norm(s: str) -> str:
        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

    q = _norm(search.strip())
    if q:
        def _matches(name: str, profile: dict) -> bool:
            if q in _norm(name):
                return True
            if q in _norm(profile["coach"]):
                return True
            for player_name, *_ in profile.get("players", []):
                if q in _norm(player_name):
                    return True
            return False

        all_teams = [(n, p) for n, p in all_teams if _matches(n, p)]

    if not all_teams:
        st.warning("No teams match your search.")
        return

    st.caption(f"{len(all_teams)} team{'s' if len(all_teams) != 1 else ''} found")

    # Render cards in a 4-column grid
    cols_per_row = 4
    for row_start in range(0, len(all_teams), cols_per_row):
        row_teams = all_teams[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (name, profile) in zip(cols, row_teams):
            group = TEAM_GROUP.get(name, "?")
            with col:
                _render_card(name, profile, group)
