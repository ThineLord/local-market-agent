# Kalshi Sprint 2 Evidence-Friendly Collection Result

Date: 2026-06-07

## Summary

DATA-COLLECT-2 added a temporary local collector at
`scripts/local_only/collect_kalshi_sprint2_evidence_friendly.py`. The helper
stays outside `src/local_market_agent`, uses public read-only Kalshi endpoints,
generates only human-review evidence candidates, and keeps `evidence.jsonl`
empty.

Real collection was attempted for:

`data/source_exports/kalshi/kalshi_sprint2_evidence_friendly_20260606/`

The final run succeeded technically, but the resulting pilot is smaller than
the 10-market / 100-200-candle target:

- Markets selected: 4
- Candle rows collected: 20
- Evidence candidates generated: 8
- Timestamp status distribution: `missing=8`
- Categories: `major_sports`
- Approved evidence rows: 0
- `terms_review`: `pending_review`

## What Was Implemented

- Offline-testable evidence-friendly market scoring.
- Category classification for macro, Fed policy, weather, election/public
  policy, company events, major sports, public events, and unknown markets.
- Hard exclusion for BTC/ETH ultra-short price markets.
- Hard exclusion for low-info tennis and small college baseball style markets.
- Hard exclusion for mention/transcript markets where evidence is likely final
  result/transcript evidence rather than forecast-time evidence.
- Public source seed generation for human-review evidence candidates.
- PR-DATA-3-shaped staged export files:
  - `source_manifest.json`
  - `markets.jsonl`
  - `candlesticks.jsonl`
  - empty `evidence.jsonl`
  - `evidence_candidates.jsonl`
  - `evidence_candidate_generation_report.md`
- Structured network failure diagnostics. If Kalshi public GET fails, the CLI
  returns non-zero and prints `network_status`, attempted endpoint families, and
  a rerun command without disabling TLS verification.

## Selection Criteria

The collector scores higher when market title/rules mention:

- CPI, PCE, unemployment, jobs, payrolls, GDP, retail sales, PPI, or other
  economic releases.
- Fed, FOMC, Federal Reserve, or rate decisions.
- Weather, NOAA, National Weather Service, hurricane, temperature, snow, rain,
  or tropical storm references.
- Elections, public policy events, official government sources, company
  filings, or major sports leagues/events.
- Official public source references in rules.
- Multi-day review windows, clear resolved binary outcomes, and usable rules.

The collector scores lower or excludes:

- BTC/ETH 15-minute or one-hour micro price markets.
- Small ITF/challenger-style tennis markets.
- Low-info college baseball/softball markets.
- Mention/transcript markets.
- Markets with missing rules or no strong public reference keyword.
- Markets without enough usable pre-settlement candlesticks.

## Network Status

Current final status: public Kalshi discovery and candlestick requests worked
well enough to write a local ignored export.

Endpoint families attempted:

- `https://external-api.kalshi.com/trade-api/v2/markets`
- `https://external-api.kalshi.com/trade-api/v2/historical/markets`
- `https://external-api.kalshi.com/trade-api/v2/markets/candlesticks`
- `https://external-api.kalshi.com/trade-api/v2/historical/markets/{ticker}/candlesticks`

Earlier interrupted runs saw TLS/network failures against the same public
endpoint family. The resumed implementation now records those failures as
structured diagnostics such as `network_blocked_or_tls_failure` instead of
requiring unsafe TLS verification changes.

No credentials, cookies, browser sessions, private endpoints, or authenticated
sources were used.

## Real Collection Result

Export id: `kalshi_sprint2_evidence_friendly_20260606`

Export directory:

`data/source_exports/kalshi/kalshi_sprint2_evidence_friendly_20260606/`

Selected markets:

| Market | Category | Candles | Candidates |
|---|---:|---:|---:|
| `KXUCLTCORNERS-26APR07RMABMU-RMA5` | major_sports | 6 | 2 |
| `KXUCLTOTAL-26APR07RMABMU-5` | major_sports | 5 | 2 |
| `KXUCLTOTAL-26APR07RMABMU-6` | major_sports | 4 | 2 |
| `KXUCLTCORNERS-26APR07RMABMU-BMU6` | major_sports | 5 | 2 |

Markets discovered: 11,639

Markets rejected by hard heuristics: 4,285

Final categories: `major_sports`

Candidate statuses:

- Top-level `reviewer_status=needs_more_review`: 8
- Metadata `reviewer_status=needs_human_review`: 8
- Approved candidates: 0

Timestamp status distribution:

- `missing`: 8

## Sprint 2 vs Sprint 1

Sprint 2 improves the market selection logic over Sprint 1 by avoiding BTC
15-minute markets, ITF tennis, placeholder template rows, and mention/transcript
markets after the resumed fixes.

Sprint 2 does not yet solve the evidence timestamp blocker. The final generated
candidates still have `timestamp_status=missing`, so timestamp coverage remains
0% until a human reviewer finds and verifies public timestamped evidence.

The final pilot also did not meet the target of 10 markets, 100-200 candle rows,
or 3 categories in the current public endpoint result set after the stricter
heuristics were applied.

## Expected Review Burden

The current export contains 8 candidates across 4 markets. Human review should
be light, but approval is unlikely without replacing or supplementing the
generated candidates with timestamp-safe public pages.

## Review UI Command

```bash
PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \
  --export-id kalshi_sprint2_evidence_friendly_20260606 \
  --export-root data/source_exports/kalshi \
  --candidates-file evidence_candidates.jsonl \
  --overwrite
```

## Rerun Command

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_sprint2_evidence_friendly.py \
  --export-id kalshi_sprint2_evidence_friendly_20260606 \
  --max-markets 10 \
  --rows-per-market 12 \
  --max-candle-market-attempts 60
```

If the Kalshi public endpoint fails again, rerun the same command after network
or VPN recovery. The script will report a structured network diagnostic rather
than disabling TLS verification.

## Remaining Blockers

- Only 4 markets and 20 candles were collected after stricter filtering.
- Candidate timestamp coverage is still 0%.
- No evidence has been approved.
- `terms_review` remains `pending_review`.
- The export is not an acceptance dataset and should remain local/ignored until
  human evidence and terms review are complete.

## Safety Notes

- No broker APIs, live trading, order, account, portfolio, or fill logic was
  added.
- No scheduler, daemon, autostart, Phase 8, strategy change, or acceptance-gate
  change was added.
- No automatic evidence approval was added.
- No source terms review was cleared or mutated.
- No profitability or Strategy v2 superiority claim is supported by this export.
