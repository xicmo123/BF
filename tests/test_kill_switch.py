from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from bitfinex_lending_bot.config import Settings
from bitfinex_lending_bot.notifier import TelegramNotifier
from bitfinex_lending_bot.ops import OpsManager
from bitfinex_lending_bot.storage import SQLiteRepository


def test_failure_counter_operations(tmp_path: Path) -> None:
    """Test failure counter increment, reset, and get operations."""
    repo = SQLiteRepository(tmp_path / "test.sqlite3")
    repo.initialize()

    # Initial count should be 0
    assert repo.get_failure_count() == 0

    # Increment to 1
    count = repo.increment_failure_count()
    assert count == 1
    assert repo.get_failure_count() == 1

    # Increment to 2
    count = repo.increment_failure_count()
    assert count == 2
    assert repo.get_failure_count() == 2

    # Reset to 0
    repo.reset_failure_count()
    assert repo.get_failure_count() == 0

    # Increment again after reset
    count = repo.increment_failure_count()
    assert count == 1


def test_reset_kill_switch(tmp_path: Path) -> None:
    """Test OpsManager reset_kill_switch method."""
    repo = SQLiteRepository(tmp_path / "test.sqlite3")
    repo.initialize()
    settings = Settings(
        bitfinex_api_key=None,
        bitfinex_api_secret=None,
        telegram_token=None,
        telegram_chat_id=None,
        database_path=tmp_path / "test.sqlite3",
        log_path=tmp_path / "test.log",
    )
    notifier = TelegramNotifier(None, None)
    ops = OpsManager(repo, notifier, settings)

    # Set failure count to 1 to verify it gets reset
    repo.increment_failure_count()
    assert repo.get_failure_count() == 1

    # Enable kill switch
    repo.set_kill_switch_state(enabled=True, reason="test", manual_override=False)
    state = repo.get_kill_switch_state()
    assert state is not None
    assert int(state.get("enabled", "0")) == 1

    # Reset kill switch
    ops.reset_kill_switch("test_reset")

    # Verify failure count is reset
    assert repo.get_failure_count() == 0

    # Verify it's disabled
    state = repo.get_kill_switch_state()
    assert state is not None
    assert int(state.get("enabled", "0")) == 0
    assert state.get("reason") == "test_reset"
    assert int(state.get("manual_override", "0")) == 1

    # Check event was logged
    events = repo.latest_events(limit=10)
    assert any("Kill switch reset" in event.get("message", "") for event in events)


def test_failure_counter_persistence(tmp_path: Path) -> None:
    """Test that failure counter persists across repository instances."""
    db_path = tmp_path / "test.sqlite3"

    # First repository instance
    repo1 = SQLiteRepository(db_path)
    repo1.initialize()
    repo1.increment_failure_count()
    repo1.increment_failure_count()
    assert repo1.get_failure_count() == 2

    # Second repository instance (simulating restart)
    repo2 = SQLiteRepository(db_path)
    repo2.initialize()
    assert repo2.get_failure_count() == 2

    # Reset with second instance
    repo2.reset_failure_count()
    assert repo2.get_failure_count() == 0

    # Verify with first instance
    assert repo1.get_failure_count() == 0
