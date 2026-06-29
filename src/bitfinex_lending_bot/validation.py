from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .models import FundingBookEntry, FundingOffer, RiskDecision, StrategyDecision, Wallet
from .risk import RiskManager
from .strategy import LendingStrategy


class DecisionTraceError(RuntimeError):
    pass


@dataclass(frozen=True)
class DecisionTrace:
    input_snapshot: dict[str, Any]
    strategy_decision: StrategyDecision | None
    risk_decision: RiskDecision | None
    outcome: str
    execution_instance_id: str | None = None
    lock_status: str | None = None
    lock_timestamp: str | None = None
    failure_reason: str | None = None


class DecisionTraceValidator:
    def validate(self, trace: DecisionTrace) -> None:
        if trace.strategy_decision is None:
            raise DecisionTraceError("Decision trace is missing strategy decision")
        if trace.risk_decision is None:
            raise DecisionTraceError("Decision bypassed risk gate")
        if trace.outcome in {"EXECUTED", "PARTIALLY_EXECUTED"} and not trace.risk_decision.allowed:
            raise DecisionTraceError("Funding offer executed after risk rejection")
        if trace.strategy_decision.create_offers and trace.outcome == "EXECUTED" and trace.risk_decision.rule != "ALLOW":
            raise DecisionTraceError("Funding offer execution is not backed by an ALLOW risk decision")


@dataclass(frozen=True)
class ReplayFrame:
    funding_book: list[FundingBookEntry]
    wallets: list[Wallet]
    open_offers: list[FundingOffer]
    daily_lending_amount: Decimal = Decimal("0")


class ReplayEngine:
    def __init__(
        self,
        *,
        strategy: LendingStrategy,
        risk_manager: RiskManager,
        validator: DecisionTraceValidator | None = None,
    ) -> None:
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._validator = validator or DecisionTraceValidator()

    def replay(self, frames: list[ReplayFrame], *, symbol: str, limit: int = 100) -> list[DecisionTrace]:
        traces: list[DecisionTrace] = []
        for frame in frames[-limit:]:
            strategy_decision = self._strategy.evaluate(
                symbol=symbol,
                funding_book=frame.funding_book,
                wallets=frame.wallets,
                open_offers=frame.open_offers,
            )
            risk_decision = self._risk_manager.evaluate(
                funding_book=frame.funding_book,
                wallets=frame.wallets,
                open_offers=frame.open_offers,
                decision=strategy_decision,
                daily_lending_amount=frame.daily_lending_amount,
            )
            outcome = "WOULD_EXECUTE" if risk_decision.allowed and strategy_decision.create_offers else "SAFE_IDLE"
            trace = DecisionTrace(
                input_snapshot={
                    "funding_book_entries": len(frame.funding_book),
                    "wallets": len(frame.wallets),
                    "open_offers": len(frame.open_offers),
                    "daily_lending_amount": str(frame.daily_lending_amount),
                },
                strategy_decision=strategy_decision,
                risk_decision=risk_decision,
                outcome=outcome,
            )
            self._validator.validate(trace)
            traces.append(trace)
        return traces
