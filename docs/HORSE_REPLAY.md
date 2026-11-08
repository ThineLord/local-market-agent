# Hong Kong racing research and historical replay

This module runs alongside existing public-market research. It never creates trading signals, approvals, paper orders or live bets, and never opens a trading database. User ticket histories remain local ignored files. Public examples are invented.

## Historical arithmetic

```sh
PYTHONPATH=src python scripts/horse_replay.py collect --date YYYY-MM-DD --course ST --races 9 --output data/horse/official --allow-network
PYTHONPATH=src python scripts/horse_replay.py replay --record data/horse/history.json --official data/horse/official --output data/horse/replay
```

Collection is an explicit, bounded read-only request: one official results page per race plus full declarations. It preserves raw responses, exact URLs, actual retrieval times and SHA-256 receipts; offline replay checks those receipts and meeting/race/horse identities. Output directories must be new. Retrospective archives are **not point-in-time evidence**, even when the URL contains `prerace`. Unavailable or changed markup fails closed. No odds are reconstructed from results.

The `HistoricalRecord` schema in `src/local_market_agent/horse_racing/models.py` requires explicit sequential race coverage. `NOT_PLACED` means no reported actual ticket, not a failed bet or a reconstructed model NO BET. Recommendations and original predictions remain UNKNOWN. Reported actual tickets are not independently verified receipts.

Three money tracks stay separate: user-reported provisional gross returns, official rule-based entitlements, and document-referenced redeemed cash. Missing cash evidence is UNKNOWN, never zero. Official dividends are gross returns per HK$10 unit, including principal. Only whole units and straightforward numeric placings with consistent WIN/PLACE pool tables are automatically supported. Withdrawals, replacements, dead heats, refunds and ambiguous settlement require manual review. Official winning combinations determine PLACE qualification; a missing dividend never implies a loss unless the source is supported and the field matches.

Metrics include tickets and bet races, separate WIN/PLACE hit rates, stake, gross return, net profit, stake ROI, bankroll return and race-close entitlement drawdown. This curve is not an intrarace cash curve. Historical risk-budget adherence stays UNKNOWN without a separately evidenced precommitted cap. Fixed stakes alone do not prove absence of chasing. One meeting and correlated tickets cannot establish stable predictive advantage. No historical probability calibration is reported without original probabilities.

## Source rules

[HKJC results](https://racing.hkjc.com/en-us/local/information/resultsall) and [HKJC Horse Race Rules illustrations](https://www.hkjc.com/english/betting/template_betting_rule_files/pdf/Horse_Race_Rules_Illustration_Eng_20260330.pdf) are the reference sources. The supported HKJC declaration archive currently returns HTML despite its `.xml.zip` suffix; other formats are rejected rather than guessed. PLACE generally pays three places for seven or more declared starters at commencement of betting, two for four to six. Post-race finisher count is not a substitute for that rule.
