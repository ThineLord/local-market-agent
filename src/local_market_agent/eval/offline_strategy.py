from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import Any

from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.config import RiskConfig
from local_market_agent.eval.forecast_assessment import (
    ForecastAssessmentEvaluator,
    assign_calibration_bucket,
)
from local_market_agent.operations.phase7_historical_dataset import (
    HistoricalDataset,
    HistoricalMarketRecord,
    load_historical_dataset,
)
from local_market_agent.schemas.models import (
    EvidenceItem,
    RecommendedAction,
    ResearchBrief,
    SignalAction,
    deterministic_model_context,
)
from local_market_agent.strategy import (
    PredictionMarketEdgeStrategy,
    PredictionMarketV2CandidateStrategy,
)

BASELINE_ALWAYS_OBSERVE = "always_observe"
BASELINE_MARKET_IMPLIED = "market_implied_probability_only"
BASELINE_STRATEGY_V1 = "strategy_v1"
BASELINE_STRATEGY_V2 = "strategy_v2_candidate"
BASELINE_HINT_THRESHOLD = "hint_threshold_policy"
BASELINE_RANDOM_NAIVE = "random_naive_policy"

REQUIRED_BASELINES = [
    BASELINE_ALWAYS_OBSERVE,
    BASELINE_MARKET_IMPLIED,
    BASELINE_STRATEGY_V1,
    BASELINE_STRATEGY_V2,
    BASELINE_HINT_THRESHOLD,
    BASELINE_RANDOM_NAIVE,
]

SAMPLE_SIZE_TARGETS = {
    "resolved_binary_markets": 25,
    "evaluation_rows": 250,
    "candidate_forecasts": 50,
    "closed_paper_trades": 30,
    "settlement_coverage_pct": 1.0,
    "evidence_timestamp_coverage_pct": 0.95,
}

DEFAULT_RANDOM_SEED = 20260605
LOG_LOSS_EPSILON = 1e-6
PAPER_UNIT_QUANTITY = 1.0
BRIER_IMPROVEMENT_THRESHOLD = 0.01
MIN_STRUCTURED_PROBABILITY_COMPLETENESS = 0.95
MIN_ABSTENTION_RATE = 0.20
MAX_ABSTENTION_RATE = 0.90
MAX_LARGE_BUCKET_CALIBRATION_GAP = 0.20
MIN_LARGE_BUCKET_ROWS = 20
GATE_PASS = "pass"
GATE_FAIL = "fail"
GATE_NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class StrategyOfflineEvaluationResult:
    json_path: Path
    markdown_path: Path
    report: dict[str, Any]
    json_checksum: str
    markdown_checksum: str


def run_strategy_offline_evaluation(
    *,
    historical_file: str | Path,
    output_dir: str | Path = Path("data/reports/strategy_eval"),
    market_id: str | None = None,
    random_seed: int = DEFAULT_RANDOM_SEED,
    risk_config: RiskConfig | None = None,
) -> StrategyOfflineEvaluationResult:
    dataset = load_historical_dataset(historical_file)
    selected_market_id = market_id or dataset.default_market_id()
    records = list(dataset.records_for_market(selected_market_id))
    if not records:
        msg = "offline strategy evaluation requires at least one historical row"
        raise ValueError(msg)

    risk_config = risk_config or RiskConfig()
    market_outcomes = _market_outcomes(records)
    report_id = _report_id(dataset.path, records, random_seed, selected_market_id)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    baselines = _evaluate_baselines(
        records=records,
        market_outcomes=market_outcomes,
        random_seed=random_seed,
        risk_config=risk_config,
    )
    _attach_benchmark_relative_returns(baselines)

    dataset_summary = _dataset_summary(
        dataset=dataset,
        records=records,
        selected_market_id=selected_market_id,
        market_outcomes=market_outcomes,
        baselines=baselines,
    )
    safety_summary = _safety_summary()
    acceptance_gate = evaluate_strategy_acceptance_gate(
        dataset_summary=dataset_summary,
        baselines=baselines,
        safety=safety_summary,
    )
    dataset_summary["superiority_claim_allowed"] = acceptance_gate[
        "superiority_claim_allowed"
    ]
    dataset_summary["superiority_claim"] = acceptance_gate["recommendation"]
    safety_summary["superiority_claim_allowed"] = acceptance_gate[
        "superiority_claim_allowed"
    ]
    report = {
        "report_id": report_id,
        "phase": "PR-V2-4",
        "created_at": datetime.now(UTC).isoformat(),
        "historical_file": str(dataset.path),
        "random_seed": random_seed,
        "paper_fill_assumptions": {
            "scope": "offline_simulated_one_unit_trades",
            "yes_entry_price": "best_ask",
            "no_entry_price": "1 - best_bid",
            "fee_rate": risk_config.paper_fee_rate,
            "slippage_bps": 0.0,
            "ledger_mutation": False,
        },
        "dataset": dataset_summary,
        "baselines": baselines,
        "acceptance_gate": acceptance_gate,
        "safety": safety_summary,
    }

    json_path = output_root / f"{report_id}.json"
    markdown_path = output_root / f"{report_id}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    return StrategyOfflineEvaluationResult(
        json_path=json_path,
        markdown_path=markdown_path,
        report=report,
        json_checksum=_file_checksum(json_path),
        markdown_checksum=_file_checksum(markdown_path),
    )


