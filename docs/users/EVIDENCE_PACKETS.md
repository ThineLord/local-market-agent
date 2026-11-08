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
