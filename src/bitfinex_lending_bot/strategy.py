from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from .models import CreateFundingOfferRequest, FundingBookEntry, FundingOffer, StrategyDecision, Wallet

from loguru import logger

BITFINEX_MIN_FUNDING_OFFER = Decimal("150")



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
        min_available: Decimal = Decimal("150"),
        offer_amount: Decimal = Decimal("150"),
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
        if amount < BITFINEX_MIN_FUNDING_OFFER:
            return StrategyDecision(reason=f"Offer amount {amount} is below Bitfinex minimum {BITFINEX_MIN_FUNDING_OFFER}")
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
        reserve_amount: Decimal = Decimal("0"),
    ) -> None:
        self._mode = mode
        self._min_available = min_available
        self._max_offer_stale_minutes = max_offer_stale_minutes
        self._high_yield_threshold_apy = high_yield_threshold_apy
        self._period_short = period_short
        self._period_long = period_long
        self._hidden_threshold_usd = hidden_threshold_usd
        self._reserve_amount = reserve_amount

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
        # Subtract reserve amount from available balance
        available_after_reserve = available - self._reserve_amount
        if available_after_reserve < self._min_available:
            if cancel_ids:
                return StrategyDecision(
                    cancel_offer_ids=tuple(cancel_ids),
                    reason="; ".join(reasons) + f" | Available after reserve {available_after_reserve} below {self._min_available}, skip new offers",
                )
            return StrategyDecision(reason=f"Available balance after reserve {available_after_reserve} is below minimum {self._min_available}")

        # Use available_after_reserve for offer creation
        available = available_after_reserve

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

            if available < BITFINEX_MIN_FUNDING_OFFER:
                reasons.append(f"⚠️ 高速模式：可用資金 {available} 低於最低門檻 {BITFINEX_MIN_FUNDING_OFFER}，跳過下單")
            else:
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

            # Tier 2: 30% at Lowest Ask * 1.5 (placeholder for 7-day high avg)
            tier2_pct = Decimal("0.30")
            tier2_amount = (available * tier2_pct).quantize(Decimal("0.01"))
            tier2_rate = (lowest_ask * Decimal("1.5")).quantize(Decimal("0.000001"))

            # Tier 3: 50% at extreme high rate (50% APY sniper)
            tier3_pct = Decimal("0.50")
            tier3_amount = (available * tier3_pct).quantize(Decimal("0.01"))
            tier3_rate = max(lowest_ask * Decimal("3"), Decimal("0.00137")).quantize(Decimal("0.000001"))

            t_offers = [
                {"name": "第一檔(20%資金)", "amount": tier1_amount, "rate": tier1_rate},
                {"name": "第二檔(30%資金)", "amount": tier2_amount, "rate": tier2_rate},
                {"name": "狙擊第三檔(50%資金)", "amount": tier3_amount, "rate": tier3_rate},
            ]

            merged_offers: list[dict[str, Any]] = []
            carry_over = Decimal("0")

            for i, t in enumerate(t_offers):
                current_amount = t["amount"] + carry_over
                if current_amount <= 0:
                    continue

                is_last_tier = (i == len(t_offers) - 1)

                if current_amount < BITFINEX_MIN_FUNDING_OFFER:
                    if not is_last_tier:
                        carry_over = current_amount
                        reasons.append(f"⚠️ {t['name']}金額 {current_amount} 低於最低門檻 {BITFINEX_MIN_FUNDING_OFFER}，合併至下一檔")
                    else:
                        if merged_offers:
                            # Merge backward
                            last_valid = merged_offers[-1]
                            old_amount = last_valid["amount"]
                            new_amount = old_amount + current_amount
                            last_valid["amount"] = new_amount
                            reasons.append(f"⚠️ {t['name']}金額 {current_amount} 低於最低門檻 {BITFINEX_MIN_FUNDING_OFFER}，且無下一檔，往回合併至上一檔，前一檔金額從 {old_amount} 變更為 {new_amount}")
                        else:
                            reasons.append(f"⚠️ 總金額 {current_amount} 低於最低門檻 {BITFINEX_MIN_FUNDING_OFFER}，跳過下單")
                else:
                    merged_offers.append({
                        "name": t["name"],
                        "amount": current_amount,
                        "rate": t["rate"]
                    })
                    carry_over = Decimal("0")

            for mo in merged_offers:
                hidden = mo["amount"] >= self._hidden_threshold_usd
                create_offers.append(CreateFundingOfferRequest(
                    symbol=symbol,
                    amount=mo["amount"],
                    rate=mo["rate"],
                    period=period,
                    hidden=hidden,
                ))
                reasons.append(f"📈 {mo['name']}: {mo['amount']} @ 利率 {mo['rate']}{' (隱藏單)' if hidden else ''}")

        return StrategyDecision(
            create_offers=tuple(create_offers),
            cancel_offer_ids=tuple(cancel_ids),
            reason=" | ".join(reasons),
        )


def select_strategy(name: str = "advanced", repository=None) -> LendingStrategy:
    if name == "passive_spread":
        return PassiveSpreadStrategy()
    if name == "advanced":
        # Load strategy settings from database if repository is provided
        mode = "high_speed"
        period = 2
        reserve_amount = Decimal("0")

        if repository is not None:
            try:
                settings = repository.get_strategy_settings()
                if settings:
                    mode = settings.get("mode", "high_speed")
                    period = int(settings.get("period", 2))
                    reserve_amount = Decimal(str(settings.get("reserve_amount", 0)))
            except Exception as e:
                # Fallback to defaults if database read fails
                pass

        return AdvancedLendingStrategy(
            mode=mode,
            period_short=period,
            period_long=period,
            reserve_amount=reserve_amount,
        )
    raise ValueError(f"Unknown strategy: {name}")