def evaluate_strategy_acceptance_gate(
    *,
    dataset_summary: dict[str, Any],
    baselines: dict[str, dict[str, Any]],
    safety: dict[str, Any],
) -> dict[str, Any]:
    failed_gates: list[str] = []
    warning_gates: list[str] = []
    gate_checks: dict[str, dict[str, Any]] = {}
    dataset_label = str(dataset_summary["classification"])
    dataset_preconditions_failed = _dataset_preconditions_failed(dataset_summary)

    for gate_name, gate in dataset_summary["sample_size_gates"].items():
        _record_gate(
            gate_checks,
            failed_gates,
            name=f"dataset.{gate_name}",
            passed=bool(gate["passed"]),
            observed=gate["observed"],
            required=gate["required"],
            reason="dataset minimum requirement",
        )

    v1 = baselines[BASELINE_STRATEGY_V1]
    v2 = baselines[BASELINE_STRATEGY_V2]
    market = baselines[BASELINE_MARKET_IMPLIED]
    metric_deltas = _metric_deltas(strategy_v1=v1, strategy_v2=v2, market=market)

    metric_failures = _forecast_quality_gate_failures(
        strategy_v1=v1,
        strategy_v2=v2,
        market=market,
        metric_deltas=metric_deltas,
    )
    metric_failures.extend(
        _paper_outcome_gate_failures(
            strategy_v1=v1,
            strategy_v2=v2,
            metric_deltas=metric_deltas,
        )
    )
    metric_failures.extend(_abstention_gate_failures(strategy_v2=v2))
    for failure in metric_failures:
        if dataset_preconditions_failed:
            warning_gates.append(f"diagnostic_only.{failure}")
        else:
            failed_gates.append(failure)

    safety_failures = _safety_gate_failures(safety=safety, strategy_v2=v2)
    failed_gates.extend(safety_failures)
    warning_gates.extend(_replay_warning_gates(strategy_v2=v2))

    if safety_failures:
        gate_status = GATE_FAIL
    elif dataset_preconditions_failed:
        gate_status = GATE_NOT_APPLICABLE
    elif failed_gates:
        gate_status = GATE_FAIL
    else:
        gate_status = GATE_PASS

    superiority_claim_allowed = gate_status == GATE_PASS
    failed_gates = list(dict.fromkeys(failed_gates))
    warning_gates = list(dict.fromkeys(warning_gates))
    return {
        "gate_status": gate_status,
        "superiority_claim_allowed": superiority_claim_allowed,
        "dataset_label": dataset_label,
        "failed_gates": failed_gates,
        "warning_gates": warning_gates,
        "metric_deltas": metric_deltas,
        "strategy_v1_summary": _baseline_summary(v1),
        "strategy_v2_summary": _baseline_summary(v2),
        "baseline_summaries": {
            name: _baseline_summary(baseline)
            for name, baseline in sorted(baselines.items())
        },
        "gate_checks": gate_checks,
        "recommendation": _gate_recommendation(
            gate_status=gate_status,
            failed_gates=failed_gates,
            warning_gates=warning_gates,
        ),
    }


def _safety_summary() -> dict[str, Any]:
    return {
        "paper_only": True,
        "local_only": True,
        "evaluation_only": True,
        "can_create_orders": False,
        "mutates_paper_trading_state": False,
        "strategy_v2_candidate_policy_included": True,
        "strategy_v2_production_enabled": False,
        "phase8_started": False,
        "live_trading_added": False,
        "scheduler_added": False,
        "direct_llm_to_order_path": False,
    }


def _evaluate_baselines(
    *,
    records: list[HistoricalMarketRecord],
    market_outcomes: dict[str, str],
    random_seed: int,
    risk_config: RiskConfig,
) -> dict[str, dict[str, Any]]:
    rng = random.Random(random_seed)
    return {
        baseline: _evaluate_baseline(
            baseline,
            records=records,
            market_outcomes=market_outcomes,
            rng=rng,
            risk_config=risk_config,
        )
        for baseline in REQUIRED_BASELINES
    }


