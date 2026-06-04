# Live Trading Checklist

Live trading is intentionally not implemented.

Any future proposal to support live orders must first pass all of the following gates outside this implementation:

- Legal and compliance review.
- Exchange API permission review.
- Secret management design review.
- Human approval workflow.
- Independent risk engine review.
- Separate implementation plan that prevents direct LLM-to-order execution.
- Tests proving disabled-by-default behavior.

Current status: live trading is disabled and vetoed.
