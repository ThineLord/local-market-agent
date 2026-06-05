# Kalshi Sprint 1 Evidence Candidate Generation

Date: 2026-06-05

Scope: DATA-EVIDENCE-4 public evidence candidate generation for
`data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/`.

This task generated candidate evidence for human review only. It did not
approve evidence, write approved `evidence.jsonl`, clear terms review, change
acceptance gates, add trading/order/account logic, start Phase 8, or make
profitability claims.

## Commands Run

Focused implementation checks:

```bash
PYTHONPATH=src .venv/bin/ruff check scripts/local_only/generate_kalshi_evidence_candidates.py tests/test_kalshi_evidence_candidate_generator.py
PYTHONPATH=src .venv/bin/pytest tests/test_kalshi_evidence_candidate_generator.py -q
```

Real Sprint 1 candidate generation:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/generate_kalshi_evidence_candidates.py \
  --export-id kalshi_sprint1_20260605_public_probe \
  --export-root data/source_exports/kalshi
```

Review UI load check:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
import importlib.util, sys
from pathlib import Path
script = Path("scripts/local_only/review_kalshi_evidence.py")
spec = importlib.util.spec_from_file_location("review_kalshi_evidence", script)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
workspace = mod.load_review_workspace(
    export_id="kalshi_sprint1_20260605_public_probe",
    export_root=Path("data/source_exports/kalshi"),
    candidates_file="evidence_candidates.jsonl",
)
print(workspace.candidate_source_path)
print(len(workspace.candidates))
print(mod.using_template_fallback(workspace))
PY
```

Full repository validation:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
```

## Output Files

Generated local files under the ignored export directory:

```text
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_candidates.jsonl
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_candidate_generation_report.md
```

The candidate file was not committed because it is real local export evidence
metadata and should remain local until explicitly reviewed for sharing.

The generator did not write or modify:

```text
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence.jsonl
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/source_manifest.json
```

`evidence.jsonl` remained an empty 0-byte file. `terms_review` remained
`pending_review`.

## Markets Processed

| Market | Candidates |
|---|---:|
| `KXBTC15M-26JUN050015-15` | 2 |
| `KXBTC15M-26JUN050030-30` | 2 |
| `KXBTC15M-26JUN050215-15` | 2 |
| `KXITFMATCH-26JUN04KOYSIN-SIN` | 2 |
| `KXITFMATCH-26JUN04ZENHUA-HUA` | 2 |
| `KXITFMATCH-26JUN04ZENHUA-ZEN` | 2 |
| `KXITFWMATCH-26JUN04SAIZHI-SAI` | 2 |
| `KXITFWMATCH-26JUN04SAIZHI-ZHI` | 2 |
| `KXITFWMATCH-26JUN04YANREN-REN` | 2 |
| `KXITFWMATCH-26JUN04YANREN-YAN` | 2 |

## Candidate Summary

- Markets processed: 10.
- Candidates generated: 20.
- Markets covered by at least one candidate: 10.
- Top-level reviewer status: `needs_more_review` for all candidates.
- Metadata reviewer status: `needs_human_review` for all candidates.
- Approved candidates: 0.
- Timestamp coverage estimate: 0%.

Evidence type split:

- `price_reference`: 6 candidates for BTC/BRTI markets.
- `sports_event_reference`: 14 candidates for ITF tennis markets.

Source strategy:

- BTC markets used public CF Benchmarks BRTI and methodology seed URLs.
- M15 Harmon used public ITF tournament/draws seed URLs.
- M15 Luan used public ITF tournament/draws seed URLs.
- W50 Wuning used public ITF tournament/draws seed URLs.

## Timestamp And Warning Summary

All 20 generated candidates have `timestamp_status=missing` because the public
pages did not expose a reliable publication timestamp that can safely prove
availability before each market's `required_evidence_before_ts`.

Warning counts from the local generation report:

- `missing_published_at`: 20.
- `metadata_fetch_non_html`: 3.
- `possible_settlement_or_final_result_context`: 7.

The public search adapter attempted DuckDuckGo HTML searches, but the search
surface returned a bot challenge for each query. The generator therefore relied
on explicit official/public seed URLs and recorded the search challenge warnings
in the local generation report.

## Manual Review Steps

Launch the existing UI with the generated candidate file:

```bash
PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \
  --export-id kalshi_sprint1_20260605_public_probe \
  --export-root data/source_exports/kalshi \
  --candidates-file evidence_candidates.jsonl \
  --overwrite
```

Reviewers should reject or keep needs-more-review for candidates whose
publication timestamp cannot be proven before the forecast window. Do not
approve official tournament/result pages as forecast-time evidence unless the
reviewer can verify timestamp-safe public availability before
`required_evidence_before_ts`.

## Remaining Blockers

- `terms_review` is still `pending_review`.
- Timestamp coverage estimate is still 0%.
- Generated candidates are discovery aids only, not approved evidence.
- Human review must still decide whether any source can be timestamp-verified.
- Acceptance-candidate import should remain blocked until reviewed evidence and
  separate terms review are complete.

## Safety Notes

The implementation stays outside `src/local_market_agent`, uses no credentials,
uses no browser cookies or logged-in sessions, adds no private/authenticated
source handling, writes no approved evidence, and does not touch strategy,
acceptance gates, live trading, account, order, portfolio, fill, or Phase 8
logic.
