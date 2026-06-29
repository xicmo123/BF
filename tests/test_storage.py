from __future__ import annotations

from decimal import Decimal

from bitfinex_lending_bot.models import FundingBookEntry, Wallet
from bitfinex_lending_bot.storage import SQLiteRepository
from bitfinex_lending_bot.models import ExposureStatus, RiskDecision, RiskMode, StrategyDecision
from bitfinex_lending_bot.validation import DecisionTrace


def test_repository_persists_wallets_and_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = SQLiteRepository(tmp_path / "bot.sqlite3")
    repository.initialize()

    repository.save_funding_book("fUSD", [FundingBookEntry(rate=Decimal("0.0002"), period=2, count=1, amount=Decimal("10"))])
    repository.save_wallets(
        [
            Wallet(
                wallet_type="funding",
                currency="USD",
                balance=Decimal("100"),
                unsettled_interest=Decimal("0"),
                available_balance=Decimal("90"),
            )
        ]
    )
    repository.add_event("INFO", "ok")

    assert repository.latest_wallets()[0]["available_balance"] == "90"
    assert repository.latest_events()[0]["message"] == "ok"


def test_repository_persists_kill_switch_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = SQLiteRepository(tmp_path / "bot.sqlite3")
    repository.initialize()

    repository.set_kill_switch_state(enabled=True, reason="api failure", manual_override=True)
    state = repository.get_kill_switch_state()

    assert state is not None
    assert state["enabled"] == "1"
    assert state["reason"] == "api failure"
    assert state["manual_override"] == "1"


def test_repository_repairs_pending_decision_traces(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = SQLiteRepository(tmp_path / "bot.sqlite3")
    repository.initialize()

    pending_trace = DecisionTrace(
        input_snapshot={"symbol": "fUSD"},
        strategy_decision=StrategyDecision(reason="none"),
            risk_decision=RiskDecision(
                allowed=False,
                mode=RiskMode.SAFE,
            rule="TEST",
            reason="test",
            exposure=ExposureStatus(
                total_capital=Decimal("0"),
                active_exposure=Decimal("0"),
                proposed_exposure=Decimal("0"),
                exposure_ratio=Decimal("0"),
                idle_cash=Decimal("0"),
                daily_lending_amount=Decimal("0"),
            ),
        ),
        outcome="PENDING",
    )
    repository.add_decision_trace(pending_trace)
    repository.repair_pending_decision_traces("Recovered on restart")

    latest = repository.latest_decision_traces(limit=1)[0]
    assert latest["outcome"] == "FAILED"
    assert latest["failure_reason"] == "Recovered on restart"

