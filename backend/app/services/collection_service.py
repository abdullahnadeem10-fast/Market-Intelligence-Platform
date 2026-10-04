"""Data collection pipeline: fetch -> parse -> clean/normalize -> de-duplicate -> store -> record run.

Failures are isolated per (company, collector): one failing source never aborts the whole run,
and the run row always ends in a terminal state with error details.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, CollectorError, CompanyQuery, RateLimitedError, RawItem
from app.collectors.registry import build_collectors, make_http_client
from app.config import get_settings
from app.models import Category, CollectedItem, CollectionRun, Company, Source, User
from app.services.categorizer import categorize
from app.services.normalization import CleanItem, InvalidItem, normalize_item

logger = logging.getLogger(__name__)

STALE_RUN_MINUTES = 30
MAX_ERRORS_RECORDED = 50


class CollectionAlreadyRunning(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def start_run(db: Session, user_id: int, trigger: str) -> CollectionRun:
    """Create a 'running' run row, refusing if the user already has a fresh running collection."""
    stale_before = utcnow() - timedelta(minutes=STALE_RUN_MINUTES)
    running = db.scalars(
        select(CollectionRun).where(CollectionRun.user_id == user_id, CollectionRun.status == "running")
    ).all()
    for run in running:
        started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
        if started < stale_before:
            run.status = "failed"
            run.finished_at = utcnow()
            run.details = {**(run.details or {}), "errors": [{"error": "Run timed out / worker stopped"}]}
        else:
            raise CollectionAlreadyRunning("A collection is already running for this account")
    run = CollectionRun(user_id=user_id, trigger=trigger, status="running", started_at=utcnow(), details={})
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_run(
    session_factory: Callable[[], Session],
    run_id: int,
    collectors: list[BaseCollector] | None = None,
) -> None:
    """Execute a previously created run. Safe to call from a background task or the scheduler."""
    settings = get_settings()
    client = None
    if collectors is None:
        client = make_http_client(settings)
        collectors = build_collectors(settings, client)

    db = session_factory()
    try:
        run = db.get(CollectionRun, run_id)
        if run is None:
            return
        try:
            _execute(db, run, collectors)
        except Exception as exc:  # last line of defence: never leave a run 'running'
            logger.exception("Collection run %s crashed", run_id)
            db.rollback()
            run = db.get(CollectionRun, run_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = utcnow()
                details = dict(run.details or {})
                details.setdefault("errors", []).append({"error": f"Unexpected failure: {exc.__class__.__name__}"})
                run.details = details
                run.error_count += 1
                db.commit()
    finally:
        db.close()
        if client is not None:
            client.close()


def _execute(db: Session, run: CollectionRun, collectors: list[BaseCollector]) -> None:
    sources = {s.key: s for s in db.scalars(select(Source))}
    categories = {c.slug: c for c in db.scalars(select(Category))}
    companies = db.scalars(select(Company).where(Company.user_id == run.user_id).order_by(Company.id)).all()

    errors: list[dict] = []
    skipped: list[dict] = []
    rate_limited: set[str] = set()  # circuit breaker: stop calling a provider once it rate-limits us
    per_source: dict[str, dict[str, int]] = {}
    attempts = successes = 0

    for company in companies:
        query = CompanyQuery(
            id=company.id, name=company.name, search_terms=company.search_terms,
            website=company.website, rss_url=company.rss_url,
        )
        for collector in collectors:
            if not collector.is_applicable(query):
                continue
            source = sources.get(collector.key)
            if source is None or not source.is_active:
                continue
            stats = per_source.setdefault(collector.key, {"fetched": 0, "new": 0, "duplicate": 0, "invalid": 0, "errors": 0, "skipped": 0})
            if collector.key in rate_limited:
                stats["skipped"] += 1
                skipped.append({"company": company.name, "source": collector.key, "reason": "Provider rate limit reached earlier in this run; will retry next run"})
                continue
            attempts += 1
            try:
                raw_items = collector.fetch(query)
            except RateLimitedError as exc:
                rate_limited.add(collector.key)
                stats["errors"] += 1
                errors.append({"company": company.name, "source": collector.key, "error": str(exc)})
                continue
            except CollectorError as exc:
                stats["errors"] += 1
                errors.append({"company": company.name, "source": collector.key, "error": str(exc)})
                continue
            except Exception as exc:
                logger.exception("Collector %s failed unexpectedly for company %s", collector.key, company.id)
                stats["errors"] += 1
                errors.append({"company": company.name, "source": collector.key, "error": f"Unexpected collector error ({exc.__class__.__name__})"})
                continue

            try:
                new, dup, invalid = store_items(db, company, source, run.id, raw_items, categories)
            except SQLAlchemyError as exc:
                db.rollback()
                logger.exception("DB failure storing items for company %s", company.id)
                stats["errors"] += 1
                errors.append({"company": company.name, "source": collector.key, "error": f"Database error while storing items ({exc.__class__.__name__})"})
                continue

            successes += 1
            stats["fetched"] += len(raw_items)
            stats["new"] += new
            stats["duplicate"] += dup
            stats["invalid"] += invalid
            run.items_fetched += len(raw_items)
            run.items_new += new
            run.items_duplicate += dup
            run.items_invalid += invalid

        company.last_collected_at = utcnow()
        run.companies_processed += 1
        db.commit()

    run.error_count = len(errors)
    run.details = {
        "sources": per_source,
        "collectors": [c.key for c in collectors],
        "errors": errors[:MAX_ERRORS_RECORDED],
        "skipped": skipped[:MAX_ERRORS_RECORDED],
        "note": None if companies else "No tracked companies — add a company to start collecting.",
    }
    if errors and successes == 0:
        run.status = "failed"
    elif errors:
        run.status = "partial"
    else:
        run.status = "success"
    run.finished_at = utcnow()
    db.commit()
    logger.info("Collection run %s finished: %s new=%s dup=%s errors=%s", run.id, run.status, run.items_new, run.items_duplicate, len(errors))


def store_items(
    db: Session,
    company: Company,
    source: Source,
    run_id: int | None,
    raw_items: list[RawItem],
    categories: dict[str, Category],
) -> tuple[int, int, int]:
    """Normalize and insert items. Returns (new, duplicate, invalid) counts."""
    cleaned: list[CleanItem] = []
    invalid = 0
    for raw in raw_items:
        try:
            cleaned.append(normalize_item(raw))
        except InvalidItem:
            invalid += 1
    if not cleaned:
        return 0, 0, invalid

    # Duplicates against the DB (same URL or same story title for this company) ...
    url_hashes = {c.url_hash for c in cleaned}
    content_hashes = {c.content_hash for c in cleaned}
    existing = db.execute(
        select(CollectedItem.url_hash, CollectedItem.content_hash).where(
            CollectedItem.company_id == company.id,
            (CollectedItem.url_hash.in_(url_hashes)) | (CollectedItem.content_hash.in_(content_hashes)),
        )
    ).all()
    seen_urls = {row.url_hash for row in existing}
    seen_content = {row.content_hash for row in existing}

    new = dup = 0
    for item in cleaned:
        # ... and within the batch itself.
        if item.url_hash in seen_urls or item.content_hash in seen_content:
            dup += 1
            continue
        seen_urls.add(item.url_hash)
        seen_content.add(item.content_hash)
        row = CollectedItem(
            company_id=company.id,
            source_id=source.id,
            collection_run_id=run_id,
            external_id=item.external_id,
            url=item.url,
            url_hash=item.url_hash,
            content_hash=item.content_hash,
            title=item.title,
            summary=item.summary,
            author=item.author,
            domain=item.domain,
            language=item.language,
            score=item.score,
            published_at=item.published_at,
            categories=[categories[s] for s in categorize(item.title, item.summary) if s in categories],
        )
        try:
            with db.begin_nested():  # savepoint: a concurrent insert of the same item is just a duplicate
                db.add(row)
                db.flush()
        except IntegrityError:
            dup += 1
            continue
        new += 1
    db.commit()
    return new, dup, invalid


def run_scheduled_collection(session_factory: Callable[[], Session]) -> None:
    """Scheduler entry point: collect for every active user that tracks at least one company."""
    db = session_factory()
    try:
        user_ids = db.scalars(
            select(User.id).where(User.is_active.is_(True), User.companies.any())
        ).all()
    finally:
        db.close()
    for user_id in user_ids:
        db = session_factory()
        try:
            run = start_run(db, user_id, "scheduled")
        except CollectionAlreadyRunning:
            logger.info("Skipping scheduled collection for user %s: already running", user_id)
            continue
        except SQLAlchemyError:
            logger.exception("Could not start scheduled run for user %s", user_id)
            continue
        finally:
            db.close()
        execute_run(session_factory, run.id)
