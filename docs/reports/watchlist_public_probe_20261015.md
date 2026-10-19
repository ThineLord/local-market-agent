# Public market watchlist probe — 2026-10-15

## Result

**The public snapshot → normalization → quality screen → saved report → dashboard
workflow works for this bounded sample. The independent research and decision
workflow remains incomplete.**

The unmodified `a37bb37e951f2da73eef0cfba03a3a145631df9f` application screened
9 real public markets at **2026-10-15 14:19:32 Hong Kong time**. All 9 snapshots
were fetched and parsed without a per-entry error. The result was **2
`needs_research`, 7 `blocked`, 0 research candidates, 0 orders**. The CLI exited 0.
The thresholds were not changed to obtain these results.

## Scope and selection

Two bounded discovery GETs returned HTTP 200:

- [Kalshi Get Markets](https://docs.kalshi.com/api-reference/market/get-markets):
  `https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100&mve_filter=exclude`
  returned 100 markets.
- [Polymarket List Markets](https://docs.polymarket.com/api-reference/markets/list-markets):
  `https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=50&order=liquidity&ascending=false`
  returned 50 markets.

Initial selection took 3 distinct events per source, ranked by reported cumulative
volume within the returned page, preserving source order for ties. The Kalshi
page consisted of newly listed electronic sports markets with zero reported
volume; the three selected Polymarket events were extreme-probability contracts
without a reported bid. This discovery heuristic therefore did not produce a
representative or broadly useful research universe.

Before running the screener, 3 controls were added from the already downloaded
Polymarket page: the first distinct events in its liquidity ordering with both
bid and ask within [0.05, 0.95]. They exercise quoted markets without removing the
original difficult inputs. This was selection for integration coverage, not a
random sample or a performance study. The full revised selection was saved
before the single CLI screening invocation.

The run performed 9 additional public market-detail GETs through the existing
adapters. There were 11 market-data requests in total, no retries, no orderbook
requests, and no authenticated API calls.

## Observed results

Bid/ask below are saved observations from this run, not current quotes.

| Source / ID | Market | Bid / ask | Result | Reason |
| --- | --- | --- | --- | --- |
| Kalshi `KXESOCCERGAME-26OCT150456HOMIMORD-TIE` | Everton (Homie) / Chelsea (Mordor): tie | 0.05 / 0.99 | blocked | Spread 0.94; liquidity absent |
| Kalshi `KXESOCCERGAME-26OCT150509MANTMORD-TIE` | Crystal Palace (Mantis) / Manchester City (Mordor): tie | 0.05 / 0.99 | blocked | Spread 0.94; liquidity absent |
| Kalshi `KXEBASKETBALLGAME-26OCT150412DAVIJAME-JAME` | Denver Nuggets (James) wins | 0.00 / 0.99 | blocked | Spread 0.99; liquidity absent |
| Polymarket `561251` | LeBron James wins 2028 presidential election | absent / 0.001 | blocked | Missing two-sided quote |
| Polymarket `559687` | Oprah Winfrey wins 2028 Democratic nomination | absent / 0.001 | blocked | Missing two-sided quote |
| Polymarket `561986` | Byron Donalds wins 2028 Republican nomination | absent / 0.002 | blocked | Missing two-sided quote |
| Polymarket `562828` | 2026 Democratic Senate and Democratic House | 0.62 / 0.63 | needs_research | Quality checks passed; no matching brief |
| Polymarket `562794` | Republican Senate control after 2026 midterms | 0.37 / 0.38 | needs_research | Quality checks passed; no matching brief |
| Polymarket `4212356` | Seahawks vs. Broncos | 0.56 / 0.57 | blocked | Outcome labels are `Seahawks` / `Broncos`, unsupported by the YES/NO-only gate |

The two `needs_research` markets reported liquidity of 2,982,091.5055 and
2,887,308.3832 respectively. These are source-provided aggregate metadata,
not measured executable depth. High reported liquidity did not rescue the
three contracts with a missing bid.

## What the run establishes

- Current public responses are compatible with both adapters for these nine
  inputs. All saved bid/ask values were independently compared with the cached
  source fields and matched exactly.
- Schema validation, normalized-snapshot hashes, status totals, and the
  no-execution report fields were checked for all nine rows. Raw inputs,
  selection records, reports, and verification receipts have a SHA-256 manifest.
- Missing quotes and liquidity were preserved instead of inferred. Unsupported
  outcome labels were rejected instead of relabeled.
- The dashboard displayed the real report with 9 markets, 2 awaiting research,
  and 7 blocked. Status filtering exposed the two quoted election markets.
- No research brief or forecast was manufactured, no LLM was called, and no
  order or execution approval was produced. Immediately after the CLI, existing
  database sizes and modification times matched the pre-run metadata. A later
  check after dashboard validation found one old database with the same size but
  an mtime difference of 95 nanoseconds; its cause was not established. The
  before/after receipts preserve that difference, so an unchanged-database claim
  for the entire session is not made. Bytewise identity was not checked: a
  checksum read of an old cloud-backed database stalled and was stopped.

## Remaining practical gaps

1. **Freshness remains unverified at the quote level.** `as_of` is generated at
   retrieval, so `snapshot_age` passes on recent downloads. Raw market update
   times are not exchange quote times and are not carried into the snapshot.
   A passing age check therefore does not establish an executable fresh quote.
2. **Kalshi metadata does not satisfy the current liquidity gate.** All three
   responses lacked the liquidity fields consumed by the adapter. Sizes were
   present, including a zero bid size in one case, but aggregate liquidity or
   depth was not derived. A future orderbook integration needs an explicit,
   source-specific depth metric; volume or quote size must not silently replace
   the existing liquidity threshold.
3. **Outcome semantics are narrow.** The sports control had two outcomes but
   was correctly rejected by the YES-first/NO-second contract. General two-outcome
   markets require explicit outcome/token mapping before strategy support.
4. **Polymarket close time is dropped.** All six raw responses had `endDate`,
   while normalized `Market.close_time` was null. Its `before_close` check could
   not verify that source timestamp. The tested markets had future end dates,
   so this did not alter this run's observed totals.
5. **Market discovery needs better research priorities.** Highest cumulative
   volume within a liquidity-ranked page selected several extreme longshots;
   the newest Kalshi page contained only zero-volume markets. Discovery should
   expose its coverage and ranking basis instead of treating these lists as a
   useful diversified universe.
6. **Research handoff is manual.** Neither source has an independent probability
   estimate or a brief bound to the exact downloaded snapshot. This run did not
   exercise Strategy v1 on real research, portfolio risk review, simulated fills,
   or profitability. The next bounded extension should first preserve source
   timestamps/close time and explicit quote-depth semantics, then prepare a
   timestamp-safe research brief for one of the two eligible election markets.

No runtime code or thresholds were modified during this probe. The negative
results above are preserved for follow-up rather than repaired during the run.

## Local artifacts and reproduction

Artifacts are intentionally ignored local data:

- Probe receipt/raw data/selection/verification:
  `data/reports/watchlist/public-probe-20261015-4f321e74/`
- Immutable screening outputs:
  `data/reports/watchlist/screen-15d9b692d739424aa8cdd3a26dcee5e7/report.json`
  and `report.md`.
- Dashboard copy: `data/reports/watchlist/latest.json`.

Exact command, with the temporary validation environment used in this workspace:

```bash
LMA_RAW_CACHE_DIR=data/reports/watchlist/public-probe-20261015-4f321e74/raw-cache \
PYTHONPYCACHEPREFIX=/tmp/lma-dashboard-pycache PYTHONPATH=src \
/tmp/lma-dashboard-venv/bin/python -m local_market_agent.cli watchlist-screen \
  --watchlist data/reports/watchlist/public-probe-20261015-4f321e74/watchlist.json \
  --allow-network --output-dir data/reports/watchlist
```

Running it again fetches new data and creates another report; it cannot reproduce
the exact original quotes. Preserve this run's dedicated raw cache and manifests
when comparing later runs.
