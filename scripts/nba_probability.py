"""Collect or reproduce fixed NBA Elo validation; no model calls or orders."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from local_market_agent.nba_history import collect_nba_history
from local_market_agent.nba_probability import (
    chronological_predictions,
    load_history,
    validate_predictions,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument("--allow-network", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("--history", required=True, type=Path)
    validate.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "collect":
            output = collect_nba_history(args.output, allow_network=args.allow_network)
            print(json.dumps({"history": str(output), "requests": 120, "orders": 0}))
            return
        now = datetime.now(UTC)
        games, audit = load_history(args.history, now=now)
        predictions, ratings, state = chronological_predictions(games, cutoff=now)
        validation = validate_predictions(predictions, audit)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "analysis.json").write_text(
            json.dumps(
                {"audit": audit, "validation": validation, "ratings": ratings, "state": state},
                indent=2,
            )
        )
        (args.output / "predictions.json").write_text(json.dumps(predictions, indent=2))
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "passed": validation["passed"],
                    "holdout_n": validation["holdout_n"],
                    "brier": validation["brier"],
                    "baseline_brier": validation["baseline_brier"],
                    "ece": validation["ece"],
                }
            )
        )
        if not validation["passed"]:
            raise SystemExit(3)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, StopIteration) as exc:
        parser.exit(2, f"NBA probability workflow failed: {exc}\n")


if __name__ == "__main__":
    main()
