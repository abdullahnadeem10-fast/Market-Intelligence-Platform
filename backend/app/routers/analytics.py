from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import AIAnalysis, CollectedItem, Company, User
from app.routers.analysis import analysis_out
from app.routers.items import item_out
from app.schemas import UsageSummary
from app.services import analytics_service as svc

router = APIRouter(tags=["analytics"])


@router.get("/analytics/dashboard")
def dashboard(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recent = db.scalars(
        select(CollectedItem)
        .join(Company, Company.id == CollectedItem.company_id)
        .where(Company.user_id == user.id)
        .options(selectinload(CollectedItem.company), selectinload(CollectedItem.source), selectinload(CollectedItem.categories))
        .order_by(CollectedItem.published_at.desc())
        .limit(8)
    ).all()
    latest_market = db.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.user_id == user.id, AIAnalysis.scope == "market", AIAnalysis.status == "success")
        .order_by(AIAnalysis.created_at.desc())
    )
    return {
        "overview": svc.overview(db, user.id),
        "activity": svc.activity_over_time(db, user.id, days),
        "by_company": svc.items_by_company(db, user.id, days),
        "by_category": svc.activity_by_category(db, user.id, days),
        "by_source": svc.items_by_source(db, user.id, days),
        "mentions": svc.mention_counts(db, user.id, days),
        "trends": svc.trending_terms(db, user.id, min(days, 30)),
        "competitors": svc.competitor_activity(db, user.id, days),
        "recent_items": [item_out(i) for i in recent],
        "latest_market_analysis": analysis_out(db, latest_market) if latest_market else None,
    }


@router.get("/usage/ai", response_model=UsageSummary)
def ai_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    totals = db.execute(
        select(
            func.count(AIAnalysis.id),
            func.count(AIAnalysis.id).filter(AIAnalysis.status == "success"),
            func.coalesce(func.sum(AIAnalysis.input_tokens), 0),
            func.coalesce(func.sum(AIAnalysis.output_tokens), 0),
            func.coalesce(func.sum(AIAnalysis.cost_usd), 0.0),
            func.coalesce(func.avg(AIAnalysis.latency_ms).filter(AIAnalysis.status == "success"), 0),
        ).where(AIAnalysis.user_id == user.id)
    ).one()
    day = func.date(AIAnalysis.created_at)
    by_day = db.execute(
        select(day, func.count(AIAnalysis.id), func.sum(AIAnalysis.input_tokens), func.sum(AIAnalysis.output_tokens), func.sum(AIAnalysis.cost_usd))
        .where(AIAnalysis.user_id == user.id)
        .group_by(day)
        .order_by(day)
    ).all()
    recent = db.scalars(
        select(AIAnalysis).where(AIAnalysis.user_id == user.id).order_by(AIAnalysis.created_at.desc()).limit(20)
    ).all()
    total, ok, tin, tout, cost, avg_latency = totals
    return UsageSummary(
        provider=settings.llm_provider,
        model=settings.llm_model if settings.llm_provider not in ("extractive", "none", "offline") else "rule-based",
        total_analyses=total,
        successful_analyses=ok,
        failed_analyses=total - ok,
        input_tokens=int(tin),
        output_tokens=int(tout),
        estimated_cost_usd=round(float(cost), 6),
        avg_latency_ms=round(float(avg_latency), 1),
        by_day=[{"date": str(d), "analyses": n, "input_tokens": int(i or 0), "output_tokens": int(o or 0), "cost_usd": round(float(c or 0), 6)} for d, n, i, o, c in by_day],
        recent=[
            {"id": a.id, "scope": a.scope, "company": a.company.name if a.company else None, "status": a.status,
             "provider": a.provider, "model": a.model, "input_tokens": a.input_tokens, "output_tokens": a.output_tokens,
             "tokens_estimated": a.tokens_estimated, "cost_usd": a.cost_usd, "latency_ms": a.latency_ms,
             "created_at": a.created_at, "error": a.error}
            for a in recent
        ],
    )
