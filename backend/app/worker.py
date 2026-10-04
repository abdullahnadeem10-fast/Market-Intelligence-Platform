"""Standalone data-collection service: `python -m app.worker`.

Runs the collection scheduler in its own process/container, separate from the API server.
"""

import logging
import signal
import threading
import time

from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.scheduler import create_scheduler
from app.services.bootstrap import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("collector-worker")


def wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            init_db()
            return
        except OperationalError:
            logger.warning("Database not ready (attempt %s/%s)", attempt, retries)
            time.sleep(delay)
    raise SystemExit("Database unavailable; collector worker exiting")


def main() -> None:
    settings = get_settings()
    wait_for_db()
    scheduler = create_scheduler(first_run_delay_seconds=15)
    scheduler.start()
    logger.info("Collector worker started: every %s min, collectors=%s, demo_mode=%s",
                settings.collection_interval_minutes, settings.enabled_collector_list, settings.collector_demo_mode)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
    scheduler.shutdown(wait=False)
    logger.info("Collector worker stopped")


if __name__ == "__main__":
    main()
