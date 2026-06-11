"""Streamlit entry point — sidebar navigation between the three pages."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.set_page_config(
    page_title="WC 2026 Predictor",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.page_modules import match_center, participants, analytics, bracket_view

_PAGES = {
    "🗓️ Fixtures":      match_center,
    "🌍 Participants":  participants,
    "📊 Analytics":     analytics,
    "🏆 Bracket":       bracket_view,
}


def main() -> None:
    st.sidebar.title("WC 2026 Predictor")
    st.sidebar.markdown("---")
    page_name = st.sidebar.radio("Navigate", list(_PAGES.keys()), label_visibility="collapsed")

    st.sidebar.markdown("---")
    st.sidebar.caption("Data: API-Football · FBref · Transfermarkt · Claude AI")
    st.sidebar.caption(f"Model: `{_load_version()}`")

    if st.sidebar.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    _PAGES[page_name].render()


def _load_version() -> str:
    try:
        from config.settings import settings
        return settings.model_version
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
