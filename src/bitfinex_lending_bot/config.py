from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bitfinex_api_key: str | None
    bitfinex_api_secret: str | None
    telegram_token: str | None
    telegram_chat_id: str | None
    database_path: Path
    log_path: Path
    default_currency: str = "fUSD"
    request_timeout_seconds: float = 20.0
    max_capital_exposure: Decimal = Decimal("0.30")
    max_daily_lending_amount: Decimal = Decimal("500")
    min_idle_cash_threshold: Decimal = Decimal("100")
    encryption_key: str | None = None
    kill_switch_enabled: bool = False
    max_funding_rate: Decimal = Decimal("0.01")
    max_funding_rate_spread: Decimal = Decimal("0.005")
    paper_trading_enabled: bool = True

    @property
    def has_bitfinex_credentials(self) -> bool:
        return bool(self.bitfinex_api_key and self.bitfinex_api_secret)

    @property
    def has_telegram_credentials(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)


def load_settings(env_file: str | Path | None = None) -> Settings:
    if env_file is not None:
        load_dotenv(env_file)
    else:
        load_dotenv()

    return Settings(
        bitfinex_api_key=os.getenv("BFX_API_KEY") or os.getenv("BITFINEX_API_KEY"),
        bitfinex_api_secret=os.getenv("BFX_API_SECRET") or os.getenv("BITFINEX_API_SECRET"),
        telegram_token=os.getenv("TELEGRAM_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        database_path=Path(os.getenv("DATABASE_PATH", "data/lending_bot.sqlite3")),
        log_path=Path(os.getenv("LOG_PATH", "logs/bot.log")),
        default_currency=os.getenv("DEFAULT_CURRENCY", "fUSD"),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        max_capital_exposure=Decimal(os.getenv("MAX_CAPITAL_EXPOSURE", "0.30")),
        max_daily_lending_amount=Decimal(os.getenv("MAX_DAILY_LENDING_AMOUNT", "500")),
        min_idle_cash_threshold=Decimal(os.getenv("MIN_IDLE_CASH_THRESHOLD", "100")),
        kill_switch_enabled=_bool(os.getenv("KILL_SWITCH", "false")),
        max_funding_rate=Decimal(os.getenv("MAX_FUNDING_RATE", "0.01")),
        max_funding_rate_spread=Decimal(os.getenv("MAX_FUNDING_RATE_SPREAD", "0.005")),
        encryption_key=os.getenv("ENCRYPTION_KEY"),
        paper_trading_enabled=_bool(os.getenv("PAPER_TRADING", "true")),
    )


def load_env() -> dict[str, str | None]:
    settings = load_settings()
    return {
        "BFX_API_KEY": settings.bitfinex_api_key,
        "BFX_API_SECRET": settings.bitfinex_api_secret,
        "TELEGRAM_TOKEN": settings.telegram_token,
        "TELEGRAM_CHAT_ID": settings.telegram_chat_id,
        "DATABASE_PATH": str(settings.database_path),
    }


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
