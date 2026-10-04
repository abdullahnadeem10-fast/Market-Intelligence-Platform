"""Cleaning / normalization of raw collected items before storage."""

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.collectors.base import RawItem

TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$|ref_src$|cmpid$)", re.IGNORECASE)
MAX_TITLE = 500
MAX_SUMMARY = 2000


@dataclass
class CleanItem:
    url: str
    url_hash: str
    content_hash: str
    title: str
    summary: str
    domain: str | None
    published_at: datetime
    external_id: str | None
    author: str | None
    score: int | None
    language: str | None


class InvalidItem(ValueError):
    pass


def canonicalize_url(url: str) -> str:
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise InvalidItem("URL must be absolute http(s)")
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, query, ""))


def clean_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def title_fingerprint(title: str) -> str:
    """Normalized title used to detect the same story arriving from different URLs/sources."""
    t = title.lower()
    t = re.sub(r"\s[-|–—]\s[^-|–—]{2,40}$", "", t)  # drop trailing " - Publisher Name"
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_item(raw: RawItem, now: datetime | None = None) -> CleanItem:
    now = now or datetime.now(timezone.utc)
    title = clean_text(raw.title, MAX_TITLE)
    if len(title) < 4:
        raise InvalidItem("Title missing or too short")
    canonical = canonicalize_url(raw.url)
    fingerprint = title_fingerprint(title)
    if not fingerprint:
        raise InvalidItem("Title has no meaningful content")

    published = raw.published_at or now
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    if published > now + timedelta(hours=1):
        published = now  # clamp obviously wrong future dates

    domain = urlsplit(canonical).netloc or None
    return CleanItem(
        url=raw.url.strip()[:2000],
        url_hash=sha256(canonical),
        content_hash=sha256(fingerprint),
        title=title,
        summary=clean_text(raw.summary, MAX_SUMMARY),
        domain=domain,
        published_at=published,
        external_id=(raw.external_id or None) and raw.external_id[:255],
        author=clean_text(raw.author, 255) or None,
        score=raw.score,
        language=raw.language,
    )
