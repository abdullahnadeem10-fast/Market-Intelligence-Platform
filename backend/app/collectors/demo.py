import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.collectors.base import BaseCollector, CompanyQuery, RawItem

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "demo_items.json"


class DemoCollector(BaseCollector):
    """Offline demo mode (COLLECTOR_DEMO_MODE=true).

    Serves a small, bundled sample dataset about *fictional* companies (Acme Robotics, Globex
    Cloud, Initech AI) so the full pipeline can be exercised without network access. Items are
    clearly labelled with the source "Demo Dataset" and point to example.com. It never invents
    content for arbitrary real companies: other company names simply get no demo items.
    """

    key = "demo"
    name = "Demo Dataset (sample, not live)"
    kind = "demo"
    base_url = "local:demo_items.json"

    def fetch(self, company: CompanyQuery) -> list[RawItem]:
        records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        wanted = {company.name.lower(), *(t.lower() for t in company.terms)}
        items: list[RawItem] = []
        for rec in records:
            if rec["company"].lower() not in wanted:
                continue
            items.append(
                RawItem(
                    external_id=f"demo:{rec['id']}",
                    url=rec["url"],
                    title=rec["title"],
                    summary=rec["summary"],
                    author="Demo dataset",
                    published_at=now - timedelta(days=rec["days_ago"], hours=rec.get("hours_ago", 0)),
                )
            )
        return items[: self.max_items]
