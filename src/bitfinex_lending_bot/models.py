from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _timestamp_ms_to_datetime(value: int | float | str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


@dataclass(frozen=True)
class FundingBookEntry:
    rate: Decimal
    period: int
    count: int
    amount: Decimal

    @classmethod
    def from_bitfinex(cls, row: list[Any]) -> "FundingBookEntry":
        return cls(rate=_decimal(row[0]), period=int(row[1]), count=int(row[2]), amount=_decimal(row[3]))


@dataclass(frozen=True)
class Wallet:
    wallet_type: str
    currency: str
    balance: Decimal
    unsettled_interest: Decimal
    available_balance: Decimal

    @classmethod
    def from_bitfinex(cls, row: list[Any]) -> "Wallet":
        return cls(
            wallet_type=str(row[0]),
            currency=str(row[1]),
            balance=_decimal(row[2]),
            unsettled_interest=_decimal(row[3]),
            available_balance=_decimal(row[4]) if len(row) > 4 and row[4] is not None else _decimal(row[2]),
        )


@dataclass(frozen=True)
class FundingOffer:
    id: int
    symbol: str
    mts_create: datetime | None
    mts_update: datetime | None
    amount: Decimal
    amount_orig: Decimal
    offer_type: str | None
    flags: int | None
    status: str | None
    rate: Decimal
    period: int

    @classmethod
    def from_bitfinex(cls, row: list[Any]) -> "FundingOffer":
        return cls(
            id=int(row[0]),
            symbol=str(row[1]),
            mts_create=_timestamp_ms_to_datetime(row[2]),
            mts_update=_timestamp_ms_to_datetime(row[3]),
            amount=_decimal(row[4]),
            amount_orig=_decimal(row[5]),
            offer_type=str(row[6]) if len(row) > 6 and row[6] is not None else None,
            flags=int(row[9]) if len(row) > 9 and row[9] is not None else None,
            status=str(row[10]) if len(row) > 10 and row[10] is not None else None,
            rate=_decimal(row[14]) if len(row) > 14 and row[14] is not None else Decimal("0"),
            period=int(row[15]) if len(row) > 15 and row[15] is not None else 0,
        )


@dataclass(frozen=True)
class CreateFundingOfferRequest:
    symbol: str
    amount: Decimal
    rate: Decimal
    period: int
    hidden: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": "LIMIT",
            "symbol": self.symbol,
            "amount": str(self.amount),
            "rate": str(self.rate),
            "period": self.period,
            "flags": 64 if self.hidden else 0,
        }


@dataclass(frozen=True)
class StrategyDecision:
    create_offers: tuple[CreateFundingOfferRequest, ...] = ()
    cancel_offer_ids: tuple[int, ...] = ()
    reason: str = ""


class RiskMode(StrEnum):
    ACTIVE = "ACTIVE"
    SAFE = "SAFE"
    KILL_SWITCH = "KILL_SWITCH"


@dataclass(frozen=True)
class ExposureStatus:
    total_capital: Decimal
    active_exposure: Decimal
    proposed_exposure: Decimal
    exposure_ratio: Decimal
    idle_cash: Decimal
    daily_lending_amount: Decimal


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    mode: RiskMode
    rule: str
    reason: str
    exposure: ExposureStatus

