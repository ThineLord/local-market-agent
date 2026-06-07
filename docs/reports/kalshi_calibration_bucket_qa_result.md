# Kalshi Calibration Bucket QA Result

PR-CAL-4 investigated large calibration-gap buckets in the existing
calibration-only Kalshi dataset:

`data/historical/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.jsonl`

This report is calibration QA only. It does not claim acceptance readiness,
Strategy v2 superiority, profitability, trading readiness, or paper-PnL
validity.

## Commands Run

```bash
PYTHONPATH=src .venv/bin/lma calibration-bucket-qa \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --gap-threshold 0.15
```

Validation:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
git diff --check
```

## Dataset Summary

- Rows: 545
- Markets: 60
- Scored rows: 545
- Dataset class from PR-CAL-3 audit: `calibration_minimum`
- Profile distribution: `calibration_only_last_price`: 545 rows
- Platform distribution: `kalshi`: 545 rows
- Source distribution: `kalshi_public_market_and_candlestick_api`: 545 rows
- Evidence timestamp coverage: 0%
- Bid/ask coverage: 0%
- Last-price coverage: 100%
- Settlement coverage for scored rows: 100%
- Category enrichment source:
  `data/source_exports/kalshi/kalshi_calibration_20260607_public_probe/markets.jsonl`

## High-Gap Buckets

With `--gap-threshold 0.15`, three buckets were flagged.

| Bucket | Rows | Markets | Mean forecast | Observed YES rate | Gap | Brier | Log loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.20-0.30` | 79 | 19 | 0.25240506 | 0.45569620 | 0.20329114 | 0.29069114 | 0.79018830 |
| `0.40-0.50` | 75 | 19 | 0.44093333 | 0.22666667 | 0.21426666 | 0.21932133 | 0.63139667 |
| `0.80-0.90` | 22 | 13 | 0.84727273 | 0.68181818 | 0.16545455 | 0.24548182 | 0.72268117 |

The two buckets already called out in PR-CAL-3 remain the main QA targets:
`0.20-0.30` and `0.40-0.50`.

## Likely Causes

The `0.20-0.30` bucket appears underconfident relative to outcomes: observed
YES rate was about 45.57% against a mean forecast of about 25.24%. The bucket
has 79 rows across 19 markets, so it is not a single-market artifact. The
largest row contributor was `KXWTAMATCH-26APR07PLISAS-PLI` with 11 rows
and about 13.92% of the bucket.

The `0.40-0.50` bucket appears overconfident relative to outcomes: observed
YES rate was about 22.67% against a mean forecast of about 44.09%. It also has
75 rows across 19 markets and is not dominated by one market. The largest row
contributors each had 11 rows, about 14.67% of the bucket:
`KXATPCHALLENGERMATCH-26APR07MARMAY-MAR` and
`KXMLBTOTAL-26APR071610AZNYM-8`.

The `0.80-0.90` bucket crossed the configured threshold, but it is less robust:
it has only 22 rows. Its warning set includes `small_sample_warning`, so it
should be treated as fragile until a larger calibration dataset is available.

Common causes across flagged buckets:

- all flagged rows are `calibration_only_last_price`;
- all rows have no bid/ask and no timestamp-safe evidence;
- the QA tool reports bid/ask and evidence warnings for every high-gap bucket;
- liquidity was present but all rows fell into the thin or zero-or-negative
  liquidity segment;
- row-level category metadata is missing, although local staged market metadata
  allowed category enrichment for segment analysis;
- repeated rows from the same resolved market can amplify market-level misses.

## Segment Findings

`0.20-0.30`:

- Outcome split: 43 NO rows and 36 YES rows.
- Category segment from local source export: 75 `public_event` rows, 3
  `weather` rows, and 1 `major_sports` row.
- Top Brier-loss contributors were concentrated in several tennis-related
  public-event markets, led by `KXWTAMATCH-26APR07PLISAS-PLI`,
  `KXATPCHALLENGERMATCH-26APR07DUTTAB-DUT`, and
  `KXATPCHALLENGERMATCH-26APR06RYBDAM-RYB`.
- The bucket is not market-concentrated by the configured dominance rule, but
  repeated sampling within markets means a few wrongly priced markets still
  contribute meaningful loss.

`0.40-0.50`:

- Outcome split: 58 NO rows and 17 YES rows.
- Category segment from local source export: 62 `public_event` rows and 13
  `major_sports` rows.
- Top Brier-loss contributors included
  `KXATPCHALLENGERMATCH-26APR06CLASOT-SOT`,
  `KXATPCHALLENGERMATCH-26APR07MARMAY-MAR`, and
  `KXMLBTOTAL-26APR071610AZNYM-8`.
- The bucket is not market-concentrated by the configured dominance rule, but
  it is still category-skewed toward public-event rows.

`0.80-0.90`:

- Outcome split: 7 NO rows and 15 YES rows.
- Category segment from local source export: 19 `public_event` rows, 2
  `weather` rows, and 1 `major_sports` row.
- The apparent gap is mostly a small-sample diagnostic, not a robust conclusion.

## Robustness Assessment

The `0.20-0.30` and `0.40-0.50` gaps look directionally meaningful for
calibration QA because they have about 75 to 79 rows each, span 19 markets, and
are not dominated by a single market. They are still fragile for broader
interpretation because the whole dataset is only `calibration_minimum`, uses
last-price-only public candles, lacks bid/ask, lacks timestamp-safe evidence,
and is category-skewed.

The `0.80-0.90` gap should be treated as fragile. It has too few rows to
support a strong calibration diagnosis.

## Guardrails

- Acceptance gate pass: false
- Acceptance-ready claim: false
- Strategy v2 superiority: false
- Profitability claim: false
- Trading-readiness claim: false
- Paper-PnL claim: false

The QA result can support only forecast calibration diagnostics and
strategy-comparison diagnostics that are explicitly labeled calibration-only.

## Recommended Next Step

Use the bucket QA output to guide a future preferred-size calibration dataset
run or a separate manual data-quality review. The next calibration dataset
should prioritize more independent markets per category and reduce repeated
within-market sampling, while preserving the current guardrails: no invented
bid/ask, no fabricated evidence, no acceptance claim, and no Strategy v2
superiority or profitability claim.
