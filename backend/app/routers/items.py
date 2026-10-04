from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user
from app.models import Category, CollectedItem, Company, Source, User
from app.schemas import CategoryOut, ItemOut, ItemPage

router = APIRouter(tags=["items"])


def item_out(item: CollectedItem) -> ItemOut:
    return ItemOut(
        id=item.id, company_id=item.company_id, company_name=item.company.name, source=item.source.name,
        url=item.url, title=item.title, summary=item.summary, author=item.author, domain=item.domain,
        score=item.score, published_at=item.published_at, collected_at=item.collected_at,
        categories=[c.name for c in item.categories],
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/items", response_model=ItemPage)
def list_items(
    company_id: int | None = Query(default=None, ge=1),
    q: str | None = Query(default=None, max_length=200, description="Keyword search in title and summary"),
    category: str | None = Query(default=None, max_length=40, description="Category slug"),
    source: str | None = Query(default=None, max_length=40, description="Source key"),
    date_from: date | None = None,
    date_to: date | None = None,
    sort: Literal["newest", "oldest", "score"] = "newest",
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_from must be on or before date_to")

    filters = [Company.user_id == user.id]
    if company_id is not None:
        filters.append(CollectedItem.company_id == company_id)
    if q and q.strip():
        for word in q.split()[:6]:
            pattern = f"%{_escape_like(word)}%"
            filters.append(or_(CollectedItem.title.ilike(pattern, escape="\\"), CollectedItem.summary.ilike(pattern, escape="\\")))
    if category:
        filters.append(CollectedItem.categories.any(Category.slug == category))
    if source:
        filters.append(CollectedItem.source.has(Source.key == source))
    if date_from:
        filters.append(CollectedItem.published_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        filters.append(CollectedItem.published_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))

    base = select(CollectedItem).join(Company, Company.id == CollectedItem.company_id).where(*filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    order = {
        "newest": (CollectedItem.published_at.desc(), CollectedItem.id.desc()),
        "oldest": (CollectedItem.published_at.asc(), CollectedItem.id.asc()),
        "score": (CollectedItem.score.desc().nulls_last(), CollectedItem.published_at.desc()),
    }[sort]
    rows = db.scalars(
        base.options(selectinload(CollectedItem.company), selectinload(CollectedItem.source), selectinload(CollectedItem.categories))
        .order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ItemPage(items=[item_out(i) for i in rows], total=total, page=page, page_size=page_size)


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.scalar(
        select(CollectedItem)
        .join(Company, Company.id == CollectedItem.company_id)
        .where(CollectedItem.id == item_id, Company.user_id == user.id)
        .options(selectinload(CollectedItem.company), selectinload(CollectedItem.source), selectinload(CollectedItem.categories))
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item_out(item)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.name)).all()


@router.get("/sources")
def list_sources(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"key": s.key, "name": s.name, "kind": s.kind} for s in db.scalars(select(Source).order_by(Source.name))]
