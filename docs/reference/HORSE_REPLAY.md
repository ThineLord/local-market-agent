# Hong Kong racing research and historical replay

[English](HORSE_REPLAY.md) · [简体中文](HORSE_REPLAY.zh-CN.md)

This module runs alongside existing public-market research. It never creates trading signals, approvals, paper orders or live bets, and never opens a trading database. User ticket histories remain local ignored files. Public examples are invented.

## Historical arithmetic

```sh
PYTHONPATH=src python scripts/horse_replay.py collect --date YYYY-MM-DD --course ST --races 9 --output data/horse/official --allow-network
PYTHONPATH=src python scripts/horse_replay.py replay --record data/horse/history.json --official data/horse/official --output data/horse/replay
```

Collection is an explicit, bounded read-only request: one official results page per race plus full declarations. It preserves raw responses, exact URLs, actual retrieval times and SHA-256 receipts; offline replay checks those receipts and meeting/race/horse identities. Output directories must be new. Retrospective archives are **not point-in-time evidence**, even when the URL contains `prerace`. Unavailable or changed markup fails closed. No odds are reconstructed from results.

The `HistoricalRecord` schema in `src/local_market_agent/horse_racing/models.py` requires explicit sequential race coverage. `NOT_PLACED` means no reported actual ticket, not a failed bet or a reconstructed model NO BET. Recommendations and original predictions remain UNKNOWN. Reported actual tickets are not independently verified receipts.

Three money tracks stay separate: user-reported provisional gross returns, official rule-based entitlements, and document-referenced redeemed cash. Missing cash evidence is UNKNOWN, never zero. Official dividends are gross returns per HK$10 unit, including principal. Only whole units and straightforward numeric placings with consistent WIN/PLACE pool tables are automatically supported. Withdrawals, replacements, dead heats, refunds and ambiguous settlement require manual review. Official winning combinations determine PLACE qualification; a missing dividend never implies a loss unless the source is supported and the field matches.

Metrics include tickets and bet races, separate WIN/PLACE hit rates, stake, gross return, net profit, stake ROI, bankroll return and race-close entitlement drawdown. A pool hit rate is the whole-pool summary and is published only when every ticket in that pool has a supported outcome; settled win counts stay visible when the summary is unknown. This curve is not an intrarace cash curve. If a later race return is missing, meeting balance, profit and drawdown stay unknown, the curve keeps the balances already settled, and `stopped_at_race` marks the first gap. Missing races are not filled with zero and the prefix is not a finished meeting. Historical risk-budget adherence stays UNKNOWN without a separately evidenced precommitted cap. Fixed stakes alone do not prove absence of chasing. One meeting and correlated tickets cannot establish stable predictive advantage. No historical probability calibration is reported without original probabilities.

## Source rules

[HKJC results](https://racing.hkjc.com/en-us/local/information/resultsall) and [HKJC Horse Race Rules illustrations](https://www.hkjc.com/english/betting/template_betting_rule_files/pdf/Horse_Race_Rules_Illustration_Eng_20260330.pdf) are the reference sources. The supported HKJC declaration archive currently returns HTML despite its `.xml.zip` suffix; other formats are rejected rather than guessed. PLACE generally pays three places for seven or more declared starters at commencement of betting, two for four to six. Post-race finisher count is not a substitute for that rule.

## Original checkpoint import

Place original files in a local directory with `research.json` matching `ResearchInput` in `horse_racing/research.py`. It records the meeting and race, T10/T3 decision times, the schedule known at each time, full horse IDs, draw/weight/jockey evidence, prior form, and separately observed WIN/PLACE indicative **gross decimal** odds. `null` means UNKNOWN; do not fill absent odds, probabilities or historical reasons. Input schemas reject current-race results/final dividends and unknown fields. Sources include actual capture time, claimed availability time, file path and SHA-256. Import time is recorded separately.

A separate `availability-review.json` may bind the exact input digest and every source digest to a named reviewer, actual review time, rationale and referenced archived timing evidence. A URL, self-filled timestamp or boolean alone is not accepted as reviewed availability. Hash binding and human review do not cryptographically prove historical availability or make a transcript independently correct. Retrospectively retrieved archives cannot replace original snapshots.

```sh
PYTHONPATH=src python scripts/horse_replay.py research --input data/horse/research --output data/horse/research-audit
PYTHONPATH=src python scripts/horse_replay.py replay --record data/horse/user-history.json --official data/horse/official --research data/horse/research --output data/horse/replay-with-research
python ui/server.py --horse-workspace data/horse --port 8510
```

The dashboard workspace uses `user-history.json`, optional `official/`, and optional `research/`. It recomputes totals from inputs and verified official sources on read, ignoring cached derived reports. Existing market pages and databases are unchanged. Keep this directory under ignored local `data/`.

T10 and T3 have explicit ±60-second windows around the then-known scheduled start; quotes must be at most 60 seconds old and already captured. These are input-quality checks, not permission to lower existing trading risk thresholds. Missing checkpoints, unknown facts, future form, stale quotes, source availability, changed identities/schedules and unproven budget freeze produce separate blocking codes. All runners are compared; form observations are descriptive counts at matching course/surface/distance, not causal rankings. Budget must be fixed before the first checkpoint, capped by bankroll, with HK$10 fixed units and a source record. No chasing or dynamic stake sizing is implemented.

**This version has no validated racing probability model, so every research decision is NO_BET.** An imported original probability and its rationale are displayed separately from the missing validated estimate. Illustrative `p × lower gross odds − 1` is an unvalidated scenario, not a betting recommendation; parimutuel odds are indicative rather than executable locked returns. WIN/PLACE remain independent and no probability is inferred from final payouts. Calibration stays UNKNOWN until a sufficiently supported original probability series and a separately specified evaluation protocol exist. This is a data/replay foundation, not a profitable algorithm or an execution adapter.

`tests/test_horse_research.py` contains a complete invented two-checkpoint example and failure cases; `data/fixtures/horse_research/` provides a runnable synthetic import. The demo remains NO_BET and is explicitly synthetic.
