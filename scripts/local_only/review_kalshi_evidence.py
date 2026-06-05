#!/usr/bin/env python3
"""Local-only Streamlit review UI for Kalshi evidence candidates.

The script reads and writes files inside a staged Kalshi export directory. It
does not fetch URLs, scrape websites, automate a browser, or call source APIs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

APP_VERSION = "data_evidence_2.local_evidence_review_ui.v1"
DEFAULT_EXPORT_ROOT = Path("data/source_exports/kalshi")
DEFAULT_CANDIDATES_FILE = "evidence_candidates.jsonl"
DEFAULT_TEMPLATE_FILE = "evidence_template.jsonl"
EVIDENCE_JSONL = "evidence.jsonl"
REVIEW_STATE_JSON = "evidence_review_state.json"
REVIEW_AUDIT_MD = "evidence_review_audit.md"

STATUS_UNREVIEWED = "unreviewed"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_NEEDS_MORE_REVIEW = "needs_more_review"
REVIEW_STATUSES = (
    STATUS_UNREVIEWED,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_NEEDS_MORE_REVIEW,
)

EVIDENCE_FIELDS = (
    "market_ticker",
    "evidence_id",
    "source",
    "title",
    "url",
    "published_at",
    "retrieved_at",
    "summary",
    "relevance_score",
    "credibility_score",
)
REVIEW_DETAIL_FIELDS = (
    "timestamp_status",
    "evidence_type",
    "supports_side",
    "curator_notes",
)
MARKET_DISPLAY_FIELDS = (
    "market_ticker",
    "title",
    "subtitle",
    "rules_primary",
    "rules_secondary",
    "result",
    "settlement_ts",
    "earliest_candle_timestamp",
    "latest_candle_timestamp",
    "required_evidence_before_ts",
    "candle_count",
)
MARKET_TIMESTAMP_FIELDS = (
    ("required_evidence_before_ts", "required_evidence_before_ts"),
    ("earliest_candle_timestamp", "earliest_candle_timestamp"),
    ("latest_candle_timestamp", "latest_candle_timestamp"),
    ("settlement_ts", "settlement_ts"),
)

PLACEHOLDER_RE = re.compile(
    r"(^|[^A-Za-z])(TODO|TBD|PLACEHOLDER|FIXME|FILL_ME|REPLACE_ME)([^A-Za-z]|$)",
    re.IGNORECASE,
)
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PRIVATE_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
}
PRIVATE_URL_PREFIXES = (
    "file:",
    "chrome:",
    "about:",
    "data:",
)
PRIVATE_SOURCE_MARKERS = (
    "authenticated",
    "login",
    "private",
    "session",
    "cookie",
    "token",
    "dashboard",
    "account-only",
    "paywalled",
)
WEAK_SOURCE_MARKERS = (
    "blogspot",
    "medium.com",
    "substack",
    "reddit.com",
    "wikipedia.org",
    "x.com",
    "twitter.com",
    "facebook.com",
    "youtube.com",
    "tiktok.com",
)
SETTLEMENT_TYPE_MARKERS = (
    "settlement",
    "settlement_label",
    "final_result",
    "post_result",
    "resolution",
    "resolved_outcome",
    "outcome_label",
)
SETTLEMENT_TEXT_MARKERS = (
    "settlement label",
    "final result",
    "post-result",
    "post result",
    "settled as",
    "resolved as",
    "market resolved",
    "final outcome",
)


@dataclass(frozen=True)
class CandidateValidation:
    blocking_errors: tuple[str, ...]
    warnings: tuple[str, ...]
    source_domain: str | None
    source_public: bool

    @property
    def can_approve(self) -> bool:
        return not self.blocking_errors


@dataclass(frozen=True)
class ReviewWorkspace:
    export_dir: Path
    export_id: str
    manifest: dict[str, Any]
    markets: tuple[dict[str, Any], ...]
    candidates: tuple[dict[str, Any], ...]
    candidate_source_path: Path | None
    worksheet_path: Path | None

    @property
    def markets_by_ticker(self) -> dict[str, dict[str, Any]]:
        return {str(row["market_ticker"]): row for row in self.markets}


@dataclass(frozen=True)
class ReviewWriteResult:
    state_path: Path
    audit_path: Path
    evidence_path: Path
    approved_count: int
    rejected_count: int
    needs_more_review_count: int
    unreviewed_count: int


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = load_review_workspace(
        export_id=args.export_id,
        export_root=args.export_root,
        candidates_file=args.candidates_file,
        template_file=args.template_file,
    )
    run_streamlit_app(workspace, overwrite_default=args.overwrite)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review local Kalshi evidence candidates in Streamlit."
    )
    parser.add_argument("--export-id", required=True)
    parser.add_argument(
        "--export-root",
        type=Path,
        default=DEFAULT_EXPORT_ROOT,
    )
    parser.add_argument(
        "--candidates-file",
        default=DEFAULT_CANDIDATES_FILE,
        help="Candidate JSONL file, resolved relative to the export directory.",
    )
    parser.add_argument(
        "--template-file",
        default=DEFAULT_TEMPLATE_FILE,
        help="Fallback template JSONL file, resolved relative to the export directory.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow export to replace an existing evidence.jsonl file.",
    )
    return parser.parse_args(argv)


def load_review_workspace(
    *,
    export_id: str,
    export_root: Path = DEFAULT_EXPORT_ROOT,
    candidates_file: str | Path = DEFAULT_CANDIDATES_FILE,
    template_file: str | Path = DEFAULT_TEMPLATE_FILE,
) -> ReviewWorkspace:
    export_dir = export_root / export_id
    manifest = load_json_object(export_dir / "source_manifest.json")
    markets_raw = load_jsonl(export_dir / "markets.jsonl")
    candles = load_jsonl(export_dir / "candlesticks.jsonl")
    worksheet_path, worksheet_rows = load_worksheet(export_dir)
    markets = build_market_summaries(
        markets=markets_raw,
        candles=candles,
        worksheet_rows=worksheet_rows,
    )
    candidate_source_path = resolve_candidate_source(
        export_dir=export_dir,
        candidates_file=candidates_file,
        template_file=template_file,
    )
    candidates = (
        normalize_candidates(load_jsonl(candidate_source_path))
        if candidate_source_path is not None
        else ()
    )
    return ReviewWorkspace(
        export_dir=export_dir,
        export_id=export_id,
        manifest=manifest,
        markets=tuple(markets),
        candidates=tuple(candidates),
        candidate_source_path=candidate_source_path,
        worksheet_path=worksheet_path,
    )


def load_worksheet(export_dir: Path) -> tuple[Path | None, dict[str, dict[str, Any]]]:
    csv_path = export_dir / "evidence_worksheet.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return csv_path, {
            required_text(row, "market_ticker"): dict(row)
            for row in rows
            if text_or_none(row.get("market_ticker"))
        }
    markdown_path = export_dir / "evidence_worksheet.md"
    if markdown_path.exists():
        return markdown_path, {}
    return None, {}


def build_market_summaries(
    *,
    markets: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    worksheet_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candles_by_market = group_candles_by_market(candles)
    summaries: list[dict[str, Any]] = []
    for market in sorted(markets, key=lambda item: required_text(item, "ticker")):
        ticker = required_text(market, "ticker")
        worksheet_row = worksheet_rows.get(ticker, {})
        candle_timestamps = sorted(
            timestamp
            for timestamp in (
                canonical_or_none(
                    candle.get("end_period_ts")
                    or candle.get("timestamp")
                    or candle.get("start_period_ts")
                )
                for candle in candles_by_market.get(ticker, [])
            )
            if timestamp is not None
        )
        earliest = candle_timestamps[0] if candle_timestamps else ""
        latest = candle_timestamps[-1] if candle_timestamps else ""
        summaries.append(
            {
                "market_ticker": ticker,
                "title": text_or_empty(market.get("title")),
                "subtitle": text_or_empty(market.get("subtitle")),
                "rules_primary": text_or_empty(
                    market.get("rules_primary") or market.get("primary_rule")
                ),
                "rules_secondary": text_or_empty(
                    market.get("rules_secondary") or market.get("secondary_rule")
                ),
                "result": text_or_empty(market.get("result") or market.get("outcome")),
                "settlement_ts": canonical_or_none(
                    market.get("settlement_ts")
                    or market.get("resolved_at")
                    or market.get("label_available_at")
                )
                or text_or_empty(worksheet_row.get("settlement_ts")),
                "earliest_candle_timestamp": text_or_empty(
                    worksheet_row.get("earliest_candle_ts")
                )
                or earliest,
                "latest_candle_timestamp": text_or_empty(
                    worksheet_row.get("latest_candle_ts")
                )
                or latest,
                "required_evidence_before_ts": text_or_empty(
                    worksheet_row.get("required_evidence_before_ts")
                )
                or earliest,
                "candle_count": int(
                    worksheet_row.get("number_of_candles") or len(candle_timestamps)
                ),
            }
        )
    return summaries


def normalize_candidates(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        metadata = json_object_or_empty(row.get("metadata"))
        candidate: dict[str, Any] = {
            "candidate_id": text_or_none(row.get("candidate_id"))
            or stable_id(
                "candidate",
                {
                    "index": index,
                    "market_ticker": row.get("market_ticker"),
                    "evidence_id": row.get("evidence_id"),
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "published_at": row.get("published_at"),
                },
            ),
            "reviewer_status": text_or_none(row.get("reviewer_status"))
            or text_or_none(metadata.get("reviewer_status"))
            or STATUS_UNREVIEWED,
            "reviewer_note": text_or_empty(row.get("reviewer_note")),
            "rejection_reason": text_or_empty(row.get("rejection_reason")),
            "metadata": metadata,
        }
        for field in EVIDENCE_FIELDS:
            candidate[field] = row.get(field, "")
        for field in REVIEW_DETAIL_FIELDS:
            candidate[field] = row.get(field, metadata.get(field, ""))
        if not text_or_none(candidate.get("evidence_id")):
            candidate["evidence_id"] = stable_id(
                "ev",
                {
                    "candidate_id": candidate["candidate_id"],
                    "market_ticker": candidate.get("market_ticker"),
                    "source": candidate.get("source"),
                    "title": candidate.get("title"),
                    "published_at": candidate.get("published_at"),
                },
            )
        candidates.append(candidate)
    return tuple(candidates)


def validate_candidate_for_approval(
    candidate: dict[str, Any],
    market: dict[str, Any] | None,
) -> CandidateValidation:
    blocking_errors: list[str] = []
    warnings: list[str] = []
    url = text_or_none(candidate.get("url"))
    title = text_or_none(candidate.get("title"))
    published_raw = text_or_none(candidate.get("published_at"))
    retrieved_raw = text_or_none(candidate.get("retrieved_at"))
    domain = domain_from_url(url)

    if market is None:
        blocking_errors.append("market_ticker is missing or does not match markets.jsonl")
    if not url:
        blocking_errors.append("url is missing")
    elif not url.lower().startswith(("http://", "https://")):
        blocking_errors.append("url must be an http(s) public URL")
    if not title:
        blocking_errors.append("title is missing")
    if not text_or_none(candidate.get("source")):
        blocking_errors.append("source is missing")
    if not text_or_none(candidate.get("summary")):
        blocking_errors.append("summary is missing")
    if not text_or_none(candidate.get("evidence_id")):
        blocking_errors.append("evidence_id is missing")

    if not published_raw:
        blocking_errors.append("published_at is missing")
        published_at = None
    else:
        published_at = parse_timestamp(published_raw)
        if published_at is None:
            blocking_errors.append("published_at must be timezone-aware ISO 8601")
    if not retrieved_raw:
        blocking_errors.append("retrieved_at is missing")
    elif parse_timestamp(retrieved_raw) is None:
        blocking_errors.append("retrieved_at must be timezone-aware ISO 8601")

    if market is not None and published_at is not None:
        required_raw = text_or_none(market.get("required_evidence_before_ts"))
        required_ts = parse_timestamp(required_raw)
        if required_ts is None:
            warnings.append("market required_evidence_before_ts is missing or invalid")
        elif published_at > required_ts:
            blocking_errors.append(
                "published_at is after required_evidence_before_ts"
            )
            latest_ts = parse_timestamp(market.get("latest_candle_timestamp"))
            if latest_ts is None or published_at <= latest_ts:
                warnings.append("evidence only covers late candles")

    if has_placeholder(candidate):
        blocking_errors.append("placeholder/TODO values remain")

    for score_field in ("relevance_score", "credibility_score"):
        score = optional_float(candidate.get(score_field))
        if score is None:
            blocking_errors.append(f"{score_field} is missing")
        elif not 0.0 <= score <= 1.0:
            blocking_errors.append(f"{score_field} must be between 0 and 1")

    source_public = not looks_private_or_authenticated(candidate, domain)
    if not source_public:
        blocking_errors.append("source is private/authenticated or local-only")

    if appears_to_be_settlement_evidence(candidate):
        blocking_errors.append(
            "evidence appears to be settlement/final-result evidence used as forecast-time evidence"
        )

    if published_raw and looks_date_only(published_raw):
        warnings.append("date-only timestamp")
    if domain_is_weak(domain) or source_is_weak(candidate.get("source")):
        warnings.append("weak source")
    if summary_too_short(candidate.get("summary")):
        warnings.append("summary too short")
    if domain_is_unknown(domain):
        warnings.append("source domain unknown")

    return CandidateValidation(
        blocking_errors=tuple(dedupe(blocking_errors)),
        warnings=tuple(dedupe(warnings)),
        source_domain=domain,
        source_public=source_public,
    )


def write_review_outputs(
    *,
    workspace: ReviewWorkspace,
    review_rows: list[dict[str, Any]],
    reviewed_by: str,
    overwrite_evidence: bool = False,
    now: datetime | None = None,
) -> ReviewWriteResult:
    reviewed_at = canonical_timestamp(now or utc_now())
    state_path = workspace.export_dir / REVIEW_STATE_JSON
    audit_path = workspace.export_dir / REVIEW_AUDIT_MD
    evidence_path = workspace.export_dir / EVIDENCE_JSONL
    markets_by_ticker = workspace.markets_by_ticker
    validations = {
        str(row["candidate_id"]): validate_candidate_for_approval(
            row,
            markets_by_ticker.get(str(row.get("market_ticker") or "")),
        )
        for row in review_rows
    }
    approved_rows = [
        row
        for row in review_rows
        if normalized_status(row.get("reviewer_status")) == STATUS_APPROVED
    ]
    if not approved_rows:
        msg = "no approved evidence rows to export"
        raise ValueError(msg)
    invalid_approved = [
        (row, validations[str(row["candidate_id"])])
        for row in approved_rows
        if not validations[str(row["candidate_id"])].can_approve
    ]
    if invalid_approved:
        details = "; ".join(
            f"{row.get('candidate_id')}: {', '.join(validation.blocking_errors)}"
            for row, validation in invalid_approved
        )
        msg = "approved evidence failed safety checks: " + details
        raise ValueError(msg)
    missing_rejection_reasons = [
        str(row.get("candidate_id") or row.get("evidence_id") or "unknown")
        for row in review_rows
        if normalized_status(row.get("reviewer_status")) == STATUS_REJECTED
        and not text_or_none(row.get("rejection_reason"))
    ]
    if missing_rejection_reasons:
        msg = "rejected evidence requires rejection_reason: " + ", ".join(
            missing_rejection_reasons
        )
        raise ValueError(msg)

    state_payload = build_review_state_payload(
        workspace=workspace,
        review_rows=review_rows,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        validations=validations,
    )
    state_path.write_text(
        json.dumps(state_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    audit_path.write_text(
        render_audit_markdown(
            workspace=workspace,
            review_rows=review_rows,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            validations=validations,
        ),
        encoding="utf-8",
    )

    if evidence_path.exists() and not overwrite_evidence:
        msg = (
            f"{evidence_path} already exists; pass --overwrite or confirm overwrite "
            "in the UI before exporting approved evidence"
        )
        raise FileExistsError(msg)

    evidence_rows = [
        build_pr_data_3_evidence_row(
            row=row,
            market=markets_by_ticker[str(row["market_ticker"])],
            validation=validations[str(row["candidate_id"])],
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
        )
        for row in sorted(
            approved_rows,
            key=lambda item: (
                str(item.get("market_ticker") or ""),
                str(item.get("evidence_id") or ""),
                str(item.get("candidate_id") or ""),
            ),
        )
    ]
    evidence_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in evidence_rows
        ),
        encoding="utf-8",
    )

    counts = review_status_counts(review_rows)
    return ReviewWriteResult(
        state_path=state_path,
        audit_path=audit_path,
        evidence_path=evidence_path,
        approved_count=counts[STATUS_APPROVED],
        rejected_count=counts[STATUS_REJECTED],
        needs_more_review_count=counts[STATUS_NEEDS_MORE_REVIEW],
        unreviewed_count=counts[STATUS_UNREVIEWED],
    )


def build_pr_data_3_evidence_row(
    *,
    row: dict[str, Any],
    market: dict[str, Any],
    validation: CandidateValidation,
    reviewed_by: str,
    reviewed_at: str,
) -> dict[str, Any]:
    metadata = json_object_or_empty(row.get("metadata"))
    metadata.update(
        {
            "reviewer_status": STATUS_APPROVED,
            "reviewed_by": reviewed_by,
            "reviewed_at": reviewed_at,
            "timestamp_status": text_or_empty(row.get("timestamp_status"))
            or "explicit_timezone_timestamp",
            "evidence_type": text_or_empty(row.get("evidence_type"))
            or "public_forecast_time_evidence",
            "supports_side": text_or_empty(row.get("supports_side")) or "context_or_rule",
            "curator_notes": text_or_empty(row.get("curator_notes")),
            "source_public": validation.source_public,
            "private_or_authenticated_source": False,
            "required_evidence_before_ts": market.get("required_evidence_before_ts"),
            "source_domain": validation.source_domain,
            "validation_warnings": list(validation.warnings),
        }
    )
    reviewer_note = text_or_none(row.get("reviewer_note"))
    if reviewer_note:
        metadata["reviewer_note"] = reviewer_note
    return {
        "market_ticker": required_text(row, "market_ticker"),
        "evidence_id": required_text(row, "evidence_id"),
        "source": required_text(row, "source"),
        "title": required_text(row, "title"),
        "url": required_text(row, "url"),
        "published_at": canonical_timestamp(parse_timestamp(row["published_at"])),
        "retrieved_at": canonical_timestamp(parse_timestamp(row["retrieved_at"])),
        "summary": required_text(row, "summary"),
        "relevance_score": float(row["relevance_score"]),
        "credibility_score": float(row["credibility_score"]),
        "metadata": metadata,
    }


def build_review_state_payload(
    *,
    workspace: ReviewWorkspace,
    review_rows: list[dict[str, Any]],
    reviewed_by: str,
    reviewed_at: str,
    validations: dict[str, CandidateValidation],
) -> dict[str, Any]:
    counts = review_status_counts(review_rows)
    state_rows = []
    for row in review_rows:
        candidate_id = str(row["candidate_id"])
        validation = validations[candidate_id]
        state_rows.append(
            {
                **row,
                "reviewer_status": normalized_status(row.get("reviewer_status")),
                "blocking_errors": list(validation.blocking_errors),
                "validation_warnings": list(validation.warnings),
                "source_domain": validation.source_domain,
                "source_public": validation.source_public,
            }
        )
    return {
        "schema_version": APP_VERSION,
        "export_id": workspace.export_id,
        "export_dir": str(workspace.export_dir),
        "candidate_source_path": str(workspace.candidate_source_path)
        if workspace.candidate_source_path is not None
        else None,
        "worksheet_path": str(workspace.worksheet_path)
        if workspace.worksheet_path is not None
        else None,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "counts": counts,
        "manifest_terms_review": workspace.manifest.get("terms_review"),
        "manifest_private_or_authenticated_source": workspace.manifest.get(
            "private_or_authenticated_source"
        ),
        "local_only": True,
        "network_used": False,
        "automatic_approval": False,
        "markets": list(workspace.markets),
        "candidates": state_rows,
    }


def render_audit_markdown(
    *,
    workspace: ReviewWorkspace,
    review_rows: list[dict[str, Any]],
    reviewed_by: str,
    reviewed_at: str,
    validations: dict[str, CandidateValidation],
) -> str:
    counts = review_status_counts(review_rows)
    lines = [
        "# Kalshi Evidence Review Audit",
        "",
        f"Generated at: `{reviewed_at}`",
        f"Reviewed by: `{reviewed_by}`",
        f"Export id: `{workspace.export_id}`",
        f"Export dir: `{workspace.export_dir}`",
        f"Candidate source: `{workspace.candidate_source_path}`",
        f"Worksheet source: `{workspace.worksheet_path}`",
        "",
        "## Counts",
        "",
        f"- Markets: {len(workspace.markets)}",
        f"- Candidates: {len(review_rows)}",
        f"- Approved: {counts[STATUS_APPROVED]}",
        f"- Rejected: {counts[STATUS_REJECTED]}",
        f"- Needs more review: {counts[STATUS_NEEDS_MORE_REVIEW]}",
        f"- Unreviewed: {counts[STATUS_UNREVIEWED]}",
        "",
        "## Safety",
        "",
        "- local_only: true",
        "- file_only: true",
        "- network_used: false",
        "- automatic_approval: false",
        "- source_api_caller: false",
        "- scraper_or_crawler: false",
        "- broker_execution_api: false",
        "",
        "## Manifest Gate",
        "",
        f"- terms_review: `{workspace.manifest.get('terms_review')}`",
        "- terms review must still be cleared outside this evidence review UI.",
        f"- private_or_authenticated_source: {workspace.manifest.get('private_or_authenticated_source')}",
        "",
        "## Candidate Decisions",
        "",
        "| Market | Evidence | Status | Blocking errors | Warnings |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in review_rows:
        validation = validations[str(row["candidate_id"])]
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(str(row.get("market_ticker") or "")),
                    markdown_cell(str(row.get("evidence_id") or row["candidate_id"])),
                    normalized_status(row.get("reviewer_status")),
                    markdown_cell("; ".join(validation.blocking_errors) or "none"),
                    markdown_cell("; ".join(validation.warnings) or "none"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Rerun Commands", ""])
    lines.extend(command_markdown(workspace.export_id))
    return "\n".join(lines) + "\n"


def command_markdown(export_id: str) -> list[str]:
    return [
        "Acceptance candidate validation:",
        "",
        "```bash",
        "PYTHONPATH=src .venv/bin/lma import-kalshi-export \\",
        f"  --export-dir data/source_exports/kalshi/{export_id} \\",
        "  --profile acceptance_candidate \\",
        "  --output-dir data/historical \\",
        "  --report-dir data/reports/historical_dataset \\",
        "  --source-audit-dir docs/reports \\",
        "  --validate",
        "```",
        "",
        "Downgrade diagnostic:",
        "",
        "```bash",
        "PYTHONPATH=src .venv/bin/lma import-kalshi-export \\",
        f"  --export-dir data/source_exports/kalshi/{export_id} \\",
        "  --profile acceptance_candidate \\",
        "  --allow-downgrade \\",
        "  --output-dir data/historical \\",
        "  --report-dir data/reports/historical_dataset \\",
        "  --source-audit-dir docs/reports \\",
        "  --validate",
        "```",
    ]


def run_streamlit_app(workspace: ReviewWorkspace, *, overwrite_default: bool) -> None:
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - exercised only without Streamlit.
        msg = "Streamlit is required. Install project dependencies, then rerun this script."
        raise RuntimeError(msg) from exc

    st.set_page_config(page_title="Kalshi Evidence Review", layout="wide")
    state_key = review_session_state_key(workspace)
    if state_key not in st.session_state:
        st.session_state[state_key] = load_existing_review_rows(workspace)

    review_rows: list[dict[str, Any]] = st.session_state[state_key]
    reviewed_by = st.sidebar.text_input(
        "Reviewed by",
        value=os.environ.get("USER", "local_reviewer"),
    )
    overwrite_evidence = st.sidebar.checkbox(
        "Overwrite evidence.jsonl",
        value=overwrite_default,
    )
    st.sidebar.caption(str(workspace.export_dir))
    counts = review_status_counts(review_rows)
    st.sidebar.metric("Approved", counts[STATUS_APPROVED])
    st.sidebar.metric("Rejected", counts[STATUS_REJECTED])
    st.sidebar.metric("Needs review", counts[STATUS_NEEDS_MORE_REVIEW])
    approved_count = counts[STATUS_APPROVED]
    if approved_count == 0:
        st.sidebar.caption("Export disabled until at least one candidate is approved.")
    if st.sidebar.button(
        "Export approved evidence",
        type="primary",
        disabled=approved_count == 0,
    ):
        try:
            result = write_review_outputs(
                workspace=workspace,
                review_rows=review_rows,
                reviewed_by=reviewed_by,
                overwrite_evidence=overwrite_evidence,
            )
        except (FileExistsError, ValueError) as exc:
            st.sidebar.error(str(exc))
        else:
            st.sidebar.success(
                f"Wrote {result.approved_count} approved rows to {result.evidence_path}"
            )
            st.code("\n".join(command_markdown(workspace.export_id)), language="markdown")

    st.title("Kalshi Evidence Review")
    st.caption(f"Export `{workspace.export_id}`")
    if workspace.manifest.get("terms_review") != "reviewed_public_research_local_only":
        st.warning(
            f"terms_review is `{workspace.manifest.get('terms_review')}`; evidence export "
            "does not clear the terms-review blocker."
        )
    if using_template_fallback(workspace):
        st.error(
            "Showing evidence_template.jsonl placeholder rows because evidence_candidates.jsonl "
            "was not found. These rows are not curated evidence."
        )
    if not review_rows:
        st.info("No evidence candidates or template rows were found.")
        return

    candidates_by_market: dict[str, list[dict[str, Any]]] = {}
    for row in review_rows:
        candidates_by_market.setdefault(str(row.get("market_ticker") or ""), []).append(row)

    first_expanded_ticker = first_market_to_expand(workspace.markets, candidates_by_market)
    for market in workspace.markets:
        ticker = str(market["market_ticker"])
        market_candidates = candidates_by_market.get(ticker, [])
        with st.expander(
            f"{ticker} - {len(market_candidates)} candidates",
            expanded=ticker == first_expanded_ticker,
        ):
            render_market_summary(st, market)
            for candidate in market_candidates:
                render_candidate_form(
                    st=st,
                    candidate=candidate,
                    market=market,
                    reviewed_by=reviewed_by,
                    state_rows=review_rows,
                    workspace=workspace,
                )


def using_template_fallback(workspace: ReviewWorkspace) -> bool:
    return (
        workspace.candidate_source_path is not None
        and workspace.candidate_source_path.name == DEFAULT_TEMPLATE_FILE
    )


def first_market_to_expand(
    markets: tuple[dict[str, Any], ...],
    candidates_by_market: dict[str, list[dict[str, Any]]],
) -> str | None:
    for market in markets:
        ticker = str(market["market_ticker"])
        if any(
            normalized_status(candidate.get("reviewer_status"))
            in {STATUS_UNREVIEWED, STATUS_NEEDS_MORE_REVIEW}
            for candidate in candidates_by_market.get(ticker, [])
        ):
            return ticker
    return str(markets[0]["market_ticker"]) if markets else None


def render_market_summary(st: Any, market: dict[str, Any]) -> None:
    ticker = text_or_empty(market.get("market_ticker")) or "unknown_market"
    for label, field in MARKET_TIMESTAMP_FIELDS:
        st.text_input(
            label,
            value=text_or_empty(market.get(field)) or "missing",
            disabled=True,
            key=f"{ticker}_market_{field}",
        )

    context_cols = st.columns(3)
    context_cols[0].metric("Result", text_or_empty(market.get("result")) or "missing")
    context_cols[1].metric("Candle count", str(market.get("candle_count") or 0))
    context_cols[2].text_input(
        "market_ticker",
        value=text_or_empty(market.get("market_ticker")),
        disabled=True,
        key=f"{ticker}_market_ticker",
    )

    st.text_area(
        "title",
        value=text_or_empty(market.get("title")),
        height=70,
        disabled=True,
        key=f"{ticker}_market_title",
    )
    subtitle = text_or_none(market.get("subtitle"))
    if subtitle:
        st.text_area(
            "subtitle",
            value=subtitle,
            height=70,
            disabled=True,
            key=f"{ticker}_market_subtitle",
        )
    st.text_area(
        "rules_primary",
        value=text_or_empty(market.get("rules_primary")),
        height=120,
        disabled=True,
        key=f"{ticker}_market_rules_primary",
    )
    secondary = text_or_none(market.get("rules_secondary"))
    if secondary:
        st.text_area(
            "rules_secondary",
            value=secondary,
            height=120,
            disabled=True,
            key=f"{ticker}_market_rules_secondary",
        )


def render_candidate_form(
    *,
    st: Any,
    candidate: dict[str, Any],
    market: dict[str, Any],
    reviewed_by: str,
    state_rows: list[dict[str, Any]],
    workspace: ReviewWorkspace,
) -> None:
    validation = validate_candidate_for_approval(candidate, market)
    title = text_or_empty(candidate.get("title")) or candidate["candidate_id"]
    st.markdown(f"#### {candidate.get('evidence_id')} - {title}")
    if validation.blocking_errors:
        st.error("Blocking: " + "; ".join(validation.blocking_errors))
    if validation.warnings:
        st.warning("Warnings: " + "; ".join(validation.warnings))
    with st.form(f"review_form_{candidate['candidate_id']}"):
        col1, col2 = st.columns(2)
        updated = dict(candidate)
        with col1:
            for field in (
                "source",
                "title",
                "url",
                "published_at",
                "retrieved_at",
                "timestamp_status",
                "evidence_type",
                "supports_side",
            ):
                updated[field] = st.text_input(
                    field,
                    value=text_or_empty(candidate.get(field)),
                    key=f"{candidate['candidate_id']}_{field}",
                )
            updated["relevance_score"] = st.number_input(
                "relevance_score",
                min_value=0.0,
                max_value=1.0,
                value=optional_float(candidate.get("relevance_score")) or 0.0,
                step=0.05,
                key=f"{candidate['candidate_id']}_relevance_score",
            )
            updated["credibility_score"] = st.number_input(
                "credibility_score",
                min_value=0.0,
                max_value=1.0,
                value=optional_float(candidate.get("credibility_score")) or 0.0,
                step=0.05,
                key=f"{candidate['candidate_id']}_credibility_score",
            )
        with col2:
            updated["summary"] = st.text_area(
                "summary",
                value=text_or_empty(candidate.get("summary")),
                height=120,
                key=f"{candidate['candidate_id']}_summary",
            )
            updated["curator_notes"] = st.text_area(
                "curator_notes",
                value=text_or_empty(candidate.get("curator_notes")),
                height=90,
                key=f"{candidate['candidate_id']}_curator_notes",
            )
            updated["reviewer_note"] = st.text_area(
                "reviewer_note",
                value=text_or_empty(candidate.get("reviewer_note")),
                height=90,
                key=f"{candidate['candidate_id']}_reviewer_note",
            )
            updated["rejection_reason"] = st.text_area(
                "rejection_reason",
                value=text_or_empty(candidate.get("rejection_reason")),
                height=90,
                key=f"{candidate['candidate_id']}_rejection_reason",
            )
        approve, reject, needs_review = st.columns(3)
        approve_clicked = approve.form_submit_button("Approve")
        reject_clicked = reject.form_submit_button("Reject")
        needs_review_clicked = needs_review.form_submit_button("Needs more review")
        if approve_clicked:
            approval_validation = validate_candidate_for_approval(updated, market)
            if approval_validation.can_approve:
                updated["reviewer_status"] = STATUS_APPROVED
                updated["reviewed_at"] = canonical_timestamp(utc_now())
                updated["reviewed_by"] = reviewed_by
                replace_review_row(state_rows, updated)
                persist_review_state(workspace, state_rows, reviewed_by)
                st.success("Approved")
            else:
                replace_review_row(state_rows, updated)
                persist_review_state(workspace, state_rows, reviewed_by)
                st.error("; ".join(approval_validation.blocking_errors))
        elif reject_clicked:
            if not text_or_none(updated.get("rejection_reason")):
                replace_review_row(state_rows, updated)
                persist_review_state(workspace, state_rows, reviewed_by)
                st.error("rejection_reason is required before rejecting evidence")
            else:
                updated["reviewer_status"] = STATUS_REJECTED
                updated["reviewed_at"] = canonical_timestamp(utc_now())
                updated["reviewed_by"] = reviewed_by
                replace_review_row(state_rows, updated)
                persist_review_state(workspace, state_rows, reviewed_by)
                st.info("Rejected")
        elif needs_review_clicked:
            updated["reviewer_status"] = STATUS_NEEDS_MORE_REVIEW
            updated["reviewed_at"] = canonical_timestamp(utc_now())
            updated["reviewed_by"] = reviewed_by
            replace_review_row(state_rows, updated)
            persist_review_state(workspace, state_rows, reviewed_by)
            st.info("Marked needs more review")


def persist_review_state(
    workspace: ReviewWorkspace,
    review_rows: list[dict[str, Any]],
    reviewed_by: str,
) -> None:
    markets_by_ticker = workspace.markets_by_ticker
    validations = {
        str(row["candidate_id"]): validate_candidate_for_approval(
            row,
            markets_by_ticker.get(str(row.get("market_ticker") or "")),
        )
        for row in review_rows
    }
    payload = build_review_state_payload(
        workspace=workspace,
        review_rows=review_rows,
        reviewed_by=reviewed_by,
        reviewed_at=canonical_timestamp(utc_now()),
        validations=validations,
    )
    (workspace.export_dir / REVIEW_STATE_JSON).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_existing_review_rows(workspace: ReviewWorkspace) -> list[dict[str, Any]]:
    state_path = workspace.export_dir / REVIEW_STATE_JSON
    if not state_path.exists():
        return [dict(row) for row in workspace.candidates]
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [dict(row) for row in workspace.candidates]
    existing_by_id = {
        str(row.get("candidate_id")): row
        for row in payload.get("candidates", [])
        if isinstance(row, dict) and row.get("candidate_id")
    }
    rows: list[dict[str, Any]] = []
    for candidate in workspace.candidates:
        candidate_id = str(candidate["candidate_id"])
        merged = dict(candidate)
        if candidate_id in existing_by_id:
            merged.update(existing_by_id[candidate_id])
        rows.append(merged)
    return rows


def review_session_state_key(workspace: ReviewWorkspace) -> str:
    return "evidence_review_rows::" + "::".join(
        [
            str(workspace.export_dir),
            candidate_source_fingerprint(workspace.candidate_source_path),
        ]
    )


def candidate_source_fingerprint(path: Path | None) -> str:
    if path is None:
        return "none"
    try:
        stat = path.stat()
    except FileNotFoundError:
        return f"{path}:missing"
    return f"{path}:{stat.st_mtime_ns}:{stat.st_size}"


def replace_review_row(rows: list[dict[str, Any]], updated: dict[str, Any]) -> None:
    for index, row in enumerate(rows):
        if row.get("candidate_id") == updated.get("candidate_id"):
            rows[index] = updated
            return
    rows.append(updated)


def resolve_candidate_source(
    *,
    export_dir: Path,
    candidates_file: str | Path,
    template_file: str | Path,
) -> Path | None:
    candidates_path = resolve_relative_to_export(export_dir, candidates_file)
    template_path = resolve_relative_to_export(export_dir, template_file)
    if candidates_path.exists():
        return candidates_path
    if template_path.exists():
        return template_path
    return None


def resolve_relative_to_export(export_dir: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return export_dir / path


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path} must contain one JSON object"
        raise ValueError(msg)
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            msg = f"{path} line {line_number} must contain a JSON object"
            raise ValueError(msg)
        rows.append(payload)
    return rows


def group_candles_by_market(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = required_text(row, "market_ticker")
        grouped.setdefault(ticker, []).append(row)
    return grouped


def json_object_or_empty(value: object) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        payload = json.loads(value)
        if isinstance(payload, dict):
            return payload
    msg = "metadata must be a JSON object"
    raise ValueError(msg)


def required_text(row: dict[str, Any], field: str) -> str:
    value = text_or_none(row.get(field))
    if value is None:
        raise ValueError(f"missing required field: {field}")
    return value


def text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def text_or_empty(value: object) -> str:
    return text_or_none(value) or ""


def optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(value: object) -> datetime | None:
    text = text_or_none(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC).replace(microsecond=0)


def canonical_or_none(value: object) -> str | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return canonical_timestamp(parsed)


def canonical_timestamp(value: datetime | None) -> str:
    if value is None:
        raise ValueError("timestamp is required")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def looks_date_only(value: object) -> bool:
    text = text_or_none(value)
    return bool(text and DATE_ONLY_RE.match(text))


def has_placeholder(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("placeholder") is True or value.get("replace_before_import") is True:
            return True
        return any(has_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    return False


def domain_from_url(url: str | None) -> str | None:
    text = text_or_none(url)
    if text is None or "://" not in text:
        return None
    rest = text.split("://", 1)[1]
    host = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].strip("[]").lower()
    return host or None


def looks_private_or_authenticated(
    candidate: dict[str, Any],
    domain: str | None,
) -> bool:
    metadata = json_object_or_empty(candidate.get("metadata"))
    if metadata.get("private_or_authenticated_source") is True:
        return True
    if metadata.get("source_public") is False:
        return True
    url = text_or_empty(candidate.get("url")).lower()
    source = text_or_empty(candidate.get("source")).lower()
    combined = " ".join([url, source, json.dumps(metadata, sort_keys=True).lower()])
    if any(url.startswith(prefix) for prefix in PRIVATE_URL_PREFIXES):
        return True
    if domain in PRIVATE_HOSTS:
        return True
    if domain and (
        domain.startswith("10.")
        or domain.startswith("192.168.")
        or domain.startswith("172.16.")
        or domain.endswith(".local")
    ):
        return True
    return any(marker in combined for marker in PRIVATE_SOURCE_MARKERS)


def appears_to_be_settlement_evidence(candidate: dict[str, Any]) -> bool:
    evidence_type = text_or_empty(candidate.get("evidence_type")).lower()
    text = " ".join(
        [
            evidence_type,
            text_or_empty(candidate.get("source")).lower(),
            text_or_empty(candidate.get("title")).lower(),
            text_or_empty(candidate.get("summary")).lower(),
            text_or_empty(candidate.get("curator_notes")).lower(),
        ]
    )
    normalized_type = evidence_type.replace("-", "_").replace(" ", "_")
    if any(marker in normalized_type for marker in SETTLEMENT_TYPE_MARKERS):
        return True
    return any(marker in text for marker in SETTLEMENT_TEXT_MARKERS)


def domain_is_weak(domain: str | None) -> bool:
    if domain is None:
        return False
    return any(marker in domain for marker in WEAK_SOURCE_MARKERS)


def source_is_weak(value: object) -> bool:
    source = text_or_empty(value).lower()
    return any(marker in source for marker in ("social", "forum", "blog", "wiki"))


def summary_too_short(value: object) -> bool:
    summary = text_or_empty(value)
    if not summary:
        return False
    return len(summary) < 40 or len(summary.split()) < 8


def domain_is_unknown(domain: str | None) -> bool:
    if domain is None:
        return True
    return "." not in domain or domain.endswith(".invalid") or domain.startswith("example.")


def normalized_status(value: object) -> str:
    status = text_or_empty(value).lower().replace("-", "_").replace(" ", "_")
    if status in REVIEW_STATUSES:
        return status
    return STATUS_UNREVIEWED


def review_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in REVIEW_STATUSES}
    for row in rows:
        counts[normalized_status(row.get("reviewer_status"))] += 1
    return counts


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return f"{prefix}_{sha256(encoded).hexdigest()[:16]}"


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    sys.exit(main())
