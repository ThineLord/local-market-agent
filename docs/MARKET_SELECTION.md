# Market Selection

Initial focus is public, observable markets with deterministic offline fixtures.

## Included

- Prediction market demo fixture.
- Public/read-only prediction market metadata where feasible.
- Historical equity or crypto OHLCV through yfinance.
- SEC EDGAR filing metadata.
- GDELT news and evidence search.

## Excluded

- Private trading APIs.
- Markets requiring secret order permissions.
- Leveraged, derivative, short, or withdrawal flows.
- Any flow where an LLM can place or route an order.
