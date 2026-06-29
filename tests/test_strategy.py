from __future__ import annotations

from decimal import Decimal

from bitfinex_lending_bot.models import FundingBookEntry, Wallet
from bitfinex_lending_bot.strategy import PassiveSpreadStrategy


def test_passive_strategy_creates_offer_when_balance_available() -> None:
    strategy = PassiveSpreadStrategy(min_available=Decimal("50"), offer_amount=Decimal("25"))

    decision = strategy.evaluate(
        symbol="fUSD",
        funding_book=[FundingBookEntry(rate=Decimal("0.0003"), period=2, count=1, amount=Decimal("100"))],
        wallets=[
            Wallet(
                wallet_type="funding",
                currency="USD",
                balance=Decimal("100"),
                unsettled_interest=Decimal("0"),
                available_balance=Decimal("75"),
            )
        ],
        open_offers=[],
    )

    assert len(decision.create_offers) == 1
    assert decision.create_offers[0].amount == Decimal("25")
    assert decision.create_offers[0].rate == Decimal("0.0003")

