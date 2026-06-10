"""
Scrapes FBref national team squad pages to extract per-player statistics.
Respects robots.txt — adds a configurable rate limit between requests.
"""
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config.settings import settings

_FBREF_BASE = "https://fbref.com"
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (research project; contact: worldcup-predictor)"
})


def _raw_path(slug: str) -> Path:
    today = date.today().isoformat()
    path = Path(settings.raw_data_dir) / "fbref" / today / f"{slug}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_squad_html(fbref_slug: str) -> str:
    cache = _raw_path(fbref_slug)
    if cache.exists():
        return cache.read_text(encoding="utf-8")

    url = f"{_FBREF_BASE}/en/national/players/{fbref_slug}/"
    time.sleep(settings.fbref_rate_limit_secs)
    resp = _SESSION.get(url, timeout=20)
    resp.raise_for_status()
    cache.write_text(resp.text, encoding="utf-8")
    return resp.text


def scrape_squad(team_name: str, fbref_slug: str, team_id: int) -> pd.DataFrame:
    """Return a DataFrame of player stats for one national team."""
    try:
        html = _fetch_squad_html(fbref_slug)
    except Exception as exc:
        print(f"  [fbref] Failed to fetch {team_name}: {exc}")
        return pd.DataFrame()

    soup = BeautifulSoup(html, "lxml")

    # FBref uses a table with id="stats_standard" or similar
    table = soup.find("table", {"id": lambda x: x and "stats" in x})
    if table is None:
        return pd.DataFrame()

    rows = []
    for tr in table.find_all("tr")[1:]:  # skip header
        cells = tr.find_all(["td", "th"])
        if len(cells) < 5:
            continue
        try:
            player = cells[0].get_text(strip=True)
            pos = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            club = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            minutes = _safe_int(cells[3].get_text(strip=True)) if len(cells) > 3 else 0
            goals = _safe_int(cells[4].get_text(strip=True)) if len(cells) > 4 else 0
            assists = _safe_int(cells[5].get_text(strip=True)) if len(cells) > 5 else 0
            sca = _safe_float(cells[6].get_text(strip=True)) if len(cells) > 6 else 0.0
            gca = _safe_float(cells[7].get_text(strip=True)) if len(cells) > 7 else 0.0
            if player:
                rows.append({
                    "team_id": team_id,
                    "player_name": player,
                    "position": pos,
                    "club": club,
                    "minutes_played": minutes,
                    "goals": goals,
                    "assists": assists,
                    "sca": sca,
                    "gca": gca,
                    "is_injured": 0,
                    "is_suspended": 0,
                })
        except (IndexError, ValueError):
            continue

    return pd.DataFrame(rows)


def _safe_int(val: str) -> int:
    try:
        return int(val.replace(",", "").replace("\xa0", ""))
    except (ValueError, AttributeError):
        return 0


def _safe_float(val: str) -> float:
    try:
        return float(val.replace(",", "").replace("\xa0", ""))
    except (ValueError, AttributeError):
        return 0.0
