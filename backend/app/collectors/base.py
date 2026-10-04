"""Collector framework.

Every data source implements `BaseCollector.fetch()` and returns `RawItem`s. Collectors only
*fetch and parse* — cleaning, de-duplication and persistence live in the collection service, so a
new source only needs a small subclass registered in `registry.py`.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CompanyQuery:
    id: int
    name: str
    search_terms: str | None = None
    website: str | None = None
    rss_url: str | None = None

    @property
    def terms(self) -> list[str]:
        """Search terms: explicit comma-separated terms, else the company name."""
        if self.search_terms:
            terms = [t.strip() for t in self.search_terms.split(",") if t.strip()]
            if terms:
                return terms
        return [self.name]


@dataclass
class RawItem:
    url: str
    title: str
    summary: str = ""
    published_at: datetime | None = None
    external_id: str | None = None
    author: str | None = None
    score: int | None = None
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class CollectorError(Exception):
    """A recoverable failure of one collector for one company. Never crashes the run."""


class RateLimitedError(CollectorError):
    pass


class InvalidResponseError(CollectorError):
    pass


class BaseCollector(ABC):
    key: str = ""
    name: str = ""
    kind: str = "api"
    base_url: str = ""
    max_retries: int = 2
    backoff_seconds: float = 1.5
    request_timeout: float | None = None  # per-collector override of the shared client timeout

    def __init__(self, client: httpx.Client, max_items: int = 30, lookback_days: int = 30):
        self.client = client
        self.max_items = max_items
        self.lookback_days = lookback_days

    def is_applicable(self, company: CompanyQuery) -> bool:
        return True

    @abstractmethod
    def fetch(self, company: CompanyQuery) -> list[RawItem]:
        """Fetch and parse items for one company. Raise CollectorError on failure."""

    # ---- HTTP helpers with retries, timeouts and response validation ----
    def _request(self, url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                kwargs = {"timeout": self.request_timeout} if self.request_timeout else {}
                resp = self.client.get(url, params=params, headers=headers, **kwargs)
            except httpx.TimeoutException as exc:
                last_error = CollectorError(f"{self.name}: request timed out")
                logger.warning("%s timeout (attempt %s): %s", self.key, attempt + 1, exc)
            except httpx.HTTPError as exc:
                last_error = CollectorError(f"{self.name}: network error ({exc.__class__.__name__})")
                logger.warning("%s network error (attempt %s): %s", self.key, attempt + 1, exc)
            else:
                if resp.status_code == 429:
                    last_error = RateLimitedError(f"{self.name}: rate limited by provider (HTTP 429)")
                    retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                    if attempt < self.max_retries:
                        self._sleep(min(retry_after or self.backoff_seconds * (attempt + 1) * 2, 15))
                    continue
                if resp.status_code >= 500:
                    last_error = CollectorError(f"{self.name}: provider error (HTTP {resp.status_code})")
                elif resp.status_code >= 400:
                    # Client errors are not retryable.
                    raise CollectorError(f"{self.name}: request rejected (HTTP {resp.status_code})")
                else:
                    return resp
            if attempt < self.max_retries:
                self._sleep(self.backoff_seconds * (attempt + 1))
        assert last_error is not None
        raise last_error

    def _get_json(self, url: str, params: dict | None = None) -> Any:
        resp = self._request(url, params=params)
        try:
            return resp.json()
        except ValueError as exc:
            snippet = resp.text[:120].strip().replace("\n", " ")
            if "limit requests" in snippet.lower() or "rate limit" in snippet.lower():
                raise RateLimitedError(f"{self.name}: rate limited by provider") from exc
            raise InvalidResponseError(f"{self.name}: response was not valid JSON") from exc

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
