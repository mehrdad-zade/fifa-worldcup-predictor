"""Run evaluation against completed matches and print a report."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.evaluator import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    run_evaluation(model_version=args.version)


if __name__ == "__main__":
    main()
