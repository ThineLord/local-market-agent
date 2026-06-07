from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

FILTER_LOSS_UNRESOLVED = "unresolved_loss"
FILTER_LOSS_NOT_FINALIZED = "not_finalized_loss"
FILTER_LOSS_NON_BINARY = "non_binary_loss"
FILTER_LOSS_OTHER = "other_filter_loss"


@dataclass
class CollectorDiagnostics:
    discovered_count: int = 0
    pre_filter_category_counts: Counter[str] = field(default_factory=Counter)
    post_filter_category_counts: Counter[str] = field(default_factory=Counter)
    selected_category_counts: Counter[str] = field(default_factory=Counter)
    filter_losses: Counter[str] = field(default_factory=Counter)
    candle_attempt_count: int = 0
    candle_success_count: int = 0
    candle_failure_count: int = 0
    candle_failure_reasons: Counter[str] = field(default_factory=Counter)
    quota_targets: dict[str, int] = field(default_factory=dict)
    quota_filled: Counter[str] = field(default_factory=Counter)

    def record_pre_filter_category(self, category: str) -> None:
        self.discovered_count += 1
        self.pre_filter_category_counts[category] += 1

    def record_post_filter_category(self, category: str) -> None:
        self.post_filter_category_counts[category] += 1

    def record_selected_category(self, category: str) -> None:
        self.selected_category_counts[category] += 1
        self.quota_filled[category] += 1

    def record_filter_loss(self, reason: str, *, count: int = 1) -> None:
        self.filter_losses[reason] += count

    def record_candle_attempt(self, *, success: bool, failure_reason: str | None = None) -> None:
        self.candle_attempt_count += 1
        if success:
            self.candle_success_count += 1
            return
        self.candle_failure_count += 1
        self.candle_failure_reasons[failure_reason or "unknown"] += 1

    def set_quota_targets(self, quota_targets: Mapping[str, int]) -> None:
        self.quota_targets = {
            str(category): int(target) for category, target in quota_targets.items()
        }

    def quota_shortfalls(self) -> dict[str, int]:
        return {
            category: max(0, target - self.quota_filled.get(category, 0))
            for category, target in sorted(self.quota_targets.items())
            if target > self.quota_filled.get(category, 0)
        }

    def availability_limitations(self) -> list[dict[str, Any]]:
        limitations: list[dict[str, Any]] = []
        for category, missing_count in self.quota_shortfalls().items():
            reasons = []
            if self.pre_filter_category_counts.get(category, 0) < self.quota_targets[category]:
                reasons.append("pre_filter_source_count_below_quota")
            if self.post_filter_category_counts.get(category, 0) < self.quota_targets[category]:
                reasons.append("post_filter_count_below_quota")
            if self.selected_category_counts.get(category, 0) < self.quota_targets[category]:
                reasons.append("selected_count_below_quota")
            if self.candle_failure_count:
                reasons.append("candle_failures_observed")
            limitations.append(
                {
                    "category": category,
                    "quota_target": self.quota_targets[category],
                    "quota_filled": self.quota_filled.get(category, 0),
                    "missing_count": missing_count,
                    "classification": "available_source_limitation",
                    "reasons": reasons or ["unknown"],
                    "not_a_true_category_effect": True,
                }
            )
        return limitations

    def as_dict(self) -> dict[str, Any]:
        return {
            "discovered_count": self.discovered_count,
            "pre_filter_category_counts": _counter_dict(self.pre_filter_category_counts),
            "post_filter_category_counts": _counter_dict(self.post_filter_category_counts),
            "selected_category_counts": _counter_dict(self.selected_category_counts),
            "filter_losses": {
                "resolved_finalized_binary": _counter_dict(self.filter_losses),
                "unresolved_loss": self.filter_losses.get(FILTER_LOSS_UNRESOLVED, 0),
                "not_finalized_loss": self.filter_losses.get(
                    FILTER_LOSS_NOT_FINALIZED,
                    0,
                ),
                "non_binary_loss": self.filter_losses.get(FILTER_LOSS_NON_BINARY, 0),
            },
            "candle_attempt_count": self.candle_attempt_count,
            "candle_success_count": self.candle_success_count,
            "candle_failure_count": self.candle_failure_count,
            "candle_failure_reasons": _counter_dict(self.candle_failure_reasons),
            "quota_targets": dict(sorted(self.quota_targets.items())),
            "quota_filled": _counter_dict(self.quota_filled),
            "quota_shortfalls": self.quota_shortfalls(),
            "availability_limitations": self.availability_limitations(),
        }


def build_collector_diagnostics(
    *,
    pre_filter_categories: Iterable[str] = (),
    post_filter_categories: Iterable[str] = (),
    selected_categories: Iterable[str] = (),
    filter_losses: Mapping[str, int] | None = None,
    candle_results: Iterable[tuple[bool, str | None]] = (),
    quota_targets: Mapping[str, int] | None = None,
) -> CollectorDiagnostics:
    diagnostics = CollectorDiagnostics()
    for category in pre_filter_categories:
        diagnostics.record_pre_filter_category(category)
    for category in post_filter_categories:
        diagnostics.record_post_filter_category(category)
    for category in selected_categories:
        diagnostics.record_selected_category(category)
    for reason, count in (filter_losses or {}).items():
        diagnostics.record_filter_loss(str(reason), count=int(count))
    for success, failure_reason in candle_results:
        diagnostics.record_candle_attempt(success=success, failure_reason=failure_reason)
    diagnostics.set_quota_targets(quota_targets or {})
    return diagnostics


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted((str(key), int(value)) for key, value in counter.items()))
