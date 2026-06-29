from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .client import BitfinexClientError, MockBitfinexApiClient
from .models import FundingBookEntry, Wallet


@dataclass(frozen=True)
class StressScenario:
    name: str
    funding_book: list[FundingBookEntry] | None = None
    wallets: list[Wallet] | None = None
    api_failure: bool = False
    sqlite_write_failure: bool = False


def extreme_rate_scenario(multiplier: Decimal) -> StressScenario:
    return StressScenario(
        name=f"funding_rate_x{multiplier}",
        funding_book=[FundingBookEntry(rate=Decimal("0.0002") * multiplier, period=2, count=1, amount=Decimal("100"))],
    )


def empty_book_scenario() -> StressScenario:
    return StressScenario(name="funding_book_empty", funding_book=[])


def wallet_balance_shock_scenario() -> StressScenario:
    return StressScenario(
        name="wallet_balance_shock",
        wallets=[
            Wallet(
                wallet_type="funding",
                currency="USD",
                balance=Decimal("25"),
                unsettled_interest=Decimal("0"),
                available_balance=Decimal("25"),
            )
        ],
    )


def api_timeout_scenario() -> StressScenario:
    return StressScenario(name="api_timeout", api_failure=True)


def sqlite_write_failure_scenario() -> StressScenario:
    return StressScenario(name="sqlite_write_failure", sqlite_write_failure=True)


class ScenarioClient(MockBitfinexApiClient):
    def __init__(self, scenario: StressScenario) -> None:
        super().__init__()
        self._scenario = scenario
        self.created_offer_count = 0

    def get_funding_book(self, symbol: str, *, precision: str = "P0", length: int = 25) -> list[FundingBookEntry]:
        if self._scenario.api_failure:
            raise BitfinexClientError("simulated timeout")
        if self._scenario.funding_book is not None:
            return self._scenario.funding_book
        return super().get_funding_book(symbol, precision=precision, length=length)

    def get_wallets(self) -> list[Wallet]:
        if self._scenario.api_failure:
            raise BitfinexClientError("simulated timeout")
        if self._scenario.wallets is not None:
            return self._scenario.wallets
        return super().get_wallets()

    def create_funding_offer(self, request):  # type: ignore[no-untyped-def]
        self.created_offer_count += 1
        return super().create_funding_offer(request)
