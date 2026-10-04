from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user, get_owned_company
from app.models import AIAnalysis, CollectedItem, Company, Source, User
from app.routers.analysis import analysis_out
from app.routers.items import item_out
from app.schemas import CompanyCreate, CompanyDetail, CompanyOut, CompanyStats, TimelinePoint, CategoryCount
from app.services import analytics_service
from app.services.enrichment import fetch_company_description

router = APIRouter(prefix="/companies", tags=["companies"])

MAX_COMPANIES_PER_USER = 50


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def _company_out(company: Company, total: int = 0, last7: int = 0) -> CompanyOut:
    out = CompanyOut.model_validate(company)
    out.item_count, out.items_last_7d = total, last7
    return out


@router.get("", response_model=list[CompanyOut])
def list_companies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=7)
    counts = (
        select(
            CollectedItem.company_id,
            func.count(CollectedItem.id).label("total"),
            func.count(CollectedItem.id).filter(CollectedItem.published_at >= since).label("last7"),
        )
        .group_by(CollectedItem.company_id)
        .subquery()
    )
    rows = db.execute(
        select(Company, counts.c.total, counts.c.last7)
        .outerjoin(counts, counts.c.company_id == Company.id)
        .where(Company.user_id == user.id)
        .order_by(Company.name)
    ).all()
    return [_company_out(c, total or 0, last7 or 0) for c, total, last7 in rows]


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(body: CompanyCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(Company.id)).where(Company.user_id == user.id)) or 0
    if count >= MAX_COMPANIES_PER_USER:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"You can track at most {MAX_COMPANIES_PER_USER} companies")
    normalized = _normalize_name(body.name)
    if db.scalar(select(Company.id).where(Company.user_id == user.id, Company.name_normalized == normalized)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"You are already tracking '{body.name}'")

    description = body.description.strip()
    if not description and body.fetch_description:
        description = fetch_company_description(body.name) or ""

    company = Company(
        user_id=user.id,
        name=body.name,
        name_normalized=normalized,
        description=description,
        website=str(body.website) if body.website else None,
        industry=(body.industry or "").strip() or None,
        ticker=body.ticker.upper() if body.ticker else None,
        search_terms=(body.search_terms or "").strip() or None,
        rss_url=str(body.rss_url) if body.rss_url else None,
        relation=body.relation,
    )
    db.add(company)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"You are already tracking '{body.name}'")
    db.refresh(company)
    return _company_out(company)


@router.get("/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = get_owned_company(company_id, user, db)
    now = datetime.now(timezone.utc)
    base = select(func.count(CollectedItem.id)).where(CollectedItem.company_id == company.id)
    total = db.scalar(base) or 0
    last7 = db.scalar(base.where(CollectedItem.published_at >= now - timedelta(days=7))) or 0
    last30 = db.scalar(base.where(CollectedItem.published_at >= now - timedelta(days=30))) or 0
    first_at, last_at = db.execute(
        select(func.min(CollectedItem.published_at), func.max(CollectedItem.published_at)).where(CollectedItem.company_id == company.id)
    ).one()
    by_source = dict(
        db.execute(
            select(Source.name, func.count(CollectedItem.id))
            .join(CollectedItem, CollectedItem.source_id == Source.id)
            .where(CollectedItem.company_id == company.id)
            .group_by(Source.name)
        ).all()
    )
    recent = db.scalars(
        select(CollectedItem)
        .where(CollectedItem.company_id == company.id)
        .options(selectinload(CollectedItem.company), selectinload(CollectedItem.source), selectinload(CollectedItem.categories))
        .order_by(CollectedItem.published_at.desc())
        .limit(15)
    ).all()
    latest = db.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.user_id == user.id, AIAnalysis.company_id == company.id, AIAnalysis.status == "success")
        .order_by(AIAnalysis.created_at.desc())
    )
    return CompanyDetail(
        company=_company_out(company, total, last7),
        stats=CompanyStats(
            total_items=total, items_last_7d=last7, items_last_30d=last30, sources=by_source,
            first_item_at=first_at, last_item_at=last_at,
        ),
        timeline=[TimelinePoint(**p) for p in analytics_service.activity_over_time(db, user.id, 30, company.id)],
        categories=[CategoryCount(**c) for c in analytics_service.activity_by_category(db, user.id, 90, company.id)],
        recent_items=[item_out(i) for i in recent],
        latest_analysis=analysis_out(db, latest) if latest else None,
    )


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = get_owned_company(company_id, user, db)
    db.delete(company)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
