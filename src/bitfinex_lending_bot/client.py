from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import hmac
import json
import time
from typing import Any, Protocol

import requests
from loguru import logger

from .models import CreateFundingOfferRequest, FundingBookEntry, FundingOffer, Wallet


class BitfinexClientError(RuntimeError):
    pass


class Transport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
        timeout: float,
    ) -> Any:
        ...


def requests_transport(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_payload: dict[str, Any] | None = None,
    timeout: float,
) -> Any:
    response = requests.request(method, url, headers=headers, json=json_payload, timeout=timeout)
    response.raise_for_status()
    if not response.content:
        return None
    return response.json()


class BitfinexApiClient:
    def __init__(
        self,
        api_key: str | None,
        api_secret: str | None,
        *,
        base_url: str = "https://api.bitfinex.com",
        timeout: float = 20.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        nonce_factory: Callable[[], str] | None = None,
        transport: Transport = requests_transport,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._nonce_factory = nonce_factory or (lambda: str(int(time.time() * 1_000_000)))
        self._transport = transport

    def get_funding_book(self, symbol: str, *, precision: str = "P0", length: int = 25) -> list[FundingBookEntry]:
        path = f"/v2/book/{symbol}/{precision}"
        data = self._public("GET", path, {"len": length})
        return [FundingBookEntry.from_bitfinex(row) for row in data]

    def get_wallets(self) -> list[Wallet]:
        data = self._private("POST", "/v2/auth/r/wallets", {})
        return [Wallet.from_bitfinex(row) for row in data]

    def get_funding_offers(self, symbol: str | None = None) -> list[FundingOffer]:
        path = f"/v2/auth/r/funding/offers/{symbol}" if symbol else "/v2/auth/r/funding/offers"
        data = self._private("POST", path, {})
        return [FundingOffer.from_bitfinex(row) for row in data]

    def create_funding_offer(self, request: CreateFundingOfferRequest) -> FundingOffer:
        if request.amount < Decimal("150"):
            raise ValueError("Funding offer amount must be >= 150 USD")
        data = self._private("POST", "/v2/auth/w/funding/offer/submit", request.to_payload())
        row = self._extract_notification_payload(data)
        offer = FundingOffer.from_bitfinex(row)
        logger.info("Created funding offer id={} symbol={} amount={} rate={}", offer.id, offer.symbol, offer.amount, offer.rate)
        return offer

    def cancel_funding_offer(self, offer_id: int) -> FundingOffer:
        data = self._private("POST", "/v2/auth/w/funding/offer/cancel", {"id": offer_id})
        row = self._extract_notification_payload(data)
        offer = FundingOffer.from_bitfinex(row)
        logger.info("Cancelled funding offer id={} status={}", offer.id, offer.status)
        return offer

    def _public(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        query = ""
        if params:
            query = "?" + "&".join(f"{key}={value}" for key, value in params.items())
        return self._request(method, f"{path}{query}", headers=None, payload=None)

    def _private(self, method: str, path: str, payload: dict[str, Any]) -> Any:
        if not self._api_key or not self._api_secret:
            raise BitfinexClientError("Bitfinex API credentials are required for private endpoints")

        nonce = self._nonce_factory()
        body = json.dumps(payload, separators=(",", ":"))
        signature_payload = f"/api{path}{nonce}{body}"
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            signature_payload.encode("utf-8"),
            hashlib.sha384,
        ).hexdigest()
        headers = {
            "bfx-nonce": nonce,
            "bfx-apikey": self._api_key,
            "bfx-signature": signature,
            "content-type": "application/json",
        }
        return self._request(method, path, headers=headers, payload=payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None,
        payload: dict[str, Any] | None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._transport(method, url, headers=headers, json_payload=payload, timeout=self._timeout)
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 429 and attempt < self._max_retries:
                    sleep_seconds = self._retry_sleep_seconds(attempt, rate_limited=True)
                    logger.warning("Bitfinex rate limit on {} attempt={}/{} backoff={}s", path, attempt, self._max_retries, sleep_seconds)
                    time.sleep(sleep_seconds)
                    continue
                if status_code is not None and 500 <= status_code < 600 and attempt < self._max_retries:
                    sleep_seconds = self._retry_sleep_seconds(attempt)
                    logger.warning("Bitfinex server error {} on {} attempt={}/{} retrying in {}s", status_code, path, attempt, self._max_retries, sleep_seconds)
                    time.sleep(sleep_seconds)
                    continue
                raise BitfinexClientError(f"Bitfinex HTTP error: {exc}") from exc
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt < self._max_retries:
                    sleep_seconds = self._retry_sleep_seconds(attempt)
                    logger.warning("Bitfinex request retry for {} attempt={}/{} backoff={}s error={}", path, attempt, self._max_retries, sleep_seconds, exc)
                    time.sleep(sleep_seconds)
                    continue
                raise BitfinexClientError(f"Bitfinex request failed after retries: {exc}") from exc
            except requests.RequestException as exc:
                raise BitfinexClientError(f"Bitfinex request failed: {exc}") from exc
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                raise BitfinexClientError(f"Unexpected Bitfinex response for {path}: {exc}") from exc
        raise BitfinexClientError(f"Bitfinex request failed after {self._max_retries} attempts: {path}")

    def _retry_sleep_seconds(self, attempt: int, *, rate_limited: bool = False) -> float:
        if rate_limited:
            # Strict 10s -> 20s -> 40s backoff for 429 Too Many Requests
            return 10.0 * (2 ** (attempt - 1))
        return self._retry_backoff_seconds * (2 ** (attempt - 1))

    @staticmethod
    def _extract_notification_payload(data: Any) -> list[Any]:
        if not isinstance(data, list) or len(data) < 5 or not isinstance(data[4], list):
            raise BitfinexClientError("Unexpected Bitfinex notification response")
        payload = data[4]
        if payload and isinstance(payload[0], list):
            return payload[0]
        return payload


class MockBitfinexApiClient(BitfinexApiClient):
    """Offline client used when API credentials are not configured."""

    def __init__(self) -> None:
        super().__init__(api_key=None, api_secret=None)
        self._offers: dict[int, FundingOffer] = {}
        self._next_offer_id = 1

    def get_funding_book(self, symbol: str, *, precision: str = "P0", length: int = 25) -> list[FundingBookEntry]:
        logger.info("Mock mode: funding book read for {} precision={} length={}", symbol, precision, length)
        return [
            FundingBookEntry(rate=Decimal("0.00020"), period=2, count=4, amount=Decimal("1200")),
            FundingBookEntry(rate=Decimal("0.00022"), period=7, count=2, amount=Decimal("800")),
        ][:length]

    def get_wallets(self) -> list[Wallet]:
        logger.info("Mock mode: wallet read")
        return [
            Wallet(
                wallet_type="funding",
                currency="USD",
                balance=Decimal("1000"),
                unsettled_interest=Decimal("0"),
                available_balance=Decimal("1000"),
            )
        ]

    def get_funding_offers(self, symbol: str | None = None) -> list[FundingOffer]:
        logger.info("Mock mode: funding offers read symbol={}", symbol or "all")
        offers = list(self._offers.values())
        if symbol is not None:
            return [offer for offer in offers if offer.symbol == symbol]
        return offers

    def create_funding_offer(self, request: CreateFundingOfferRequest) -> FundingOffer:
        if request.amount < Decimal("150"):
            raise ValueError("Funding offer amount must be >= 150 USD")
        offer_id = self._next_offer_id
        self._next_offer_id += 1
        now = datetime.now(UTC)
        offer = FundingOffer(
            id=offer_id,
            symbol=request.symbol,
            mts_create=now,
            mts_update=now,
            amount=request.amount,
            amount_orig=request.amount,
            offer_type="LIMIT",
            flags=64 if request.hidden else 0,
            status="MOCK_ACTIVE",
            rate=request.rate,
            period=request.period,
        )
        self._offers[offer.id] = offer
        logger.info("Mock mode: created funding offer id={} symbol={} amount={} rate={}", offer.id, offer.symbol, offer.amount, offer.rate)
        return offer

    def cancel_funding_offer(self, offer_id: int) -> FundingOffer:
        existing = self._offers.pop(offer_id, None)
        if existing is None:
            raise BitfinexClientError(f"Mock offer not found: {offer_id}")
        cancelled = FundingOffer(
            id=existing.id,
            symbol=existing.symbol,
            mts_create=existing.mts_create,
            mts_update=datetime.now(UTC),
            amount=Decimal("0"),
            amount_orig=existing.amount_orig,
            offer_type=existing.offer_type,
            flags=existing.flags,
            status="MOCK_CANCELLED",
            rate=existing.rate,
            period=existing.period,
        )
        logger.info("Mock mode: cancelled funding offer id={}", cancelled.id)
        return cancelled


class PaperTradingBitfinexApiClient(BitfinexApiClient):
    """Delegates reads to Bitfinex but never sends live create/cancel writes."""

    def __init__(self, live_client: BitfinexApiClient) -> None:
        super().__init__(api_key=None, api_secret=None)
        self._live_client = live_client
        self._paper_offers: dict[int, FundingOffer] = {}
        self._next_paper_offer_id = -1

    def get_funding_book(self, symbol: str, *, precision: str = "P0", length: int = 25) -> list[FundingBookEntry]:
        return self._live_client.get_funding_book(symbol, precision=precision, length=length)

    def get_wallets(self) -> list[Wallet]:
        return self._live_client.get_wallets()

    def get_funding_offers(self, symbol: str | None = None) -> list[FundingOffer]:
        live_offers = self._live_client.get_funding_offers(symbol)
        paper_offers = list(self._paper_offers.values())
        if symbol is not None:
            paper_offers = [offer for offer in paper_offers if offer.symbol == symbol]
        return live_offers + paper_offers

    def create_funding_offer(self, request: CreateFundingOfferRequest) -> FundingOffer:
        if request.amount < Decimal("150"):
            raise ValueError("Funding offer amount must be >= 150 USD")
        offer_id = self._next_paper_offer_id
        self._next_paper_offer_id -= 1
        now = datetime.now(UTC)
        offer = FundingOffer(
            id=offer_id,
            symbol=request.symbol,
            mts_create=now,
            mts_update=now,
            amount=request.amount,
            amount_orig=request.amount,
            offer_type="PAPER_LIMIT",
            flags=64 if request.hidden else 0,
            status="PAPER_ACTIVE",
            rate=request.rate,
            period=request.period,
        )
        self._paper_offers[offer.id] = offer
        logger.warning(
            "Paper trading mode: simulated funding offer id={} symbol={} amount={} rate={} period={}",
            offer.id,
            offer.symbol,
            offer.amount,
            offer.rate,
            offer.period,
        )
        return offer

    def cancel_funding_offer(self, offer_id: int) -> FundingOffer:
        existing = self._paper_offers.pop(offer_id, None)
        if existing is None:
            logger.warning("Paper trading mode: simulated cancel for live offer id={} without sending API write", offer_id)
            now = datetime.now(UTC)
            return FundingOffer(
                id=offer_id,
                symbol="PAPER",
                mts_create=None,
                mts_update=now,
                amount=Decimal("0"),
                amount_orig=Decimal("0"),
                offer_type="PAPER_CANCEL",
                flags=0,
                status="PAPER_CANCELLED",
                rate=Decimal("0"),
                period=0,
            )
        cancelled = FundingOffer(
            id=existing.id,
            symbol=existing.symbol,
            mts_create=existing.mts_create,
            mts_update=datetime.now(UTC),
            amount=Decimal("0"),
            amount_orig=existing.amount_orig,
            offer_type=existing.offer_type,
            flags=existing.flags,
            status="PAPER_CANCELLED",
            rate=existing.rate,
            period=existing.period,
        )
        logger.warning("Paper trading mode: simulated cancel for paper offer id={}", cancelled.id)
        return cancelled
