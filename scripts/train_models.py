"""Train Poisson, XGBoost, and LightGBM models and save artifacts."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.trainer import train_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Train WC 2026 prediction models")
    parser.add_argument("--version", default=None, help="Override MODEL_VERSION from .env")
    parser.add_argument("--optuna-trials", type=int, default=50)
    args = parser.parse_args()

    train_all(version=args.version, n_optuna_trials=args.optuna_trials)


if __name__ == "__main__":
    main()
