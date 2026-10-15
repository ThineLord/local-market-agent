# Watchlist screening

`lma watchlist-screen` connects the existing public metadata adapters, local
snapshots, Strategy v1, saved reports, and the read-only dashboard into one
bounded research triage workflow. It never executes a trade or writes SQLite.

## Offline example

```bash
lma watchlist-screen --as-of 2026-06-05T00:02:00Z
python ui/server.py
```

Open <http://127.0.0.1:8502/#watchlist/screening>. The five synthetic examples
produce one `research_candidate`, one `needs_research`, and three `blocked`
results. The candidate brief is a deterministic mock example with an explicitly
fictional resolution URL. Its probability and edge are fixture values, not
research results or measured performance.

Omitting `--as-of` uses current UTC time. Old fixtures then fail freshness checks.
An explicit time must include a timezone and is only supported for all-file
watchlists. Current public snapshots cannot be backdated for historical review.

## Inputs

Copy and edit a watchlist JSON file. Each relative file path is resolved against
the watchlist's directory, independent of the shell's current directory:

```json
{
  "name": "Local research queue",
  "entries": [
    {
      "source": "file",
      "market_id": "demo-candidate",
      "snapshot_file": "candidate.json",
      "brief_file": "candidate-brief.json"
    }
  ]
}
```

The watchlist must contain 1–50 entries with unique `(source, market_id)` pairs.
Unknown keys and unsupported sources are rejected. File mode accepts an existing
fixture envelope (`market` plus `snapshot`) or a serialized `MarketSnapshot`.
It requires explicit `snapshot_id` and `as_of`; omitted provenance is not
replaced with a newly generated ID or current timestamp.

`brief_file` is optional. When present it must contain a serialized
`ResearchBrief` referencing that exact market and snapshot, with explicit
`created_at`. Existing briefs containing any `must_not_trade_reasons` remain
blocked, including generic paper-only warnings stored in that field. The
screener does not silently reinterpret or remove those vetoes.

## Public snapshots

Entries may instead use `source: "kalshi"` with a market ticker, or
`source: "polymarket"` with a Gamma market ID. Those entries must omit local
file fields. Actual identifiers must be chosen from the public market source;
the screener does not discover or subscribe to markets automatically.

```bash
lma watchlist-screen --watchlist /path/to/my-watchlist.json --allow-network
```

Without `--allow-network`, public entries receive an explicit `network_disabled`
result and make no requests. With it, the command performs at most one public
market request per entry, sequentially, using the existing bounded HTTP timeout.
Responses are cached in the configured raw-cache directory. Failures are
preserved per entry; there are no automatic retries or background collectors.

The public adapters supply retrieval timestamps, not exchange quote timestamps.
Reports label these `retrieval_only`; recent retrieval does not prove quote
freshness. Missing liquidity stays unknown and blocks the quality screen.
Kalshi's current metadata can omit liquidity, so a valid fetched quote may still
be blocked. No synthetic depth or liquidity is inferred from volume.

Public entries have no attached research estimate and cannot become research
candidates. Save the returned `rows[i].snapshot` as a local JSON snapshot and
provide a matching, independently prepared brief for a later file-mode review.
Doing so does not turn metadata snapshots into acceptance-grade evidence.

Adapter field references checked during implementation:

- [Kalshi Get Market](https://docs.kalshi.com/api-reference/market/get-market):
  public market endpoint and dollar-denominated price fields.
- [Polymarket Get market by ID](https://docs.polymarket.com/api-reference/markets/get-market-by-id):
  Gamma market metadata and probability quotes.

## Decisions

| Status | Meaning |
| --- | --- |
| `blocked` | One or more required quality/provenance checks failed, or network access was not enabled. |
| `error` | An input could not be read/validated or a public request failed. Other entries still run. |
| `needs_research` | Snapshot quality checks passed but no matching brief was supplied. |
| `observe` | A valid brief and snapshot were evaluated, but Strategy v1 did not emit a paper buy signal. |
| `research_candidate` | Strategy v1 emitted a paper buy signal; no execution or portfolio risk approval is implied. |

Snapshot checks include identity, explicit open status, binary YES/NO ordering,
close time when supplied, nonfuture/nonstale observation time, bid and ask,
spread, reported liquidity, and a probability within the bid/ask interval.
Default limits are the existing risk configuration: 300 seconds, maximum spread
0.08, and minimum reported liquidity 100.

Brief checks include exact snapshot linkage, creation between snapshot and review
time, two distinct evidence IDs, timezone-aware publication times no later than
the snapshot, no veto reasons, and a named unambiguous resolution source.
Strategy v1 then applies its existing confidence, evidence-quality, directional
edge, and spread-buffer rules. These are input checks, not independent factual
verification or evidence approval. Portfolio exposure, loss limits, fees, fills,
and human approval remain the responsibility of the existing paper workflow.

## Outputs and automation

Each invocation preserves JSON and Markdown in a new run directory beneath
`--output-dir` (default `data/reports/watchlist`). Only after both files are
written is `latest.json` replaced atomically. JSON includes all per-market
checks, settings thresholds, input SHA-256 values, observation timestamps,
source semantics, and the zero-order/no-authorization boundary.

The CLI prints report paths and status counts as JSON. Exit status is 0 for a
complete screen (including blocked/observe results), 1 if any entry errored,
and 2 for invalid top-level arguments/configuration or output write failure.
Inspect counts as well as exit status; success never means trade approval.

The dashboard reads the saved report only. Refresh does not collect data.
Missing or invalid reports show a dedicated empty/error state while existing
dashboard pages remain usable. To inspect another report directory or a past run:

```bash
python ui/server.py --screen-report /path/to/screen-id/report.json
```

This workflow makes no profitability, Strategy v2 superiority, source-terms
clearance, acceptance-readiness, or live-trading claims.
