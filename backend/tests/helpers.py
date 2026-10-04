from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.collectors.base import BaseCollector, CollectorError, CompanyQuery, RawItem
from app.models import Category, Company, Source
from app.services.collection_service import store_items


class FakeCollector(BaseCollector):
    """Deterministic collector for tests (no network)."""

    key = "hackernews"
    name = "Hacker News"

    def __init__(self, items_by_company: dict[str, list[RawItem]] | None = None, fail: bool = False):
        self.items_by_company = items_by_company or {}
        self.fail = fail
        self.calls = 0

    def fetch(self, company: CompanyQuery) -> list[RawItem]:
        self.calls += 1
        if self.fail:
            raise CollectorError("Hacker News: request timed out")
        return list(self.items_by_company.get(company.name, []))


class FailingGdelt(FakeCollector):
    key = "gdelt"
    name = "GDELT News"

    def __init__(self):
        super().__init__(fail=True)


def raw(title: str, url: str, days_ago: float = 1, summary: str = "") -> RawItem:
    return RawItem(url=url, title=title, summary=summary, published_at=datetime.now(timezone.utc) - timedelta(days=days_ago))


def seed_items(db, company_id: int, items: list[RawItem]) -> tuple[int, int, int]:
    company = db.get(Company, company_id)
    source = db.scalar(select(Source).where(Source.key == "hackernews"))
    categories = {c.slug: c for c in db.scalars(select(Category))}
    return store_items(db, company, source, None, items, categories)
