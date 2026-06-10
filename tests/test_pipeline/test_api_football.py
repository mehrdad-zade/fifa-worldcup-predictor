"""Tests for API-Football client with HTTP mocking."""
import json

import pytest
import responses as resp_lib

from pipeline.api_football import parse_fixture_row


def _make_fixture(home_id: int, away_id: int, home_name: str, away_name: str,
                  home_score: int | None = None, away_score: int | None = None) -> dict:
    return {
        "fixture": {
            "id": 1001,
            "date": "2026-06-11T18:00:00+00:00",
            "status": {"long": "Group Stage", "short": "FT" if home_score is not None else "NS"},
            "venue": {"name": "MetLife Stadium"},
        },
        "teams": {
            "home": {"id": home_id, "name": home_name},
            "away": {"id": away_id, "name": away_name},
        },
        "goals": {"home": home_score, "away": away_score},
    }


def test_parse_fixture_row_with_result():
    raw = _make_fixture(9, 94, "Spain", "Canada", 2, 0)
    row = parse_fixture_row(raw)
    assert row["home_name"] == "Spain"
    assert row["away_name"] == "Canada"
    assert row["home_score"] == 2
    assert row["away_score"] == 0
    assert row["status"] == "FT"


def test_parse_fixture_row_without_result():
    raw = _make_fixture(9, 94, "Spain", "Canada")
    row = parse_fixture_row(raw)
    assert row["home_score"] is None
    assert row["away_score"] is None
    assert row["status"] == "NS"


def test_parse_fixture_row_venue():
    raw = _make_fixture(1, 6, "Belgium", "Argentina", 1, 2)
    row = parse_fixture_row(raw)
    assert row["venue"] == "MetLife Stadium"
    assert row["api_fixture_id"] == 1001
