# Local Market Agent Phase 7 Plan

## Phase Name

Phase 7 - Paper Trading Continuous Operations

## Objective

Build a paper-only continuous operation framework on top of the existing Local
Market Agent MVP.

This phase must NOT introduce:

- Real brokerage integration
- Real money trading
- Automatic live order execution
- API keys for brokers

This phase only supports:

- Paper portfolio
- Simulated orders
- Simulated fills
- Risk management
- Daily reports
- Continuous operation workflow

## Architecture

The Phase 7 architecture adds an operational layer above the existing
signal-generation pipeline.

Daily flow:

```text
Market Data
    |
Market Scan
    |
Signal Engine
    |
Risk Gate
    |
Paper Portfolio
    |
Daily Report
```

## Safety Requirements

The system must remain paper-only.

Any code path that could submit real orders must be explicitly out of scope.

Future broker integrations are Phase 8 work and must not be implemented during
Phase 7.

## Risk Gates

### Gate 1 - Market Data Freshness

Reject execution if market data is stale.

Example:

- Maximum data age: configurable
- Default target: 5 minutes

### Gate 2 - Daily New Position Limit

Limit the number of new positions opened per day.

Example:

- Default: 3

### Gate 3 - Position Size Limit

Limit position size as a percentage of portfolio value.

Example:

- Default: 10%

### Gate 4 - Portfolio Exposure Limit

Limit total exposure.

Example:

- Default: 50%

### Gate 5 - Drawdown Circuit Breaker

Block new positions when drawdown exceeds threshold.

Example:

- Daily drawdown > 3%

### Gate 6 - Consecutive Loss Circuit Breaker

Pause new positions after a configurable number of consecutive losses.

Example:

- 5 consecutive losses
- 48 hour cooldown

### Gate 7 - Manual Approval Mode

Support a configuration option requiring manual approval before paper orders are
accepted.

Example:

```toml
require_manual_approval = true
```

Signals may be generated but not executed automatically.

## Daily Operational Runbook

### Step 1

Refresh market data.

Validate freshness and completeness.

### Step 2

Run market scan.

Generate candidate symbols.

### Step 3

Run signal generation.

Produce BUY / SELL / HOLD recommendations.

### Step 4

Run risk gates.

Reject signals violating risk constraints.

### Step 5

Generate paper trades.

Update simulated portfolio state.

### Step 6

Generate daily report.

## Monitoring Metrics

### Portfolio Metrics

- Daily PnL
- Weekly PnL
- Monthly PnL
- Equity Curve

### Risk Metrics

- Max Drawdown
- Exposure
- Position Count

### Strategy Metrics

- Win Rate
- Profit Factor
- Sharpe Ratio

### Operational Metrics

- Daily Run Success Rate
- Failed Runs
- Skipped Runs
- Report Generation Success

## Output Structure

```text
data/
paper_trades/
reports/
metrics/
logs/
```

## Implementation Strategy

Implementation must be split into multiple small PRs.

No large multi-feature PRs are allowed.

Recommended sequence:

- PR-1 Paper Portfolio Engine
- PR-2 Risk Gate Framework
- PR-3 Daily Report Generator
- PR-4 Continuous Runner
- PR-5 Operations Dashboard

## Phase Completion Criteria

The phase is considered complete only when:

- Paper portfolio operational
- Risk gates operational
- Daily reports generated
- Continuous runs functional
- Audit trail preserved
- Historical replay possible
- No real trading capability introduced

After completion, the system should be capable of running continuously in paper
mode for at least 30 days.
