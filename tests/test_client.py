from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import requests

from bitfinex_lending_bot.client import BitfinexApiClient, BitfinexClientError
from bitfinex_lending_bot.models import CreateFundingOfferRequest


def test_get_funding_book_parses_rows() -> None:
    calls: list[dict[str, Any]] = []

    def fake_transport(method: str, url: str, **kwargs: Any) -> list[list[Any]]:
        calls.append({"method": method, "url": url, **kwargs})
        return [["0.0002", 2, 3, "100.5"]]

    client = BitfinexApiClient(None, None, transport=fake_transport)
    entries = client.get_funding_book("fUSD")

    assert calls[0]["url"].endswith("/v2/book/fUSD/P0?len=25")
    assert entries[0].rate == Decimal("0.0002")
    assert entries[0].amount == Decimal("100.5")


def test_private_endpoint_requires_credentials() -> None:
    client = BitfinexApiClient(None, None)

    with pytest.raises(BitfinexClientError):
        client.get_wallets()


def test_create_offer_signs_private_request() -> None:
    captured: dict[str, Any] = {}

    def fake_transport(method: str, url: str, **kwargs: Any) -> list[Any]:
        captured.update({"method": method, "url": url, **kwargs})
        row = [123, "fUSD", 0, 0, "150", "150", "LIMIT", None, None, 0, "ACTIVE", None, None, None, "0.0002", 2]
        return [0, "fon-req", None, None, row, None, "SUCCESS", "Submitted"]

    client = BitfinexApiClient("key", "secret", nonce_factory=lambda: "42", transport=fake_transport)
    offer = client.create_funding_offer(
        CreateFundingOfferRequest(symbol="fUSD", amount=Decimal("150"), rate=Decimal("0.0002"), period=2)
    )

    assert offer.id == 123
    assert captured["headers"]["bfx-apikey"] == "key"
    assert captured["headers"]["bfx-nonce"] == "42"
    assert captured["json_payload"]["symbol"] == "fUSD"


def test_request_retries_timeout_then_succeeds() -> None:
    attempts = 0

    def fake_transport(method: str, url: str, **kwargs: Any) -> list[list[Any]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("slow")
        return [["0.0002", 2, 1, "10"]]

    client = BitfinexApiClient(None, None, transport=fake_transport, retry_backoff_seconds=0)

    entries = client.get_funding_book("fUSD")

    assert attempts == 2
    assert entries[0].amount == Decimal("10")


def test_create_offer_validation_raises_error() -> None:
    client = BitfinexApiClient("key", "secret")
    with pytest.raises(ValueError, match="Funding offer amount must be >= 150 USD"):
        client.create_funding_offer(
            CreateFundingOfferRequest(symbol="fUSD", amount=Decimal("149.99"), rate=Decimal("0.0002"), period=2)
        )

    from bitfinex_lending_bot.client import MockBitfinexApiClient, PaperTradingBitfinexApiClient
    mock_client = MockBitfinexApiClient()
    with pytest.raises(ValueError, match="Funding offer amount must be >= 150 USD"):
        mock_client.create_funding_offer(
            CreateFundingOfferRequest(symbol="fUSD", amount=Decimal("10"), rate=Decimal("0.0002"), period=2)
        )

    paper_client = PaperTradingBitfinexApiClient(mock_client)
    with pytest.raises(ValueError, match="Funding offer amount must be >= 150 USD"):
        paper_client.create_funding_offer(
            CreateFundingOfferRequest(symbol="fUSD", amount=Decimal("10"), rate=Decimal("0.0002"), period=2)
        )
