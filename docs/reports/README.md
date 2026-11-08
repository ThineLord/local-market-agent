# Legacy report compatibility

This directory remains for existing CLI output paths. Newly generated Markdown reports are ignored by Git.

`kalshi_category_calibration_analysis.md` is retained unchanged because `category-balance-plan` reads its historical high-gap table by default. It is dated evidence, not current calibration acceptance. Supply `--category-report-path` for a different analysis.

Other old generated reports are available in the [v0.5.0 report archive](https://github.com/ThineLord/local-market-agent/tree/v0.5.0/docs/reports). Current guidance lives in the [documentation index](../README.md).
