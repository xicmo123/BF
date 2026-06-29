from __future__ import annotations

from bitfinex_lending_bot.client import BitfinexApiClient
from bitfinex_lending_bot.config import load_settings
from bitfinex_lending_bot.models import FundingOffer


def get_funding_offers(symbol: str | None = None) -> list[FundingOffer]:
    settings = load_settings()
    client = BitfinexApiClient(settings.bitfinex_api_key, settings.bitfinex_api_secret)
    return client.get_funding_offers(symbol)