def _evaluate_baseline(
    baseline: str,
    *,
    records: list[HistoricalMarketRecord],
    market_outcomes: dict[str, str],
    rng: random.Random,
    risk_config: RiskConfig,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    evaluator = ForecastAssessmentEvaluator()
    strategy = PredictionMarketEdgeStrategy(risk_config)
    strategy_v2 = PredictionMarketV2CandidateStrategy(risk_config=risk_config)

    for index, record in enumerate(records, start=1):
        seed = f"strategy-eval:{baseline}:{record.market_id}:{record.record_date.isoformat()}"
        with deterministic_model_context(seed=seed, now=record.timestamp):
            rows.append(
                _evaluate_row(
                    baseline,
                    record=record,
                    row_number=index,
                    market_outcomes=market_outcomes,
                    evaluator=evaluator,
                    strategy=strategy,
                    strategy_v2=strategy_v2,
                    rng=rng,
                    risk_config=risk_config,
                )
            )

    metrics = {
        "activity": _activity_metrics(rows),
        "forecast": _forecast_metrics(rows),
        "paper_outcome": _paper_outcome_metrics(rows),
        "risk_reliability": _risk_reliability_metrics(rows),
    }
    return {
        "baseline": baseline,
        "description": _baseline_description(baseline),
        "metrics": metrics,
        "rows": rows,
    }


def _evaluate_row(
    baseline: str,
    *,
    record: HistoricalMarketRecord,
    row_number: int,
    market_outcomes: dict[str, str],
    evaluator: ForecastAssessmentEvaluator,
    strategy: PredictionMarketEdgeStrategy,
    strategy_v2: PredictionMarketV2CandidateStrategy,
    rng: random.Random,
    risk_config: RiskConfig,
) -> dict[str, Any]:
    snapshot = record.to_snapshot()
    outcome = market_outcomes.get(record.market_id)
    action_reason = "baseline_not_evaluated"

    if baseline == BASELINE_ALWAYS_OBSERVE:
        probability = None
        action = SignalAction.OBSERVE
        action_reason = "always_observe_baseline"
        brief = _baseline_brief(
            baseline=baseline,
            record=record,
            snapshot_id=snapshot.snapshot_id,
            probability=probability,
            action=action,
            rationale="Always-observe baseline records no structured forecast.",
        )
        assessment = evaluator.evaluate(
            brief,
            snapshot,
            evidence_metadata={
                "probability_source": "missing",
                "market_source": "historical-file",
                "data_mode": "historical_local_dataset",
            },
        )
    elif baseline == BASELINE_MARKET_IMPLIED:
        probability = record.implied_probability
        action = SignalAction.OBSERVE
        action_reason = "market_implied_baseline_never_claims_edge"
        brief = _baseline_brief(
            baseline=baseline,
            record=record,
            snapshot_id=snapshot.snapshot_id,
            probability=probability,
            action=action,
            rationale="Market-implied baseline uses only local market probability.",
        )
        assessment = evaluator.evaluate(
            brief,
            snapshot,
            evidence_metadata={
                "probability_source": "market_implied_only",
                "market_source": "historical-file",
                "data_mode": "historical_local_dataset",
            },
        )
    elif baseline == BASELINE_STRATEGY_V1:
        brief = ResearchBriefGenerator().generate(snapshot, list(record.evidence))
        signal = strategy.generate_signal(brief, snapshot)
        probability = brief.estimated_probability
        action = signal.action
        action_reason = signal.rationale
        assessment = evaluator.evaluate(
            brief,
            snapshot,
            evidence_metadata={
                "market_source": "historical-file",
                "data_mode": "historical_local_dataset",
                "provider_label": "mock",
            },
        )
    elif baseline == BASELINE_STRATEGY_V2:
        brief = ResearchBriefGenerator().generate(snapshot, list(record.evidence))
        assessment = evaluator.evaluate(
            brief,
            snapshot,
            evidence_metadata={
                "market_source": "historical-file",
                "data_mode": "historical_local_dataset",
                "provider_label": "mock",
            },
        )
        signal = strategy_v2.generate_signal(assessment, snapshot)
        probability = assessment.estimated_probability_yes
        action = signal.action
        action_reason = signal.rationale
    elif baseline == BASELINE_HINT_THRESHOLD:
        probability = _weighted_probability_hint(list(record.evidence))
        action, action_reason = _hint_threshold_action(
            probability=probability,
            record=record,
            risk_config=risk_config,
        )
        brief = _baseline_brief(
            baseline=baseline,
            record=record,
            snapshot_id=snapshot.snapshot_id,
            probability=probability,
            action=action,
            rationale="Hint-threshold baseline uses only local evidence probability_hint values.",
        )
        assessment = evaluator.evaluate(
            brief,
            snapshot,
            evidence_metadata={
                "probability_source": "historical_hint"
                if probability is not None
                else "missing",
                "market_source": "historical-file",
                "data_mode": "historical_local_dataset",
            },
        )
    elif baseline == BASELINE_RANDOM_NAIVE:
        probability = round(rng.random(), 4)
        action = rng.choice(
            [
                SignalAction.OBSERVE,
                SignalAction.PAPER_BUY_YES,
                SignalAction.PAPER_BUY_NO,
            ]
        )
        action_reason = "fixed_seed_random_naive_baseline"
        brief = _baseline_brief(
            baseline=baseline,
            record=record,
            snapshot_id=snapshot.snapshot_id,
            probability=probability,
            action=action,
            rationale="Fixed-seed random/naive baseline for tiny-sample artifact checks.",
        )
        assessment = evaluator.evaluate(
            brief,
            snapshot,
            evidence_metadata={
                "market_source": "historical-file",
                "data_mode": "historical_local_dataset",
                "baseline_probability_source": "fixed_seed_random",
            },
        )
    else:
        msg = f"unsupported offline baseline: {baseline}"
        raise ValueError(msg)

    paper_outcome = _simulate_paper_trade(
        action=action,
        record=record,
        market_outcome=outcome,
        risk_config=risk_config,
    )
    rejection_reasons = list(assessment.rejection_reasons)
    if baseline == BASELINE_STRATEGY_V2 and action in {
        SignalAction.OBSERVE,
        SignalAction.SKIP,
    }:
        rejection_reasons.extend(
            str(reason)
            for reason in signal.metadata.get("strategy_v2_reasons", [])
        )
    if paper_outcome.get("rejection_reason"):
        rejection_reasons.append(str(paper_outcome["rejection_reason"]))

    return {
        "row_number": row_number,
        "date": record.record_date.isoformat(),
        "timestamp": record.timestamp.isoformat(),
        "market_id": record.market_id,
        "forecast_probability": probability,
        "calibration_bucket": assign_calibration_bucket(probability),
        "settlement_outcome": outcome,
        "row_settlement_outcome": record.settlement_outcome,
        "action": action.value,
        "action_reason": action_reason,
        "forecast_assessment": assessment.model_dump(mode="json"),
        "paper_outcome": paper_outcome,
        "rejection_reasons": rejection_reasons,
    }


def _baseline_brief(
    *,
    baseline: str,
    record: HistoricalMarketRecord,
    snapshot_id: str,
    probability: float | None,
    action: SignalAction,
    rationale: str,
) -> ResearchBrief:
    return ResearchBrief(
        market_id=record.market_id,
        snapshot_id=snapshot_id,
        created_at=record.timestamp,
        thesis=f"{baseline} offline evaluation baseline.",
        rationale=rationale,
        evidence=list(record.evidence),
        counter_evidence=[],
        uncertainty_notes=[
            "Offline baseline diagnostic only; not a Strategy v2 policy."
        ],
        confidence=1.0 if probability is not None else 0.0,
        evidence_quality=_evidence_quality(record.evidence),
        estimated_probability=probability,
        market_implied_probability=record.implied_probability,
        recommended_action=_recommended_action(action),
        must_not_trade_reasons=[],
        resolution_source="local_historical_dataset"
        if record.settlement_outcome is not None
        else None,
        resolution_ambiguity=False,
    )


def _hint_threshold_action(
    *,
    probability: float | None,
    record: HistoricalMarketRecord,
    risk_config: RiskConfig,
) -> tuple[SignalAction, str]:
    if probability is None:
        return SignalAction.OBSERVE, "missing_probability_hint"
    spread = round(record.ask - record.bid, 10)
    threshold = max(risk_config.min_edge, 2 * spread)
    yes_edge = probability - record.implied_probability
    no_edge = record.implied_probability - probability
    yes_ev = probability - record.ask
    no_ev = (1 - probability) - (1 - record.bid)
    if yes_edge >= no_edge and yes_edge >= threshold and yes_ev >= threshold:
        return SignalAction.PAPER_BUY_YES, "historical_hint_yes_edge_clears_threshold"
    if no_edge > yes_edge and no_edge >= threshold and no_ev >= threshold:
        return SignalAction.PAPER_BUY_NO, "historical_hint_no_edge_clears_threshold"
    return SignalAction.OBSERVE, "historical_hint_edge_below_threshold"


def _simulate_paper_trade(
    *,
    action: SignalAction,
    record: HistoricalMarketRecord,
    market_outcome: str | None,
    risk_config: RiskConfig,
) -> dict[str, Any]:
    if action == SignalAction.OBSERVE:
        return {
            "trade": False,
            "closed": False,
            "entry_price": None,
            "quantity": 0.0,
            "fee": 0.0,
            "realized_pnl": None,
            "rejection_reason": None,
        }
    if action == SignalAction.SKIP:
        return {
            "trade": False,
            "closed": False,
            "entry_price": None,
            "quantity": 0.0,
            "fee": 0.0,
            "realized_pnl": None,
            "rejection_reason": "skip_action",
        }
    if action == SignalAction.PAPER_BUY_YES:
        entry_price = record.ask
        winning_outcome = "yes"
    elif action == SignalAction.PAPER_BUY_NO:
        entry_price = 1 - record.bid
        winning_outcome = "no"
    else:
        return {
            "trade": False,
            "closed": False,
            "entry_price": None,
            "quantity": 0.0,
            "fee": 0.0,
            "realized_pnl": None,
            "rejection_reason": f"unsupported_action_{action.value}",
        }

    fee = round(entry_price * PAPER_UNIT_QUANTITY * risk_config.paper_fee_rate, 8)
    if market_outcome is None:
        return {
            "trade": True,
            "closed": False,
            "entry_price": entry_price,
            "quantity": PAPER_UNIT_QUANTITY,
            "fee": fee,
            "realized_pnl": None,
            "rejection_reason": "missing_settlement",
        }
    gross_pnl = (
        (1 - entry_price) * PAPER_UNIT_QUANTITY
        if market_outcome == winning_outcome
        else -entry_price * PAPER_UNIT_QUANTITY
    )
    return {
        "trade": True,
        "closed": True,
        "entry_price": round(entry_price, 8),
        "quantity": PAPER_UNIT_QUANTITY,
        "fee": fee,
        "realized_pnl": round(gross_pnl - fee, 8),
        "rejection_reason": None,
    }


def _activity_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated_rows = len(rows)
    trade_count = sum(1 for row in rows if row["paper_outcome"]["trade"])
    closed_trade_count = sum(1 for row in rows if row["paper_outcome"]["closed"])
    abstention_count = sum(1 for row in rows if row["action"] == SignalAction.OBSERVE.value)
    skip_count = sum(1 for row in rows if row["action"] == SignalAction.SKIP.value)
    rejection_count = sum(1 for row in rows if row["rejection_reasons"])
    missing_probability_count = sum(1 for row in rows if row["forecast_probability"] is None)
    missing_evidence_count = sum(
        1 for row in rows if row["forecast_assessment"]["missing_evidence"]
    )
    missing_settlement_count = sum(1 for row in rows if row["settlement_outcome"] is None)
    return {
        "evaluated_rows": evaluated_rows,
        "markets_evaluated": len({row["market_id"] for row in rows}),
        "trade_count": trade_count,
        "closed_trade_count": closed_trade_count,
        "abstention_count": abstention_count,
        "abstention_rate": _rate(abstention_count, evaluated_rows),
        "skip_count": skip_count,
        "rejection_count": rejection_count,
        "failure_count": 0,
        "missing_probability_count": missing_probability_count,
        "missing_evidence_count": missing_evidence_count,
        "missing_settlement_count": missing_settlement_count,
    }


def _forecast_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [
        (float(row["forecast_probability"]), _outcome_yes(row["settlement_outcome"]))
        for row in rows
        if row["forecast_probability"] is not None and row["settlement_outcome"] is not None
    ]
    brier = None
    log_loss = None
    if scored:
        brier = round(sum((probability - outcome) ** 2 for probability, outcome in scored) / len(scored), 8)
        log_loss = round(
            sum(_log_loss(probability, outcome) for probability, outcome in scored)
            / len(scored),
            8,
        )

    complete_count = sum(
        1 for row in rows if row["forecast_assessment"]["structured_output_complete"]
    )
    probability_count = sum(1 for row in rows if row["forecast_probability"] is not None)
    return {
        "brier_score": brier,
        "log_loss": log_loss,
        "log_loss_epsilon": LOG_LOSS_EPSILON,
        "calibration_by_bucket": _calibration_by_bucket(rows),
        "forecast_coverage": _rate(probability_count, len(rows)),
        "structured_probability_completeness_rate": _rate(complete_count, len(rows)),
        "scored_forecast_count": len(scored),
    }


def _paper_outcome_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [
        row["paper_outcome"]
        for row in rows
        if row["paper_outcome"]["closed"]
        and row["paper_outcome"]["realized_pnl"] is not None
    ]
    pnls = [float(outcome["realized_pnl"]) for outcome in closed]
    trade_count = sum(1 for row in rows if row["paper_outcome"]["trade"])
    fee_total = round(
        sum(float(row["paper_outcome"]["fee"]) for row in rows if row["paper_outcome"]["trade"]),
        8,
    )
    gross_profit = round(sum(pnl for pnl in pnls if pnl > 0), 8)
    gross_loss = round(abs(sum(pnl for pnl in pnls if pnl < 0)), 8)
    total_cost = sum(
        float(outcome["entry_price"]) * PAPER_UNIT_QUANTITY + float(outcome["fee"])
        for outcome in closed
        if outcome["entry_price"] is not None
    )
    realized_pnl = round(sum(pnls), 8)
    return {
        "realized_paper_pnl": realized_pnl,
        "total_return": round(realized_pnl / total_cost, 8) if total_cost else 0.0,
        "benchmark_relative_return": None,
        "max_drawdown": _max_drawdown(pnls),
        "win_rate": _rate(sum(1 for pnl in pnls if pnl > 0), len(pnls)) if pnls else None,
        "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss else None,
        "average_trade_pnl": round(sum(pnls) / len(pnls), 8) if pnls else None,
        "median_trade_pnl": round(median(pnls), 8) if pnls else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "fee_total": fee_total,
        "slippage_total": 0.0,
        "slippage_summary": "No slippage applied in PR-V2-2 offline one-unit simulation.",
        "open_position_count": trade_count - len(closed),
    }


def _risk_reliability_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    for row in rows:
        reason_counter.update(row["rejection_reasons"])
        if row["action"] in {SignalAction.OBSERVE.value, SignalAction.SKIP.value}:
            action_counter.update([str(row["action_reason"])])
    provider_failures = reason_counter.get("provider_structured_output_incomplete", 0)
    return {
        "rejection_reasons_by_category": dict(sorted(reason_counter.items())),
        "observe_skip_reasons": dict(sorted(action_counter.items())),
        "provider_structured_output_failure_count": provider_failures,
        "risk_veto_count_by_reason": {},
        "risk_gate_rejection_count_by_reason": {},
        "replay_validation": {
            "applicable": False,
            "reason": "PR-V2-2 harness is pure offline evaluation and does not create replayable run records.",
            "replay_success_rate": None,
            "replay_mutation_count": None,
            "report_checksum_available": True,
        },
        "run_success_rate": 1.0,
        "data_quality_failure_count": 0,
    }


def _calibration_by_bucket(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[tuple[float, float]]] = {
        f"{index / 10:.2f}-{(index + 1) / 10:.2f}": [] for index in range(10)
    }
    for row in rows:
        probability = row["forecast_probability"]
        outcome = row["settlement_outcome"]
        bucket = assign_calibration_bucket(probability)
        if probability is None or outcome is None or bucket is None:
            continue
        buckets[bucket].append((float(probability), _outcome_yes(outcome)))
    return {
        bucket: {
            "row_count": len(values),
            "mean_forecast": _mean([probability for probability, _outcome in values]),
            "observed_yes_rate": _mean([outcome for _probability, outcome in values]),
            "absolute_gap": _absolute_gap(values),
        }
        for bucket, values in buckets.items()
    }


def _dataset_summary(
    *,
    dataset: HistoricalDataset,
    records: list[HistoricalMarketRecord],
    selected_market_id: str | None,
    market_outcomes: dict[str, str],
    baselines: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evaluated_rows = len(records)
    markets = sorted({record.market_id for record in records})
    resolved_markets = sorted(market_outcomes)
    evidence_timestamp_coverage = _evidence_timestamp_coverage(records)
    strategy_v2_metrics = baselines[BASELINE_STRATEGY_V2]["metrics"]
    strategy_v2_closed_trades = strategy_v2_metrics["activity"]["closed_trade_count"]
    strategy_v2_candidate_forecasts = strategy_v2_metrics["forecast"][
        "scored_forecast_count"
    ]
    gates = {
        "resolved_binary_markets": {
            "observed": len(resolved_markets),
            "required": SAMPLE_SIZE_TARGETS["resolved_binary_markets"],
            "passed": len(resolved_markets) >= SAMPLE_SIZE_TARGETS["resolved_binary_markets"],
        },
        "evaluation_rows": {
            "observed": evaluated_rows,
            "required": SAMPLE_SIZE_TARGETS["evaluation_rows"],
            "passed": evaluated_rows >= SAMPLE_SIZE_TARGETS["evaluation_rows"],
        },
        "candidate_forecasts": {
            "observed": strategy_v2_candidate_forecasts,
            "required": SAMPLE_SIZE_TARGETS["candidate_forecasts"],
            "passed": strategy_v2_candidate_forecasts
            >= SAMPLE_SIZE_TARGETS["candidate_forecasts"],
        },
        "closed_paper_trades": {
            "observed": strategy_v2_closed_trades,
            "required": SAMPLE_SIZE_TARGETS["closed_paper_trades"],
            "passed": strategy_v2_closed_trades
            >= SAMPLE_SIZE_TARGETS["closed_paper_trades"],
        },
        "settlement_coverage_pct": {
            "observed": _rate(len(resolved_markets), len(markets)),
            "required": SAMPLE_SIZE_TARGETS["settlement_coverage_pct"],
            "passed": len(resolved_markets) == len(markets),
        },
        "evidence_timestamp_coverage_pct": {
            "observed": evidence_timestamp_coverage,
            "required": SAMPLE_SIZE_TARGETS["evidence_timestamp_coverage_pct"],
            "passed": evidence_timestamp_coverage
            >= SAMPLE_SIZE_TARGETS["evidence_timestamp_coverage_pct"],
        },
    }
    acceptance_eligible = all(gate["passed"] for gate in gates.values())
    classification, detail = _dataset_classification(
        dataset=dataset,
        records=records,
        acceptance_eligible=acceptance_eligible,
    )
    return {
        "historical_file": str(dataset.path),
        "selected_market_id": selected_market_id,
        "classification": classification,
        "classification_detail": detail,
        "evaluated_rows": evaluated_rows,
        "markets_evaluated": len(markets),
        "market_ids": markets,
        "resolved_markets": len(resolved_markets),
        "settlement_coverage": dataset.settlement_coverage,
        "market_settlement_coverage": "full"
        if len(resolved_markets) == len(markets)
        else "none",
        "has_settlement": bool(market_outcomes),
        "warnings": list(dataset.warnings),
        "sample_size_targets": SAMPLE_SIZE_TARGETS,
        "sample_size_gates": gates,
        "acceptance_evaluation_eligible": acceptance_eligible,
        "superiority_claim_allowed": acceptance_eligible,
        "superiority_claim": "blocked: sample-size and acceptance gates not met"
        if not acceptance_eligible
        else "allowed only after holdout comparison gate review",
    }


def _dataset_classification(
    *,
    dataset: HistoricalDataset,
    records: list[HistoricalMarketRecord],
    acceptance_eligible: bool,
) -> tuple[str, str]:
    path_text = str(dataset.path).replace("\\", "/")
    fixture_like = "/fixtures/" in path_text or dataset.path.name.startswith("phase7_historical_5d")
    if fixture_like:
        if dataset.has_settlement:
            return (
                "fixture_smoke",
                "fixture smoke / historical local dataset with settlement but below sample-size target",
            )
        return (
            "fixture_smoke",
            "fixture smoke / historical local dataset without settlement",
        )
    if not dataset.has_settlement:
        return (
            "historical_local_dataset_without_settlement",
            "historical local dataset without settlement",
        )
    if acceptance_eligible:
        return (
            "historical_local_dataset_eligible_for_acceptance_evaluation",
            "historical local dataset eligible for acceptance evaluation",
        )
    return (
        "historical_local_dataset_with_settlement_below_sample_size_target",
        "historical local dataset with settlement but below sample-size target",
    )


def _dataset_preconditions_failed(dataset_summary: dict[str, Any]) -> bool:
    if dataset_summary["classification"] in {
        "fixture_smoke",
        "historical_local_dataset_without_settlement",
    }:
        return True
    if not dataset_summary["acceptance_evaluation_eligible"]:
        return True
    return any(
        not bool(gate["passed"])
        for gate in dataset_summary["sample_size_gates"].values()
    )


def _record_gate(
    gate_checks: dict[str, dict[str, Any]],
    failed_gates: list[str],
    *,
    name: str,
    passed: bool,
    observed: object,
    required: object,
    reason: str,
) -> None:
    gate_checks[name] = {
        "passed": passed,
        "observed": observed,
        "required": required,
        "reason": reason,
    }
    if not passed:
        failed_gates.append(name)


def _metric_deltas(
    *,
    strategy_v1: dict[str, Any],
    strategy_v2: dict[str, Any],
    market: dict[str, Any],
) -> dict[str, Any]:
    v1_forecast = strategy_v1["metrics"]["forecast"]
    v2_forecast = strategy_v2["metrics"]["forecast"]
    market_forecast = market["metrics"]["forecast"]
    v1_paper = strategy_v1["metrics"]["paper_outcome"]
    v2_paper = strategy_v2["metrics"]["paper_outcome"]
    market_paper = market["metrics"]["paper_outcome"]
    calibration = _calibration_delta_summary(
        v1_forecast["calibration_by_bucket"],
        v2_forecast["calibration_by_bucket"],
    )
    return {
        "brier_score_improvement_vs_strategy_v1": _lower_is_better_delta(
            v1_forecast["brier_score"],
            v2_forecast["brier_score"],
        ),
        "brier_score_improvement_vs_market_implied": _lower_is_better_delta(
            market_forecast["brier_score"],
            v2_forecast["brier_score"],
        ),
        "log_loss_improvement_vs_strategy_v1": _lower_is_better_delta(
            v1_forecast["log_loss"],
            v2_forecast["log_loss"],
        ),
        "calibration_buckets_compared": calibration["compared"],
        "calibration_buckets_improved_vs_strategy_v1": calibration["improved"],
        "calibration_buckets_worse_vs_strategy_v1": calibration["worse"],
        "large_calibration_gap_buckets": calibration["large_gap_buckets"],
        "total_return_delta_vs_strategy_v1": _simple_delta(
            v2_paper["total_return"],
            v1_paper["total_return"],
        ),
        "total_return_delta_vs_market_implied": _simple_delta(
            v2_paper["total_return"],
            market_paper["total_return"],
        ),
        "realized_paper_pnl_delta_vs_strategy_v1": _simple_delta(
            v2_paper["realized_paper_pnl"],
            v1_paper["realized_paper_pnl"],
        ),
        "max_drawdown_improvement_vs_strategy_v1": _lower_is_better_delta(
            v1_paper["max_drawdown"],
            v2_paper["max_drawdown"],
        ),
        "profit_factor_delta_vs_strategy_v1": _profit_factor_delta(
            v2_paper,
            v1_paper,
        ),
        "benchmark_relative_return": v2_paper["benchmark_relative_return"],
        "abstention_rate_delta_vs_strategy_v1": _simple_delta(
            strategy_v2["metrics"]["activity"]["abstention_rate"],
            strategy_v1["metrics"]["activity"]["abstention_rate"],
        ),
    }


def _forecast_quality_gate_failures(
    *,
    strategy_v1: dict[str, Any],
    strategy_v2: dict[str, Any],
    market: dict[str, Any],
    metric_deltas: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    v2_forecast = strategy_v2["metrics"]["forecast"]
    if (
        metric_deltas["brier_score_improvement_vs_strategy_v1"] is None
        or metric_deltas["brier_score_improvement_vs_strategy_v1"]
        < BRIER_IMPROVEMENT_THRESHOLD
    ):
        failures.append("forecast.brier_score_not_better_than_strategy_v1")
    if (
        metric_deltas["brier_score_improvement_vs_market_implied"] is None
        or metric_deltas["brier_score_improvement_vs_market_implied"]
        < BRIER_IMPROVEMENT_THRESHOLD
    ):
        failures.append("forecast.brier_score_not_better_than_market_implied")
    if (
        v2_forecast["structured_probability_completeness_rate"]
        < MIN_STRUCTURED_PROBABILITY_COMPLETENESS
    ):
        failures.append("forecast.structured_probability_completeness_below_target")
    compared = int(metric_deltas["calibration_buckets_compared"])
    improved = int(metric_deltas["calibration_buckets_improved_vs_strategy_v1"])
    if compared == 0:
        failures.append("forecast.calibration_bucket_comparison_missing")
    elif improved <= compared / 2:
        failures.append("forecast.calibration_buckets_not_majority_improved")
    if metric_deltas["large_calibration_gap_buckets"]:
        failures.append("forecast.large_calibration_bucket_gap")
    if _missing_probability_created_trade(strategy_v2):
        failures.append("forecast.missing_probability_created_trade")
    if _missing_probability_created_trade(strategy_v1):
        failures.append("forecast.strategy_v1_missing_probability_created_trade")
    if market["metrics"]["forecast"]["brier_score"] is None:
        failures.append("forecast.market_implied_brier_missing")
    return failures


def _paper_outcome_gate_failures(
    *,
    strategy_v1: dict[str, Any],
    strategy_v2: dict[str, Any],
    metric_deltas: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    v1_paper = strategy_v1["metrics"]["paper_outcome"]
    v2_paper = strategy_v2["metrics"]["paper_outcome"]
    if v2_paper["max_drawdown"] > v1_paper["max_drawdown"]:
        failures.append("paper.max_drawdown_worse_than_strategy_v1")
    v2_profit_factor = _profit_factor_for_gate(v2_paper)
    v1_profit_factor = _profit_factor_for_gate(v1_paper)
    if v2_profit_factor is None:
        failures.append("paper.profit_factor_missing")
    else:
        if v2_profit_factor < 1.0:
            failures.append("paper.profit_factor_below_one")
        if v1_profit_factor is not None and v2_profit_factor < v1_profit_factor:
            failures.append("paper.profit_factor_worse_than_strategy_v1")
    if (
        metric_deltas["total_return_delta_vs_strategy_v1"] is None
        or metric_deltas["total_return_delta_vs_strategy_v1"] < 0
    ):
        failures.append("paper.benchmark_relative_return_negative_vs_strategy_v1")
    return failures


def _abstention_gate_failures(strategy_v2: dict[str, Any]) -> list[str]:
    abstention_rate = strategy_v2["metrics"]["activity"]["abstention_rate"]
    if not MIN_ABSTENTION_RATE <= abstention_rate <= MAX_ABSTENTION_RATE:
        return ["activity.abstention_rate_out_of_bounds"]
    return []


def _safety_gate_failures(
    *,
    safety: dict[str, Any],
    strategy_v2: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    expected_values = {
        "paper_only": True,
        "local_only": True,
        "evaluation_only": True,
        "can_create_orders": False,
        "mutates_paper_trading_state": False,
        "strategy_v2_candidate_policy_included": True,
        "strategy_v2_production_enabled": False,
        "phase8_started": False,
        "live_trading_added": False,
        "scheduler_added": False,
        "direct_llm_to_order_path": False,
    }
    for key, expected in expected_values.items():
        if safety.get(key) != expected:
            failures.append(f"safety.{key}")

    reliability = strategy_v2["metrics"]["risk_reliability"]
    replay = reliability.get("replay_validation")
    if not isinstance(replay, dict):
        failures.append("replay.validation_missing")
    else:
        if not replay.get("report_checksum_available"):
            failures.append("replay.report_checksum_unavailable")
        if replay.get("applicable"):
            if replay.get("replay_success_rate") != 1.0:
                failures.append("replay.success_rate_below_one")
            if replay.get("replay_mutation_count") != 0:
                failures.append("replay.mutation_count_nonzero")
        elif replay.get("replay_mutation_count") not in (None, 0):
            failures.append("replay.placeholder_mutation_count_nonzero")
    if reliability.get("data_quality_failure_count", 0) != 0:
        failures.append("safety.data_quality_failure_count")
    return failures


def _replay_warning_gates(strategy_v2: dict[str, Any]) -> list[str]:
    replay = strategy_v2["metrics"]["risk_reliability"].get("replay_validation")
    if isinstance(replay, dict) and replay.get("applicable") is False:
        return ["replay.validation_placeholder_only"]
    return []


def _baseline_summary(baseline: dict[str, Any]) -> dict[str, Any]:
    activity = baseline["metrics"]["activity"]
    forecast = baseline["metrics"]["forecast"]
    paper = baseline["metrics"]["paper_outcome"]
    reliability = baseline["metrics"]["risk_reliability"]
    return {
        "baseline": baseline["baseline"],
        "trade_count": activity["trade_count"],
        "closed_trade_count": activity["closed_trade_count"],
        "abstention_rate": activity["abstention_rate"],
        "rejection_count": activity["rejection_count"],
        "missing_probability_count": activity["missing_probability_count"],
        "missing_settlement_count": activity["missing_settlement_count"],
        "brier_score": forecast["brier_score"],
        "log_loss": forecast["log_loss"],
        "forecast_coverage": forecast["forecast_coverage"],
        "structured_probability_completeness_rate": forecast[
            "structured_probability_completeness_rate"
        ],
        "scored_forecast_count": forecast["scored_forecast_count"],
        "realized_paper_pnl": paper["realized_paper_pnl"],
        "total_return": paper["total_return"],
        "benchmark_relative_return": paper["benchmark_relative_return"],
        "max_drawdown": paper["max_drawdown"],
        "win_rate": paper["win_rate"],
        "profit_factor": paper["profit_factor"],
        "gross_profit": paper["gross_profit"],
        "gross_loss": paper["gross_loss"],
        "provider_structured_output_failure_count": reliability[
            "provider_structured_output_failure_count"
        ],
        "replay_validation": reliability["replay_validation"],
    }


def _calibration_delta_summary(
    v1_buckets: dict[str, dict[str, Any]],
    v2_buckets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    compared = 0
    improved = 0
    worse = 0
    large_gap_buckets: list[str] = []
    for bucket, v2_metrics in v2_buckets.items():
        v2_gap = v2_metrics["absolute_gap"]
        v2_count = int(v2_metrics["row_count"])
        v1_gap = v1_buckets.get(bucket, {}).get("absolute_gap")
        if v2_count >= MIN_LARGE_BUCKET_ROWS and (
            v2_gap is None or v2_gap > MAX_LARGE_BUCKET_CALIBRATION_GAP
        ):
            large_gap_buckets.append(bucket)
        if v2_gap is None or v1_gap is None or v2_count == 0:
            continue
        compared += 1
        if v2_gap <= v1_gap:
            improved += 1
        else:
            worse += 1
    return {
        "compared": compared,
        "improved": improved,
        "worse": worse,
        "large_gap_buckets": large_gap_buckets,
    }


def _missing_probability_created_trade(baseline: dict[str, Any]) -> bool:
    trade_actions = {
        SignalAction.PAPER_BUY_YES.value,
        SignalAction.PAPER_BUY_NO.value,
    }
    return any(
        row["forecast_probability"] is None and row["action"] in trade_actions
        for row in baseline["rows"]
    )


def _lower_is_better_delta(
    baseline_value: float | None,
    candidate_value: float | None,
) -> float | None:
    if baseline_value is None or candidate_value is None:
        return None
    return round(float(baseline_value) - float(candidate_value), 8)


def _simple_delta(
    candidate_value: float | None,
    baseline_value: float | None,
) -> float | None:
    if baseline_value is None or candidate_value is None:
        return None
    return round(float(candidate_value) - float(baseline_value), 8)


def _profit_factor_delta(
    candidate_paper: dict[str, Any],
    baseline_paper: dict[str, Any],
) -> float | None:
    candidate = _profit_factor_for_gate(candidate_paper)
    baseline = _profit_factor_for_gate(baseline_paper)
    if candidate is None or baseline is None:
        return None
    return round(candidate - baseline, 8)


def _profit_factor_for_gate(paper: dict[str, Any]) -> float | None:
    value = paper["profit_factor"]
    if value is not None:
        return float(value)
    gross_profit = float(paper["gross_profit"])
    gross_loss = float(paper["gross_loss"])
    if gross_profit > 0 and gross_loss == 0:
        return 1_000_000.0
    return None


def _gate_recommendation(
    *,
    gate_status: str,
    failed_gates: list[str],
    warning_gates: list[str],
) -> str:
    if gate_status == GATE_PASS:
        return "Strategy v2 passed the acceptance gate; superiority claims are allowed for this dataset."
    if gate_status == GATE_NOT_APPLICABLE:
        missing = ", ".join(failed_gates[:6]) if failed_gates else "acceptance preconditions"
        return (
            "Do not claim Strategy v2 superiority; acceptance is not applicable "
            f"because minimum requirements are missing: {missing}."
        )
    failed = ", ".join(failed_gates[:6]) if failed_gates else "unspecified gate failure"
    warnings = f" Warnings: {', '.join(warning_gates[:4])}." if warning_gates else ""
    return f"Do not claim Strategy v2 superiority; acceptance failed: {failed}.{warnings}"


def _attach_benchmark_relative_returns(baselines: dict[str, dict[str, Any]]) -> None:
    benchmark_return = baselines[BASELINE_MARKET_IMPLIED]["metrics"]["paper_outcome"][
        "total_return"
    ]
    for baseline in baselines.values():
        paper = baseline["metrics"]["paper_outcome"]
        paper["benchmark_relative_return"] = round(
            paper["total_return"] - benchmark_return,
            8,
        )


def _market_outcomes(records: list[HistoricalMarketRecord]) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for record in records:
        if record.settlement_outcome is not None:
            outcomes[record.market_id] = record.settlement_outcome
    return outcomes


def _weighted_probability_hint(evidence: list[EvidenceItem]) -> float | None:
    hints: list[tuple[float, float]] = []
    for item in evidence:
        if "probability_hint" not in item.metadata:
            continue
        hints.append((float(item.metadata["probability_hint"]), item.relevance_score * item.credibility_score))
    if not hints:
        return None
    total_weight = sum(weight for _probability, weight in hints)
    if total_weight <= 0:
        return None
    probability = sum(probability * weight for probability, weight in hints) / total_weight
    return round(min(0.99, max(0.01, probability)), 4)


def _evidence_quality(evidence: tuple[EvidenceItem, ...]) -> float:
    if not evidence:
        return 0.0
    scores = [item.relevance_score * item.credibility_score for item in evidence]
    return round(sum(scores) / len(scores), 4)


def _recommended_action(action: SignalAction) -> RecommendedAction:
    if action == SignalAction.PAPER_BUY_YES:
        return RecommendedAction.PAPER_BUY_YES
    if action == SignalAction.PAPER_BUY_NO:
        return RecommendedAction.PAPER_BUY_NO
    if action == SignalAction.SKIP:
        return RecommendedAction.SKIP
    return RecommendedAction.OBSERVE


def _baseline_description(baseline: str) -> str:
    return {
        BASELINE_ALWAYS_OBSERVE: "Always emits observe; no structured forecast or trade.",
        BASELINE_MARKET_IMPLIED: "Uses market-implied probability for forecast metrics and never claims edge.",
        BASELINE_STRATEGY_V1: "Runs current PredictionMarketEdgeStrategy unchanged against mock research briefs.",
        BASELINE_STRATEGY_V2: "Runs the Strategy v2 candidate policy in offline evaluation only.",
        BASELINE_HINT_THRESHOLD: "Uses historical probability_hint metadata with fixed v1-style thresholds.",
        BASELINE_RANDOM_NAIVE: "Fixed-seed random action/probability diagnostic baseline.",
    }[baseline]


def _outcome_yes(outcome: str) -> float:
    return 1.0 if outcome == "yes" else 0.0


def _log_loss(probability: float, outcome: float) -> float:
    p = min(1 - LOG_LOSS_EPSILON, max(LOG_LOSS_EPSILON, probability))
    return -outcome * math.log(p) - (1 - outcome) * math.log(1 - p)


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 8)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 8)


def _absolute_gap(values: list[tuple[float, float]]) -> float | None:
    if not values:
        return None
    mean_forecast = _mean([probability for probability, _outcome in values])
    observed = _mean([outcome for _probability, outcome in values])
    if mean_forecast is None or observed is None:
        return None
    return round(abs(mean_forecast - observed), 8)


def _max_drawdown(pnls: list[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return round(max_drawdown, 8)


def _evidence_timestamp_coverage(records: list[HistoricalMarketRecord]) -> float:
    evidence_items = [item for record in records for item in record.evidence]
    if not evidence_items:
        return 0.0
    timestamped = [item for item in evidence_items if item.published_at is not None]
    return _rate(len(timestamped), len(evidence_items))


def _report_id(
    historical_file: Path,
    records: list[HistoricalMarketRecord],
    random_seed: int,
    market_id: str | None,
) -> str:
    payload = {
        "historical_file": str(historical_file),
        "record_count": len(records),
        "market_id": market_id,
        "random_seed": random_seed,
        "source_checksum": _file_checksum(historical_file),
    }
    digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    return f"strategy_eval_{historical_file.stem}_{digest}"


def _file_checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _markdown_report(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    gate = report["acceptance_gate"]
    lines = [
        "# Strategy Offline Evaluation Report",
        "",
        f"Report id: `{report['report_id']}`",
        "",
        "## Dataset",
        "",
        f"- Historical file: `{report['historical_file']}`",
        f"- Classification: `{dataset['classification']}`",
        f"- Detail: {dataset['classification_detail']}",
        f"- Evaluated rows: {dataset['evaluated_rows']}",
        f"- Markets evaluated: {dataset['markets_evaluated']}",
        f"- Superiority claims allowed: {dataset['superiority_claim_allowed']}",
        f"- Superiority claim status: {dataset['superiority_claim']}",
        "",
        "## Strategy v2 Acceptance Gate",
        "",
        f"- Gate status: `{gate['gate_status']}`",
        f"- Strategy v2 passed acceptance: {gate['gate_status'] == GATE_PASS}",
        f"- Superiority claims allowed: {gate['superiority_claim_allowed']}",
        f"- Dataset label: `{gate['dataset_label']}`",
        f"- Recommendation: {gate['recommendation']}",
        "",
        "### Failed Gates",
        "",
    ]
    if gate["failed_gates"]:
        lines.extend(f"- `{name}`" for name in gate["failed_gates"])
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "### Warning Gates",
            "",
        ]
    )
    if gate["warning_gates"]:
        lines.extend(f"- `{name}`" for name in gate["warning_gates"])
    else:
        lines.append("- None")
    deltas = gate["metric_deltas"]
    lines.extend(
        [
            "",
            "### Strategy v2 Deltas",
            "",
            "| Metric | Delta |",
            "| --- | ---: |",
            "| Brier improvement vs Strategy v1 | "
            f"{deltas['brier_score_improvement_vs_strategy_v1']} |",
            "| Brier improvement vs market-implied | "
            f"{deltas['brier_score_improvement_vs_market_implied']} |",
            "| Total return delta vs Strategy v1 | "
            f"{deltas['total_return_delta_vs_strategy_v1']} |",
            "| Max drawdown improvement vs Strategy v1 | "
            f"{deltas['max_drawdown_improvement_vs_strategy_v1']} |",
            "| Profit factor delta vs Strategy v1 | "
            f"{deltas['profit_factor_delta_vs_strategy_v1']} |",
            "| Calibration buckets improved vs Strategy v1 | "
            f"{deltas['calibration_buckets_improved_vs_strategy_v1']} / "
            f"{deltas['calibration_buckets_compared']} |",
            "",
            "### Minimum Requirements",
            "",
            "| Gate | Observed | Required | Passed |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for gate_name, sample_gate in dataset["sample_size_gates"].items():
        lines.append(
            f"| {gate_name} | {sample_gate['observed']} | "
            f"{sample_gate['required']} | {sample_gate['passed']} |"
        )
    lines.extend(
        [
            "",
        "## Baseline Metrics",
        "",
        "| Baseline | Trades | Abstention rate | Brier | PnL | Total return |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for baseline_name, baseline in report["baselines"].items():
        activity = baseline["metrics"]["activity"]
        forecast = baseline["metrics"]["forecast"]
        paper = baseline["metrics"]["paper_outcome"]
        lines.append(
            "| "
            f"{baseline_name} | "
            f"{activity['trade_count']} | "
            f"{activity['abstention_rate']} | "
            f"{forecast['brier_score']} | "
            f"{paper['realized_paper_pnl']} | "
            f"{paper['total_return']} |"
        )
    lines.extend(
        [
            "",
            "## Dataset Sample Gates",
            "",
            "| Gate | Observed | Required | Passed |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for gate_name, gate in dataset["sample_size_gates"].items():
        lines.append(
            f"| {gate_name} | {gate['observed']} | {gate['required']} | {gate['passed']} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Paper-only: true",
            "- Local-only: true",
            "- Evaluation-only: true",
            "- Strategy v2 candidate included: true",
            "- Strategy v2 production enabled: false",
            "- Live trading added: false",
            "- Scheduler added: false",
            "- Direct LLM-to-order path: false",
            "",
        ]
    )
    return "\n".join(lines)
