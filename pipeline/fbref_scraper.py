"""
Scrapes FBref national team squad pages to extract per-player statistics.

FBref URL format:  /en/squads/{fbref_squad_id}/{country}-Men-Stats
The fbref_squad_id is an 8-character hex string stored in config/teams.json.
Run scripts/lookup_fbref_ids.py to populate missing IDs.

FBref has bot-detection. If 403 errors persist, fetch the HTML manually in a
browser (File → Save As) and place it at data/raw/fbref/today/{squad_id}.html.
"""
import time
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config.settings import settings

_FBREF_BASE = "https://fbref.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://fbref.com/",
    "DNT": "1",
}

_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)

# After this many consecutive 403s, skip the rest of the squads for today.
_MAX_CONSECUTIVE_BLOCKS = 2
_consecutive_blocks = 0


def _raw_path(squad_id: str) -> Path:
    today = date.today().isoformat()
    path = Path(settings.raw_data_dir) / "fbref" / today / f"{squad_id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_squad_html(squad_id: str, team_name: str, url_name: str | None = None) -> str:
    cache = _raw_path(squad_id)
    if cache.exists():
        return cache.read_text(encoding="utf-8")

    # url_name overrides team_name for teams where FBref uses a different slug
    name_slug = (url_name or team_name).replace(" ", "-")
    url = f"{_FBREF_BASE}/en/squads/{squad_id}/{name_slug}-Men-Stats"

    time.sleep(settings.fbref_rate_limit_secs)
    resp = _SESSION.get(url, timeout=20)
    resp.raise_for_status()
    cache.write_text(resp.text, encoding="utf-8")
    return resp.text


def scrape_squad(
    team_name: str,
    squad_id: str | None,
    team_id: int,
    url_name: str | None = None,
) -> pd.DataFrame:
    """Return a DataFrame of player stats for one national team.

    squad_id is the FBref internal 8-char hex ID from config/teams.json.
    url_name overrides team_name in the URL slug for teams where FBref uses a
    different name (e.g. "United-States" for USA, "Korea-Republic" for South Korea).
    Returns an empty DataFrame (silently) when squad_id is not configured.
    """
    global _consecutive_blocks

    if not squad_id:
        return pd.DataFrame()  # not configured — skip quietly

    if _consecutive_blocks >= _MAX_CONSECUTIVE_BLOCKS:
        return pd.DataFrame()  # FBref is blocking — don't keep trying

    try:
        html = _fetch_squad_html(squad_id, team_name, url_name)
        _consecutive_blocks = 0  # reset on success
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 403:
            _consecutive_blocks += 1
            if _consecutive_blocks == 1:
                print(
                    f"  [fbref] 403 Forbidden for {team_name}. "
                    "FBref is blocking automated requests.\n"
                    "  To fix: open the squad page in a browser, Save As HTML, "
                    f"and place it at data/raw/fbref/{date.today().isoformat()}/{squad_id}.html"
                )
            elif _consecutive_blocks >= _MAX_CONSECUTIVE_BLOCKS:
                print(
                    f"  [fbref] {_MAX_CONSECUTIVE_BLOCKS} consecutive blocks — "
                    "skipping remaining FBref scrapes for today."
                )
        else:
            print(f"  [fbref] HTTP error for {team_name}: {exc}")
        return pd.DataFrame()
    except Exception as exc:
        print(f"  [fbref] Failed to fetch {team_name}: {exc}")
        return pd.DataFrame()

    return _parse_squad_table(html, team_id)


def _parse_squad_table(html: str, team_id: int) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": lambda x: x and "stats_standard" in str(x)})
    if table is None:
        table = soup.find("table", {"id": lambda x: x and "stats" in str(x)})
    if table is None:
        return pd.DataFrame()

    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 5:
            continue
        try:
            player = cells[0].get_text(strip=True)
            if not player or player in ("Player", ""):
                continue
            rows.append({
                "team_id": team_id,
                "player_name": player,
                "position": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                "club": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                "minutes_played": _safe_int(cells[3].get_text(strip=True)) if len(cells) > 3 else 0,
                "goals": _safe_int(cells[4].get_text(strip=True)) if len(cells) > 4 else 0,
                "assists": _safe_int(cells[5].get_text(strip=True)) if len(cells) > 5 else 0,
                "sca": _safe_float(cells[6].get_text(strip=True)) if len(cells) > 6 else 0.0,
                "gca": _safe_float(cells[7].get_text(strip=True)) if len(cells) > 7 else 0.0,
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
