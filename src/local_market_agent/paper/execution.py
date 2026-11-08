"""Local single-user paper authorization. All executable inputs are content-bound."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from local_market_agent.config import Settings
from local_market_agent.integrity import seal_execution
from local_market_agent.paper.ledger import PaperLedger, _paper_side_and_limit
from local_market_agent.risk import RiskEngine, RiskGateEvaluator
from local_market_agent.risk.equity import loss_metrics, observe_equity_in_transaction
from local_market_agent.risk.preflight import portfolio_marks, preflight
from local_market_agent.schemas.models import (
    PaperApproval,
    PaperOrderIntent,
    PreparedExecution,
    deterministic_model_context,
)
from local_market_agent.storage import SQLiteRepository


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def utc(value=None):
    value = value or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("Timezone required")
    return value.astimezone(UTC)


@dataclass
class PaperExecutionService:
    repository: SQLiteRepository
    settings: Settings

    def configuration(self):
        return {"risk": self.settings.risk.as_dict(), "gates": self.settings.risk_gates.as_dict(), "real_money_enabled": self.settings.real_money_enabled, "allow_live_orders": self.settings.allow_live_orders}

    def prepare(self, signal, risk_decision, snapshot, brief, *, now=None, simulation=False):
        now = utc(now)
        if self.settings.real_money_enabled or self.settings.allow_live_orders:
            raise ValueError("Live trading flags must remain disabled")
        if self.repository.load_settlement_receipt(snapshot.market.market_id):
            raise ValueError("Market already settled in this paper ledger")
        if not risk_decision.is_approved or risk_decision.signal_id != signal.signal_id:
            raise ValueError("An approved matching risk decision is required")
        if signal.brief_id != brief.brief_id or signal.market_id != snapshot.market.market_id:
            raise ValueError("Signal, brief and snapshot identity mismatch")
        if simulation and snapshot.market.platform not in {"fixture", "historical-file"}:
            raise ValueError(
                "Automatic simulation authorization is restricted to local fixture/history inputs"
            )
        failures = [
            c.message for c in preflight(snapshot, brief, self.settings, now) if not c.passed
        ]
        if failures:
            raise ValueError("; ".join(failures))
        side, price = _paper_side_and_limit(signal, snapshot)
        if price is None or price <= 0:
            raise ValueError("Positive executable quote required")
        notional = min(
            self.settings.risk.paper_starting_cash * risk_decision.max_position_pct,
            risk_decision.max_position_usd,
        )
        fill_price = min(1.0, round(price + self.settings.risk.paper_slippage_bps / 10000, 4))
        intent = PaperOrderIntent(
            signal_id=signal.signal_id,
            market_id=signal.market_id,
            created_at=now,
            side=side,
            quantity=round(notional / fill_price, 8),
            limit_price=price,
            notional=notional,
            metadata={
                "fill_price": fill_price,
                "fees": round(notional * self.settings.risk.paper_fee_rate, 4),
            },
        )
        config = self.configuration()
        payload = self._content(intent, snapshot, brief, signal, risk_decision, config, simulation)
        prepared = PreparedExecution(
            intent_id=intent.intent_id,
            created_at=now,
            intent=intent,
            snapshot_id=snapshot.snapshot_id,
            brief_id=brief.brief_id,
            risk_decision_id=risk_decision.risk_decision_id,
            content_hash=digest(payload),
            config=config,
            simulation=simulation,
        )
        with self.repository.transaction() as repo:
            for obj, loader, saver, key in [
                (
                    snapshot,
                    repo.load_market_snapshot,
                    repo.save_market_snapshot,
                    snapshot.snapshot_id,
                ),
                (brief, repo.load_brief, repo.save_brief, brief.brief_id),
                (signal, repo.load_signal, repo.save_signal, signal.signal_id),
                (
                    risk_decision,
                    repo.load_risk_decision,
                    repo.save_risk_decision,
                    risk_decision.risk_decision_id,
                ),
            ]:
                previous = loader(key)
                if previous is not None and previous != obj:
                    raise ValueError("Cannot overwrite an existing execution input")
                if previous is None:
                    saver(obj)
            repo.save_prepared_execution(prepared)
        return prepared

    @staticmethod
    def _content(intent, snapshot, brief, signal, risk, config, simulation):
        return {
            "inputs": [v.model_dump(mode="json") for v in (intent, snapshot, brief, signal, risk)],
            "config": config,
            "simulation": simulation,
        }

    def _load(self, repo, intent_id):
        prepared = repo.load_prepared_execution(intent_id)
        if prepared is None:
            raise ValueError("Unknown paper intent")
        snapshot = repo.load_market_snapshot(prepared.snapshot_id)
        brief = repo.load_brief(prepared.brief_id)
        signal = repo.load_signal(prepared.intent.signal_id)
        risk = repo.load_risk_decision(prepared.risk_decision_id)
        if any(v is None for v in (snapshot, brief, signal, risk)):
            raise ValueError("Missing execution input")
        current = digest(
            self._content(
                prepared.intent,
                snapshot,
                brief,
                signal,
                risk,
                self.configuration(),
                prepared.simulation,
            )
        )
        if current != prepared.content_hash:
            raise ValueError("Execution inputs/configuration changed; prepare a new intent")
        latest = repo.list_market_snapshots(snapshot.market.market_id, limit=1)
        if latest and latest[0].snapshot_id != snapshot.snapshot_id:
            raise ValueError("Newer market observation exists; prepare a new intent")
        return prepared, snapshot, brief, signal, risk

    def approve(self, intent_id, *, actor, reason, expires_seconds=300, reject=False, now=None):
        now = utc(now)
        if not actor.strip() or not reason.strip() or not 1 <= expires_seconds <= 3600:
            raise ValueError("Actor/reason required; approval lifetime must be 1–3600 seconds")
        with self.repository.transaction() as repo:
            prepared, snapshot, brief, _, _ = self._load(repo, intent_id)
            if now < prepared.created_at:
                raise ValueError("Cannot approve before intent creation")
            failures = [
                c.message for c in preflight(snapshot, brief, self.settings, now) if not c.passed
            ]
            if failures and not reject:
                raise ValueError("; ".join(failures))
            approval = PaperApproval(
                intent_id=intent_id,
                content_hash=prepared.content_hash,
                actor=actor.strip(),
                reason=reason.strip(),
                created_at=now,
                expires_at=now + timedelta(seconds=expires_seconds),
                decision="rejected" if reject else "approved",
                simulation=prepared.simulation,
            )
            repo.save_paper_approval(approval)
        return approval

    def execute(self, intent_id, *, now=None):
        now = utc(now)
        with deterministic_model_context(seed=f"execute:{intent_id}", now=now), self.repository.transaction() as repo:
            prepared, snapshot, brief, signal, risk = self._load(repo, intent_id)

            def result(status, reasons, **extra):
                return {"status": status, "intent_id": intent_id, "reasons": reasons, **extra}

            approvals = [a for a in repo.list_paper_approvals() if a.intent_id == intent_id]
            approval = approvals[0] if approvals else None
            existing = [o for o in repo.list_paper_orders() if o.signal_id == signal.signal_id]
            if existing:
                if existing[0].risk_decision_id != risk.risk_decision_id:
                    raise ValueError("Conflicting executed signal")
                return result(
                    "completed",
                    ["Already executed; no duplicate fill"],
                    order_id=existing[0].order_id,
                )
            if repo.load_settlement_receipt(snapshot.market.market_id):
                return result("rejected", ["Market already settled in this paper ledger"])
            if approval is None:
                return result(
                    "pending_manual_approval", ["Approve this intent explicitly before execution"]
                )
            if approval.decision != "approved":
                return result("rejected", ["Latest approval decision rejects this intent"])
            if (
                approval.content_hash != prepared.content_hash
                or not approval.created_at <= now < approval.expires_at
            ):
                return result("rejected", ["Approval expired, future-dated or content mismatch"])
            failures = [
                c.message for c in preflight(snapshot, brief, self.settings, now) if not c.passed
            ]
            if failures:
                return result("rejected", failures)
            ledger = PaperLedger(repo, self.settings.risk)
            try:
                marks = portfolio_marks(repo, snapshot, self.settings, now)
            except ValueError as exc:
                return result("rejected", [str(exc)])
            portfolio = observe_equity_in_transaction(
                repo, ledger._snapshot_in_transaction(marks, persist=False), now
            )
            current_risk = RiskEngine(self.settings.risk).evaluate_signal(
                signal, open_positions=portfolio.open_positions, **loss_metrics(portfolio)
            )
            if not current_risk.is_approved:
                return result("rejected", current_risk.reasons)
            if (
                risk.max_position_usd > current_risk.max_position_usd
                or risk.max_position_pct > current_risk.max_position_pct
            ):
                return result("rejected", ["Risk sizing changed; prepare a new intent"])
            gate = RiskGateEvaluator(
                replace(self.settings.risk_gates, require_manual_approval=False), repo
            ).evaluate(
                intent=prepared.intent,
                signal=signal,
                portfolio_snapshot=portfolio,
                positions=repo.list_positions(),
                recent_fills=repo.list_paper_fills(),
                market_data_as_of=snapshot.as_of,
                now=now,
            )
            if gate.status != "approved":
                return result(str(gate.status), gate.reasons)
            order, fill, position = ledger._open_in_transaction(
                signal=signal, risk_decision=risk, snapshot=snapshot
            )
            seal_execution(repo, prepared, approval, gate, order, fill, position, now)
            repo.save_portfolio_snapshot(
                observe_equity_in_transaction(
                    repo, ledger._snapshot_in_transaction(marks, persist=False), now
                )
            )
            return result(
                "completed",
                ["Approved paper intent executed"],
                order_id=order.order_id,
                approval_id=approval.approval_id,
                risk_gate_decision_id=gate.risk_gate_decision_id,
                simulation=prepared.simulation,
            )
