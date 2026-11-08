# Synthetic racing checkpoint example

All runners, form, odds, budget and review are invented deterministic test data. These files do not represent a real race or a genuine reviewer attestation. The source text files are placeholders that deliberately say SYNTHETIC FIXTURE.

Run from repository root:

```sh
PYTHONPATH=src python scripts/horse_replay.py research --input data/fixtures/horse_research --output data/reports/horse-synthetic
```

Expected: seven synthetic runners at both T10 and T3; decision NO_BET; blockers PROBABILITY_MODEL_NOT_VALIDATED and SYNTHETIC_DATA_ONLY; zero orders. This demonstrates the import contract and does not validate predictions or profit.

For actual originals, create a separate ignored `data/horse/research/` directory, retain raw files, transcribe only available facts and obtain an availability review bound to the new input/source hashes. Never reuse this synthetic review as real evidence. See the [guide](../../../docs/reference/HORSE_REPLAY.md).
