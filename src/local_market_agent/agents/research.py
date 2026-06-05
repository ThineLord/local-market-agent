from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from local_market_agent.llm import BaseLLMProvider, MockLLMProvider, structured_completion
from local_market_agent.schemas.models import (
    EvidenceItem,
    MarketSnapshot,
    RecommendedAction,
    ResearchBrief,
)
from local_market_agent.storage import SQLiteRepository

PAPER_BUY_ACTIONS = {
    RecommendedAction.PAPER_BUY_YES,
    RecommendedAction.PAPER_BUY_NO,
    RecommendedAction.PAPER_BUY,
}


@dataclass
class Researcher:
    provider: BaseLLMProvider

    def draft(self, snapshot: MarketSnapshot, evidence: list[EvidenceItem]) -> ResearchBrief:
        prompt = json.dumps(
            {
                "snapshot": snapshot.model_dump(mode="json"),
                "evidence": [item.model_dump(mode="json") for item in evidence],
                "research_guidance": _research_guidance(snapshot, evidence),
            },
            sort_keys=True,
        )
        return structured_completion(self.provider, prompt, ResearchBrief)


class Skeptic:
    def review(self, brief: ResearchBrief) -> ResearchBrief:
        reasons = list(brief.must_not_trade_reasons)
        action = brief.recommended_action
        if not brief.evidence and not brief.counter_evidence:
            action = RecommendedAction.SKIP
            reasons.append("No trade recommendation without evidence.")
        if brief.market_implied_probability is None and action in PAPER_BUY_ACTIONS:
            action = RecommendedAction.OBSERVE
            reasons.append("Missing market price prevents paper_buy_yes/no.")
        if action == RecommendedAction.PAPER_SELL:
            action = RecommendedAction.OBSERVE
            reasons.append("Shorting is disabled; negative edge is observe-only.")
        reasons = sorted(set(reasons))
        return brief.model_copy(
            update={"recommended_action": action, "must_not_trade_reasons": reasons}
        )


class Calibrator:
    def calibrate(self, brief: ResearchBrief) -> ResearchBrief:
        confidence = brief.confidence
        reasons = list(brief.must_not_trade_reasons)
        action = brief.recommended_action
        evidence_count = len(brief.evidence) + len(brief.counter_evidence)
        if evidence_count < 2:
            confidence = min(confidence, 0.45)
            reasons.append("Sparse evidence lowers confidence.")
        if brief.evidence_quality < 0.65 and action in PAPER_BUY_ACTIONS:
            action = RecommendedAction.OBSERVE
            reasons.append("Evidence quality is below the paper_buy_yes/no threshold.")
        if confidence < 0.60 and action in PAPER_BUY_ACTIONS:
            action = RecommendedAction.OBSERVE
            reasons.append("Confidence is below the paper_buy_yes/no threshold.")
        return brief.model_copy(
            update={
                "confidence": round(confidence, 4),
                "recommended_action": action,
                "must_not_trade_reasons": sorted(set(reasons)),
            }
        )


@dataclass
class Reporter:
    output_dir: Path

    def write_markdown(self, brief: ResearchBrief) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{brief.brief_id}.md"
        evidence_titles = "\n".join(f"- {item.title}" for item in brief.evidence) or "- None"
        counter_titles = (
            "\n".join(f"- {item.title}" for item in brief.counter_evidence) or "- None"
        )
        reasons = "\n".join(f"- {reason}" for reason in brief.must_not_trade_reasons) or "- None"
        content = f"""# Research Brief: {brief.market_id}

Thesis: {brief.thesis}

Recommended action: `{brief.recommended_action}`

Confidence: {brief.confidence}

Evidence quality: {brief.evidence_quality}

Estimated probability: {brief.estimated_probability}

Market probability: {brief.market_implied_probability}

## Rationale

{brief.rationale}

## Evidence

{evidence_titles}

## Counter Evidence

{counter_titles}

## Must Not Trade Reasons

{reasons}
"""
        path.write_text(content, encoding="utf-8")
        return path


@dataclass
class ResearchBriefGenerator:
    repository: SQLiteRepository | None = None
    provider: BaseLLMProvider | None = None
    reporter: Reporter | None = None

    def generate(self, snapshot: MarketSnapshot, evidence: list[EvidenceItem]) -> ResearchBrief:
        provider = self.provider or MockLLMProvider()
        brief = Researcher(provider).draft(snapshot, evidence)
        brief = Skeptic().review(brief)
        brief = Calibrator().calibrate(brief)
        if self.repository is not None:
            self.repository.save_brief(brief)
        if self.reporter is not None:
            self.reporter.write_markdown(brief)
        return brief


def _research_guidance(
    snapshot: MarketSnapshot,
    evidence: list[EvidenceItem],
) -> dict[str, object]:
    estimate = _weighted_probability_hint(evidence, snapshot.market_implied_probability)
    market_probability = snapshot.market_implied_probability
    spread = snapshot.spread
    threshold = max(0.08, 2 * spread) if spread is not None else 0.08
    suggested_action = "observe"
    if estimate is not None and market_probability is not None:
        yes_edge = round(estimate - market_probability, 4)
        no_edge = round(market_probability - estimate, 4)
        if yes_edge >= threshold:
            suggested_action = "paper_buy_yes"
        elif no_edge >= threshold:
            suggested_action = "paper_buy_no"
    return {
        "paper_only": True,
        "can_create_orders": False,
        "use_probability_hints_when_available": True,
        "estimated_probability_from_evidence_hints": estimate,
        "market_implied_probability": market_probability,
        "bid_ask_spread": spread,
        "action_edge_threshold": round(threshold, 4),
        "suggested_research_action_from_hints": suggested_action,
        "instructions": [
            "This is research only; do not create or imply live orders.",
            "If evidence metadata includes probability_hint values, use the weighted "
            "hint estimate as estimated_probability unless you identify a clear "
            "evidence-based reason to choose a different probability.",
            "Use paper_buy_yes only for a positive YES edge, paper_buy_no only for "
            "a positive NO edge, otherwise observe or skip.",
        ],
    }


def _weighted_probability_hint(
    evidence: list[EvidenceItem],
    market_probability: float | None,
) -> float | None:
    hints: list[tuple[float, float]] = []
    for item in evidence:
        if "probability_hint" not in item.metadata:
            continue
        weight = item.relevance_score * item.credibility_score
        hints.append((float(item.metadata["probability_hint"]), weight))
    if not hints:
        return market_probability
    total_weight = sum(weight for _probability, weight in hints)
    if total_weight <= 0:
        return market_probability
    probability = sum(probability * weight for probability, weight in hints) / total_weight
    return round(min(0.99, max(0.01, probability)), 4)
