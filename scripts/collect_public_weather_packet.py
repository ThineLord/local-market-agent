"""Collect a bounded public Kalshi/NWS observation packet in a new directory."""
import argparse
import json

from local_market_agent.public_weather import collect_weather_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-id", required=True, help="KXHIGHNY daily-high market ticker")
    parser.add_argument("--output", required=True, help="New isolated output directory")
    parser.add_argument("--allow-network", action="store_true", help="Explicitly allow six public read-only GETs")
    args = parser.parse_args()
    try:
        path = collect_weather_packet(args.output, args.market_id, allow_network=args.allow_network)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        parser.exit(2, f"Public collection failed; partial files, if any, remain for diagnosis: {exc}\n")
    print(json.dumps({"packet": str(path), "review_required": True, "order_created": False}))


if __name__ == "__main__":
    main()
