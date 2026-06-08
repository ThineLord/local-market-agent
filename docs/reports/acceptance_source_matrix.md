# Acceptance Source Matrix

Scope: ACCEPT-1 planning only. This matrix does not collect data, approve
evidence, build an acceptance dataset, mutate source terms, implement a
collector, add scraping or browser automation, change strategy logic, change
acceptance gates, start Phase 8, add broker/live/order/account/portfolio/fill
paths, add scheduler/daemon/autostart behavior, or make profitability,
paper-PnL, Strategy v2 superiority, acceptance-ready, or live-readiness claims.

## Timestamp Standard

Every acceptance-candidate forecast row must have public evidence whose
`published_at` is known and at or before the row timestamp. `retrieved_at` may
be later because it records manual curation time. Settlement sources may be
after the forecast timestamp, but they must be labeled as settlement evidence
and must not be counted as forecast-time evidence.

Date-only or inferred timestamps can be retained in notes, but they should not
count toward acceptance evidence coverage unless a reviewer records a
conservative timestamp rule that makes the item safely available before every
attached row timestamp.

## Source Family Matrix

| Family | Acceptable public source types | Timestamp requirements | Evidence cutoff rules | Settlement source rules | Likely role | Expected difficulty |
| --- | --- | --- | --- | --- | --- | --- |
| Fed/FOMC/rate decisions | Federal Reserve calendar pages, FOMC statement pages, meeting minutes release pages, official press releases, official target-rate tables, timestamped wire/news previews only as secondary evidence | Official release or calendar page must show a publication, release, or update timestamp. Secondary news must show exact publication time and timezone. | Forecast evidence must be available before the sampled candle timestamp. Do not use the post-meeting statement as forecast evidence for rows before the statement release. | Use official Federal Reserve statement, target-rate table, or Kalshi resolution metadata with public rule cross-check. Record `label_available_at` as the first public release time. | Strong forecast-time and settlement evidence when timestamped calendars/previews exist. | Medium |
| CPI/inflation releases | BLS release calendar, CPI news release pages, archived BLS release pages, official data tables, timestamped pre-release calendar pages, timestamped public previews only as secondary evidence | Calendar evidence must predate the row. Release evidence must include release date/time and must be used as settlement-only for pre-release rows. | Before release, use only calendars or timestamped previews. After release, do not treat the CPI report itself as forecast-time evidence for rows before the report timestamp. | Use BLS CPI release and table values, plus market rule text. Record final value, release timestamp, and rule threshold. | Strong for settlement, good for forecast-time if calendars/previews are timestamped. | Medium |
| Unemployment/jobs/nonfarm payrolls | BLS Employment Situation release calendar, official BLS release pages, archived BLS tables, timestamped official calendar notices, timestamped public previews only as secondary evidence | Calendar/previews need exact publication time or conservative date-time handling. Release pages need official release timestamp. | Pre-release rows can use release calendar and timestamped previews only. The released jobs report is settlement-only for earlier rows. | Use BLS Employment Situation release and official table values. Record release timestamp and market threshold mapping. | Strong settlement, moderate forecast-time evidence. | Medium |
| Weather official-only | NOAA/NWS pages, National Hurricane Center advisories, National Weather Service forecast discussions, official station observations, official climatological reports, timestamped government alerts | Every forecast-time item must show an issued time, valid time, update time, or archive timestamp with timezone or source-local timezone. | Evidence must be issued before the row timestamp and relevant to the location/time window in the market rule. Later observations are settlement-only. | Use official station observation, official climate product, NHC archive, NWS product, or Kalshi rule-compatible official source. Avoid unofficial aggregators. | Can be strong, but only for official timestamped pages. | High |
| Major sports | Official league/team schedules, official injury reports where public and timestamped, official box scores/results, timestamped official preview pages, venue/league status pages | Forecast-time evidence needs visible publication/update time before the row. Schedules can be used only if the schedule page timestamp or archive confirms availability before the row. | Use schedules/previews/injury reports only if timestamp-safe. Final score, box score, or game status is settlement-only for pre-game rows. | Use official league/team box score, gamecenter, or Kalshi rule-compatible official result. Record game start, final status, and final score/result. | Good for settlement, mixed for forecast-time evidence because many official pages lack stable timestamps. | Medium |
| Crypto benchmark markets | Official benchmark administrator pages, exchange-published index methodology, timestamped benchmark snapshots, official index files with retrieval metadata, timestamped public market notices | Must prove the benchmark or source value was public at or before the row timestamp. A current value page without archive/time proof is not enough. | Pre-settlement rows need timestamped benchmark context or methodology evidence. Final settlement benchmark value is settlement-only. | Use the market rule's named benchmark and official benchmark publication, not generic exchange price pages unless the rules specify them. | Usually settlement-only unless reliable timestamped benchmark archives exist. | High |

## Common Rejection Reasons

- Evidence has no `published_at`, visible publication time, issued time, or
  reliable archive timestamp.
- Evidence was published after the row timestamp.
- Evidence is private, authenticated, paywalled without cleared terms, or from
  browser/session state.
- Evidence is ambiguous about timezone or source availability.
- Evidence is a final result source being reused as pre-result forecast
  evidence.
- Evidence does not map cleanly to the market resolution rule.
- Settlement source is not public, is disputed, or does not identify the exact
  value/outcome required by the market.
- The market requires invented bid/ask, inferred quotes, or last-price-only
  promotion.
- `terms_review` remains unresolved for any acceptance claim.

## Manual Reviewer Checklist

For each candidate market, the reviewer should record:

- Market ticker, title, rules text, close time, and settlement rule.
- Candidate family from this matrix.
- Row timestamps planned for inclusion.
- At least two evidence items per market where possible.
- For each forecast-time evidence item: public URL, title, `published_at`,
  timezone, `retrieved_at`, source type, and one-sentence relevance summary.
- For each row: proof that at least one evidence item has
  `published_at <= row.timestamp`.
- Settlement source URL, outcome, `resolved_at`, `label_available_at`,
  settlement value if applicable, and ambiguity status.
- Bid/ask source fields, confirming they are point-in-time bid/ask values and
  not invented from last price.
- `terms_review` status, which must remain `pending_review` unless separately
  reviewed outside this pilot-plan document.

## Family Ranking For A 5-10 Market Pilot

Best starting families:

1. Fed/FOMC/rate decisions, if the market rules point to official Federal
   Reserve releases and timestamp-safe pre-release calendars or previews.
2. CPI/inflation and jobs/nonfarm payrolls, because BLS release schedules and
   official result tables are relatively auditable.
3. Weather official-only, but only when NWS/NOAA/NHC issued-time pages match
   the exact market location/window.
4. Major sports, only when official schedule/result pages and any preview
   evidence are timestamp-safe.

Defer or exclude for the first pilot:

- Crypto benchmark markets without timestamp-safe benchmark archives.
- Entertainment, politics, or public-event-generic markets whose only
  forecast-time evidence is untimestamped news or social content.
- Mention markets where source semantics are hard to separate from event-format
  noise.
- Any family that needs private, authenticated, scraped, or browser-session
  evidence.
