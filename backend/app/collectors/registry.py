"""Collector registry. To add a source: subclass BaseCollector and add it to COLLECTOR_CLASSES."""

import httpx

from app.collectors.base import BaseCollector
from app.collectors.demo import DemoCollector
from app.collectors.gdelt import GdeltNewsCollector
from app.collectors.hackernews import HackerNewsCollector
from app.collectors.rss import RssFeedCollector
from app.config import Settings

COLLECTOR_CLASSES: dict[str, type[BaseCollector]] = {
    cls.key: cls for cls in (HackerNewsCollector, GdeltNewsCollector, RssFeedCollector, DemoCollector)
}


def make_http_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_seconds, connect=10.0),
        headers={"User-Agent": settings.collector_user_agent, "Accept": "application/json, application/xml, text/xml, */*"},
        follow_redirects=True,
    )


def build_collectors(settings: Settings, client: httpx.Client) -> list[BaseCollector]:
    keys = ["demo"] if settings.collector_demo_mode else settings.enabled_collector_list
    collectors = []
    for key in keys:
        cls = COLLECTOR_CLASSES.get(key)
        if cls is None:
            continue
        collectors.append(cls(client, max_items=settings.max_items_per_source, lookback_days=settings.collection_lookback_days))
    return collectors
