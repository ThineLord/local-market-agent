"""Run the complete synthetic CLI workflow in a new, isolated output directory."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from local_market_agent.demo import demo_packet, demo_settlement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    db = output / "demo.sqlite"
    transcript = []
    def run(command, *options, expected=0, database=False):
        tokens = [sys.executable, "-m", "local_market_agent.cli", command, *map(str, options)]
        if database:
            tokens.extend(["--db", str(db)])
        result = subprocess.run(tokens, capture_output=True, text=True, env=os.environ.copy(), timeout=60)
        if result.returncode != expected:
            raise RuntimeError(f"{command}: expected {expected}, got {result.returncode}: {result.stdout} {result.stderr}")
        payload = json.loads(result.stdout)
        transcript.append({"command": tokens[3:], "exit_code": result.returncode, "result": payload})
        return payload
    packet = demo_packet(output / "executed", market_id="synthetic-executed-demo")
    run("packet-check", "--packet", packet)
    review = packet.parent / "research-review.json"
    run("packet-review", "--packet", packet, "--output", review, "--actor", "synthetic-demo", "--reason", "Synthetic source review; not human review of public markets")
    prepared = run("packet-prepare", "--packet", packet, "--review", review, expected=4, database=True)
    intent_id = prepared["intent_id"]
    run("paper-execute", "--intent-id", intent_id, expected=4, database=True)
    run("paper-approve", "--intent-id", intent_id, "--actor", "synthetic-demo", "--reason", "Explicit synthetic paper-order approval", database=True)
    run("paper-execute", "--intent-id", intent_id, database=True)
    run("paper-execute", "--intent-id", intent_id, database=True)
    run("paper-replay", "--intent-id", intent_id, database=True)
    settled = demo_settlement(packet)
    settlement_review = packet.parent / "settlement-review.json"
    run("packet-review", "--packet", settled, "--output", settlement_review, "--scope", "settlement", "--actor", "synthetic-demo", "--reason", "Synthetic final outcome; no real market claim")
    run("packet-settle", "--packet", settled, "--review", settlement_review, database=True)
    run("paper-replay", "--intent-id", intent_id, database=True)
    run("report-daily", database=True)
    pending = demo_packet(output / "pending", market_id="synthetic-pending-demo")
    pending_review = pending.parent / "research-review.json"
    run("packet-review", "--packet", pending, "--output", pending_review, "--actor", "synthetic-demo", "--reason", "Synthetic pending-stage demonstration")
    run("packet-prepare", "--packet", pending, "--review", pending_review, database=True, expected=4)
    status = run("workflow-status", database=True)
    summary = {"synthetic": True, "db_path": str(db), "executed_intent": intent_id,
        "workflow": status, "steps": transcript, "limitations": ["No public-market order or actual human approval", "Demonstrates controls, not profitability"]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"output": str(output), "steps": len(transcript), "states": [i["status"] for i in status["intents"]], "db_path": str(db)}))


if __name__ == "__main__":
    main()
