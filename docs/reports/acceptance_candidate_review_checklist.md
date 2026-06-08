# Acceptance Candidate Review Checklist

Scope: ACCEPT-2 documentation/checklist only. This checklist does not collect
data, approve evidence, build an acceptance dataset, implement a collector,
scrape sources, automate a browser, mutate source terms, change strategy logic,
change acceptance gates, start Phase 8, add broker/live/order/account,
portfolio/fill paths, add scheduler/daemon/autostart behavior, or make
profitability, paper-PnL, Strategy v2 superiority, acceptance-ready, or
live-readiness claims.

## Review Rule

Every shortlisted candidate must pass the checks below before it can be selected
for a future manual pilot. A pass here is only a pre-screening result. It is not
approved evidence, not an acceptance dataset, not an acceptance-gate pass, and
not permission to make paper-PnL, profitability, Strategy v2 superiority, or
live-readiness claims.

## Pass/Fail Checklist

| Check | Pass condition | Fail condition | Decision impact |
| --- | --- | --- | --- |
| Evidence timestamp before row | Each proposed forecast row has at least one evidence item with `published_at <= row.timestamp`. | Any proposed row lacks timestamp-safe forecast evidence. | Reject or narrow the row window. |
| Forecast-time evidence | Evidence was available before the forecast row and informs the market before outcome revelation. | Evidence is only a final result, settlement notice, or after-the-fact report. | Reject for forecast evidence. |
| Settlement source | Settlement source is public, rule-compatible, and identifies the final YES/NO outcome. | Settlement source is private, ambiguous, disputed, or mismatched to market rules. | Reject. |
| Point-in-time bid/ask | Bid and ask are source fields at or before each row timestamp. | Bid/ask is missing, inferred from last price, inferred from close, or synthesized. | Reject for acceptance. |
| Public/non-authenticated source | Source is reachable without credentials, account state, cookies, browser session data, or private dashboards. | Source requires login, account, private API, paid terminal, cookies, or session data. | Reject. |
| Timezone clarity | Timestamp includes timezone or a documented source-local timezone that can be converted consistently. | Timestamp timezone is unknown or ambiguous. | Reject or mark `needs_more_review`. |
| Settlement ambiguity | Market was resolved/finalized and not canceled, voided, disputed, or ambiguous. | Settlement is canceled, voided, disputed, unclear, or not binary. | Reject. |
| Terms review | `terms_review` is visible and remains `pending_review` unless separately reviewed. | Terms are missing, blocked, or implied as approved without separate review. | Block acceptance claims. |

## Candidate Outcome Rubric

| Outcome | Use when |
| --- | --- |
| `select` | All checklist items pass for the planned row window, except terms may remain `pending_review` with acceptance claims blocked. |
| `alternate` | Source quality is acceptable, but another candidate has stronger timestamp confidence or family diversity. |
| `needs_more_review` | A source appears promising but one timestamp, timezone, settlement mapping, or bid/ask proof is unresolved. |
| `reject` | Any hard fail exists: ambiguous timestamp, no forecast-time evidence, no point-in-time bid/ask, private source, or ambiguous settlement. |

## Family-Specific Checks

### Fed/FOMC/rate decisions

Pass if:

- Forecast evidence is an official calendar, timestamped pre-meeting page, or
  timestamped public preview available before proposed rows.
- Settlement source is an official Federal Reserve statement, target-rate table,
  or rule-compatible official release.
- `label_available_at` is the statement or official table release time.

Fail if:

- The FOMC statement is used as forecast-time evidence for rows before the
  statement release.
- The market threshold cannot be mapped to the official target range or rate
  decision.

### CPI/inflation

Pass if:

- Forecast evidence is a BLS calendar or timestamped pre-release source
  available before rows.
- Settlement source is the official BLS CPI release/table and matches the
  market rule.

Fail if:

- The CPI report itself is attached as forecast evidence for rows before the
  release timestamp.
- The market references a value that is not clearly present in the official
  source.

### Unemployment/jobs/nonfarm payrolls

Pass if:

- Forecast evidence comes from a BLS release calendar or timestamped public
  pre-release source.
- Settlement source is the official BLS Employment Situation release/table.

Fail if:

- The source does not distinguish unemployment rate, payrolls, jobs report, or
  another metric named in the market rule.
- Publication time or timezone is unclear.

### Official-only weather

Pass if:

- Forecast evidence is NOAA, NWS, NHC, or another official source with issued
  time, valid time, update time, or archive timestamp.
- Settlement source maps exactly to the location, station, threshold, and time
  window in the market rule.

Fail if:

- The source is an aggregator, screenshot, social post, or untimestamped page.
- Location, station, threshold, or time-window mapping is ambiguous.

### Major sports

Pass if:

- Forecast evidence is an official schedule, official timestamped preview, or
  another public pre-game source whose availability before the row is clear.
- Settlement source is an official league/team gamecenter, box score, or final
  result page.

Fail if:

- The only forecast evidence is an untimestamped schedule page.
- Final score or box score is used as pre-game forecast evidence.

### Conditional crypto benchmark markets

Pass if:

- The market rule names a benchmark with public timestamped records.
- Forecast evidence and settlement source both point to the benchmark or
  benchmark administrator, not a generic spot-price page.

Fail if:

- The page only shows current price without historical publication proof.
- The benchmark methodology or final value source is not public and
  timestamp-safe.

## Reviewer Notes To Capture

For every candidate, record:

- Which proposed row timestamps are covered by which evidence items.
- Whether evidence is forecast-time, settlement-only, or rejected.
- How timezone was interpreted.
- Why the settlement source is rule-compatible.
- Whether point-in-time bid/ask is proven.
- Why `terms_review=pending_review` blocks acceptance claims.

## Manual Procedure

1. Manually inspect 8 to 12 candidate markets.
2. Fill `docs/reports/acceptance_candidate_shortlist_template.md` fields in a
   local working copy or spreadsheet.
3. Apply this checklist to each candidate.
4. Reject anything with ambiguous timestamps or source availability.
5. Select 5 to 10 survivors only after forecast evidence, settlement evidence,
   bid/ask source, and terms status are visible.
6. Only after that, stage a future local export manually.

This checklist is not an approval workflow. Accepted evidence must still be
human-reviewed in the future review UI, and acceptance claims remain blocked
until validation and the full acceptance gate pass.
