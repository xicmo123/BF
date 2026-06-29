from __future__ import annotations

from decimal import Decimal
import sqlite3

import pytest

from bitfinex_lending_bot.bot import LendingBot
from bitfinex_lending_bot.config import Settings
from bitfinex_lending_bot.notifier import TelegramNotifier
from bitfinex_lending_bot.risk import RiskConfig, RiskManager
from bitfinex_lending_bot.storage import SQLiteRepository
from bitfinex_lending_bot.strategy import PassiveSpreadStrategy
from bitfinex_lending_bot.stress import (
    ScenarioClient,
    StressScenario,
    api_timeout_scenario,
    empty_book_scenario,
    extreme_rate_scenario,
    sqlite_write_failure_scenario,
    wallet_balance_shock_scenario,
)


class FailingWriteRepository(SQLiteRepository):
    def save_funding_book(self, symbol, entries):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("simulated sqlite write failure")


def _settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        bitfinex_api_key=None,
        bitfinex_api_secret=None,
        telegram_token=None,
        telegram_chat_id=None,
        database_path=tmp_path / "bot.sqlite3",
        log_path=tmp_path / "bot.log",
        max_funding_rate=Decimal("0.001"),
        min_idle_cash_threshold=Decimal("100"),
    )


def _bot_for_scenario(tmp_path, scenario: StressScenario):  # type: ignore[no-untyped-def]
    settings = _settings(tmp_path)
    client = ScenarioClient(scenario)
    repository: SQLiteRepository = FailingWriteRepository(settings.database_path) if scenario.sqlite_write_failure else SQLiteRepository(settings.database_path)
    bot = LendingBot(
        settings=settings,
        client=client,
        repository=repository,
        notifier=TelegramNotifier(None, None),
        strategy=PassiveSpreadStrategy(),
        risk_manager=RiskManager(RiskConfig.from_settings(settings)),
    )
    return bot, client, repository


@pytest.mark.parametrize(
    "scenario",
    [
        extreme_rate_scenario(Decimal("10")),
        extreme_rate_scenario(Decimal("50")),
        empty_book_scenario(),
        api_timeout_scenario(),
        sqlite_write_failure_scenario(),
        wallet_balance_shock_scenario(),
    ],
)
def test_stress_scenarios_block_offer_execution(tmp_path, scenario: StressScenario) -> None:  # type: ignore[no-untyped-def]
    bot, client, repository = _bot_for_scenario(tmp_path, scenario)

    bot.run_once("fUSD")

    assert client.created_offer_count == 0
    if not scenario.sqlite_write_failure:
        risk = repository.latest_risk_decision()
        assert risk is not None
        assert risk["allowed"] == "0"
        assert risk["mode"] == "KILL_SWITCH"


def test_sqlite_write_failure_triggers_kill_switch_without_offer_execution(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bot, client, _repository = _bot_for_scenario(tmp_path, sqlite_write_failure_scenario())

    bot.run_once("fUSD")

    assert client.created_offer_count == 0
    assert bot._risk_manager.mode == "KILL_SWITCH"
