# DATA-RESEARCH-1 Historical Dataset Source Feasibility Audit

Date: 2026-06-05

Scope: research and documentation only. This audit does not implement
downloader code, source-specific adapters, network automation, Phase 8, broker
integrations, live trading, scheduler, daemon, autostart, strategy changes,
acceptance-gate changes, or profitability claims.

## Executive Summary

An acceptance-candidate dataset appears realistically obtainable, but the first
source should be chosen carefully.

The best technical first source is **Kalshi official market data**, because its
current documentation exposes:

- settled/historical market metadata through live and historical market tiers;
- candlesticks with `yes_bid`, `yes_ask`, `price`, `volume`, and open interest;
- trade history;
- structured market lifecycle and settlement fields.

This matters because Phase 7G acceptance requires real point-in-time YES bid
and YES ask. Kalshi candlesticks can support that if rows use a documented
candle boundary timestamp, for example `end_period_ts`, and the row stores
`yes_bid.close_dollars` and `yes_ask.close_dollars` as the point-in-time top of
book for that candle boundary. This is not the same as a full historical
orderbook snapshot, but it is enough for the Phase 7G bid/ask requirement if
validated conservatively.

The main Kalshi blocker is not technical. It is terms and permission review.
The [Kalshi Developer Agreement](https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf)
contains restrictions on collecting, caching, aggregating, or storing API data
except for permitted uses. Any acceptance-candidate dataset built from Kalshi
API data must record `terms_review=reviewed_public_research_local_only` only
after a human terms review or written permission supports the intended local
research use.

The best calibration-only source is **ImpliedData prediction-markets on
Hugging Face**, because it already provides public 1-hour OHLCV samples and a
large market catalog. It does not provide bid/ask or orderbook snapshots, so it
cannot support paper PnL or Strategy v2 acceptance as-is.

