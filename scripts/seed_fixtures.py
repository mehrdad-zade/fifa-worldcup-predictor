"""
Seeds all WC 2026 data from hardcoded sources — no external API calls required.

Steps:
  1. Upsert 48 teams from config/teams.json with sequential IDs
  2. Clear elo_history and seed initial Elo ratings based on FIFA ranking tier
  3. Apply recent trophy bonuses (WC 2022, Euro 2024, Copa America 2024)
  4. Seed all 104 fixtures from config/fixtures.py
  5. Initialise and save Poisson model artifact from Elo ratings

Run this once (or to reset to a clean state):
  python scripts/seed_fixtures.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.fixtures import FIXTURES, DB_STAGE
from db.database import execute_sql, executemany_sql, query_one
from features.elo import _save_elo


# ── Initial Elo ratings ───────────────────────────────────────────────────────
# Based on FIFA World Rankings + WC 2022/Euro 2024/Copa 2024 outcomes.
# These are the "as of tournament start" ratings after all recent form.

_INITIAL_ELOS: dict[str, float] = {
    # Group A
    "Mexico":                    1810,
    "South Africa":              1530,
    "South Korea":               1720,
    "Czechia":                   1660,
    # Group B
    "Canada":                    1690,
    "Bosnia and Herzegovina":    1640,
    "Switzerland":               1780,
    "Qatar":                     1600,
    # Group C
    "Haiti":                     1470,
    "Scotland":                  1700,
    "Brazil":                    1890,
    "Morocco":                   1790,
    # Group D
    "USA":                       1760,
    "Paraguay":                  1660,
    "Australia":                 1720,
    "Türkiye":                   1730,
    # Group E
    "Ivory Coast":               1700,
    "Ecuador":                   1720,
    "Germany":                   1870,
    "Curaçao":                   1460,
    # Group F
    "Netherlands":               1840,
    "Japan":                     1790,
    "Sweden":                    1730,
    "Tunisia":                   1650,
    # Group G
    "Iran":                      1660,
    "New Zealand":               1500,
    "Belgium":                   1820,
    "Egypt":                     1650,
    # Group H
    "Saudi Arabia":              1640,
    "Uruguay":                   1800,
    "Cape Verde":                1590,
    "Spain":                     1930,   # Euro 2024 winner
    # Group I
    "France":                    1950,   # WC 2022 runner-up
    "Senegal":                   1770,
    "Iraq":                      1610,
    "Norway":                    1720,
    # Group J
    "Argentina":                 1960,   # WC 2022 + Copa 2024 winner
    "Algeria":                   1670,
    "Austria":                   1730,
    "Jordan":                    1570,
    # Group K
    "Portugal":                  1880,
    "Congo DR":                  1590,
    "Uzbekistan":                1560,
    "Colombia":                  1790,
    # Group L
    "Ghana":                     1680,
    "Panama":                    1560,
    "England":                   1880,
    "Croatia":                   1800,
}

_ELO_SEED_DATE = "2026-01-01"


def _load_teams() -> list[dict]:
    config_path = Path(__file__).parent.parent / "config" / "teams.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    teams = []
    for group, members in data["groups"].items():
        for t in members:
            teams.append({**t, "group_code": group})
    return teams


def seed_teams(teams: list[dict]) -> dict[str, int]:
    """Upsert teams and return {name: team_id}."""
    name_to_id: dict[str, int] = {}
    for i, t in enumerate(teams):
        team_id = t.get("api_football_id") or (i + 1)
        execute_sql(
            "INSERT OR REPLACE INTO teams "
            "(team_id, name, group_code, confederation, api_football_id, fbref_slug, transfermarkt_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                team_id,
                t["name"],
                t["group_code"],
                t["confederation"],
                t.get("api_football_id") or None,
                t.get("fbref_squad_id"),
                t.get("transfermarkt_id") or None,
            ),
        )
        name_to_id[t["name"]] = team_id
    return name_to_id


def seed_elo(name_to_id: dict[str, int]) -> dict[int, float]:
    """Seed initial Elo ratings for all 48 teams (elo_history already cleared)."""
    elo_map: dict[int, float] = {}
    for name, elo in _INITIAL_ELOS.items():
        tid = name_to_id.get(name)
        if tid is None:
            print(f"  WARNING: team '{name}' not in DB — skipping Elo seed")
            continue
        _save_elo(tid, elo, _ELO_SEED_DATE, "initial_seed")
        elo_map[tid] = elo
    return elo_map


def seed_fixtures(name_to_id: dict[str, int]) -> None:
    """Insert all 104 WC 2026 fixtures."""
    execute_sql("DELETE FROM fixtures")

    rows = []
    for match_num, date_str, time_est, _, matchup, group, round_label, venue, city in FIXTURES:
        fixture_id = f"wc-2026-m{match_num}"
        db_stage = DB_STAGE.get(round_label, round_label)
        group_code = group or None

        # Parse match date + time
        try:
            dt = datetime.strptime(f"{date_str} {time_est}", "%d-%b-%y %H:%M")
            match_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            match_date = datetime.strptime(date_str, "%d-%b-%y").strftime("%Y-%m-%d")

        # Resolve team IDs (None for knockout placeholder matchups)
        home_id = away_id = None
        parts = matchup.split(" v ", 1)
        if len(parts) == 2:
            home_id = name_to_id.get(parts[0])
            away_id = name_to_id.get(parts[1])

        rows.append((fixture_id, db_stage, group_code, home_id, away_id, match_date, venue))

    executemany_sql(
        "INSERT OR REPLACE INTO fixtures "
        "(fixture_id, stage, group_code, home_team_id, away_team_id, match_date, venue) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def build_poisson_model(elo_map: dict[int, float], version: str) -> None:
    """Create and save a Poisson model initialised from Elo ratings."""
    from models.poisson_model import PoissonModel
    artifacts = Path("models/artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    path = artifacts / f"poisson_{version}.pkl"
    model = PoissonModel.from_elo_ratings(elo_map)
    model.save(str(path))
    print(f"  Poisson model saved → {path}")


def _clear_dependent_tables() -> None:
    """Clear all tables that FK-reference teams so we can replace teams safely."""
    for tbl in ("elo_history", "predictions", "results", "fixtures",
                "player_stats", "player_values", "claude_news_cache"):
        execute_sql(f"DELETE FROM {tbl}")


def main() -> None:
    from config.settings import settings

    print("=== Seeding WC 2026 fixtures ===")

    print("[0/4] Clearing dependent tables...")
    _clear_dependent_tables()

    teams = _load_teams()
    print(f"[1/4] Upserting {len(teams)} teams...")
    name_to_id = seed_teams(teams)
    print(f"      Team IDs: {min(name_to_id.values())}–{max(name_to_id.values())}")

    print("[2/4] Seeding initial Elo ratings...")
    elo_map = seed_elo(name_to_id)
    print(f"      {len(elo_map)} teams rated  (avg {sum(elo_map.values())/len(elo_map):.0f})")
    top3 = sorted(elo_map.items(), key=lambda x: x[1], reverse=True)[:3]
    for tid, elo in top3:
        name = next(n for n, i in name_to_id.items() if i == tid)
        print(f"        {name}: {elo:.0f}")

    print("[3/4] Seeding 104 fixtures...")
    seed_fixtures(name_to_id)
    gs = sum(1 for f in FIXTURES if f[6] == "Group Stage")
    ko = sum(1 for f in FIXTURES if f[6] != "Group Stage")
    print(f"      {gs} group stage + {ko} knockout fixtures")

    print("[4/4] Building Poisson model from Elo ratings...")
    build_poisson_model(elo_map, settings.model_version)

    print("\n=== Seed complete ===")
    print(f"  Teams:    {len(name_to_id)}")
    print(f"  Fixtures: {len(FIXTURES)}")
    print(f"  Elo entries seeded for: {len(elo_map)} teams")


if __name__ == "__main__":
    main()
