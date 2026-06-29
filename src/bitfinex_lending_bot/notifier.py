from __future__ import annotations

from typing import Any

import requests
from loguru import logger


class NotificationError(RuntimeError):
    pass


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None, *, timeout: float = 10.0) -> None:
        self._token = token
        self._chat_id = chat_id
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, message: str) -> None:
        if not self.enabled:
            logger.debug("Telegram notification skipped because credentials are not configured")
            return

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload: dict[str, Any] = {"chat_id": self._chat_id, "text": message, "parse_mode": "HTML"}
        try:
            response = requests.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NotificationError(f"Telegram notification failed: {exc}") from exc


def notify(message: str) -> None:
    from .config import load_settings

    settings = load_settings()
    TelegramNotifier(settings.telegram_token, settings.telegram_chat_id).send(message)

