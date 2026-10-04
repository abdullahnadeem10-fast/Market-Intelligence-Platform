from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector, CollectorError, CompanyQuery, InvalidResponseError, RawItem


class RssFeedCollector(BaseCollector):
    """A company's own public RSS/Atom feed (press room, blog, changelog).

    Only runs for companies that have an `rss_url`. robots.txt is checked before fetching and the
    collector refuses to fetch disallowed feeds.
    """

    key = "rss"
    name = "Company RSS Feed"
    kind = "rss"
    user_agent = "MarketIntelligencePlatform"

    def is_applicable(self, company: CompanyQuery) -> bool:
        return bool(company.rss_url)

    def fetch(self, company: CompanyQuery) -> list[RawItem]:
        assert company.rss_url
        if not self._robots_allowed(company.rss_url):
            raise CollectorError("Company RSS Feed: fetching this feed is disallowed by robots.txt")
        resp = self._request(company.rss_url)
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type and "xml" not in content_type:
            raise InvalidResponseError("Company RSS Feed: URL returned HTML, not an RSS/Atom feed")
        try:
            soup = BeautifulSoup(resp.content, "xml")
        except Exception as exc:  # parser errors vary by lxml version
            raise InvalidResponseError("Company RSS Feed: could not parse feed XML") from exc

        entries = soup.find_all("item") or soup.find_all("entry")
        if not entries and not soup.find(["rss", "feed", "RDF"]):
            raise InvalidResponseError("Company RSS Feed: document is not an RSS/Atom feed")

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        items: list[RawItem] = []
        for entry in entries:
            title = _text(entry.find("title"))
            link = _link(entry)
            if not title or not link:
                continue
            published = _parse_date(
                _text(entry.find("pubDate")) or _text(entry.find("published")) or _text(entry.find("updated"))
            )
            if published and published < cutoff:
                continue
            raw_summary = _text(entry.find("description")) or _text(entry.find("summary")) or _text(entry.find("content"))
            summary = BeautifulSoup(raw_summary, "html.parser").get_text(" ") if raw_summary else ""
            items.append(
                RawItem(
                    external_id=_text(entry.find("guid")) or _text(entry.find("id")) or None,
                    url=link,
                    title=title,
                    summary=summary,
                    author=_text(entry.find("author")) or _text(entry.find("creator")) or None,
                    published_at=published,
                )
            )
            if len(items) >= self.max_items:
                break
        return items

    def _robots_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            resp = self.client.get(robots_url)
        except httpx.HTTPError:
            return True  # robots.txt unreachable: treat as no restrictions (standard crawler behaviour)
        if resp.status_code in (401, 403):
            return False
        if resp.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.parse(resp.text.splitlines())
        return parser.can_fetch(self.user_agent, url)


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _link(entry) -> str:
    link = entry.find("link")
    if link is None:
        return ""
    href = link.get("href")
    return (href or link.get_text(strip=True) or "").strip()


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
