# Repository Rules for Agents

This repository is paper-trading only.

- Run `ruff check .` and `pytest` before opening a PR.
- Never commit secrets, API keys, cookies, private keys, `.env`, local databases, browser data, or credential files.
- Do not add live trading, private trading endpoints, withdrawals, leverage, derivatives, shorting, geoblock bypasses, or direct LLM-to-order paths.
- Keep `REAL_MONEY_ENABLED=false`, `ALLOW_LIVE_ORDERS=false`, and `HUMAN_APPROVAL_REQUIRED=true` as defaults.
- All paper orders must reference a signal and an approved risk decision.
- Network tests must be optional and marked `network`.
- Keep fixtures deterministic and suitable for offline demos.
- Prefer small, coherent changes and document validation results in `docs/IMPLEMENTATION_LOG.md`.
