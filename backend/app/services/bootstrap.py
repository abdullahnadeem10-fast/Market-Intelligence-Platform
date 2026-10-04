"""Idempotent DB bootstrap: create tables and seed reference data (sources, categories)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.registry import COLLECTOR_CLASSES
from app.db import Base, engine
from app.models import Category, Source
from app.services.categorizer import CATEGORIES

logger = logging.getLogger(__name__)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        seed_reference_data(db)


def seed_reference_data(db: Session) -> None:
    existing_sources = {s.key for s in db.scalars(select(Source))}
    for key, cls in COLLECTOR_CLASSES.items():
        if key not in existing_sources:
            db.add(Source(key=key, name=cls.name, kind=cls.kind, base_url=cls.base_url))
    existing_categories = {c.slug for c in db.scalars(select(Category))}
    for slug, (name, _) in CATEGORIES.items():
        if slug not in existing_categories:
            db.add(Category(slug=slug, name=name))
    db.commit()
