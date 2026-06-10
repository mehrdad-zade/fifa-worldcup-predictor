"""
Generates today's match predictions + full bracket simulation,
writes a JSON snapshot to data/snapshots/ and upserts into SQLite.

Flags:
  --skip-if-fresh   Skip if a snapshot for today already exists.
  --no-news         Disable Claude news/fitness call (no Anthropic key needed).
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from predictions.daily_predictor import predict_todays_matches
from predictions.bracket_predictor import predict_full_bracket
from predictions.snapshot_writer import write_snapshot, load_latest_snapshot


def _snapshot_fresh() -> bool:
    """Return True if a snapshot for today already exists."""
    today = date.today().isoformat()
    snapshot_dir = Path(settings.snapshot_dir)
    return any(snapshot_dir.glob(f"{today}_*.json")) if snapshot_dir.exists() else False


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate WC 2026 predictions snapshot")
    parser.add_argument("--skip-if-fresh", action="store_true",
                        help="Skip if today's snapshot already exists")
    parser.add_argument("--no-news", action="store_true",
                        help="Skip Claude news/fitness calls (no Anthropic key needed)")
    parser.add_argument("--n-sims", type=int, default=None,
                        help="Override SIMULATION_N_RUNS (default: from .env)")
    args = parser.parse_args()

    if args.skip_if_fresh and _snapshot_fresh():
        print("Predictions already fresh for today — skipping.")
        return

    use_news = not args.no_news and bool(settings.anthropic_api_key)

    print("Generating today's match predictions...")
    try:
        daily = predict_todays_matches(use_news=use_news)
        print(f"  {len(daily)} match prediction(s) generated.")
    except Exception as exc:
        print(f"  Daily predictions failed: {exc}")
        daily = []

    print("Simulating full tournament bracket (Monte Carlo)...")
    try:
        bracket = predict_full_bracket(n_runs=args.n_sims)
        champion = bracket.get("champion", "TBD")
        champ_prob = bracket.get("champion_probability", 0.0)
        n_sims = bracket.get("n_simulations", 0)
        print(f"  {n_sims:,} simulations → predicted champion: {champion} ({champ_prob*100:.1f}%)")
    except Exception as exc:
        print(f"  Bracket simulation failed: {exc}")
        bracket = {}

    if not daily and not bracket:
        print("Nothing to write — skipping snapshot.")
        return

    snapshot_path = write_snapshot(daily, bracket)
    print(f"  Snapshot written: {snapshot_path}")


if __name__ == "__main__":
    main()
