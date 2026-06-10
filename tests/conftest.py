"""pytest fixtures: in-memory SQLite, mock API responses."""
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Point at an in-memory DB for tests
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("API_FOOTBALL_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")


@pytest.fixture(autouse=True)
def reset_db(tmp_path, monkeypatch):
    """Each test gets a fresh temporary DB."""
    db_file = tmp_path / "test_worldcup.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    # Reimport settings to pick up the patched env var
    import importlib
    import config.settings as settings_mod
    importlib.reload(settings_mod)
    # Initialize schema
    from scripts.init_db import main as init_db
    init_db()
    yield
    # Cleanup handled by tmp_path fixture


@pytest.fixture
def sample_matches() -> list[dict]:
    return [
        {"home_team_id": 1, "away_team_id": 2, "home_score": 2, "away_score": 1},
        {"home_team_id": 2, "away_team_id": 3, "home_score": 0, "away_score": 0},
        {"home_team_id": 3, "away_team_id": 1, "home_score": 1, "away_score": 3},
        {"home_team_id": 1, "away_team_id": 3, "home_score": 1, "away_score": 1},
        {"home_team_id": 2, "away_team_id": 1, "home_score": 0, "away_score": 2},
    ]


@pytest.fixture
def seed_teams(reset_db):
    """Insert a minimal set of teams for testing."""
    from db.database import executemany_sql
    executemany_sql(
        "INSERT OR REPLACE INTO teams (team_id, name, group_code, confederation) VALUES (?, ?, ?, ?)",
        [
            (1, "Spain", "A", "UEFA"),
            (2, "Germany", "A", "UEFA"),
            (3, "France", "B", "UEFA"),
            (4, "Brazil", "B", "CONMEBOL"),
        ],
    )
