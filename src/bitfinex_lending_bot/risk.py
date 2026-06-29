from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from loguru import logger

from .config import Settings
from .models import (
    ExposureStatus,
    FundingBookEntry,
    FundingOffer,
    RiskDecision,
    RiskMode,
    StrategyDecision,
    Wallet,
)


@dataclass(frozen=True)
class RiskConfig:
    max_capital_exposure: Decimal
    max_daily_lending_amount: Decimal
    min_idle_cash_threshold: Decimal
    kill_switch_enabled: bool
    max_funding_rate: Decimal
    max_funding_rate_spread: Decimal

    @classmethod
    def from_settings(cls, settings: Settings) -> "RiskConfig":
        return cls(
            max_capital_exposure=settings.max_capital_exposure,
            max_daily_lending_amount=settings.max_daily_lending_amount,
            min_idle_cash_threshold=settings.min_idle_cash_threshold,
            kill_switch_enabled=settings.kill_switch_enabled,
            max_funding_rate=settings.max_funding_rate,
            max_funding_rate_spread=settings.max_funding_rate_spread,
        )


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._auto_kill_switch = False

    def restore_kill_switch(self, *, enabled: bool, manual_override: bool = False) -> None:
        self._auto_kill_switch = enabled
        if enabled:
            logger.warning("Restored persistent kill switch (manual_override={})", manual_override)

    @property
    def mode(self) -> RiskMode:
        if self._config.kill_switch_enabled or self._auto_kill_switch:
            return RiskMode.KILL_SWITCH
        return RiskMode.ACTIVE

    def trigger_kill_switch(self, reason: str) -> None:
        self._auto_kill_switch = True
        logger.critical("Risk kill switch triggered: {}", reason)
        # notify ops manager if available
        try:
            if hasattr(self, "_ops") and self._ops:
                self._ops.alert_kill_switch(reason)
        except Exception:
            pass

    def evaluate(
        self,
        *,
        funding_book: list[FundingBookEntry],
        wallets: list[Wallet],
        open_offers: list[FundingOffer],
        decision: StrategyDecision,
        daily_lending_amount: Decimal,
    ) -> RiskDecision:
        exposure = self._exposure_status(
            wallets=wallets,
            open_offers=open_offers,
            decision=decision,
            daily_lending_amount=daily_lending_amount,
        )

        if self.mode == RiskMode.KILL_SWITCH:
            return self._reject("KILL_SWITCH", "Kill switch is enabled", exposure, RiskMode.KILL_SWITCH)

        sanity_failure = self._market_sanity_failure(funding_book)
        if sanity_failure is not None:
            self.trigger_kill_switch(sanity_failure[1])
            return self._reject(sanity_failure[0], sanity_failure[1], exposure, RiskMode.KILL_SWITCH)

        if exposure.total_capital <= 0:
            self.trigger_kill_switch("No funding wallet capital available")
            return self._reject("NO_CAPITAL", "No funding wallet capital available", exposure, RiskMode.KILL_SWITCH)

        if exposure.exposure_ratio > self._config.max_capital_exposure:
            return self._reject(
                "MAX_CAPITAL_EXPOSURE",
                f"Exposure {exposure.exposure_ratio:.4f} exceeds max {self._config.max_capital_exposure}",
                exposure,
                RiskMode.SAFE,
            )

        if exposure.daily_lending_amount + exposure.proposed_exposure > self._config.max_daily_lending_amount:
            return self._reject(
                "MAX_DAILY_LENDING_AMOUNT",
                (
                    f"Daily lending {exposure.daily_lending_amount + exposure.proposed_exposure} "
                    f"would exceed max {self._config.max_daily_lending_amount}"
                ),
                exposure,
                RiskMode.SAFE,
            )

        if exposure.idle_cash < self._config.min_idle_cash_threshold:
            self.trigger_kill_switch(f"Idle cash {exposure.idle_cash} is below threshold {self._config.min_idle_cash_threshold}")
            return self._reject(
                "MIN_IDLE_CASH_THRESHOLD",
                f"Idle cash {exposure.idle_cash} is below threshold {self._config.min_idle_cash_threshold}",
                exposure,
                RiskMode.KILL_SWITCH,
            )

        risk_decision = RiskDecision(
            allowed=True,
            mode=RiskMode.ACTIVE,
            rule="ALLOW",
            reason="Risk checks passed",
            exposure=exposure,
        )
        self.log_decision(risk_decision)
        return risk_decision

    def safe_idle_decision(self, reason: str) -> RiskDecision:
        exposure = ExposureStatus(
            total_capital=Decimal("0"),
            active_exposure=Decimal("0"),
            proposed_exposure=Decimal("0"),
            exposure_ratio=Decimal("0"),
            idle_cash=Decimal("0"),
            daily_lending_amount=Decimal("0"),
        )
        decision = RiskDecision(False, self.mode if self.mode == RiskMode.KILL_SWITCH else RiskMode.SAFE, "API_FAILURE", reason, exposure)
        self.log_decision(decision)
        return decision

    def log_decision(self, decision: RiskDecision) -> None:
        if decision.allowed:
            logger.info(
                "Risk decision allowed rule={} mode={} exposure_ratio={} idle_cash={} daily_lending={}",
                decision.rule,
                decision.mode,
                decision.exposure.exposure_ratio,
                decision.exposure.idle_cash,
                decision.exposure.daily_lending_amount,
            )
            return

        logger.warning(
            "Risk decision rejected rule={} mode={} reason={} exposure_ratio={} active_exposure={} proposed_exposure={} "
            "idle_cash={} daily_lending={} total_capital={}",
            decision.rule,
            decision.mode,
            decision.reason,
            decision.exposure.exposure_ratio,
            decision.exposure.active_exposure,
            decision.exposure.proposed_exposure,
            decision.exposure.idle_cash,
            decision.exposure.daily_lending_amount,
            decision.exposure.total_capital,
        )

    def _reject(self, rule: str, reason: str, exposure: ExposureStatus, mode: RiskMode) -> RiskDecision:
        decision = RiskDecision(allowed=False, mode=mode, rule=rule, reason=reason, exposure=exposure)
        self.log_decision(decision)
        return decision

    def _exposure_status(
        self,
        *,
        wallets: list[Wallet],
        open_offers: list[FundingOffer],
        decision: StrategyDecision,
        daily_lending_amount: Decimal,
    ) -> ExposureStatus:
        funding_wallets = [wallet for wallet in wallets if wallet.wallet_type == "funding"]
        wallet_balance = sum((wallet.balance for wallet in funding_wallets), Decimal("0"))
        idle_cash = sum((wallet.available_balance for wallet in funding_wallets), Decimal("0"))
        active_exposure = sum((abs(offer.amount) for offer in open_offers if _is_active_offer(offer)), Decimal("0"))
        proposed_exposure = sum((request.amount for request in decision.create_offers), Decimal("0"))
        total_capital = wallet_balance + active_exposure
        ratio = (active_exposure + proposed_exposure) / total_capital if total_capital > 0 else Decimal("0")
        return ExposureStatus(
            total_capital=total_capital,
            active_exposure=active_exposure,
            proposed_exposure=proposed_exposure,
            exposure_ratio=ratio,
            idle_cash=idle_cash - proposed_exposure,
            daily_lending_amount=daily_lending_amount,
        )

    def _market_sanity_failure(self, funding_book: list[FundingBookEntry]) -> tuple[str, str] | None:
        if not funding_book:
            return ("FUNDING_BOOK_EMPTY", "Funding book is empty")

        rates = [entry.rate for entry in funding_book if entry.rate > 0 and entry.amount != 0]
        if not rates:
            return ("FUNDING_BOOK_INVALID", "Funding book has no positive rates")

        max_rate = max(rates)
        min_rate = min(rates)
        if max_rate > self._config.max_funding_rate:
            return ("MAX_FUNDING_RATE", f"Funding rate {max_rate} exceeds max {self._config.max_funding_rate}")

        spread = max_rate - min_rate
        if spread > self._config.max_funding_rate_spread:
            return (
                "FUNDING_RATE_VOLATILITY",
                f"Funding rate spread {spread} exceeds max {self._config.max_funding_rate_spread}",
            )

        return None


def _is_active_offer(offer: FundingOffer) -> bool:
    status = (offer.status or "").upper()
    return offer.amount != 0 and "CANCEL" not in status and "EXECUTED" not in status
