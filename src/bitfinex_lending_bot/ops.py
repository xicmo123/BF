from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from .storage import SQLiteRepository
from .notifier import TelegramNotifier
from .validation import DecisionTrace
from .models import FundingOffer


class OpsManager:
    def __init__(self, repository: SQLiteRepository, notifier: TelegramNotifier, settings: Any = None) -> None:
        self._repo = repository
        self._notifier = notifier
        self._settings = settings

    def record_execution_result(self, trace: DecisionTrace, wallets: list[Any], open_offers: list[FundingOffer]) -> None:
        try:
            # compute simple exposure metrics
            funding_wallets = [w for w in wallets if getattr(w, "wallet_type", "") == "funding"]
            total_capital = sum((w.balance for w in funding_wallets), Decimal("0"))
            active_exposure = sum((abs(o.amount) for o in open_offers if o.amount is not None), Decimal("0"))
            proposed_exposure = Decimal("0")
            if trace.strategy_decision is not None:
                proposed_exposure = sum((r.amount for r in trace.strategy_decision.create_offers), Decimal("0"))

            # record exposure history
            symbol = trace.input_snapshot.get("symbol", "UNKNOWN")
            self._repo.record_exposure(symbol, total_capital, active_exposure, proposed_exposure)

            # simple APY/PnL placeholders: record zero values if not calculable
            self._repo.record_apy(symbol, 0.0)
            self._repo.record_pnl(symbol, 0.0)

            # metrics
            success = 1.0 if trace.outcome == "EXECUTED" else 0.0
            self._repo.add_metric("execution_success", success)
            if trace.failure_reason:
                self._repo.add_metric("execution_failure", 1.0)
        except Exception:
            # be resilient: ops must not break bot
            return

    def alert_api_failure(self, message: str) -> None:
        try:
            text = f"[ALERT] API failure: {message}"
            self._notifier.send(text)
            self._repo.add_metric("api_failure", 1.0)
        except Exception:
            pass

    def alert_kill_switch(self, reason: str) -> None:
        try:
            text = f"[ALERT] Kill switch triggered: {reason}"
            self._notifier.send(text)
            self._repo.add_metric("kill_switch", 1.0)
        except Exception:
            pass

    def alert_high_exposure(self, symbol: str, exposure_ratio: float) -> None:
        try:
            text = f"[ALERT] High exposure {symbol}: ratio={exposure_ratio:.4f}"
            self._notifier.send(text)
            self._repo.add_metric("high_exposure", exposure_ratio)
        except Exception:
            pass

    def startup_reconcile(self, client: Any, symbol: str | None = None) -> dict[str, Any]:
        report: dict[str, Any] = {"reconciled": False, "offers_upserted": 0}
        try:
            # repair pending traces (mark as failed)
            self._repo.repair_pending_decision_traces("Recovered on startup")
            # reconcile open offers
            s = symbol or (self._settings.default_currency if self._settings else None)
            if s is not None:
                offers = client.get_funding_offers(s)
                if offers:
                    self._repo.upsert_funding_offers(offers)
                    report["reconciled"] = True
                    report["offers_upserted"] = len(offers)
            # attach rollout state
            report["rollout_state"] = self._repo.get_rollout_state()
        except Exception as exc:
            report["error"] = str(exc)
        return report

    def get_health_report(self) -> dict[str, Any]:
        state = self._repo.get_kill_switch_state()
        rollout = self._repo.get_rollout_state()
        return {"kill_switch": state, "rollout": rollout, "time": datetime.utcnow().isoformat()}

    def set_rollout(self, stage: int, allocation_percent: float, max_percent: float = 100.0) -> None:
        try:
            self._repo.set_rollout_state(stage, allocation_percent, max_percent)
        except Exception:
            pass

    def _metrics_snapshot(self, lookback: int = 100) -> dict[str, int]:
        succ = self._repo.get_metrics("execution_success", lookback)
        fail = self._repo.get_metrics("execution_failure", lookback)
        api_fail = self._repo.get_metrics("api_failure", lookback)
        return {"success": len(succ), "failure": len(fail), "api_fail": len(api_fail)}

    def run_auto_rollout(self, cycles_stable: int = 5) -> dict[str, Any]:
        """Evaluate metrics and adjust rollout one step up/down according to rules."""
        result: dict[str, Any] = {"changed": False}
        try:
            # stages and map
            stages = [1, 5, 10, 25]
            state = self._repo.get_rollout_state() or {}
            current_percent = float(state.get("allocation_percent", "0") or 0)
            # get metrics snapshot
            snap = self._metrics_snapshot(lookback=cycles_stable * 20)
            total = snap["success"] + snap["failure"]
            failure_rate = (snap["failure"] / total) if total > 0 else 0.0

            # check kill switch
            ks = self._repo.get_kill_switch_state() or {}
            kill_enabled = int(ks.get("enabled", "0") or 0) == 1

            # compute pnl variance
            # use last N pnl values
            pnl_series = self._repo.get_pnl_series(self._settings.default_currency if self._settings else "fUSD", cycles_stable * 10)
            pnl_vals = [float(r.get("pnl", "0") or 0) for r in pnl_series]
            mean = sum(pnl_vals) / len(pnl_vals) if pnl_vals else 0.0
            var = sum((x - mean) ** 2 for x in pnl_vals) / len(pnl_vals) if pnl_vals else 0.0

            reason = f"failure_rate={failure_rate:.4f} var={var:.6f} api_fail={snap['api_fail']}"

            # safety: if kill switch or high failure rate -> downgrade
            if kill_enabled or failure_rate > 0.05:
                # downgrade one stage or to 0
                if current_percent == 0:
                    result.update({"reason": "already stopped", "failure_rate": failure_rate})
                    return result
                # find current index
                idx = max([i for i, p in enumerate(stages) if p <= current_percent], default=-1)
                if idx <= 0:
                    # go to 0
                    self._repo.set_rollout_state(0, 0.0, 100.0)
                    self._repo.add_rollout_history(0, 0.0, "AUTO_DOWN", reason)
                    self._repo.set_rollout_settings(True, "AUTO_DOWN", reason)
                    result.update({"changed": True, "to": 0, "reason": reason})
                    return result
                else:
                    new_percent = stages[idx - 1]
                    new_stage = idx
                    self._repo.set_rollout_state(new_stage, float(new_percent), 100.0)
                    self._repo.add_rollout_history(new_stage, float(new_percent), "AUTO_DOWN", reason)
                    self._repo.set_rollout_settings(True, "AUTO_DOWN", reason)
                    result.update({"changed": True, "to": new_percent, "reason": reason})
                    return result

            # upgrade path: require failure_rate < 1% and stable successes for cycles_stable
            if failure_rate < 0.01 and var < 1e-4 and snap["api_fail"] == 0:
                # find next stage
                idx = max([i for i, p in enumerate(stages) if p <= current_percent], default=-1)
                next_idx = idx + 1
                if next_idx >= len(stages):
                    result.update({"reason": "already at max"})
                    return result
                # only step one level
                new_percent = stages[next_idx]
                new_stage = next_idx + 1
                self._repo.set_rollout_state(new_stage, float(new_percent), 100.0)
                self._repo.add_rollout_history(new_stage, float(new_percent), "AUTO_UP", reason)
                self._repo.set_rollout_settings(True, "AUTO_UP", reason)
                result.update({"changed": True, "to": new_percent, "reason": reason})
                return result

            result.update({"reason": "no_change", "failure_rate": failure_rate, "var": var})
            return result
        except Exception as exc:
            result.update({"error": str(exc)})
            return result

    def reset_kill_switch(self, reason: str = "manual_reset") -> None:
        """Reset the kill switch state to disabled. Raises if the state write fails."""
        from loguru import logger
        self._repo.set_kill_switch_state(enabled=False, reason=reason, manual_override=True)
        self._repo.reset_failure_count()
        logger.info("Kill switch reset: {}", reason)
        try:
            self._repo.add_event("INFO", f"Kill switch reset: {reason}")
        except Exception as exc:
            logger.error("Failed to record kill switch reset event (state was reset successfully): {}", exc)