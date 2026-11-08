# Fixed NBA probability protocol

This is a custom, reproducible Elo baseline. It is not a reproduction of FiveThirtyEight, an LLM estimate, or a claim of profitability. Public prices are not model inputs. The independent reviewer examined the protocol before validation results were calculated.

## Frozen method

- Initial rating 1500; logistic scale 400; update K=20; home advantage 65; neutral sites receive no home advantage.
- Consecutive season ratings revert 25% toward 1500. A prediction is calculated before its own result can update ratings.
- Results enter the retrospective reconstruction at the start of the second UTC calendar day after the game's start date. This conservative lag avoids immediate same-day/cross-midnight feedback. It is not a historical publication timestamp.
- Warmup: seasons ending 2024 and 2025. Independent chronological scoring: season ending 2026. Current forward ratings: season ending 2027. No parameter search or tuning against the holdout or current market prices.
- Collect all 30 team schedule pages for each of the four seasons (120 endpoints, at most one retry each, four concurrent requests). Check exact URLs, hashes, retrieval times, team and per-event season identities. Deduplicate by game ID and require matching final scores in both team schedules. Exclude non-final games and non-standard competition types, including the NBA Cup final. Audit every historical team for 82 games and each historical season for 1,230 unique games.

## Predeclared validation requirements

At least 2,300 warmup and 1,100 holdout games plus complete historical-season coverage; Brier and logloss both better than the fixed warmup home-win-rate baseline; 97.5th percentile of the paired Brier difference below zero using 1,000 UTC-day block-bootstrap samples with seed 20261109; ten-bin ECE at most 0.05. These are project engineering gates, not universal scientific certification.

Report every bin's sample count, mean raw probability, observed frequency and Wilson frequency interval. Each game contributes once in home-team orientation. A bin frequency interval is not a confidence interval for a particular match's true probability.

For a current candidate, require at least 50 holdout examples in the raw home-probability bin. Stress the current raw home probability using the bin's residual calibration error under the same fixed UTC-day resampling, transform into the exact YES/NO buy direction, and subtract the actual configured simulated fill price plus fees. Require the lower 2.5th percentile net edge to clear the unchanged `max(min_edge, 2 × spread)` gate. Empty-bin bootstrap samples count as unsupported. The raw Elo probability remains unchanged; this is a residual-transfer stress diagnostic, not a refitted model independently validated on the same holdout.

`confidence` for this workflow is the bootstrap fraction clearing that net-edge gate, explicitly labelled **edge-support fraction**. It is not the probability of winning or a Bayesian confidence level. It never substitutes for the separate conservative-edge and validation gates. Any required check failure must retain an execution veto. Evidence quality measures completed, verified input prerequisites, not fabricated certainty.

## Reproduce

```bash
python scripts/nba_probability.py collect --output data/reports/nba-history-NEW --allow-network
python scripts/nba_probability.py validate --history data/reports/nba-history-NEW --output data/reports/nba-validation-NEW
```

Validation is offline and reconstructs predictions from the checksummed source files. Historical files were retrieved now; their corrected final scores are not a point-in-time historical archive. This does not establish historic trading performance or causal execution-time availability. Current new predictions are forward observations only if created before the explicitly matched game start.

ESPN's public schedule payloads supply scores; this endpoint is not a guaranteed stable developer contract. Top-level season labels can refer to the current year, so the loader validates each event's season instead. The algorithm ignores injuries, lineups, roster changes and bookmaker information. It does not perform parameter-sensitivity validation. Current input age and pregame identity/status must be checked separately by the packet workflow.

Reference: [FiveThirtyEight's original data README](https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/README.md) distinguishes pregame/postgame ratings and forecasts. The actual fixed formula and parameters for this project are defined in `src/local_market_agent/nba_probability.py` and recorded in each acquisition's `protocol.json` before its data collection starts.
