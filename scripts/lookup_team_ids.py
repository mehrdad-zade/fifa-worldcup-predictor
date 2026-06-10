"""
Queries API-Football /teams endpoint to verify or populate api_football_id values
in config/teams.json. Prints a diff table and optionally writes the updated JSON.

Usage:
    python scripts/lookup_team_ids.py           # dry run — print diff only
    python scripts/lookup_team_ids.py --write   # update teams.json in place
"""
import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings

TEAMS_JSON = Path(__file__).parent.parent / "config" / "teams.json"


def lookup_team_id(name: str, session: requests.Session) -> int | None:
    resp = session.get(
        f"https://{settings.api_football_host}/teams",
        params={"search": name},
        headers={
            "x-apisports-key": settings.api_football_key,
            "x-rapidapi-host": settings.api_football_host,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("response", [])
    if data:
        return data[0]["team"]["id"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write updated IDs to teams.json")
    args = parser.parse_args()

    if not settings.api_football_key:
        print("ERROR: API_FOOTBALL_KEY not set in .env")
        sys.exit(1)

    config = json.loads(TEAMS_JSON.read_text(encoding="utf-8"))
    session = requests.Session()
    updated = False

    print(f"{'Team':<20} {'Current ID':>10} {'API ID':>10} {'Match?':>8}")
    print("-" * 52)

    for group, teams in config["groups"].items():
        for team in teams:
            name = team["name"]
            current = team.get("api_football_id", 0)
            found = lookup_team_id(name, session)
            match = "✓" if found == current else "≠"
            print(f"{name:<20} {current:>10} {str(found or '?'):>10} {match:>8}")
            if found and found != current:
                team["api_football_id"] = found
                updated = True

    if args.write and updated:
        TEAMS_JSON.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\nteams.json updated.")
    elif updated:
        print("\nRun with --write to apply these changes.")
    else:
        print("\nAll IDs match.")


if __name__ == "__main__":
    main()
