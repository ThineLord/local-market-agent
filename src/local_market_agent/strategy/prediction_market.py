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

YES_RECOMMENDATIONS = {
    RecommendedAction.PAPER_BUY_YES,
    RecommendedAction.PAPER_BUY,
}

NO_RECOMMENDATIONS = {RecommendedAction.PAPER_BUY_NO}


@dataclass
class PredictionMarketEdgeStrategy:
    config: RiskConfig = RiskConfig()

    def generate_signal(self, brief: ResearchBrief, snapshot: MarketSnapshot) -> Signal:
        spread = snapshot.spread
        market_probability = snapshot.market_implied_probability
        agent_probability = brief.estimated_probability

        if snapshot.liquidity is not None and snapshot.liquidity < self.config.min_liquidity_depth:
            return self._signal(
                brief,
                SignalAction.SKIP,
                agent_probability,
                market_probability,
                spread,
                None,
                "Liquidity depth is below the strategy threshold.",
            )
        if brief.resolution_ambiguity:
            return self._signal(
                brief,
                SignalAction.SKIP,
                agent_probability,
                market_probability,
                spread,
                None,
                "Resolution source is ambiguous.",
            )
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
                "Missing market or agent probability prevents paper_buy_yes/no.",
            )
        if spread is None:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                None,
                "Missing bid/ask spread prevents paper_buy_yes/no.",
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

        yes_edge = round(agent_probability - market_probability, 4)
        no_edge = round(market_probability - agent_probability, 4)
        directional_edge = max(yes_edge, no_edge)
        threshold = max(self.config.min_edge, 2 * spread)
        if directional_edge < threshold:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                directional_edge,
                "Edge is below the actionable threshold.",
            )
        ev_yes = None
        if snapshot.best_ask is not None:
            ev_yes = round(agent_probability - snapshot.best_ask, 4)
        ev_no = None
        if snapshot.best_bid is not None:
            best_ask_no = 1 - snapshot.best_bid
            ev_no = round((1 - agent_probability) - best_ask_no, 4)

        if yes_edge >= no_edge:
            if brief.recommended_action not in YES_RECOMMENDATIONS:
                return self._signal(
                    brief,
                    SignalAction.OBSERVE,
                    agent_probability,
                    market_probability,
                    spread,
                    yes_edge,
                    "Brief did not recommend paper_buy_yes.",
                )
            if ev_yes is None or ev_yes < threshold:
                return self._signal(
                    brief,
                    SignalAction.OBSERVE,
                    agent_probability,
                    market_probability,
                    spread,
                    yes_edge,
                    "YES EV is below the spread/fee/slippage buffer.",
                )
            return self._signal(
                brief,
                SignalAction.PAPER_BUY_YES,
                agent_probability,
                market_probability,
                spread,
                yes_edge,
                "Positive YES edge clears paper-only strategy thresholds.",
            )

        if brief.recommended_action not in NO_RECOMMENDATIONS:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                no_edge,
                "Brief did not recommend paper_buy_no.",
            )
        if ev_no is None or ev_no < threshold:
            return self._signal(
                brief,
                SignalAction.OBSERVE,
                agent_probability,
                market_probability,
                spread,
                no_edge,
                "NO EV is below the spread/fee/slippage buffer.",
            )
        return self._signal(
            brief,
            SignalAction.PAPER_BUY_NO,
            agent_probability,
            market_probability,
            spread,
            no_edge,
            "Positive NO edge clears paper-only strategy thresholds.",
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
