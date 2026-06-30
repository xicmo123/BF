from __future__ import annotations

from decimal import Decimal

from bitfinex_lending_bot.models import FundingBookEntry, Wallet
from bitfinex_lending_bot.strategy import (
    BITFINEX_MIN_FUNDING_OFFER,
    AdvancedLendingStrategy,
    PassiveSpreadStrategy,
)


def test_passive_strategy_creates_offer_when_balance_available() -> None:
    strategy = PassiveSpreadStrategy(min_available=Decimal("150"), offer_amount=Decimal("150"))

    decision = strategy.evaluate(
        symbol="fUSD",
        funding_book=[FundingBookEntry(rate=Decimal("0.0003"), period=2, count=1, amount=Decimal("100"))],
        wallets=[
            Wallet(
                wallet_type="funding",
                currency="USD",
                balance=Decimal("200"),
                unsettled_interest=Decimal("0"),
                available_balance=Decimal("175"),
            )
        ],
        open_offers=[],
    )

    assert len(decision.create_offers) == 1
    assert decision.create_offers[0].amount == Decimal("150")
    assert decision.create_offers[0].rate == Decimal("0.0003")


def test_passive_strategy_skips_below_minimum() -> None:
    strategy = PassiveSpreadStrategy(min_available=Decimal("50"), offer_amount=Decimal("50"))

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

    assert len(decision.create_offers) == 0
    assert "below Bitfinex minimum" in decision.reason


def test_advanced_strategy_high_speed_skips_below_minimum() -> None:
    strategy = AdvancedLendingStrategy(mode="high_speed", min_available=Decimal("50"))

    decision = strategy.evaluate(
        symbol="fUSD",
        funding_book=[FundingBookEntry(rate=Decimal("0.0003"), period=2, count=1, amount=Decimal("100"))],
        wallets=[
            Wallet(
                wallet_type="funding",
                currency="USD",
                balance=Decimal("100"),
                unsettled_interest=Decimal("0"),
                available_balance=Decimal("100"),
            )
        ],
        open_offers=[],
    )

    assert len(decision.create_offers) == 0
    assert "低於最低門檻" in decision.reason


def test_advanced_strategy_high_yield_merges_tiers() -> None:
    # Scenario A: Total balance < 150 -> skip all
    strategy = AdvancedLendingStrategy(mode="high_yield", min_available=Decimal("50"))
    decision_skip = strategy.evaluate(
        symbol="fUSD",
        funding_book=[FundingBookEntry(rate=Decimal("0.0003"), period=2, count=1, amount=Decimal("100"))],
        wallets=[Wallet("funding", "USD", Decimal("100"), Decimal("0"), Decimal("100"))],
        open_offers=[],
    )
    assert len(decision_skip.create_offers) == 0
    assert "跳過下單" in decision_skip.reason

    # Scenario B: Total balance = 150 -> T1(30), T2(45), T3(75) all merged forward/backward into T3(150)
    decision_merge_all = strategy.evaluate(
        symbol="fUSD",
        funding_book=[FundingBookEntry(rate=Decimal("0.0003"), period=2, count=1, amount=Decimal("100"))],
        wallets=[Wallet("funding", "USD", Decimal("150"), Decimal("0"), Decimal("150"))],
        open_offers=[],
    )
    assert len(decision_merge_all.create_offers) == 1
    assert decision_merge_all.create_offers[0].amount == Decimal("150")

    # Scenario C: Total balance = 500 -> T1(100), T2(150), T3(250). T1 merges to T2, resulting in T2(250) and T3(250).
    decision_merge_some = strategy.evaluate(
        symbol="fUSD",
        funding_book=[FundingBookEntry(rate=Decimal("0.0003"), period=2, count=1, amount=Decimal("100"))],
        wallets=[Wallet("funding", "USD", Decimal("500"), Decimal("0"), Decimal("500"))],
        open_offers=[],
    )
    assert len(decision_merge_some.create_offers) == 2
    assert decision_merge_some.create_offers[0].amount == Decimal("250")
    assert decision_merge_some.create_offers[1].amount == Decimal("250")

    # Scenario D: Total balance = 800 -> T1(160), T2(240), T3(400)
    decision_800 = strategy.evaluate(
        symbol="fUSD",
        funding_book=[FundingBookEntry(rate=Decimal("0.0003"), period=2, count=1, amount=Decimal("100"))],
        wallets=[Wallet("funding", "USD", Decimal("800"), Decimal("0"), Decimal("800"))],
        open_offers=[],
    )
    assert len(decision_800.create_offers) == 3
    assert decision_800.create_offers[0].amount == Decimal("160")
    assert decision_800.create_offers[1].amount == Decimal("240")
    assert decision_800.create_offers[2].amount == Decimal("400")
