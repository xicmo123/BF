from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

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
        min_available: Decimal = Decimal("1"),
        offer_amount: Decimal = Decimal("1"),
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


class AdvancedLendingStrategy(LendingStrategy):
    """
    Advanced multi-mode lending strategy with:
      A) Auto-cancellation of stale overpriced offers
      B) Dynamic period selection based on market rate
      C) High-speed mode (single offer at market) or
         High-yield mode (3-tier ladder offers)
    """

    name = "advanced"

    def __init__(
        self,
        *,
        mode: Literal["high_speed", "high_yield"] = "high_speed",
        min_available: Decimal = Decimal("50"),
        max_offer_stale_minutes: int = 10,
        high_yield_threshold_apy: Decimal = Decimal("20"),  # 20% APY threshold for period selection
        period_short: int = 2,
        period_long: int = 30,
        hidden_threshold_usd: Decimal = Decimal("10000"),
    ) -> None:
        self._mode = mode
        self._min_available = min_available
        self._max_offer_stale_minutes = max_offer_stale_minutes
        self._high_yield_threshold_apy = high_yield_threshold_apy
        self._period_short = period_short
        self._period_long = period_long
        self._hidden_threshold_usd = hidden_threshold_usd

    def evaluate(
        self,
        *,
        symbol: str,
        funding_book: list[FundingBookEntry],
        wallets: list[Wallet],
        open_offers: list[FundingOffer],
    ) -> StrategyDecision:
        cancel_ids: list[int] = []
        create_offers: list[CreateFundingOfferRequest] = []
        reasons: list[str] = []

        # ====== Parse market data ======
        currency = symbol.removeprefix("f")
        funding_wallets = [
            wallet for wallet in wallets
            if wallet.wallet_type == "funding" and wallet.currency in {symbol, currency}
        ]
        available = sum((wallet.available_balance for wallet in funding_wallets), Decimal("0"))

        # Positive asks = lenders offering funds (lowest rate first)
        positive_asks = [entry for entry in funding_book if entry.amount > 0]
        lowest_ask = positive_asks[0].rate if positive_asks else Decimal("0.0001")

        # ====== A) Auto-Cancellation: cancel stale overpriced offers ======
        now = datetime.now(UTC)
        stale_cutoff = now - timedelta(minutes=self._max_offer_stale_minutes)

        for offer in open_offers:
            # Determine the most recent update time
            update_time = offer.mts_update or offer.mts_create
            if update_time is None:
                continue

            # Check if offer is stale (older than cutoff) AND rate > lowest ask
            if update_time < stale_cutoff and offer.rate > lowest_ask:
                cancel_ids.append(offer.id)
                reasons.append(f"❌ 取消過期單 {offer.id} (掛單利率 {offer.rate} > 目前市場最低要價 {lowest_ask})")

        # ====== B) Check available balance ======
        if available < self._min_available:
            if cancel_ids:
                return StrategyDecision(
                    cancel_offer_ids=tuple(cancel_ids),
                    reason="; ".join(reasons) + f" | Available {available} below {self._min_available}, skip new offers",
                )
            return StrategyDecision(reason=f"Available balance {available} is below minimum {self._min_available}")

        # ====== Dynamic period selection ======
        # Convert lowest_ask (daily rate) to APY: rate * 365 * 100 = APY%
        # Bitfinex funding rates are daily decimal rates (e.g. 0.0005 = 0.05%/day ≈ 18.25% APY)
        lowest_ask_apy = float(lowest_ask) * 365 * 100
        if lowest_ask_apy < float(self._high_yield_threshold_apy):
            period = self._period_short  # 2 days for low-rate market
        else:
            period = self._period_long  # 30 days for high-rate market

        # ====== C) Mode-specific offer creation ======
        if self._mode == "high_speed":
            # High-Speed Mode: single offer at lowest ask - 0.0001% (slightly undercut)
            rate = lowest_ask - Decimal("0.000001")
            if rate <= Decimal("0"):
                rate = lowest_ask
            # Quantize rate to 6 decimal places to avoid Bitfinex 500 error
            rate = rate.quantize(Decimal("0.000001"))

            hidden = available >= self._hidden_threshold_usd
            offer = CreateFundingOfferRequest(
                symbol=symbol,
                amount=available,
                rate=rate,
                period=period,
                hidden=hidden,
            )
            create_offers.append(offer)
            reasons.append(
                f"⚡ 高速模式：投入資金 {available} @ 利率 {rate} 放貸天數={period}天"
                f"{' (隱藏單)' if hidden else ''}"
            )

        else:  # high_yield mode — 3-tier ladder
            # Tier 1: 20% at Lowest Ask + 2% (safe base)
            tier1_pct = Decimal("0.20")
            tier1_amount = (available * tier1_pct).quantize(Decimal("0.01"))
            tier1_rate = (lowest_ask * Decimal("1.02")).quantize(Decimal("0.000001"))  # +2%
            if tier1_amount > 0:
                hidden1 = tier1_amount >= self._hidden_threshold_usd
                create_offers.append(CreateFundingOfferRequest(
                    symbol=symbol,
                    amount=tier1_amount,
                    rate=tier1_rate,
                    period=period,
                    hidden=hidden1,
                ))
                reasons.append(f"📈 階梯第一檔(20%資金): {tier1_amount} @ 利率 {tier1_rate}")

            # Tier 2: 30% at Lowest Ask * 1.5 (placeholder for 7-day high avg)
            tier2_pct = Decimal("0.30")
            tier2_amount = (available * tier2_pct).quantize(Decimal("0.01"))
            tier2_rate = (lowest_ask * Decimal("1.5")).quantize(Decimal("0.000001"))  # placeholder: 1.5x lowest ask
            if tier2_amount > 0:
                hidden2 = tier2_amount >= self._hidden_threshold_usd
                create_offers.append(CreateFundingOfferRequest(
                    symbol=symbol,
                    amount=tier2_amount,
                    rate=tier2_rate,
                    period=period,
                    hidden=hidden2,
                ))
                reasons.append(f"📈 階梯第二檔(30%資金): {tier2_amount} @ 利率 {tier2_rate}")

            # Tier 3: 50% at extreme high rate (50% APY sniper)
            tier3_pct = Decimal("0.50")
            tier3_amount = (available * tier3_pct).quantize(Decimal("0.01"))
            # 50% APY ≈ 0.00137 daily rate (50 / 365 / 100)
            tier3_rate = max(lowest_ask * Decimal("3"), Decimal("0.00137")).quantize(Decimal("0.000001"))
            if tier3_amount > 0:
                hidden3 = tier3_amount >= self._hidden_threshold_usd
                create_offers.append(CreateFundingOfferRequest(
                    symbol=symbol,
                    amount=tier3_amount,
                    rate=tier3_rate,
                    period=period,
                    hidden=hidden3,
                ))
                reasons.append(f"🎯  sniper狙擊第三檔(50%資金): {tier3_amount} @ 利率 {tier3_rate} (極高回報單)")

        return StrategyDecision(
            create_offers=tuple(create_offers),
            cancel_offer_ids=tuple(cancel_ids),
            reason=" | ".join(reasons),
        )


def select_strategy(name: str = "advanced") -> LendingStrategy:
    if name == "passive_spread":
        return PassiveSpreadStrategy()
    if name == "advanced":
        return AdvancedLendingStrategy(mode="high_speed")
    raise ValueError(f"Unknown strategy: {name}")