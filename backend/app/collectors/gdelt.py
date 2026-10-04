import threading
import time
from datetime import datetime, timezone

from app.collectors.base import BaseCollector, CompanyQuery, InvalidResponseError, RateLimitedError, RawItem


class GdeltNewsCollector(BaseCollector):
    """Global online news coverage via the public GDELT DOC 2.0 API (no key needed).

    GDELT asks clients to send at most one request every 5 seconds, so requests are throttled
    process-wide (measured from when the previous response finished). GDELT returns headlines and
    metadata only (no article body) and matches full text, so items may only mention the company.
    """

    key = "gdelt"
    name = "GDELT News"
    kind = "api"
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    min_interval_seconds = 10.0  # GDELT asks for >=5s; responses are slow so leave headroom
    max_retries = 1
    backoff_seconds = 10.0
    request_timeout = 45.0  # GDELT full-text queries routinely take 15-25s

    cooldown_seconds = 120.0

    _lock = threading.Lock()
    _last_request = 0.0
    _cooldown_until = 0.0  # shared across runs: back off after GDELT rate-limits this host

    def fetch(self, company: CompanyQuery) -> list[RawItem]:
        if time.monotonic() < GdeltNewsCollector._cooldown_until:
            raise RateLimitedError("GDELT News: cooling down after a recent rate limit")
        terms = company.terms[:3]
        query = " OR ".join(f'"{t}"' for t in terms)
        if len(terms) > 1:
            query = f"({query})"
        days = max(1, min(self.lookback_days, 90))
        with GdeltNewsCollector._lock:
            wait = self.min_interval_seconds - (time.monotonic() - GdeltNewsCollector._last_request)
            if wait > 0:
                self._sleep(wait)
            try:
                data = self._get_json(
                    self.base_url,
                    params={
                        "query": f"{query} sourcelang:english",
                        "mode": "artlist",
                        "format": "json",
                        "maxrecords": self.max_items,
                        "sort": "datedesc",
                        "timespan": f"{days}d",
                    },
                )
            except RateLimitedError:
                GdeltNewsCollector._cooldown_until = time.monotonic() + self.cooldown_seconds
                raise
            finally:
                GdeltNewsCollector._last_request = time.monotonic()

        if data == {} or (isinstance(data, dict) and "articles" not in data):
            return []  # GDELT returns {} when there are no matches
        if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
            raise InvalidResponseError("GDELT: unexpected response shape")

        items: list[RawItem] = []
        for art in data["articles"]:
            if not isinstance(art, dict) or not art.get("url") or not art.get("title"):
                continue
            items.append(
                RawItem(
                    url=art["url"],
                    title=art["title"],
                    published_at=_parse_seendate(art.get("seendate")),
                    language=(art.get("language") or "")[:20] or None,
                    extra={"domain": art.get("domain"), "country": art.get("sourcecountry")},
                )
            )
        return items


def _parse_seendate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
