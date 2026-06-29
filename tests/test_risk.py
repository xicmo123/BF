from __future__ import annotations

from decimal import Decimal

from bitfinex_lending_bot.models import CreateFundingOfferRequest, FundingBookEntry, StrategyDecision, Wallet
from bitfinex_lending_bot.risk import RiskConfig, RiskManager


def _config(**overrides: object) -> RiskConfig:
    values = {
        "max_capital_exposure": Decimal("0.30"),
        "max_daily_lending_amount": Decimal("500"),
        "min_idle_cash_threshold": Decimal("100"),
        "kill_switch_enabled": False,
        "max_funding_rate": Decimal("0.01"),
        "max_funding_rate_spread": Decimal("0.005"),
    }
    values.update(overrides)
    return RiskConfig(**values)  # type: ignore[arg-type]


def _wallet() -> Wallet:
    return Wallet(
        wallet_type="funding",
        currency="USD",
        balance=Decimal("1000"),
        unsettled_interest=Decimal("0"),
        available_balance=Decimal("1000"),
    )


def _book() -> list[FundingBookEntry]:
    return [FundingBookEntry(rate=Decimal("0.0002"), period=2, count=1, amount=Decimal("100"))]


def test_risk_manager_allows_safe_decision() -> None:
    manager = RiskManager(_config())
    decision = StrategyDecision(
        create_offers=(CreateFundingOfferRequest("fUSD", Decimal("50"), Decimal("0.0002"), 2),)
    )

    risk = manager.evaluate(
        funding_book=_book(),
        wallets=[_wallet()],
        open_offers=[],
        decision=decision,
        daily_lending_amount=Decimal("0"),
    )

    assert risk.allowed is True
    assert risk.rule == "ALLOW"


def test_risk_manager_blocks_kill_switch() -> None:
    manager = RiskManager(_config(kill_switch_enabled=True))

    risk = manager.evaluate(
        funding_book=_book(),
        wallets=[_wallet()],
        open_offers=[],
        decision=StrategyDecision(),
        daily_lending_amount=Decimal("0"),
    )

    assert risk.allowed is False
    assert risk.rule == "KILL_SWITCH"


def test_risk_manager_blocks_abnormal_rate() -> None:
    manager = RiskManager(_config(max_funding_rate=Decimal("0.001")))

    risk = manager.evaluate(
        funding_book=[FundingBookEntry(rate=Decimal("0.02"), period=2, count=1, amount=Decimal("100"))],
        wallets=[_wallet()],
        open_offers=[],
        decision=StrategyDecision(),
        daily_lending_amount=Decimal("0"),
    )

    assert risk.allowed is False
    assert risk.rule == "MAX_FUNDING_RATE"


def test_risk_manager_blocks_daily_limit() -> None:
    manager = RiskManager(_config(max_daily_lending_amount=Decimal("60")))
    decision = StrategyDecision(
        create_offers=(CreateFundingOfferRequest("fUSD", Decimal("50"), Decimal("0.0002"), 2),)
    )

    risk = manager.evaluate(
        funding_book=_book(),
        wallets=[_wallet()],
        open_offers=[],
        decision=decision,
        daily_lending_amount=Decimal("20"),
    )

    assert risk.allowed is False
    assert risk.rule == "MAX_DAILY_LENDING_AMOUNT"
