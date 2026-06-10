"""
Orchestrates the full daily data refresh pipeline:
  1. API-Football: fixtures + standings → DB
  2. FBref: player stats → DB
  3. Transfermarkt: market values → DB
  4. Trigger feature recomputation cache invalidation

CLI flags:
  --dry-run       Print what would be done without writing to DB
  --skip-if-fresh Skip if ingestion already ran today
  --verbose       Verbose output
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from db.database import execute_sql, executemany_sql, query_one
from pipeline.api_football import get_fixtures, get_standings, parse_fixture_row
from pipeline.fbref_scraper import scrape_squad
from pipeline.transfermarkt_scraper import scrape_market_values


def _all_teams() -> list[dict]:
    config_path = Path(__file__).parent.parent / "config" / "teams.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    teams = []
    for group, members in data["groups"].items():
        for t in members:
            teams.append({**t, "group_code": group})
    return teams


def _already_ran_today() -> bool:
    today = date.today().isoformat()
    raw_dir = Path(settings.raw_data_dir) / "api_football" / today
    return raw_dir.exists() and any(raw_dir.iterdir())


def run_ingestion(dry_run: bool = False, verbose: bool = False) -> None:
    teams = _all_teams()

    # ── Upsert teams into DB ───────────────────────────────────
    if not dry_run:
        for t in teams:
            execute_sql(
                "INSERT OR REPLACE INTO teams "
                "(team_id, name, group_code, confederation, api_football_id, fbref_slug, transfermarkt_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    t.get("api_football_id", 0) or teams.index(t) + 1,
                    t["name"],
                    t["group_code"],
                    t["confederation"],
                    t.get("api_football_id"),
                    t.get("fbref_slug"),
                    t.get("transfermarkt_id"),
                ),
            )
        if verbose:
            print(f"  Upserted {len(teams)} teams.")

    # ── Fixtures from API-Football ─────────────────────────────
    if verbose:
        print("Fetching fixtures from API-Football...")
    try:
        fixtures = get_fixtures()
        if verbose:
            print(f"  Got {len(fixtures)} fixtures.")
        if not dry_run:
            _store_fixtures(fixtures, teams)
    except Exception as exc:
        print(f"  [api_football] Fixture fetch failed: {exc}")

    # ── Player stats from FBref ────────────────────────────────
    if verbose:
        print("Scraping FBref player stats...")
    for t in teams:
        slug = t.get("fbref_slug", "")
        tid = t.get("api_football_id", 0) or 0
        if not slug:
            continue
        if verbose:
            print(f"  {t['name']}...")
        df = scrape_squad(t["name"], slug, tid)
        if not dry_run and not df.empty:
            execute_sql("DELETE FROM player_stats WHERE team_id = ?", (tid,))
            executemany_sql(
                "INSERT INTO player_stats "
                "(team_id, player_name, position, club, minutes_played, goals, assists, sca, gca) "
                "VALUES (:team_id, :player_name, :position, :club, :minutes_played, :goals, :assists, :sca, :gca)",
                df.to_dict("records"),
            )

    # ── Market values from Transfermarkt ──────────────────────
    if verbose:
        print("Scraping Transfermarkt market values...")
    for t in teams:
        tid_tm = t.get("transfermarkt_id", 0)
        tid = t.get("api_football_id", 0) or 0
        if not tid_tm:
            continue
        values = scrape_market_values(t["name"], tid_tm, tid)
        if not dry_run and values:
            execute_sql("DELETE FROM player_values WHERE team_id = ?", (tid,))
            executemany_sql(
                "INSERT INTO player_values (team_id, player_name, market_value_eur) VALUES (?, ?, ?)",
                [(tid, name, val) for name, val in values.items()],
            )

    print("Ingestion complete." if not dry_run else "Dry-run complete — no changes written.")


def _store_fixtures(fixtures: list[dict], teams: list[dict]) -> None:
    api_id_to_team_id = {t.get("api_football_id"): t.get("api_football_id", 0) for t in teams}
    for i, f in enumerate(fixtures):
        row = parse_fixture_row(f)
        fixture_id = f"wc-2026-m{i+1:03d}"
        home_id = api_id_to_team_id.get(row["home_api_id"])
        away_id = api_id_to_team_id.get(row["away_api_id"])
        execute_sql(
            "INSERT OR REPLACE INTO fixtures "
            "(fixture_id, api_fixture_id, stage, match_date, venue, home_team_id, away_team_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fixture_id, row["api_fixture_id"], row["stage"], row["match_date"],
             row["venue"], home_id, away_id),
        )
        if row["home_score"] is not None and row["away_score"] is not None:
            execute_sql(
                "INSERT OR REPLACE INTO results (fixture_id, home_score, away_score, status) "
                "VALUES (?, ?, ?, ?)",
                (fixture_id, row["home_score"], row["away_score"], row["status"] or "FT"),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="FIFA WC 2026 data ingestion pipeline")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-if-fresh", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.skip_if_fresh and _already_ran_today():
        print("Data already fresh for today — skipping ingestion.")
        return

    run_ingestion(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
