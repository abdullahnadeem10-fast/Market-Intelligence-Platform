from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.deps import get_current_user
from app.models import CollectionRun, User
from app.rate_limit import collection_limiter
from app.schemas import CollectionRunOut, CollectionStatus
from app.services.collection_service import CollectionAlreadyRunning, execute_run, start_run

router = APIRouter(prefix="/collection", tags=["collection"])


def session_factory():
    """Overridable in tests so background runs use the test database."""
    return SessionLocal


@router.post("/run", response_model=CollectionRunOut, status_code=status.HTTP_202_ACCEPTED)
def run_collection_now(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory=Depends(session_factory),
):
    collection_limiter.check(f"user:{user.id}")
    try:
        run = start_run(db, user.id, "manual")
    except CollectionAlreadyRunning as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    background.add_task(execute_run, factory, run.id)
    return run


@router.get("/runs", response_model=list[CollectionRunOut])
def list_runs(
    limit: int = Query(default=25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(CollectionRun).where(CollectionRun.user_id == user.id).order_by(CollectionRun.started_at.desc()).limit(limit)
    ).all()


@router.get("/runs/{run_id}", response_model=CollectionRunOut)
def get_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(CollectionRun).where(CollectionRun.id == run_id, CollectionRun.user_id == user.id))
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection run not found")
    return run


@router.get("/status", response_model=CollectionStatus)
def collection_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    last_scheduled = db.scalar(
        select(CollectionRun.started_at)
        .where(CollectionRun.user_id == user.id, CollectionRun.trigger == "scheduled")
        .order_by(CollectionRun.started_at.desc())
    )
    next_run = last_scheduled + timedelta(minutes=settings.collection_interval_minutes) if last_scheduled else None
    return CollectionStatus(
        scheduler_enabled=settings.scheduler_enabled,
        interval_minutes=settings.collection_interval_minutes,
        demo_mode=settings.collector_demo_mode,
        collectors=["demo"] if settings.collector_demo_mode else settings.enabled_collector_list,
        next_run_at=next_run,
    )
