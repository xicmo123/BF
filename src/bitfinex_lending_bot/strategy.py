from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from .models import CreateFundingOfferRequest, FundingBookEntry, FundingOffer, StrategyDecision, Wallet


class LendingStrategy(ABC):
    name: str

    @abstractmethod
    def evaluate(
        self,
        *,
        symbol: str,
        funding_book: list[FundingBookEntry],
        wallets: list[Wallet],
        open_offers: list[FundingOffer],
    ) -> StrategyDecision:
        raise NotImplementedError


class PassiveSpreadStrategy(LendingStrategy):
    name = "passive_spread"

    def __init__(
        self,
        *,
        min_available: Decimal = Decimal("50"),
        offer_amount: Decimal = Decimal("50"),
        min_rate: Decimal = Decimal("0.0001"),
        period: int = 2,
    ) -> None:
        self._min_available = min_available
        self._offer_amount = offer_amount
        self._min_rate = min_rate
        self._period = period

    def evaluate(
        self,
        *,
        symbol: str,
        funding_book: list[FundingBookEntry],
        wallets: list[Wallet],
        open_offers: list[FundingOffer],
    ) -> StrategyDecision:
        if open_offers:
            return StrategyDecision(reason="Existing offers present; no new offer created")

        currency = symbol.removeprefix("f")
        funding_wallets = [
            wallet for wallet in wallets if wallet.wallet_type == "funding" and wallet.currency in {symbol, currency}
        ]
        available = sum((wallet.available_balance for wallet in funding_wallets), Decimal("0"))
        if available < self._min_available:
            return StrategyDecision(reason=f"Available balance {available} is below minimum {self._min_available}")

        positive_asks = [entry for entry in funding_book if entry.amount > 0]
        market_rate = positive_asks[0].rate if positive_asks else self._min_rate
        rate = max(market_rate, self._min_rate)
        amount = min(self._offer_amount, available)
        offer = CreateFundingOfferRequest(symbol=symbol, amount=amount, rate=rate, period=self._period)
        return StrategyDecision(create_offers=(offer,), reason=f"Create passive offer at {rate}")


def select_strategy(name: str = "passive_spread") -> LendingStrategy:
    if name == "passive_spread":
        return PassiveSpreadStrategy()
    raise ValueError(f"Unknown strategy: {name}")

