"""Collect official results or replay locally supplied tickets; never place bets."""

import argparse
import json
from pathlib import Path

from local_market_agent.horse_racing.models import HistoricalRecord
from local_market_agent.horse_racing.replay import replay_history
from local_market_agent.horse_racing.results import collect_results, load_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--date", required=True)
    collect.add_argument("--course", choices=["ST", "HV"], default="ST")
    collect.add_argument("--races", type=int, default=9)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--allow-network", action="store_true")
    replay = sub.add_parser("replay")
    replay.add_argument("--record", type=Path, required=True)
    replay.add_argument("--official", type=Path)
    replay.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "collect":
            meeting = collect_results(
                args.output,
                args.date,
                course=args.course,
                races=args.races,
                allow_network=args.allow_network,
            )
            print(
                json.dumps(
                    {"output": str(args.output), "races": len(meeting.races), "orders_created": 0}
                )
            )
            return
        if args.record.stat().st_size > 5_000_000:
            raise ValueError("Historical record exceeds 5 MB")
        record = HistoricalRecord.model_validate_json(args.record.read_text())
        official = load_results(args.official) if args.official else None
        report = replay_history(record, official)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "replay.json").write_text(json.dumps(report, indent=2))
        if official:
            (args.output / "official.json").write_text(official.model_dump_json(indent=2))
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "tickets": report["ticket_count"],
                    "entitlement": report["official_entitlement"],
                    "orders_created": 0,
                }
            )
        )
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        parser.exit(2, f"Horse replay failed: {exc}\n")


if __name__ == "__main__":
    main()
