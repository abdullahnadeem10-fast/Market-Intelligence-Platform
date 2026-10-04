import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.config import get_settings
from app.db import engine
from app.routers import analysis, analytics, auth, collection, companies, items

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler = None
    if settings.environment != "test":
        from app.services.bootstrap import init_db

        init_db()
        if settings.scheduler_enabled:
            from app.scheduler import create_scheduler

            scheduler = create_scheduler()
            scheduler.start()
            logger.info("In-process collection scheduler started (every %s min)", settings.collection_interval_minutes)
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"].removeprefix("Value error, ")}
        for e in exc.errors()
    ]
    message = "; ".join(f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors)
    return JSONResponse(status_code=422, content={"detail": message or "Invalid request", "errors": errors})


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request: Request, exc: OperationalError):
    logger.error("Database unavailable: %s", exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"detail": "Database is temporarily unavailable. Please try again."})


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(request: Request, exc: SQLAlchemyError):
    error_id = uuid.uuid4().hex[:12]
    logger.exception("Database error %s", error_id)
    return JSONResponse(status_code=500, content={"detail": "A database error occurred.", "error_id": error_id})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    # Never leak stack traces to clients; log with a correlation id instead.
    error_id = uuid.uuid4().hex[:12]
    logger.exception("Unhandled error %s on %s %s", error_id, request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "error_id": error_id})


for r in (auth.router, companies.router, items.router, collection.router, analysis.router, analytics.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return JSONResponse(
        status_code=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ok" if db_ok else "degraded", "database": db_ok},
    )
