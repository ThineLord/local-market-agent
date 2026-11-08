"""Screen bounded public sports markets without modifying a ledger."""
import argparse
import json

from local_market_agent.public_screen import screen_public_markets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--series", default="KXNBAGAME", choices=["KXNBAGAME", "KXNFLGAME"])
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    try:
        report = screen_public_markets(args.output, series=args.series,
            max_pages=args.max_pages, allow_network=args.allow_network)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"Public screening failed: {exc}\n")
    print(json.dumps({key: report[key] for key in
        ("series", "market_count", "eligible_count", "truncated", "ranked_market_ids")}))


if __name__ == "__main__":
    main()
