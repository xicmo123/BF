from __future__ import annotations

from decimal import Decimal
from threading import Thread

from bitfinex_lending_bot.bot import LendingBot
from bitfinex_lending_bot.client import BitfinexClientError, MockBitfinexApiClient
from bitfinex_lending_bot.config import Settings
from bitfinex_lending_bot.notifier import TelegramNotifier
from bitfinex_lending_bot.risk import RiskConfig, RiskManager
from bitfinex_lending_bot.stress import ScenarioClient, StressScenario
from bitfinex_lending_bot.storage import SQLiteRepository
from bitfinex_lending_bot.strategy import PassiveSpreadStrategy


class FailingClient(MockBitfinexApiClient):
    def get_funding_book(self, symbol: str, *, precision: str = "P0", length: int = 25):  # type: ignore[no-untyped-def]
        raise BitfinexClientError("boom")


def test_bot_api_failure_falls_back_to_safe_idle(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = SQLiteRepository(tmp_path / "bot.sqlite3")
    settings = Settings(
        bitfinex_api_key=None,
        bitfinex_api_secret=None,
        telegram_token=None,
        telegram_chat_id=None,
        database_path=tmp_path / "bot.sqlite3",
        log_path=tmp_path / "bot.log",
    )
    bot = LendingBot(
        settings=settings,
        client=FailingClient(),
        repository=repository,
        notifier=TelegramNotifier(None, None),
        strategy=PassiveSpreadStrategy(),
        risk_manager=RiskManager(RiskConfig.from_settings(settings)),
    )

    bot.run_once("fUSD")

    risk = repository.latest_risk_decision()
    assert risk is not None
    assert risk["mode"] == "KILL_SWITCH"
    assert risk["rule"] == "API_FAILURE"


def test_global_execution_lock_prevents_duplicate_create(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        bitfinex_api_key=None,
        bitfinex_api_secret=None,
        telegram_token=None,
        telegram_chat_id=None,
        database_path=tmp_path / "bot.sqlite3",
        log_path=tmp_path / "bot.log",
    )
    client = ScenarioClient(StressScenario(name="normal"))
    repository1 = SQLiteRepository(settings.database_path)
    repository2 = SQLiteRepository(settings.database_path)
    bot1 = LendingBot(
        settings=settings,
        client=client,
        repository=repository1,
        notifier=TelegramNotifier(None, None),
        strategy=PassiveSpreadStrategy(),
        risk_manager=RiskManager(RiskConfig.from_settings(settings)),
    )
    bot2 = LendingBot(
        settings=settings,
        client=client,
        repository=repository2,
        notifier=TelegramNotifier(None, None),
        strategy=PassiveSpreadStrategy(),
        risk_manager=RiskManager(RiskConfig.from_settings(settings)),
    )

    threads = [Thread(target=bot.run_once, args=("fUSD",)) for bot in (bot1, bot2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert client.created_offer_count == 1
    traces = SQLiteRepository(settings.database_path).latest_decision_traces()
    assert any(trace["lock_status"] == "ACQUIRED" for trace in traces)
