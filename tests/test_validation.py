from __future__ import annotations

from decimal import Decimal

import pytest

from bitfinex_lending_bot.models import CreateFundingOfferRequest, FundingBookEntry, StrategyDecision, Wallet
from bitfinex_lending_bot.risk import RiskConfig, RiskManager
from bitfinex_lending_bot.strategy import PassiveSpreadStrategy
from bitfinex_lending_bot.validation import (
    DecisionTrace,
    DecisionTraceError,
    DecisionTraceValidator,
    ReplayEngine,
    ReplayFrame,
)


def _risk_manager() -> RiskManager:
    return RiskManager(
        RiskConfig(
            max_capital_exposure=Decimal("0.30"),
            max_daily_lending_amount=Decimal("500"),
            min_idle_cash_threshold=Decimal("100"),
            kill_switch_enabled=False,
            max_funding_rate=Decimal("0.01"),
            max_funding_rate_spread=Decimal("0.005"),
        )
    )


def _book(rate: Decimal = Decimal("0.0002")) -> list[FundingBookEntry]:
    return [FundingBookEntry(rate=rate, period=2, count=1, amount=Decimal("100"))]


def _wallet(balance: Decimal = Decimal("1000")) -> Wallet:
    return Wallet("funding", "USD", balance, Decimal("0"), balance)


def test_decision_trace_validator_rejects_risk_bypass() -> None:
    validator = DecisionTraceValidator()
    trace = DecisionTrace(
        input_snapshot={"funding_book_entries": 1},
        strategy_decision=StrategyDecision(
            create_offers=(CreateFundingOfferRequest("fUSD", Decimal("50"), Decimal("0.0002"), 2),)
        ),
        risk_decision=None,
        outcome="EXECUTED",
    )

    with pytest.raises(DecisionTraceError):
        validator.validate(trace)


def test_decision_trace_validator_rejects_execution_after_risk_rejection() -> None:
    manager = _risk_manager()
    strategy_decision = StrategyDecision(
        create_offers=(CreateFundingOfferRequest("fUSD", Decimal("50"), Decimal("0.02"), 2),)
    )
    risk_decision = manager.evaluate(
        funding_book=_book(Decimal("0.02")),
        wallets=[_wallet()],
        open_offers=[],
        decision=strategy_decision,
        daily_lending_amount=Decimal("0"),
    )

    trace = DecisionTrace(
        input_snapshot={"funding_book_entries": 1},
        strategy_decision=strategy_decision,
        risk_decision=risk_decision,
        outcome="EXECUTED",
    )

    with pytest.raises(DecisionTraceError):
        DecisionTraceValidator().validate(trace)


def test_replay_mode_replays_last_100_market_frames() -> None:
    frames = [
        ReplayFrame(
            funding_book=_book(),
            wallets=[_wallet()],
            open_offers=[],
            daily_lending_amount=Decimal("0"),
        )
        for _ in range(120)
    ]
    engine = ReplayEngine(strategy=PassiveSpreadStrategy(), risk_manager=_risk_manager())

    traces = engine.replay(frames, symbol="fUSD", limit=100)

    assert len(traces) == 100
    assert all(trace.risk_decision is not None for trace in traces)
    assert all(trace.outcome in {"WOULD_EXECUTE", "SAFE_IDLE"} for trace in traces)
