from __future__ import annotations

import sqlite3

from loguru import logger

from .client import BitfinexApiClient, BitfinexClientError, MockBitfinexApiClient, PaperTradingBitfinexApiClient
from .config import Settings, load_settings
from .execution_lock import ExecutionLockResult, GlobalExecutionLock
from .logging import configure_logging
from .models import StrategyDecision
from .notifier import NotificationError, TelegramNotifier
from .risk import RiskConfig, RiskManager
from .storage import SQLiteRepository
from .strategy import LendingStrategy, select_strategy
from .validation import DecisionTrace, DecisionTraceValidator


class LendingBot:
    def __init__(
        self,
        *,
        settings: Settings,
        client: BitfinexApiClient,
        repository: SQLiteRepository,
        notifier: TelegramNotifier,
        strategy: LendingStrategy,
        risk_manager: RiskManager,
        ops_manager: object | None = None,
        trace_validator: DecisionTraceValidator | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._repository = repository
        self._notifier = notifier
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._ops = ops_manager
        self._trace_validator = trace_validator or DecisionTraceValidator()
        self._execution_lock = GlobalExecutionLock(settings.database_path)

    def run_once(self, symbol: str | None = None) -> None:
        symbol = symbol or self._settings.default_currency
        self._repository.initialize()
        self._recover_pending_state()
        # run ops startup reconcile if available
        try:
            if getattr(self, "_ops", None):
                self._ops.startup_reconcile(self._client, symbol)
        except Exception:
            pass
        logger.info("Starting lending bot cycle symbol={}", symbol)
        try:
            with self._execution_lock.acquire() as lock_result:
                if not lock_result.acquired:
                    logger.warning("Execution lock acquisition failed instance={}", lock_result.instance_id)
                    strategy_decision = StrategyDecision(reason="Execution lock failed")
                    risk_decision = self._risk_manager.safe_idle_decision("Execution lock unavailable")
                    self._record_risk_decision(risk_decision)
                    rejected_trace = DecisionTrace(
                        input_snapshot={
                            "symbol": symbol,
                            "lock_status": lock_result.status,
                        },
                        strategy_decision=strategy_decision,
                        risk_decision=risk_decision,
                        outcome="SAFE_IDLE",
                        execution_instance_id=lock_result.instance_id,
                        lock_status=lock_result.status,
                        lock_timestamp=lock_result.timestamp,
                    )
                    self._trace_validator.validate(rejected_trace)
                    self._record_decision_trace(rejected_trace)
                    self._record_event("WARNING", "Execution lock unavailable; safe idle enforced")
                    return

            logger.info("Execution lock acquired instance_id=%s", lock_result.instance_id)
            try:
                logger.info("Reading funding book")
                funding_book = self._client.get_funding_book(symbol)
                logger.info("Funding book read successfully entries={}", len(funding_book))

                logger.info("Reading wallets")
                wallets = self._client.get_wallets()
                logger.info("Wallet read successfully wallets={}", len(wallets))

                logger.info("Reading funding offers")
                open_offers = self._client.get_funding_offers(symbol)
                logger.info("Funding offers read successfully offers={}", len(open_offers))
            except BitfinexClientError as exc:
                self._risk_manager.trigger_kill_switch(f"API failure: {exc}")
                risk_decision = self._risk_manager.safe_idle_decision(str(exc))
                self._record_risk_decision(risk_decision)
                self._record_event("ERROR", f"API failure fallback to safe idle: {exc}")
                logger.error("API failure fallback to safe idle: {}", exc)
                try:
                    if getattr(self, "_ops", None):
                        self._ops.alert_api_failure(str(exc))
                except Exception:
                    pass
                return

            try:
                self._repository.save_funding_book(symbol, funding_book)
                self._repository.save_wallets(wallets)
                self._repository.upsert_funding_offers(open_offers)
            except sqlite3.Error as exc:
                self._risk_manager.trigger_kill_switch(f"SQLite write failure: {exc}")
                risk_decision = self._risk_manager.safe_idle_decision(str(exc))
                self._record_risk_decision(risk_decision)
                self._record_event("ERROR", f"SQLite write failure fallback to safe idle: {exc}")
                logger.error("SQLite write failure fallback to safe idle: {}", exc)
                try:
                    if getattr(self, "_ops", None):
                        self._ops.alert_api_failure(str(exc))
                except Exception:
                    pass
                return

            logger.info("Calling strategy {}", self._strategy.name)
            decision = self._strategy.evaluate(
                symbol=symbol,
                funding_book=funding_book,
                wallets=wallets,
                open_offers=open_offers,
            )
            logger.info("Strategy {} decision: {}", self._strategy.name, decision.reason)
            self._record_event("INFO", f"{self._strategy.name}: {decision.reason}")

            try:
                daily_lending_amount = self._repository.todays_lending_amount()
            except sqlite3.Error as exc:
                self._risk_manager.trigger_kill_switch(f"SQLite read failure: {exc}")
                risk_decision = self._risk_manager.safe_idle_decision(str(exc))
                self._record_risk_decision(risk_decision)
                self._record_event("ERROR", f"SQLite read failure fallback to safe idle: {exc}")
                logger.error("SQLite read failure fallback to safe idle: {}", exc)
                return

            risk_decision = self._risk_manager.evaluate(
                funding_book=funding_book,
                wallets=wallets,
                open_offers=open_offers,
                decision=decision,
                daily_lending_amount=daily_lending_amount,
            )
            pending_trace = DecisionTrace(
                input_snapshot={
                    "symbol": symbol,
                    "funding_book_entries": len(funding_book),
                    "wallets": len(wallets),
                    "open_offers": len(open_offers),
                },
                strategy_decision=decision,
                risk_decision=risk_decision,
                outcome="PENDING",
                execution_instance_id=lock_result.instance_id,
                lock_status=lock_result.status,
                lock_timestamp=lock_result.timestamp,
            )
            self._trace_validator.validate(pending_trace)
            self._record_risk_decision(risk_decision)
            pending_trace_id = None
            try:
                pending_trace_id = self._repository.add_decision_trace(pending_trace)
            except sqlite3.Error as exc:
                logger.error("Failed to persist pending decision trace: {}", exc)
            if not risk_decision.allowed:
                rejected_trace = DecisionTrace(
                    input_snapshot=pending_trace.input_snapshot,
                    strategy_decision=decision,
                    risk_decision=risk_decision,
                    outcome="REJECTED",
                    execution_instance_id=lock_result.instance_id,
                    lock_status=lock_result.status,
                    lock_timestamp=lock_result.timestamp,
                )
                self._trace_validator.validate(rejected_trace)
                if pending_trace_id is not None:
                    self._repository.update_decision_trace(pending_trace_id, rejected_trace)
                else:
                    self._record_decision_trace(rejected_trace)
                self._record_event(
                    "WARNING",
                    f"Risk rejected rule={risk_decision.rule}: {risk_decision.reason}",
                )
                logger.warning("Funding offer execution skipped by risk manager")
                return

            try:
                for offer_id in decision.cancel_offer_ids:
                    cancelled = self._client.cancel_funding_offer(offer_id)
                    self._repository.upsert_funding_offers([cancelled])
                    self._notify(f"Cancelled funding offer {cancelled.id}: {cancelled.status}")

                for request in decision.create_offers:
                    created = self._client.create_funding_offer(request)
                    self._repository.upsert_funding_offers([created])
                    self._notify(f"Created {created.symbol} funding offer {created.id} at rate {created.rate}")
            except (BitfinexClientError, sqlite3.Error) as exc:
                self._handle_execution_failure(
                    pending_trace_id,
                    pending_trace,
                    str(exc),
                    lock_result,
                )
                return

            executed_trace = DecisionTrace(
                input_snapshot=pending_trace.input_snapshot,
                strategy_decision=decision,
                risk_decision=risk_decision,
                outcome="EXECUTED" if decision.create_offers or decision.cancel_offer_ids else "SAFE_IDLE",
                execution_instance_id=lock_result.instance_id,
                lock_status=lock_result.status,
                lock_timestamp=lock_result.timestamp,
            )
            self._trace_validator.validate(executed_trace)
            if pending_trace_id is not None:
                self._repository.update_decision_trace(pending_trace_id, executed_trace)
            else:
                self._record_decision_trace(executed_trace)
            logger.info("Lending bot cycle completed")
        except (NotificationError, ValueError) as exc:
            logger.exception("Bot run failed")
            self._repository.add_event("ERROR", str(exc))
            raise

    def _notify(self, message: str) -> None:
        self._notifier.send(message)
        self._record_event("INFO", message)

    def _record_risk_decision(self, risk_decision) -> None:  # type: ignore[no-untyped-def]
        try:
            self._repository.add_risk_decision(risk_decision)
        except sqlite3.Error as exc:
            logger.error("Failed to persist risk decision: {}", exc)

    def _record_event(self, level: str, message: str) -> None:
        try:
            self._repository.add_event(level, message)
        except sqlite3.Error as exc:
            logger.error("Failed to persist event level={} message={} error={}", level, message, exc)

    def _record_decision_trace(self, trace: DecisionTrace) -> None:
        try:
            self._repository.add_decision_trace(trace)
        except (sqlite3.Error, ValueError) as exc:
            logger.error("Failed to persist decision trace outcome={} error={}", trace.outcome, exc)

    def _recover_pending_state(self) -> None:
        try:
            self._repository.repair_pending_decision_traces("Recovered from restart after incomplete execution")
            kill_switch = self._repository.get_kill_switch_state()
            if kill_switch is None:
                return
            enabled = int(kill_switch.get("enabled", "0")) == 1
            manual_override = int(kill_switch.get("manual_override", "0")) == 1
            if enabled:
                self._risk_manager.restore_kill_switch(enabled=True, manual_override=manual_override)
                self._record_event(
                    "WARNING",
                    f"Persistent kill switch loaded enabled={enabled} reason={kill_switch.get('reason')}"
                )
        except sqlite3.Error as exc:
            logger.error("Failed to recover persistent state: {}", exc)

    def _handle_execution_failure(
        self,
        trace_id: int | None,
        trace: DecisionTrace,
        failure_reason: str,
        lock_result: ExecutionLockResult,
    ) -> None:
        logger.error("Execution failure: {}", failure_reason)
        self._risk_manager.trigger_kill_switch(failure_reason)
        try:
            self._repository.set_kill_switch_state(enabled=True, reason=failure_reason)
        except sqlite3.Error as exc:
            logger.error("Failed to persist kill switch state: {}", exc)
        try:
            if getattr(self, "_ops", None):
                self._ops.alert_kill_switch(failure_reason)
        except Exception:
            pass
        failure_trace = DecisionTrace(
            input_snapshot=trace.input_snapshot,
            strategy_decision=trace.strategy_decision,
            risk_decision=trace.risk_decision,
            outcome="FAILED",
            execution_instance_id=lock_result.instance_id,
            lock_status=lock_result.status,
            lock_timestamp=lock_result.timestamp,
            failure_reason=failure_reason,
        )
        if trace_id is not None:
            try:
                self._repository.update_decision_trace(trace_id, failure_trace)
            except sqlite3.Error as exc:
                logger.error("Failed to persist failed decision trace: {}", exc)
        try:
            symbol = trace.input_snapshot.get("symbol") or self._settings.default_currency
            open_offers = self._client.get_funding_offers(symbol)
            self._repository.upsert_funding_offers(open_offers)
        except Exception:
            pass


def build_bot(settings: Settings | None = None) -> LendingBot:
    settings = settings or load_settings()
    configure_logging(settings.log_path)
    if settings.has_bitfinex_credentials:
        live_client = BitfinexApiClient(
            settings.bitfinex_api_key,
            settings.bitfinex_api_secret,
            timeout=settings.request_timeout_seconds,
        )
        if settings.paper_trading_enabled:
            client = PaperTradingBitfinexApiClient(live_client)
            logger.warning("Paper trading enabled; live funding offer create/cancel API calls are disabled")
            logger.info("Bitfinex client initialized in paper trading mode")
        else:
            client = live_client
            logger.warning("Paper trading disabled; live funding offer writes are enabled")
            logger.info("Bitfinex client initialized in live mode")
    else:
        client = MockBitfinexApiClient()
        logger.warning("Bitfinex API credentials not found; mock mode enabled")
        logger.info("Bitfinex client initialized in mock mode")
    repository = SQLiteRepository(settings.database_path)
    repository.initialize()
    notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id)
    strategy = select_strategy()
    risk_manager = RiskManager(RiskConfig.from_settings(settings))
    # create OpsManager and attach to risk manager
    from .ops import OpsManager

    ops = OpsManager(repository, notifier, settings)
    # attach ops to risk manager for kill switch notifications
    setattr(risk_manager, "_ops", ops)
    kill_switch_state = repository.get_kill_switch_state()
    if kill_switch_state is not None and int(kill_switch_state.get("enabled", "0")) == 1:
        risk_manager.restore_kill_switch(
            enabled=True,
            manual_override=int(kill_switch_state.get("manual_override", "0")) == 1,
        )
        logger.warning(
            "Persistent kill switch state loaded enabled=true reason={}",
            kill_switch_state.get("reason"),
        )
    logger.info("Strategy initialized: {}", strategy.name)
    logger.info(
        "Risk manager initialized max_exposure={} max_daily={} min_idle={} kill_switch={}",
        settings.max_capital_exposure,
        settings.max_daily_lending_amount,
        settings.min_idle_cash_threshold,
        settings.kill_switch_enabled,
    )
    return LendingBot(
        settings=settings,
        client=client,
        repository=repository,
        notifier=notifier,
        strategy=strategy,
        risk_manager=risk_manager,
        ops_manager=ops,
    )


def main() -> None:
    bot = build_bot()
    bot.run_once()
