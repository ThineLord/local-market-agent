# Implementation Log

Earlier development notes are preserved in the [v0.5.0 history](https://github.com/ThineLord/local-market-agent/blob/v0.5.0/docs/IMPLEMENTATION_LOG.md). Current release work follows below.

## Version 0.2.0 — repository organization and release management (2026-11-09)

- Reorganized the GitHub entry around concise English/Chinese homepages, role-specific bilingual user and Agent guides, a documentation index, and versioned release notes. Used Idea Explorer's public-facing structure as the presentation reference; no research corpus or application code was copied.
- Moved 20 historical phase design files into `docs/archive/phases/` and the dated root project review into `docs/archive/reviews/`. Updated current references and documented path mapping; preserved the original master plan and prior implementation-log wording. Runtime/data paths and `docs/reports/` remain stable.
- Established the 0.2.0 package version, changelog, bilingual version policy, PR checklist, and branch/PR/tag CI metadata validation. Four release-guard regression tests cover matching tags, stale runtime versions, missing Chinese notes, and stale Chinese homepage versions. Codex coordinates and publishes; subagents independently review and merge, without bot delegation.
- Initial full offline validation exposed an existing calendar-dependent test: the public-watchlist mock reused a fixture closing on 2026-11-03 with the real clock. Fixed only that test's clock and mocked snapshot timestamp to the existing deterministic REVIEW instant. Production market-close checks and fixture data are unchanged.
- Validation in a fresh checkout and external Python 3.13.15 environment: `ruff check .` passed; `pytest` completed with **350 passed, 1 skipped** (optional network test); `python scripts/check_release.py --tag v0.2.0` passed. Installed package metadata and runtime both report 0.2.0. Checked **147 relative Markdown links**, with no missing targets. The documented synthetic watchlist command produced **5 rows / 1 research candidate / 1 needs-research / 3 blocked / 0 orders**, and the documented dashboard command served HTTP 200 on loopback. `git diff --check` passed after removing Markdown hard-break trailing spaces.
- Scope/limits: documentation, release metadata/validation, and deterministic test repair. No external market collection, model call, trading-logic change, or data migration. Independent draft PR #4 (paper ledger atomicity/dry-run state) remains excluded, with known limitations disclosed in both release notes. Existing local databases, ignored reports, credentials, and original working-branch state are preserved.

- Independent subagent review identified that relative links in notes would break when copied into a GitHub Release body. Converted both release-note files to immutable `blob/v0.2.0/` URLs and documented that requirement for future releases.

### Ledger/dry-run refresh for 0.3 (2026-11-09)

- Integrated the current main documentation/version baseline into PR #4, preserving both implementation-log histories. Added the fix to Unreleased.
- Validation on the refreshed branch: `ruff check .` passed; full offline pytest **380 passed, 1 skipped**; release metadata and diff whitespace checks passed. Existing fault/commit/concurrency and populated dry-run regression coverage remains in place. No existing user database was opened or migrated.

### Shared preflight and equity risk (2026-11-09)

- Screening and daily paper execution now share market identity, open/close state, freshness, finite quote/liquidity, evidence timing, resolution and research-veto checks. Public observations retain their source timestamps. Synthetic mock paper-only notes are uncertainty notes, not unconditional trade vetoes.
- Persist UTC day-start equity and running observed peak in an additive table. First observation explicitly bootstraps from initial capital; later days use the previous session's last observed equity (not an invented midnight quote). Reject backdated updates; use a separate replay database. Daily RiskEngine receives actual loss/drawdown metrics and RiskGate uses day-start equity.
- Validation: full offline suite **388 passed, 1 skipped**; Ruff, release metadata and diff checks passed. Added multi-day peak/daily baseline, backdate refusal, six hard preflight failures, and runner loss propagation regressions. Existing dry-run settlement tests now correctly expect a closed-market rejection with unchanged source state.
- Follow-up PR will route legacy CLI and per-intent approval through the same execution authorization service. No live trading or user database changes.

- Final portfolio persistence check exposed equal observation timestamps selecting the earlier state. Added insertion-order tie-breaking to repository reads; the dashboard now selects the final state for a deterministic run timestamp.

- Independent review found rejected quote observations could poison persistent equity baselines. Moved preflight ahead of observation persistence, added requested market identity checks and three populated-holding regressions (stale/future/mismatched market). Final full offline validation: **391 passed, 1 skipped**.

### Per-intent paper authorization (2026-11-09)

- Added prepared execution/approval tables and content binding across intent, snapshot, brief, signal, risk and configuration. Added explicit local actor/reason/expiry/rejection history. All ordinary opens use the execution service; legacy paper-log now prepares/pends, daily persists actionable intents, and public-source runs cannot disable approval.
- Execution rechecks hard preflight, latest local observation, all held-market marks, current loss/exposure/limits under the same SQLite write lock as fills. Approval cannot override failures. Fixture/history no-manual simulations generate labelled receipts; fixture-only low-level simulation remains explicit for deterministic fault tests. Actor names are local audit labels, not authenticated multi-user identities.
- Added bilingual workflow/migration documentation and approval CLI commands. Existing static legacy demo now correctly rejects stale/expired data; a dynamic synthetic CLI test verifies pending → approve → execute. Added expiry, rejection, future/stale data, changed inputs/config/live flags, concurrent retry, transaction-failure rollback, newer observation and unmarked holding regressions.
- Validation: Ruff, version metadata, diff checks; full offline suite **404 passed, 1 skipped**. No user database, live endpoint or paid model call.

### Replay content integrity and CLI contract (2026-11-09)

- Sealed new daily run/manifest/reference payloads and separate execution receipts, including approval, opening fill and immutable position-opening projections. Replay detects same-ID content edits and inconsistent links; legitimate later closing is preserved. Legacy runs explicitly report unsealed limitations. These are local checks, not signed tamperproof records or model recomputation.
- Added paper-replay and nonzero JSON outcomes for failed/rejected/pending/halted daily runs, invalid datasets, and aggregate sandbox outcomes. Risk-check now returns rejection status for failed hard checks.
- Validation covers six artifact mutations, relationship inconsistencies despite refreshed hashes, legitimate close, legacy warnings, execution receipt/fill/approval changes, and real CLI error paths. Full offline suite **415 passed, 1 skipped**, Ruff/version/diff checks passed.

- Independent review found missing semantic checks for position market/signal/risk/side. Added one complete opening-chain validator shared by run and execution replay, including bound input digest, linked IDs, prices, quantities, fees and approval timing. Four resealed mismatch regressions ensure hashes alone do not excuse inconsistent relationships. Final full offline validation: **419 passed, 1 skipped**.

### Evidence handoff, settlement and next-step guidance (2026-11-09)

- Added local single-market evidence packets with source-file hashes, bounded relative paths, publication/retrieval timing, exact brief evidence, separate content-bound research and settlement reviews. Explicit preparation still requires a distinct order approval. Settlement records final source/review/closing-fill receipts atomically and blocks reopening a settled market. Source meaning and estimates remain reviewer judgments; local actor labels are not authenticated identities.
- Added a fresh explicitly synthetic packet generator and complete isolated CLI demonstration. Fifteen actual CLI invocations exercised pending → approve → execute → idempotent retry → replay → reviewed settlement → replay, plus a second pending intent; one opening and one closing fill. No existing user database used.
- Added read-only workflow JSON and dashboard guidance: version, observation time, state/reasons, copyable next commands, and bounded recent intents. Dashboard remains without approval or write routes. Browser desktop rendering checked; mobile/clipboard checks recorded with final release validation.
- Bounded public probe: official Kalshi market/series and NWS forecast/observation responses succeeded. A single NYC Nov 9 market packet has four source receipts and two evidence items. Provenance checks passed, but missing liquidity and absent reviewed brief block preparation; no probability or approval was fabricated. The exchange rules name The Weather Company as settlement source, so NWS forecasts/observations are supporting research only. Raw receipts remain ignored local artifacts.
- Validation: full offline suite **429 passed, 1 skipped**; Ruff, release metadata, three JavaScript syntax checks and diff whitespace passed. Ten new packet/workflow tests cover end-to-end settlement, source/path/time/review/brief failures, missing-liquidity blocks, atomic fault rollback, and read-only/tamper-state projection.

- Independent review found an old research source could be reused as final settlement evidence. Added exact resolution-source URL binding and final-source retrieval/publication timing checks; the synthetic demo now carries a distinct final-resolution receipt. Three regressions reject wrong sources, pre-result collection and pre-result publication with the holding unchanged. Final full suite: **432 passed, 1 skipped**.

## Version 0.3.0 release validation (2026-11-09)

- Updated package/runtime versions, bilingual homepages/release notes, versioned validation map and current user/Agent guidance. Functional fixes were reviewed and merged in PRs #4, #6, #7, #8 and #9.
- Release review found the demo report step wrote default exports outside its output directory. Added optional report-daily --export-dir, passed the isolated demo reports directory, and added a sentinel-export regression. Also clarified that independent source review is specific to evidence packets; daily/legacy paths require hard preflight and order approval but not a PacketReview.
- Final release validation: **433 passed, 1 skipped**; Ruff, v0.3.0 metadata, three JavaScript syntax checks, diff checks and 157 local Markdown targets passed. Actual demo uses 15 CLI calls; browser navigation covered all ten pages with no overflow, desktop/390px and command copying. Full real-source results and remaining limits are in docs/reports/0.3.0-validation.zh-CN.md.

- Final 320px dark screenshot exposed low-contrast browser-default copy buttons. Applied existing surface/ink/border palette tokens to the workflow copy controls; desktop/mobile layout and copy behavior remain unchanged.


## 2026-11-09 — Public Kalshi liquidity normalization

Current public market responses omit legacy liquidity but include fixed-point best bid/ask contract sizes. Normalize conservatively to USD: `min(YES ask × YES ask size, (1 − YES bid) × YES bid size)`. This is capacity to buy at the best quotes on both outcome sides, not aggregate order-book liquidity, volume, or open interest. Missing sides remain unknown; zero stays zero; malformed/nonfinite sizes are rejected. Legacy cents are divided by 100, dollar fields take precedence. No snapshot schema change, preserving existing sealed input shapes. Preflight now reports actual versus required liquidity.

Validation: deterministic adapter regressions cover fractional sizes, zero/missing/invalid depth, units and no volume substitution; full Ruff/pytest/release checks recorded in the PR. Read-only probe of `KXHIGHNY-26NOV09-T57` observed YES ask 0.13 × 10 = $1.30 and NO ask 0.88 × 30 = $26.40, correctly below the default $100 minimum. Public raw responses remain local ignored artifacts.


## 2026-11-09 — Exact packet review and actionable readiness

Separate provenance validity, market/brief preflight, matching research-review receipt, strategy actionability, portfolio risk and order approval. `packet-check --review` verifies the supplied receipt; its diagnostic exit-code contract stays unchanged. Missing briefs cannot receive research-review receipts. Observe/missing-probability briefs no longer appear research-ready; preparation preserves strategy and portfolio-risk veto reasons. Equity projection for preparation is read-only, so rejected attempts cannot create partial baselines; execution still persists/checks equity atomically.

Validation covers missing brief, missing/mismatched review, non-actionable probability, actionable fixture path, and zero-capacity portfolio rejection with unchanged business hash. Full offline suite, Ruff, release guard and diff check run before PR; no fabricated market probability or order approval.


## 2026-11-09 — Reproducible public weather observation packet

Added an explicit-network, six-GET Kalshi/NWS collector scoped to NYC daily-high markets. New isolated directories retain source receipts, same-event depth scan, pre-brief and post-brief diagnostics. The market is fetched last; observation time is the actual retrieval time. Output is an observation-only brief with null probability and clear trade vetoes, never a fabricated estimate/review/order. Source-review and order-approval remain separate. Deterministic tests cover scope/network opt-in, exact market identity, no-overwrite, file integrity, bounded requests and non-actionable output. Full offline/Ruff/release checks run before PR; actual public acceptance recorded in the version report.

## 2026-11-09 — Release 0.3.1 public-data acceptance

Prepared bilingual 0.3.1 release notes/homepages/changelog and detailed public-data validation. Same-response comparison proves unknown legacy liquidity becomes $1.30 conservative depth; independent source review becomes valid while genuine economic vetoes remain. Two real preparation attempts return exit 3 with identical hashes across all 17 business tables. Public execution/settlement are inapplicable; a separate synthetic 15-step workflow verifies those existing paths. No user database migrated or public order approval fabricated. Full offline suite: 449 passed, 1 optional network skipped; separately enabled network test: 1 passed. Reviewer findings and final exact-head CI are required before release merge/tag.

## 2026-11-09 — Bounded liquid public-market discovery

Added opt-in, bounded NBA/NFL binary game-market screening with unchanged shared quote/depth thresholds. Captures source hashes/timestamps, retains failures, ranks passing market checks by conservative USD depth, and explicitly separates quote eligibility from pregame/model/order readiness. Refuses overwrite, duplicates, wrong series, repeated cursors and oversized responses. No credentials, ledger writes or order creation. Deterministic coverage and full Ruff/pytest/release checks run before the PR.

Independent review identified that legacy aggregate liquidity could pass the discovery screen. Discovery now explicitly requires current best-quote size provenance; the legacy adapter remains backward compatible. Added a regression demonstrating a $10,000 aggregate-only response remains blocked.

## 2026-11-09 — Frozen NBA probability model and retrospective validation

Implemented a custom fixed Elo model (no market-price fitting/model API calls), checksummed 120-page public history acquisition, exact final-game deduplication and season coverage audit, conservative two-UTC-day result update lag, chronological holdout scoring and deterministic day-block bootstrap. Protocol and thresholds were frozen before collecting the validation data. Current-candidate confidence is a reproducible net-edge support fraction with a separate conservative edge requirement, not a hand-filled probability confidence score. See `docs/NBA_PROBABILITY.md` for formulas, prerequisites and limitations.

Real public reconstruction: 2024/2025/2026 each 1,230 unique games and every team 82 games; 2,460 warmup, 1,230 holdout, 139 current-season final games. Raw Elo Brier 0.209639 versus home-rate baseline 0.247153; logloss 0.608033 versus 0.687444; ECE 0.028186; paired Brier difference bootstrap 95% interval [-0.047430,-0.028255]. All frozen validation gates passed and a subagent independently reproduced the stored results. Historical data is retrospectively retrieved, not a point-in-time trading backtest. Raw public sources remain local ignored outputs. Integration must still enforce current history age, exact pregame identity, sample support, conservative edge, existing risk gates and separate per-intent approval.

Independent review found that final-game time validation used analysis time rather than each source receipt time. The loader now rejects any source claiming a final for a game that had not started when that file was retrieved; a targeted provenance regression covers this contradiction.

## 2026-11-09 — Source-bound NBA paper workflow

Integrated depth-ranked public pregame selection, exact NBA/contract matching and the frozen model into an evidence packet. Every import reproduces ratings, holdout validation, quote and conservative support from receipt-bound public files; local derived reports use an explicitly labelled analysis URI and their true creation time. No historical publication timestamps are invented. Runtime preflight rechecks game start, event/source age, model/bin/cost consistency and conservative edge at preparation, approval and execution. Existing risk and approval thresholds remain unchanged; collector never opens a ledger or approves an order.

Initial real integration captured 130 sources and selected `KXNBAGAME-26NOV08NOPLAC-LAC`: conservative depth $558.0635, raw probability 0.669838, holdout bin 219 games, net-edge stress lower bound 0.112352 versus 0.08 required. All source/model/market preflight checks passed; research review remained explicitly missing, with zero orders/approvals. This observation is time-bound and must be refreshed before execution. Offline regressions cover exact identity, incomplete history, source-based proof reconstruction/tampering, time/edge/validation failures and game-start rejection at approval/execution. Full validation is recorded in the PR before review.

Independent integration review found that import-time reproduction did not recheck unit payout, depth provenance, series settlement source or the derived prerequisites. Added shared contract checks (including rejection of boolean payouts), rebuilt all eight prerequisites on import, and locked the supported postponement/cancellation rule version. Source-mutating regressions update the file hash yet must still be rejected, exercising semantic consistency rather than checksum failure alone.

## 2026-11-09 — Release 0.4.0 actual acceptance

Final public NBA scan: 70 markets, 31 quote/depth passes, 25 exact pregame matches, three supported contracts; selected one NOP BUY_NO packet. Independent research review reproduced 130 sources. Preparation passed portfolio risk and initially remained pending with zero orders. The user then explicitly approved the exact $100 intent. Freshness and all unchanged gates passed at actual execution: one paper fill at 0.481, 207.9002079 contracts, $0.10 fees; repeated execution did not duplicate the fill and replay returned ok=true. The game is still pregame, so the position remains open without fabricated settlement. Existing user databases untouched. Full offline suite 498 passed/1 optional skipped; separately enabled network 1 passed; synthetic 15-step regression completed. Bilingual 0.4.0 metadata, notes and detailed real-data report prepared for independent release review.


## 2026-11-09 — Actual UI acceptance exposed NO valuation inversion

Before publishing v0.4.0, the real NOP BUY_NO ledger displayed false positive equity because market-ID marks in YES probability were used directly for NO positions. Corrected the common valuation helper to invert explicit marks for BUY_NO while preserving own-outcome cost fallback. Regression covers endpoints, absent marks, execution-time portfolio/baseline/peak/drawdown and report consistency. The approved fill remains unchanged. Original acceptance DB preserved; an explicit separate historical valuation replay corrected equity 10009.0476→9998.6526 and unrealized PnL→−1.3474, with 14 non-derived business tables identical and sealed execution replay still valid. Existing user data is not silently migrated. Release notes document the historical-data boundary; final full-suite results recorded in correction PR.

## 2026-11-09 — Isolated Hong Kong historical replay

Added strict historical ticket records, separate provisional/official-entitlement/cash tracks, per-pool and race-close statistics, and bounded opt-in HKJC result/declaration acquisition with offline source verification. Actual public acquisition exposed duplicate HTML navigation/section IDs; parsing now chooses the unique declaration section. Unknown original predictions remain UNKNOWN and no strategy backtest is inferred. User history and raw captures stay in ignored local outputs. No trading database or existing market is modified. Deterministic tests cover source identity/hash/time tampering, incomplete fields, unsupported settlement, cash evidence and whole-unit payouts. Ruff, release consistency and full offline suite run before PR; exact-head subagent review and green CI required before merge.

Independent subagent review found two fail-open cases: an incomplete PLACE table could label a winner as lost, and a truncated record could appear to cover an entire meeting. Fixed both by checking unchanged-field pool completeness and exact meeting race coverage, with regression tests. Final core verification: 527 passed, 1 optional network test skipped; Ruff and release checks pass.

Final-source review additionally found same-day pre-start final-result receipts were accepted. The loader now checks each result receipt against the declaration's explicit Hong Kong scheduled start; impossible final-result chronology fails closed. Full suite after this correction: 528 passed, 1 skipped.

## 2026-11-09 — Horse checkpoint audit and parallel dashboard

Added strict original-transcription inputs, source-bound availability review, separate T10/T3 full-field checks, descriptive form comparisons, separately labelled WIN/PLACE original probabilities and indicative-value scenarios. No horse probability model is claimed: every current research result is NO_BET and zero orders. Budget freeze must precede the first checkpoint. Missing originals remain UNKNOWN while the user locates their archives. The optional loopback horse workspace recomputes history from inputs and public receipts; HKD entitlements and cash remain distinct from existing paper markets. Browser and regression validation recorded before PR.

Independent review found unknown form finishes were included in observation denominators. Fixed by counting only known finishes and adding explicit missing-finish uncertainty/blockers. Final feature suite: 555 passed, 1 optional network skipped; Ruff, release metadata and JavaScript syntax checks pass. Actual loopback browser exercised historical ledger, full-field and pre-race checks alongside the existing paper ledger; 12 original database file hashes remained unchanged. No user history or browser screenshots are committed.

## 2026-11-09 — Release 0.5.0 acceptance

Prepared consistent 0.5.0 package/homepage/changelog metadata and bilingual release/user/agent documentation. Source capture parsed all nine races and 111 declared runners in a real public meeting, while private financial records and screenshots remain ignored local outputs. Every horse research result remains NO_BET due to unvalidated probability and missing original checkpoints; manual availability review and historical budget evidence also remain UNKNOWN. Original markets are preserved: all 12 pre-existing database hashes unchanged. Full offline suite 555 passed/1 optional skipped; separately enabled public network test 1 passed; original 15-step synthetic workflow completed. Browser exercised new pages and existing ledger without console errors. No database migration, real trade, fabricated odds/probability or racing paper order was created.

## 2026-11-09 — Release 0.5.1 repository presentation

Reduced the GitHub root from 14 to 12 entries by relocating the Chinese homepage and changelog under docs; grouped technical and maintenance documentation. Removed 81 superseded documents from the current tree plus five unused runtime-directory placeholders; complete originals remain in immutable v0.5.0 history. Retained the default category-balance Markdown input byte-for-byte after dependency review. Earlier implementation notes now link to their full historical version. Runtime code, fixtures, local databases and CLI paths are unchanged. Bilingual homepages share two actual light-theme synthetic dashboard captures, with the audit image collapsed. No private transaction data is published. Release checks follow the new paths. Validation includes Ruff, full pytest, version/tag metadata, documentation/archived-target checks and the existing 15-step synthetic workflow; no network collection.

Final local validation: 555 passed, 1 optional network skipped; Ruff, `check_release.py --tag v0.5.1` and `git diff --check` passed. Checked 235 documentation links and 13 immutable archive targets with no missing files. The 15-step demo completed and the README screen reported one research candidate, one needs-research and three blocked synthetic markets. Both screenshots were visually inspected; the retained runtime Markdown input is identical to v0.5.0. Original local data was accessed only for a preservation hash baseline, not modified.
