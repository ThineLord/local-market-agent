"""Build a verified public NBA research packet without approving an order."""

import argparse
import json
from pathlib import Path

from local_market_agent.nba_workflow import build_nba_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    try:
        path = build_nba_packet(args.output, args.history, allow_network=args.allow_network)
        print(json.dumps({"packet": str(path), "orders": 0, "approvals": 0}))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, StopIteration) as exc:
        parser.exit(2, f"NBA packet workflow failed: {exc}\n")


if __name__ == "__main__":
    main()
