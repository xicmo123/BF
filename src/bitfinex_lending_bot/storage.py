from __future__ import annotations

import sqlite3
import json
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from .models import FundingBookEntry, FundingOffer, RiskDecision, Wallet
from .validation import DecisionTrace


class SQLiteRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(f"""
                CREATE TABLE IF NOT EXISTS funding_book_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    rate TEXT NOT NULL,
                    period INTEGER NOT NULL,
                    count INTEGER NOT NULL,
                    amount TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at TEXT NOT NULL,
                    wallet_type TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    balance TEXT NOT NULL,
                    unsettled_interest TEXT NOT NULL,
                    available_balance TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS funding_offers (
                    id INTEGER PRIMARY KEY,
                    captured_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    mts_create TEXT,
                    mts_update TEXT,
                    amount TEXT NOT NULL,
                    amount_orig TEXT NOT NULL,
                    offer_type TEXT,
                    flags INTEGER,
                    status TEXT,
                    rate TEXT NOT NULL,
                    period INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS risk_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    total_capital TEXT NOT NULL,
                    active_exposure TEXT NOT NULL,
                    proposed_exposure TEXT NOT NULL,
                    exposure_ratio TEXT NOT NULL,
                    idle_cash TEXT NOT NULL,
                    daily_lending_amount TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decision_traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    input_snapshot TEXT NOT NULL,
                    strategy_reason TEXT NOT NULL,
                    create_offer_count INTEGER NOT NULL,
                    cancel_offer_count INTEGER NOT NULL,
                    risk_allowed INTEGER NOT NULL,
                    risk_mode TEXT NOT NULL,
                    risk_rule TEXT NOT NULL,
                    risk_reason TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    execution_instance_id TEXT,
                    lock_status TEXT,
                    lock_timestamp TEXT,
                    failure_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS kill_switch_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL,
                    reason TEXT,
                    manual_override INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO kill_switch_state (id, enabled, reason, manual_override, updated_at)
                VALUES (1, 0, '', 0, '{_now()}');
                """
            )
            self._ensure_decision_trace_columns(connection)
            # ensure observability and rollout tables
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS apy_series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    measured_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    apy REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pnl_series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    measured_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    pnl REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exposure_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    measured_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    total_capital TEXT NOT NULL,
                    active_exposure TEXT NOT NULL,
                    proposed_exposure TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rollout_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    stage INTEGER NOT NULL,
                    allocation_percent REAL NOT NULL,
                    max_percent REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO rollout_state (id, stage, allocation_percent, max_percent, updated_at)
                VALUES (1, 0, 0.0, 100.0, '{_now()}');
                """
            )
            # rollout history table
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rollout_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    stage INTEGER NOT NULL,
                    allocation_percent REAL NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT
                );
                """
            )
            # rollout settings (auto mode + last auto decision)
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rollout_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    auto_enabled INTEGER NOT NULL,
                    last_decision TEXT,
                    last_reason TEXT,
                    updated_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO rollout_settings (id, auto_enabled, last_decision, last_reason, updated_at)
                VALUES (1, 0, '', '', '{_now()}');
                """
            )
            # api_credentials table for multi-tenant SaaS
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL UNIQUE,
                    api_key TEXT NOT NULL,
                    encrypted_api_secret TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _ensure_decision_trace_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(decision_traces)").fetchall()}
        for column in ["execution_instance_id", "lock_status", "lock_timestamp"]:
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE decision_traces ADD COLUMN {column} TEXT")
        if "failure_reason" not in existing_columns:
            connection.execute("ALTER TABLE decision_traces ADD COLUMN failure_reason TEXT")

    def save_funding_book(self, symbol: str, entries: Iterable[FundingBookEntry]) -> None:
        captured_at = _now()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO funding_book_snapshots (captured_at, symbol, rate, period, count, amount)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(captured_at, symbol, str(entry.rate), entry.period, entry.count, str(entry.amount)) for entry in entries],
            )

    def save_wallets(self, wallets: Iterable[Wallet]) -> None:
        captured_at = _now()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO wallets (captured_at, wallet_type, currency, balance, unsettled_interest, available_balance)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        captured_at,
                        wallet.wallet_type,
                        wallet.currency,
                        str(wallet.balance),
                        str(wallet.unsettled_interest),
                        str(wallet.available_balance),
                    )
                    for wallet in wallets
                ],
            )

    def upsert_funding_offers(self, offers: Iterable[FundingOffer]) -> None:
        captured_at = _now()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO funding_offers (
                    id, captured_at, symbol, mts_create, mts_update, amount, amount_orig,
                    offer_type, flags, status, rate, period
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    captured_at = excluded.captured_at,
                    mts_update = excluded.mts_update,
                    amount = excluded.amount,
                    status = excluded.status,
                    rate = excluded.rate,
                    period = excluded.period
                """,
                [
                    (
                        offer.id,
                        captured_at,
                        offer.symbol,
                        _dt(offer.mts_create),
                        _dt(offer.mts_update),
                        str(offer.amount),
                        str(offer.amount_orig),
                        offer.offer_type,
                        offer.flags,
                        offer.status,
                        str(offer.rate),
                        offer.period,
                    )
                    for offer in offers
                ],
            )

    def add_event(self, level: str, message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO events (created_at, level, message) VALUES (?, ?, ?)",
                (_now(), level, message),
            )

    def add_risk_decision(self, decision: RiskDecision) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO risk_decisions (
                    created_at, allowed, mode, rule, reason, total_capital, active_exposure,
                    proposed_exposure, exposure_ratio, idle_cash, daily_lending_amount
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    1 if decision.allowed else 0,
                    decision.mode.value,
                    decision.rule,
                    decision.reason,
                    str(decision.exposure.total_capital),
                    str(decision.exposure.active_exposure),
                    str(decision.exposure.proposed_exposure),
                    str(decision.exposure.exposure_ratio),
                    str(decision.exposure.idle_cash),
                    str(decision.exposure.daily_lending_amount),
                ),
            )

    def add_rollout_history(self, stage: int, allocation_percent: float, action: str, reason: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO rollout_history (created_at, stage, allocation_percent, action, reason) VALUES (?, ?, ?, ?, ?)",
                (_now(), stage, allocation_percent, action, reason or ""),
            )

    def get_rollout_history(self, limit: int = 100) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM rollout_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_rollout_settings(self) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM rollout_settings WHERE id = 1").fetchone()
        return _row_to_dict(row) if row is not None else None

    def set_rollout_settings(self, auto_enabled: bool, last_decision: str | None = None, last_reason: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO rollout_settings (id, auto_enabled, last_decision, last_reason, updated_at)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    auto_enabled = excluded.auto_enabled,
                    last_decision = excluded.last_decision,
                    last_reason = excluded.last_reason,
                    updated_at = excluded.updated_at
                """,
                (1 if auto_enabled else 0, last_decision or "", last_reason or "", _now()),
            )

    def add_decision_trace(self, trace: DecisionTrace) -> int:
        if trace.strategy_decision is None or trace.risk_decision is None:
            raise ValueError("Decision trace requires strategy and risk decisions")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO decision_traces (
                    created_at, input_snapshot, strategy_reason, create_offer_count, cancel_offer_count,
                    risk_allowed, risk_mode, risk_rule, risk_reason, outcome,
                    execution_instance_id, lock_status, lock_timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    json.dumps(trace.input_snapshot, sort_keys=True),
                    trace.strategy_decision.reason,
                    len(trace.strategy_decision.create_offers),
                    len(trace.strategy_decision.cancel_offer_ids),
                    1 if trace.risk_decision.allowed else 0,
                    trace.risk_decision.mode.value,
                    trace.risk_decision.rule,
                    trace.risk_decision.reason,
                    trace.outcome,
                    trace.execution_instance_id,
                    trace.lock_status,
                    trace.lock_timestamp,
                ),
            )
            return cursor.lastrowid

    def update_decision_trace(self, trace_id: int, trace: DecisionTrace) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE decision_traces SET
                    outcome = ?,
                    execution_instance_id = ?,
                    lock_status = ?,
                    lock_timestamp = ?,
                    failure_reason = ?
                WHERE id = ?
                """,
                (
                    trace.outcome,
                    trace.execution_instance_id,
                    trace.lock_status,
                    trace.lock_timestamp,
                    trace.failure_reason,
                    trace_id,
                ),
            )

    def get_kill_switch_state(self) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM kill_switch_state WHERE id = 1"
            ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def set_kill_switch_state(self, enabled: bool, reason: str | None = None, manual_override: bool = False) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kill_switch_state (id, enabled, reason, manual_override, updated_at)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    enabled = excluded.enabled,
                    reason = excluded.reason,
                    manual_override = excluded.manual_override,
                    updated_at = excluded.updated_at
                """,
                (
                    1 if enabled else 0,
                    reason or "",
                    1 if manual_override else 0,
                    _now(),
                ),
            )

    def save_api_credentials(self, user_id: str, api_key: str, encrypted_secret: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_credentials (user_id, api_key, encrypted_api_secret, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    api_key = excluded.api_key,
                    encrypted_api_secret = excluded.encrypted_api_secret,
                    updated_at = excluded.updated_at
                """,
                (user_id, api_key, encrypted_secret, _now()),
            )

    def get_api_credentials(self, user_id: str = "default_user") -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM api_credentials WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def get_all_api_credentials(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM api_credentials ORDER BY user_id"
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def repair_pending_decision_traces(self, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE decision_traces
                SET outcome = 'FAILED', failure_reason = ?
                WHERE outcome = 'PENDING'
                """,
                (reason,),
            )

    def record_apy(self, symbol: str, apy: float) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO apy_series (measured_at, symbol, apy) VALUES (?, ?, ?)",
                (_now(), symbol, apy),
            )

    def record_pnl(self, symbol: str, pnl: float) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pnl_series (measured_at, symbol, pnl) VALUES (?, ?, ?)",
                (_now(), symbol, pnl),
            )

    def record_exposure(self, symbol: str, total_capital: Decimal, active_exposure: Decimal, proposed_exposure: Decimal) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO exposure_history (measured_at, symbol, total_capital, active_exposure, proposed_exposure) VALUES (?, ?, ?, ?, ?)",
                (_now(), symbol, str(total_capital), str(active_exposure), str(proposed_exposure)),
            )

    def add_metric(self, name: str, value: float) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO metrics (created_at, name, value) VALUES (?, ?, ?)",
                (_now(), name, value),
            )

    def get_metrics(self, name: str, limit: int = 100) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM metrics WHERE name = ? ORDER BY created_at DESC LIMIT ?",
                (name, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_exposure_history(self, symbol: str, limit: int = 100) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM exposure_history WHERE symbol = ? ORDER BY measured_at DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_apy_series(self, symbol: str, limit: int = 100) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM apy_series WHERE symbol = ? ORDER BY measured_at DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_pnl_series(self, symbol: str, limit: int = 100) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pnl_series WHERE symbol = ? ORDER BY measured_at DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_rollout_state(self) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM rollout_state WHERE id = 1").fetchone()
        return _row_to_dict(row) if row is not None else None

    def set_rollout_state(self, stage: int, allocation_percent: float, max_percent: float) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO rollout_state (id, stage, allocation_percent, max_percent, updated_at)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    stage = excluded.stage,
                    allocation_percent = excluded.allocation_percent,
                    max_percent = excluded.max_percent,
                    updated_at = excluded.updated_at
                """,
                (stage, allocation_percent, max_percent, _now()),
            )

    def todays_lending_amount(self) -> Decimal:
        start = datetime.now(UTC).date().isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(CAST(amount_orig AS REAL)), 0) AS total
                FROM funding_offers
                WHERE captured_at >= ?
                  AND UPPER(COALESCE(status, '')) NOT LIKE '%CANCEL%'
                """,
                (start,),
            ).fetchone()
        return Decimal(str(row["total"] if row is not None else 0))

    def latest_wallets(self, limit: int = 50) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM wallets ORDER BY captured_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def latest_offers(self, limit: int = 50) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM funding_offers ORDER BY captured_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def latest_events(self, limit: int = 50) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def latest_risk_decision(self) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM risk_decisions ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def latest_decision_traces(self, limit: int = 100) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM decision_traces ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _row_to_dict(row: sqlite3.Row) -> dict[str, str]:
    return {key: str(_restore_decimal(row[key])) for key in row.keys()}


def _restore_decimal(value: object) -> object:
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return value
    return value
