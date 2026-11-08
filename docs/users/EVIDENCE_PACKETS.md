# Evidence packets and settlement

[中文](EVIDENCE_PACKETS.zh-CN.md) · [Approval workflow](PAPER_WORKFLOW.md)

Use a small, single-market packet before expanding a real-data experiment. A packet is local JSON containing a `MarketSnapshot`, evidence items, source receipts, resolution-source URL, optional authored `ResearchBrief`, and optional settlement. The tool does not fetch arbitrary URLs or call a model. Keep the packet and its source files in one directory.

Every source receipt has `source_id`, public `url`, relative `path`, SHA-256, `retrieved_at`, and optional `published_at`. Every evidence item's `metadata.source_id`, URL and times must match its receipt. Evidence publication **and retrieval** must precede the snapshot; collecting an article after an outcome does not establish point-in-time availability. Source files cannot escape the packet directory. The brief must use exactly the packet's reviewed evidence and resolution source. `packet-check` separates provenance validity from execution blockers such as absent liquidity, stale data or a missing brief.

```bash
lma packet-check --packet packet/packet.json
lma packet-review --packet packet/packet.json --output packet/research-review.json --actor YOUR_NAME --reason 'Checked source meaning, timestamps and resolution rules'
lma packet-prepare --packet packet/packet.json --review packet/research-review.json --db data/experiment.sqlite
```

Preparation returns exit code 4 and an intent ID. Follow the separate order approval/execution commands in the [workflow guide](PAPER_WORKFLOW.md). Evidence review is not order approval. An estimate must be supplied and justified in the brief; no probability is invented to make a real sample tradeable. A review binds the packet hash, actor, rationale, scope and time. Local actor labels are not authenticated identities. Hash checks do not establish that a summary accurately represents a source; that is the reviewer's responsibility.

For settlement, create a **new** packet preserving original evidence files. Include a settled snapshot and `settlement` with `market_id`, `outcome` (`yes`/`no`), `source_id`, and `resolved_at`. The outcome must come from the market's actual resolution source, which can differ from the forecast provider.

```bash
lma packet-review --packet packet/settlement-packet.json --output packet/settlement-review.json --scope settlement --actor YOUR_NAME --reason 'Checked the final published resolution'
lma packet-settle --packet packet/settlement-packet.json --review packet/settlement-review.json --db data/experiment.sqlite
lma paper-replay --intent-id INTENT_ID --db data/experiment.sqlite
```

Settlement writes closing fills and a source/review receipt atomically. The same packet is idempotent; conflicting settlement packets are refused. A market recorded as settled cannot be opened again through the execution service. Existing historical-file sandbox settlement remains a local simulation facility.

Run the documented isolated demo to obtain a complete concrete packet example. Demo receipts are explicitly synthetic and are not human review of public market evidence. A public sample with missing fields remains blocked; that is a useful validation result, not permission to fabricate the fields. Raw public receipts remain local generated artifacts, not bundled market datasets.

The final settlement receipt URL must exactly match `resolution_source`. Its collection time must be at or after `resolved_at` and no later than the settled snapshot. When publication time is known, it must also be at or after resolution. A pre-resolution research article cannot substitute for the final source.


## Diagnosing blocked packets

`lma packet-check --packet packet/packet.json --review packet/research-review.json` validates an optional research review against the exact packet. `valid` means source integrity; `preflight_ready` means market/brief checks passed; `research_ready` additionally requires a matching research review and an actionable strategy. Neither is portfolio-risk or order approval. `checks`, `research_review`, `strategy`, and `blockers` expose each decision separately. `packet-check` remains a diagnostic command: exit 0 means a valid packet was inspected, not that an order is allowed.

Author the brief before `packet-review --scope research`; a source-only package cannot be stamped as a reviewed brief. An honest `observe` brief with no defensible probability may be reviewed, but remains non-actionable. `packet-prepare` preserves the strategy/risk rejection reasons and does not write equity baselines on refusal. The preparation service still checks portfolio risk; execution rechecks current risk and requires its separate per-intent approval.

For current Kalshi data, liquidity is conservative best-quote buy capacity in USD: the smaller of `YES ask × YES ask size` and `(1 − YES bid) × YES bid size`. It is not whole-book liquidity or traded volume. Unknown capacity stays unknown; genuinely small capacity stays blocked by the unchanged $100 default.


### Repeat the bounded public-data check

```bash
python scripts/collect_public_weather_packet.py --market-id KXHIGHNY-26NOV09-T57 --output data/reports/public-weather-NEW --allow-network
lma packet-check --packet data/reports/public-weather-NEW/packet.json
# Read source files and the observation brief before recording a research review.
lma packet-review --packet data/reports/public-weather-NEW/packet.json --output data/reports/public-weather-NEW/research-review.json --actor YOUR_REVIEWER_LABEL --reason YOUR_ACTUAL_REVIEW_FINDINGS
lma packet-check --packet data/reports/public-weather-NEW/packet.json --review data/reports/public-weather-NEW/research-review.json
lma packet-prepare --packet data/reports/public-weather-NEW/packet.json --review data/reports/public-weather-NEW/research-review.json --db data/reports/public-weather-NEW/paper.sqlite
```

Choose a current KXHIGHNY daily-high ticker; the dated example eventually closes. The collector makes six public read-only GETs: series rules, NWS forecast/observation, one bounded same-event market listing, order book, then the exact market. It refuses existing output directories and other market series. It saves checksummed JSON receipts and before/after-brief diagnostics. NWS generation/observation times are labeled explicitly; first-publication times are not claimed verified. Order-book data is archived for inspection, while snapshot depth comes entirely from the market response at its own retrieval time.

The generated brief is an **observation draft**, with null probability and explicit trade vetoes; it cannot produce an order even after source review. It never writes a review, approval or database. Reviewers must assess the actual sources and identify themselves honestly; an agent source review is not human order approval. Supplying a defensible calibrated estimate, sufficient depth and explicit order approval are separate prerequisites, not values to fabricate for a successful demo. A blocked preparation (exit 3) is the expected truthful result when those prerequisites are absent. No settlement is invented for an unresolved market.
