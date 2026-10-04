"""Optional company description enrichment from the public Wikipedia REST API."""

import logging
from urllib.parse import quote

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def fetch_company_description(name: str, client: httpx.Client | None = None) -> str | None:
    settings = get_settings()
    if not settings.enrichment_enabled:
        return None
    own_client = client is None
    client = client or httpx.Client(timeout=6.0, headers={"User-Agent": settings.collector_user_agent})
    try:
        resp = client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(name.replace(' ', '_'))}")
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("type") != "standard":  # skip disambiguation pages
            return None
        extract = (data.get("extract") or "").strip()
        return extract[:1500] or None
    except (httpx.HTTPError, ValueError):
        logger.info("Wikipedia enrichment unavailable for %r", name)
        return None
    finally:
        if own_client:
            client.close()
