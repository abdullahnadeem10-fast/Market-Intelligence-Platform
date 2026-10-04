from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_owned_company
from app.models import AIAnalysis, User
from app.rate_limit import analysis_limiter
from app.schemas import AnalysisOut, AnalysisRequest, AnalysisResult
from app.services.analysis_service import AnalysisInputError, analysis_sources, run_analysis
from app.services.llm_service import LLMError, LLMService, get_llm_service

router = APIRouter(prefix="/analysis", tags=["analysis"])


def get_llm() -> LLMService | None:
    """Dependency so tests (or future per-user providers) can swap the LLM implementation."""
    try:
        return get_llm_service()
    except LLMError as exc:
        raise HTTPException(exc.status_code, exc.message)


def analysis_out(db: Session, analysis: AIAnalysis, cached: bool = False) -> AnalysisOut:
    result = None
    if analysis.status == "success" and analysis.result:
        result = AnalysisResult.model_validate(analysis.result)
    return AnalysisOut(
        id=analysis.id, scope=analysis.scope, company_id=analysis.company_id, status=analysis.status,
        provider=analysis.provider, model=analysis.model, result=result, error=analysis.error,
        sources=analysis_sources(db, analysis), context_item_count=analysis.context_item_count,
        input_tokens=analysis.input_tokens, output_tokens=analysis.output_tokens,
        tokens_estimated=analysis.tokens_estimated, cost_usd=analysis.cost_usd,
        latency_ms=analysis.latency_ms, created_at=analysis.created_at, cached=cached,
    )


def _run(db: Session, user: User, company, body: AnalysisRequest, llm: LLMService | None) -> AnalysisOut:
    analysis_limiter.check(f"user:{user.id}")
    try:
        analysis, cached = run_analysis(db, user, company, body.days, body.force, llm)
    except AnalysisInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except LLMError as exc:
        raise HTTPException(exc.status_code, f"AI analysis failed: {exc.message}")
    return analysis_out(db, analysis, cached)


def _history(db: Session, user: User, company_id: int | None, limit: int) -> list[AnalysisOut]:
    stmt = select(AIAnalysis).where(AIAnalysis.user_id == user.id).order_by(AIAnalysis.created_at.desc()).limit(limit)
    stmt = stmt.where(AIAnalysis.company_id == company_id) if company_id else stmt.where(AIAnalysis.scope == "market")
    return [analysis_out(db, a) for a in db.scalars(stmt)]


@router.post("/company/{company_id}", response_model=AnalysisOut)
def analyze_company(
    company_id: int,
    body: AnalysisRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm: LLMService | None = Depends(get_llm),
):
    company = get_owned_company(company_id, user, db)
    return _run(db, user, company, body or AnalysisRequest(), llm)


@router.get("/company/{company_id}", response_model=list[AnalysisOut])
def company_analyses(
    company_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_company(company_id, user, db)
    return _history(db, user, company_id, limit)


@router.post("/market", response_model=AnalysisOut)
def analyze_market(
    body: AnalysisRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm: LLMService | None = Depends(get_llm),
):
    return _run(db, user, None, body or AnalysisRequest(), llm)


@router.get("/market", response_model=list[AnalysisOut])
def market_analyses(
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _history(db, user, None, limit)


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.scalar(select(AIAnalysis).where(AIAnalysis.id == analysis_id, AIAnalysis.user_id == user.id))
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    return analysis_out(db, analysis)
