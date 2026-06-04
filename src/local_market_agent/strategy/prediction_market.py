from __future__ import annotations

from dataclasses import dataclass

from local_market_agent.config import RiskConfig
from local_market_agent.schemas.models import (
    MarketSnapshot,
    RecommendedAction,
    ResearchBrief,
    Signal,
    SignalAction,
)


@dataclass
class PredictionMarketEdgeStrategy:
    config: RiskConfig = RiskConfig()

    def generate_signal(self, brief: ResearchBrief, snapshot: MarketSnapshot) -> Signal:
        spread = snapshot.spread
        market_probability = snapshot.market_implied_probability
        agent_probability = brief.estimated_probability

        if brief.evidence_quality < 0.65:
            return self._signal(
                brief,
                SignalAction.SKIP,
                agent_probability,
                market_probability,
                spread,
                None,
                "Evidence quality is below 0.65.",
            )
        if brief.confidence < self.config.min_confidence:
            return self._signal(
                brief,
                SignalAction.SKIP,
                agent_probability,
                market_probability,
                spread,
                None,
                "Confidence is below the strategy threshold.",
            )
        if market_probability is None or agent_probability is None:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                None,
                "Missing market or agent probability prevents paper_buy.",
            )
        if spread is None:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                None,
                "Missing bid/ask spread prevents paper_buy.",
            )
        if spread > self.config.max_spread:
            return self._signal(
                brief,
                SignalAction.SKIP,
                agent_probability,
                market_probability,
                spread,
                None,
                "Spread is above the maximum allowed threshold.",
            )

        edge = round(agent_probability - market_probability, 4)
        threshold = max(self.config.min_edge, 2 * spread)
        if abs(edge) < threshold:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                edge,
                "Edge is below the actionable threshold.",
            )
        if edge < 0:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                edge,
                "Negative edge is observe-only because shorting is disabled.",
            )
        if brief.recommended_action != RecommendedAction.PAPER_BUY:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                edge,
                "Brief did not recommend paper_buy.",
            )
        return self._signal(
            brief,
            SignalAction.PAPER_BUY,
            agent_probability,
            market_probability,
            spread,
            edge,
            "Positive edge clears paper-only strategy thresholds.",
        )

    @staticmethod
    def _signal(
        brief: ResearchBrief,
        action: SignalAction,
        agent_probability: float | None,
        market_probability: float | None,
        spread: float | None,
        edge: float | None,
        rationale: str,
    ) -> Signal:
        return Signal(
            brief_id=brief.brief_id,
            market_id=brief.market_id,
            action=action,
            agent_probability=agent_probability,
            market_probability=market_probability,
            spread=spread,
            edge=edge,
            confidence=brief.confidence,
            evidence_quality=brief.evidence_quality,
            rationale=rationale,
        )


class CryptoTrendNewsVetoStrategy:
    def generate_signal(self) -> SignalAction:
        return SignalAction.OBSERVE


class EquityEventMonitorStrategy:
    def generate_signal(self) -> SignalAction:
        return SignalAction.OBSERVE
