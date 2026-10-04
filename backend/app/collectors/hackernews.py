import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector, CompanyQuery, InvalidResponseError, RawItem


class HackerNewsCollector(BaseCollector):
    """Tech news & discussion from Hacker News via the public Algolia search API (no key needed)."""

    key = "hackernews"
    name = "Hacker News"
    kind = "api"
    base_url = "https://hn.algolia.com/api/v1/search_by_date"

    def fetch(self, company: CompanyQuery) -> list[RawItem]:
        since = int((datetime.now(timezone.utc) - timedelta(days=self.lookback_days)).timestamp())
        items: list[RawItem] = []
        seen: set[str] = set()
        for term in company.terms[:3]:
            data = self._get_json(
                self.base_url,
                params={
                    "query": f'"{term}"',
                    "tags": "story",
                    "numericFilters": f"created_at_i>{since}",
                    "hitsPerPage": self.max_items,
                },
            )
            if not isinstance(data, dict) or not isinstance(data.get("hits"), list):
                raise InvalidResponseError("Hacker News: unexpected response shape")
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for hit in data["hits"]:
                if not isinstance(hit, dict):
                    continue
                object_id = str(hit.get("objectID") or "")
                title = hit.get("title") or ""
                story_text = hit.get("story_text") or ""
                # Algolia matching is fuzzy; keep only stories that actually mention the term.
                if not object_id or object_id in seen or not (pattern.search(title) or pattern.search(story_text)):
                    continue
                seen.add(object_id)
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
                summary = " ".join(BeautifulSoup(story_text, "html.parser").get_text(" ").split()) if story_text else ""
                items.append(
                    RawItem(
                        external_id=f"hn:{object_id}",
                        url=url,
                        title=title,
                        summary=summary,
                        author=hit.get("author"),
                        score=hit.get("points") if isinstance(hit.get("points"), int) else None,
                        published_at=_from_ts(hit.get("created_at_i")),
                        language="en",
                        extra={"discussion_url": f"https://news.ycombinator.com/item?id={object_id}"},
                    )
                )
        return items[: self.max_items]


def _from_ts(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
