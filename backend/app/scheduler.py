"""Scheduled collection using APScheduler.

A Postgres advisory lock guarantees only one scheduler (API process or worker container) executes a
scheduled collection at a time, even if several are running.
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.services.collection_service import run_scheduled_collection

logger = logging.getLogger(__name__)
ADVISORY_LOCK_ID = 842_001


def scheduled_job() -> None:
    if engine.dialect.name != "postgresql":
        run_scheduled_collection(SessionLocal)
        return
    try:
        conn = engine.connect()
    except Exception:
        logger.exception("Scheduled collection skipped: database unavailable")
        return
    try:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": ADVISORY_LOCK_ID}).scalar():
            logger.info("Scheduled collection already running in another process; skipping")
            return
        try:
            run_scheduled_collection(SessionLocal)
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID})
    except Exception:
        logger.exception("Scheduled collection failed")
    finally:
        conn.close()


def create_scheduler(first_run_delay_seconds: int = 30) -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_job,
        IntervalTrigger(minutes=settings.collection_interval_minutes),
        id="scheduled_collection",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=first_run_delay_seconds),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    return scheduler