The best fallback for full historical orderbook data is a third-party
Polymarket orderbook archive such as
[Resolved Markets](https://resolvedmarkets.com/docs), but this introduces API
keys, vendor coverage, cost, and redistribution/license risks. It should not be
the first PR-DATA-3 path unless Kalshi terms or field availability blocks the
official Kalshi path.

## Acceptance Requirements Restated

For Phase 7G and PR-V2-4, an acceptance-candidate dataset must include at
minimum:

- 25 or more resolved binary markets;
- 250 or more point-in-time rows;
- 50 or more forecast candidates;
- enough accepted rows to produce 30 closed paper trades without forcing
  trades;
- 100% settlement coverage for scored markets;
- 95% or better evidence timestamp coverage;
- point-in-time `bid`, `ask`, `last_price`, and `implied_probability`;
- unambiguous settlement labels;
- source provenance and terms review;
- no future evidence leakage.

Close prices, last trade prices, OHLC prices, historical trades, current
orderbooks, and settlement labels are not interchangeable. In particular:

- current snapshots show only the market state at query time;
- historical prices show historical probability or trade/candle values;
- historical trades show executions, not resting liquidity;
- historical orderbooks show resting bid/ask/depth at a past timestamp;
- settlement labels show the outcome and must be withheld from forecast-time
  evidence.

## Sources Reviewed

Sources and primary public materials checked:

- Kalshi:
  [Historical Data](https://docs.kalshi.com/getting_started/historical_data),
  [Get Market Candlesticks](https://docs.kalshi.com/api-reference/market/get-market-candlesticks),
  [Batch Get Market Candlesticks](https://docs.kalshi.com/api-reference/market/batch-get-market-candlesticks),
  [Get Markets](https://docs.kalshi.com/api-reference/market/get-markets),
  [Orderbook Responses](https://docs.kalshi.com/getting_started/orderbook_responses),
  [Market Lifecycle](https://docs.kalshi.com/getting_started/market_lifecycle),
  [Market Settlement](https://docs.kalshi.com/getting_started/market_settlement),
  [Developer Agreement](https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf).
- Polymarket:
  [API Introduction](https://docs.polymarket.com/api-reference),
  [Gamma API Overview](https://docs.polymarket.com/developers/gamma-markets-api/overview),
  [Orderbook and Price History](https://docs.polymarket.com/trading/orderbook),
  [Geographic Restrictions](https://docs.polymarket.com/api-reference/geoblock).
- ImpliedData:
  [Prediction Markets Dataset](https://huggingface.co/datasets/ImpliedData/prediction-markets).
- Other relevant public/commercial sources:
  [Resolved Markets API](https://resolvedmarkets.com/docs),
  [Resolved Markets FAQ](https://resolvedmarkets.com/faq),
  [Metaculus API](https://www.metaculus.com/api/),
  [Metaculus API changes](https://www.metaculus.com/notebooks/42554/changes-to-the-metaculus-api/).

## Kalshi

### What Data Exists

Kalshi is the strongest first-party acceptance candidate.

Available data includes:

- settled market discovery through `GET /markets` and historical markets;
- market timestamps such as open, close, expected expiration, and settlement;
- settlement fields including result and settlement timestamp in market
  records;
- candlesticks at 1 minute, 1 hour, or 1 day intervals;
- candlestick fields for `yes_bid`, `yes_ask`, `price`, `volume_fp`, and
  `open_interest_fp`;
- trade records with market ticker, YES/NO trade price, count, and timestamp;
- current orderbook data with YES and NO bid arrays.

Kalshi's historical data documentation says data is partitioned into live and
historical tiers. Older settled markets and their candlesticks move to
historical endpoints. The current target live window is documented as about
three months, with cutoffs exposed through `GET /historical/cutoff`.

### Current Snapshots

Current market records include current YES bid, YES ask, NO bid, NO ask, last
price, volume, liquidity, and settlement/rule metadata. Current orderbook
responses expose the current bids for YES and NO.

Current snapshots are useful for live monitoring but cannot reconstruct past
states unless they were captured at the time. They are not sufficient by
themselves for this historical dataset.

### Historical Prices

Kalshi candlesticks are the key discovery. The documented candle response
includes:

- `end_period_ts`;
- `yes_bid.open_dollars`, `low_dollars`, `high_dollars`, `close_dollars`;
- `yes_ask.open_dollars`, `low_dollars`, `high_dollars`, `close_dollars`;
- `price.open_dollars`, `low_dollars`, `high_dollars`, `close_dollars`,
  `mean_dollars`, `previous_dollars`, `min_dollars`, `max_dollars`;
- `volume_fp`;
- `open_interest_fp`.

For Phase 7G acceptance, use a conservative point-in-time rule:

- row `timestamp` = candle `end_period_ts`;
- row `bid` = `yes_bid.close_dollars`;
- row `ask` = `yes_ask.close_dollars`;
- row `last_price` = `price.close_dollars` or the latest trade at or before
  the candle end when available;
- row `implied_probability` = midpoint of bid/ask when both exist.

Do not use high/low/open values as executable point-in-time quotes unless the
row timestamp explicitly represents that boundary.

### Historical Bid/Ask

Historical bid and ask appear available at candle resolution. This is the
reason Kalshi is now upgraded from "possible but uncertain" to "technically
viable".

This is L1 bid/ask history, not full L2 orderbook history. It should be marked
with a provenance note such as `quote_source=kalshi_candlestick_close_bid_ask`.

### Historical Orderbooks

First-party public docs expose current orderbook data. They do not show a
first-party historical endpoint that returns full depth-of-book snapshots for
past timestamps.

This is acceptable for Phase 7G only because the acceptance schema requires
top-of-book bid/ask, not full book depth. It is not enough for richer execution
simulation or slippage modeling.

### Historical Trades

Kalshi exposes trade history through live and historical trade endpoints. Trades
can provide `last_price`, volume checks, and activity filters, but trades are
not substitutes for bid/ask.

### Settlement And Outcomes

Kalshi has strong settlement metadata. Market lifecycle docs describe statuses
from active through finalized, and market records expose `result` and
`settlement_ts`. Settlement is still not evidence. It must be stored in the
nested settlement object and withheld from forecast-time evidence.

### Evidence Metadata

Kalshi does not provide row-level external evidence metadata for Strategy v2.
Evidence must be curated separately from market rules, official resolution
sources, news archives, and primary data releases. Every evidence item needs
`published_at` and `retrieved_at`.

### Source Provenance

Source provenance is feasible:

- endpoint URL and parameters;
- market ticker and series ticker;
- candle timestamp and interval;
- retrieval/export timestamp;
- raw response checksum;
- transform version;
- terms review status.

### Scale Feasibility

Likely sufficient. The settled-market filters, historical market tier, and
batch candlestick endpoint should support far more than 25 resolved markets and
250 rows if terms allow the local export. Candidate selection should start with
35 to 50 markets and 10 to 20 pre-resolution candles per market.

### Difficulty

Medium. The hard parts are market selection, avoiding multivariate/scalar
markets, preserving timestamp semantics, evidence curation, and terms review.

### Legal And Terms Considerations

High. Kalshi's developer agreement restricts storing or aggregating API data
except under permitted uses. Before building an acceptance dataset, a human
must complete a terms review and decide whether local research storage is
allowed, whether written permission is needed, or whether the dataset must
remain manual/private and unshared.

### Viability

- Acceptance-candidate viability: **Yes, technically realistic, terms-gated**.
- Calibration-only viability: **Yes**.

## Polymarket

### What Data Exists

Polymarket has excellent public market discovery and current CLOB data, but
official public APIs are weaker than Kalshi for first-party historical bid/ask.

Available data includes:

- Gamma market and event metadata;
- market outcomes and current outcome prices;
- public CLOB current orderbook, current price, midpoint, spread, and last
  trade price;
- price history points for a token;
- real-time WebSocket market channel with book, price changes, last trade,
  best bid/ask, and market resolution events.

The official API introduction states that Gamma and Data APIs are public, and
that CLOB includes public endpoints for orderbook and prices while trading
endpoints require authentication.

### Current Snapshots

The CLOB orderbook endpoint returns current bids and asks for a token, including
top-of-book and depth. Current `price`, `midpoint`, and `spread` endpoints are
also available.

Current snapshots cannot be used as historical rows unless captured at the row
timestamp.

### Historical Prices

The `prices-history` endpoint returns `{t, p}` style historical price points for
token IDs. This is useful for calibration, but the documented price history is
not a historical bid/ask archive.

### Historical Bid/Ask

Official Polymarket docs do not show a public first-party historical bid/ask
endpoint. The real-time WebSocket has `best_bid_ask` events, but those only
help if the project captures them prospectively.

Historical bid/ask is available only through prior local capture or third-party
archives.

### Historical Orderbooks

Official Polymarket APIs expose current orderbooks and live WebSocket book
updates. They do not appear to provide first-party historical orderbook
snapshots.

Third-party vendors such as Resolved Markets fill this gap by storing historical
Polymarket orderbook snapshots.

### Historical Trades

Trade data exists in public or authenticated surfaces depending on endpoint and
use case, and on-chain fills can be reconstructed to some extent. Trades are
useful for last price and volume, but they are not resting bid/ask.

### Settlement And Outcomes

Gamma metadata and live market resolution events can support settlement labels,
but every market still needs audit. Multi-outcome, negative-risk, canceled, and
ambiguous markets must be excluded unless represented as unambiguous binary
YES/NO rows.

### Evidence Metadata

Not provided at row level. Evidence must be curated separately.

### Source Provenance

Source provenance is feasible for market metadata and price history:

- Gamma event/market IDs;
- token IDs;
- condition IDs;
- CLOB endpoint parameters;
- retrieval/export timestamp;
- raw checksums;
- terms/geographic review.

### Scale Feasibility

Strong for calibration-only. Polymarket has broad market coverage and price
history. Official public APIs alone are not sufficient for acceptance because
historical bid/ask is missing.

### Difficulty

Medium for calibration-only, high for acceptance. Acceptance requires a
third-party orderbook archive, prior local capture, or another reliable
historical bid/ask source.

### Legal And Terms Considerations

Medium to high. Market data endpoints are public, but order placement is
geographically restricted, including the United States according to current
Polymarket documentation. This project must remain read-only and must not use
trading, bridge, wallet, geoblock bypass, private profile, or authenticated
order endpoints. Terms review is required before storing or redistributing
exports.

### Viability

- Acceptance-candidate viability from official API only: **No**.
- Acceptance-candidate viability with third-party historical orderbook archive:
  **Possible, vendor/terms-gated**.
- Calibration-only viability: **Yes**.

## ImpliedData Prediction-Markets Dataset

### What Data Exists

The public Hugging Face dataset provides:

- `markets_metadata.parquet`, a large market catalog with platform, status,
  dates, and resolution fields;
- `polymarket_ohlcv_1h_sample.parquet`, top Polymarket markets by volume for
  recent history;
- `manifold_ohlcv_1h_sample.parquet`, top Manifold markets by volume for
  recent history.

The dataset page lists 1-hour OHLCV rows with UTC candle timestamps, open, high,
low, close, volume, and trade count. It also notes that the public release
contains no Kalshi price or trade data.

### Current Snapshots

Not applicable. This is a static dataset.

### Historical Prices

Yes. The public files provide 1-hour OHLCV implied-probability candles.

### Historical Bid/Ask

No. The public dataset does not expose bid and ask fields.

### Historical Orderbooks

No. The public dataset does not expose orderbook depth.

### Historical Trades

The public sample provides aggregated OHLCV and trade count. The dataset page
states that full trade history and intraday candles are available through the
paid ImpliedData product, but the public sample is not a trade-level archive.

### Settlement And Outcomes

The metadata file includes status and resolution fields. This should be
audited because `resolution` can be YES/NO or numeric, and non-binary rows must
be excluded from Phase 7G acceptance-style scoring.

### Evidence Metadata

No. Evidence must be curated separately.

### Source Provenance

Good for a public dataset import:

- Hugging Face dataset revision or file hash;
- file name;
- row index and market ID;
- platform;
- transform version;
- research-only license note;
- underlying platform terms note.

### Scale Feasibility

Strong for calibration-only. The public page reports a large market catalog,
about 80K Polymarket OHLCV sample rows, about 50K Manifold OHLCV sample rows,
and hundreds of thousands of rows overall.

The public sample likely has enough rows for 250+ point-in-time rows and 50+
forecast candidates, but the 25+ resolved binary market requirement must be
checked by joining OHLCV rows to metadata and filtering to resolved binary
markets.

### Difficulty

Low for calibration-only. Medium for acceptance-style settlement/evidence
augmentation. Not viable for paper PnL acceptance without external bid/ask.

### Legal And Terms Considerations

Medium. The Hugging Face dataset says it is made available for research
purposes and that underlying market data remains subject to platform terms. The
project should avoid redistribution and store the dataset as local research
input only.

### Viability

- Acceptance-candidate viability: **No, missing bid/ask**.
- Calibration-only viability: **Yes, best fast path**.

## Resolved Markets And Similar Historical Orderbook Vendors

This section covers Resolved Markets as the clearest public-facing example of a
third-party historical orderbook source. Similar vendors found during the audit
include PolymarketData and Probalytics.

### What Data Exists

Resolved Markets documents:

- historical Polymarket orderbook snapshots;
- full bid/ask depth arrays;
- best bid/ask, mid price, spread, depth totals, and sequence metadata;
- event/capture timestamps;
- REST, WebSocket, CLI, and MCP access;
- free and paid tiers.

This is exactly the type of historical microstructure data that official
Polymarket APIs do not expose.

### Current Snapshots

Yes. The API can return live/current orderbooks for tracked markets.

### Historical Prices

Yes, via mid/price fields derived from stored snapshots.

### Historical Bid/Ask

Yes. This is the main value of the source.

### Historical Orderbooks

Yes. This is the main value of the source.

### Historical Trades

The FAQ says the service captures orderbook snapshots and trades. Trade fields
would need schema inspection before use.

### Settlement And Outcomes

Not enough on its own. Settlement labels should be joined from Polymarket Gamma
metadata or another settlement source. Vendor claims should not be treated as
the only settlement source without audit.

### Evidence Metadata

No. Evidence still must be curated separately.

### Source Provenance

Feasible, but vendor-specific:

- vendor source name and plan/tier;
- API endpoint and query parameters;
- capture timestamp and Polymarket event timestamp;
- raw checksum;
- export timestamp;
- license/terms review.

### Scale Feasibility

Likely sufficient if full-history access is available. Coverage is vendor and
plan dependent. Free tiers may be too narrow or too recent for 25 resolved
markets.

### Difficulty

Medium to high. Technically attractive, but it adds an API key, vendor contract,
pricing, retention, coverage, and reproducibility risk.

### Legal And Terms Considerations

High. This is a third-party archive of platform data. Use requires vendor terms
review and may require paid access or explicit export permission. Do not
commit API keys, account data, or vendor downloads unless licensing allows.

### Viability

- Acceptance-candidate viability: **Possible, vendor/terms-gated**.
- Calibration-only viability: **Yes**.

## Manifold And Metaculus Notes

Manifold appears in the ImpliedData dataset and has public API/documentation
surfaces. It is useful for calibration diagnostics, especially as a social or
play-money prediction venue, but Manifold does not provide a CLOB-style
bid/ask/orderbook history suitable for paper PnL acceptance.

Metaculus is a high-quality forecasting platform, but it is not a prediction
market orderbook source. Current API documentation describes limited access to
community predictions and resolution values, with broader data available by
request. It is useful as a calibration or forecasting benchmark source, not a
Phase 7G acceptance-candidate market dataset.

## Feasibility Matrix

| Source | Historical Prices | Historical Bid | Historical Ask | Settlement | Point-in-Time Reconstructable | Acceptance Candidate Possible | Calibration Only Possible | Effort | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Kalshi official market data | Yes, candlesticks and trades | Yes, candle `yes_bid` OHLC | Yes, candle `yes_ask` OHLC | Yes, market result/status/settlement fields | Yes at candle boundaries; not full L2 orderbook | Yes, technically realistic, terms-gated | Yes | Medium | Terms/caching restrictions; evidence curation; candle boundary semantics; category concentration |
| Polymarket official public APIs | Yes, `prices-history`, trades/price surfaces | Current only, not historical | Current only, not historical | Partial via Gamma/resolution metadata, needs audit | Price history yes; bid/ask no unless previously captured | No from official API alone | Yes | Medium | Missing historical bid/ask; geoblock/trading restrictions; multi-outcome markets; evidence curation |
| ImpliedData public HF dataset | Yes, 1-hour OHLCV samples | No | No | Metadata includes status/resolution, needs audit | Yes for OHLCV candles only | No | Yes, strongest fast path | Low | Research-only terms; no bid/ask; sample coverage; binary filtering needed |
| Resolved Markets or similar orderbook vendor | Yes | Yes | Yes | Needs Polymarket join/audit | Yes, high-frequency snapshots | Possible, vendor/terms-gated | Yes | Medium-high | API key/payment; vendor coverage; export rights; third-party provenance |
| Manifold direct/public data | Yes through bets/probability history or ImpliedData | No CLOB bid | No CLOB ask | Yes for resolved markets | Probability history yes; orderbook no | No | Yes | Low-medium | Play-money economics; no paper PnL bid/ask; API/schema drift |
| Metaculus | Forecast history/requested data only | No | No | Yes for questions with resolution access | Forecast history possible, market microstructure no | No | Possible benchmark only | Medium | Not a market; API access limits; no bid/ask/orderbook |

## Recommendation

### 1. Best Source For First Acceptance-Candidate Dataset

Use **Kalshi official market data**, specifically settled binary markets plus
1-minute or 1-hour candlesticks with documented `yes_bid` and `yes_ask` fields.

Recommended construction rule:

- choose 35 to 50 settled binary markets;
- sample 10 to 20 candle boundaries before close/resolution per market;
- use candle close bid/ask at `end_period_ts`;
- join market result and settlement timestamp from market metadata;
- curate independent evidence for every row;
- run PR-DATA-1 validation before any Strategy v2 evaluation;
- label the dataset acceptance-candidate only after terms review passes.

### 2. Best Source For Calibration-Only Dataset

Use **ImpliedData prediction-markets** for a fast calibration-only dataset.

It has enough OHLCV-style probability history to exercise calibration and
forecast-quality diagnostics, but it lacks bid/ask and must be blocked from
paper PnL and Strategy v2 acceptance.

### 3. Fastest Path

Fastest honest path:

1. Manually download or locally stage the ImpliedData public files.
2. Convert a resolved binary subset into
   `calibration_only_last_price`.
3. Use PR-DATA-1 validation to prove the dataset is calibration-only and cannot
   support paper PnL.

Fastest acceptance path:

1. Terms-review Kalshi API/storage use.
2. Manually export a small Kalshi settled-market sample.
3. Convert using PR-DATA-2 or a future local Kalshi export adapter.
4. Validate bid/ask, settlement, evidence timestamps, and provenance.

### 4. Most Robust Path

Most robust acceptance path:

1. Build a Kalshi official-data acceptance candidate from candlestick bid/ask.
2. Keep all raw public export files local with hashes and manifests.
3. Add manual evidence curation and settlement audit.
4. Use a third-party historical orderbook archive only as an optional
   cross-check or future richer execution dataset, not as the first dependency.

### 5. Is PR-DATA-3 Justified Now?

Yes, with a narrower scope than a downloader:

- PR-DATA-3 should be a **Kalshi local public-export adapter** that reads
  manually staged local Kalshi export files and converts them into Phase 7G
  JSONL.
- It should not call Kalshi APIs itself.
- It should require an explicit terms-review field in the input manifest.
- It should downgrade to `calibration_only_last_price` if bid/ask candle fields
  are missing, null, or semantically untrusted.

This keeps the next PR useful while respecting the current no-downloader and
local-only constraints.

## Acceptance-Candidate Realism

Acceptance-candidate data is realistic, not guaranteed.

Technically realistic because:

- Kalshi has structured settled markets;
- Kalshi candle rows expose historical YES bid and YES ask;
- market result and settlement timestamps appear structured;
- the dataset scale target is modest relative to available market count.

Still blocked until:

- Kalshi terms review allows local research storage/export;
- a pilot sample proves candle bid/ask fields are populated for enough settled
  binary markets;
- evidence curation can reach 95% timestamp coverage;
- all rows pass PR-DATA-1 validation and PR-V2-4 sample-size gates.

## Safety Notes

This audit recommends no live trading path. Future data work must remain:

- local-only after export;
- file-only until a separate approved source adapter PR;
- no private/authenticated source material in committed files;
- no broker API;
- no live orders;
- no scheduler, daemon, or autostart;
- no direct LLM-to-order path;
- no strategy or acceptance-gate changes;
- no profitability claims.
