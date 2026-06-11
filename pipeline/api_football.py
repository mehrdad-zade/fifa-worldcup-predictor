from __future__ import annotations

"""
REST client for API-Football v3.
Implements daily JSON caching to stay within the 100 req/day free tier.
"""
import json
import time
from datetime import date, datetime
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

_BASE = f"https://{settings.api_football_host}"
_HEADERS = {
    "x-apisports-key": settings.api_football_key,
    "x-rapidapi-host": settings.api_football_host,
}
_WC_2026_LEAGUE_ID = 1  # API-Football league ID for FIFA World Cup 2026
_WC_2026_SEASON = 2026


def _cache_path(endpoint: str) -> Path:
    today = date.today().isoformat()
    safe = endpoint.replace("/", "_").strip("_")
    path = Path(settings.raw_data_dir) / "api_football" / today / f"{safe}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _cached_get(endpoint: str, params: dict | None = None) -> dict:
    cache = _cache_path(endpoint + "_" + "_".join(f"{k}{v}" for k, v in (params or {}).items()))
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    resp = _get_with_retry(endpoint, params or {})
    data = resp.json()
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get_with_retry(endpoint: str, params: dict) -> requests.Response:
    resp = requests.get(f"{_BASE}/{endpoint}", params=params, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp


def get_fixtures(league_id: int = _WC_2026_LEAGUE_ID, season: int = _WC_2026_SEASON) -> list[dict]:
    data = _cached_get("fixtures", {"league": league_id, "season": season})
    return data.get("response", [])


def get_standings(league_id: int = _WC_2026_LEAGUE_ID, season: int = _WC_2026_SEASON) -> list[dict]:
    data = _cached_get("standings", {"league": league_id, "season": season})
    return data.get("response", [])


def get_live_scores() -> list[dict]:
    # Live scores are never cached — always fresh
    resp = _get_with_retry("fixtures", {"live": "all", "league": _WC_2026_LEAGUE_ID})
    return resp.json().get("response", [])


def get_team_form(team_id: int, last_n: int = 10) -> list[dict]:
    data = _cached_get("fixtures", {
        "team": team_id,
        "last": last_n,
        "season": _WC_2026_SEASON,
    })
    return data.get("response", [])


def parse_fixture_row(f: dict) -> dict:
    """Normalise an API-Football fixture response into a flat dict."""
    fix = f.get("fixture", {})
    teams = f.get("teams", {})
    goals = f.get("goals", {})
    return {
        "api_fixture_id": fix.get("id"),
        "stage": fix.get("status", {}).get("long", ""),
        "match_date": fix.get("date", ""),
        "venue": fix.get("venue", {}).get("name", ""),
        "home_api_id": teams.get("home", {}).get("id"),
        "home_name": teams.get("home", {}).get("name", ""),
        "away_api_id": teams.get("away", {}).get("id"),
        "away_name": teams.get("away", {}).get("name", ""),
        "home_score": goals.get("home"),
        "away_score": goals.get("away"),
        "status": fix.get("status", {}).get("short", ""),
    }
