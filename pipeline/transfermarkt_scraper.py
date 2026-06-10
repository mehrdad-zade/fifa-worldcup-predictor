"""
Scrapes Transfermarkt national team squad pages to extract player market values
as an additional squad strength signal.
"""
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from lxml import etree  # noqa: F401  — kept for lxml backend

from config.settings import settings

_BASE = "https://www.transfermarkt.com"
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (research project; contact: worldcup-predictor)"
})


def _raw_path(team_id: int) -> Path:
    today = date.today().isoformat()
    path = Path(settings.raw_data_dir) / "transfermarkt" / today / f"team_{team_id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def scrape_market_values(team_name: str, transfermarkt_id: int, team_id: int) -> dict[str, int]:
    """Return {player_name: market_value_eur} for a national team."""
    if not transfermarkt_id:
        return {}

    cache = _raw_path(transfermarkt_id)
    if cache.exists():
        html = cache.read_text(encoding="utf-8")
    else:
        slug = team_name.lower().replace(" ", "-")
        url = f"{_BASE}/{slug}/startseite/verein/{transfermarkt_id}/saison_id/2026"
        try:
            time.sleep(settings.transfermarkt_rate_limit_secs)
            resp = _SESSION.get(url, timeout=20)
            resp.raise_for_status()
            html = resp.text
            cache.write_text(html, encoding="utf-8")
        except Exception as exc:
            print(f"  [transfermarkt] Failed to fetch {team_name}: {exc}")
            return {}

    soup = BeautifulSoup(html, "lxml")
    values: dict[str, int] = {}

    for row in soup.select("table.items > tbody > tr"):
        name_td = row.select_one("td.hauptlink a")
        value_td = row.select_one("td.rechts.hauptlink")
        if name_td and value_td:
            player = name_td.get_text(strip=True)
            raw = value_td.get_text(strip=True)
            values[player] = _parse_value(raw)

    return values


def _parse_value(raw: str) -> int:
    """Convert '€45m' or '€500k' to integer euros."""
    raw = raw.replace("€", "").replace("\xa0", "").strip()
    try:
        if raw.endswith("m"):
            return int(float(raw[:-1]) * 1_000_000)
        if raw.endswith("k"):
            return int(float(raw[:-1]) * 1_000)
        return int(raw.replace(",", ""))
    except ValueError:
        return 0
