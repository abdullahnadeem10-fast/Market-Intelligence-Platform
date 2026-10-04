from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    full_name: str = Field(default="", max_length=120)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter and one number")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=64)


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------- Companies ----------
Relation = Literal["own", "competitor", "watch"]


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    website: HttpUrl | None = None
    industry: str | None = Field(default=None, max_length=80)
    ticker: str | None = Field(default=None, max_length=12, pattern=r"^[A-Za-z0-9.\-]+$")
    search_terms: str | None = Field(default=None, max_length=255)
    rss_url: HttpUrl | None = None
    relation: Relation = "watch"
    fetch_description: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Company name cannot be blank")
        return v


class CompanyOut(ORM):
    id: int
    name: str
    description: str
    website: str | None
    industry: str | None
    ticker: str | None
    search_terms: str | None
    rss_url: str | None
    relation: str
    created_at: datetime
    last_collected_at: datetime | None
    item_count: int = 0
    items_last_7d: int = 0


class TimelinePoint(BaseModel):
    date: str
    count: int


class CategoryCount(BaseModel):
    category: str
    count: int


class CompanyStats(BaseModel):
    total_items: int
    items_last_7d: int
    items_last_30d: int
    sources: dict[str, int]
    first_item_at: datetime | None
    last_item_at: datetime | None


class CompanyDetail(BaseModel):
    company: CompanyOut
    stats: CompanyStats
    timeline: list[TimelinePoint]
    categories: list[CategoryCount]
    recent_items: list["ItemOut"]
    latest_analysis: "AnalysisOut | None"


# ---------- Items ----------
class ItemOut(ORM):
    id: int
    company_id: int
    company_name: str
    source: str
    url: str
    title: str
    summary: str
    author: str | None
    domain: str | None
    score: int | None
    published_at: datetime
    collected_at: datetime
    categories: list[str]


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int
    page: int
    page_size: int


class CategoryOut(ORM):
    id: int
    slug: str
    name: str


# ---------- Collection ----------
class CollectionRunOut(ORM):
    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    companies_processed: int
    items_fetched: int
    items_new: int
    items_duplicate: int
    items_invalid: int
    error_count: int
    details: dict


class CollectionStatus(BaseModel):
    scheduler_enabled: bool
    interval_minutes: int
    demo_mode: bool
    collectors: list[str]
    next_run_at: datetime | None


# ---------- Analysis ----------
class Insight(BaseModel):
    text: str
    sources: list[int]


class AnalysisResult(BaseModel):
    market_summary: str = ""
    emerging_trends: list[Insight] = []
    important_developments: list[Insight] = []
    competitor_activity: list[Insight] = []
    opportunities: list[Insight] = []
    risks: list[Insight] = []
    key_takeaways: list[Insight] = []


class AnalysisSource(BaseModel):
    ref: int
    item_id: int
    title: str
    url: str
    source: str
    company_name: str
    published_at: datetime


class AnalysisOut(BaseModel):
    id: int
    scope: str
    company_id: int | None
    status: str
    provider: str
    model: str
    result: AnalysisResult | None
    error: str | None
    sources: list[AnalysisSource]
    context_item_count: int
    input_tokens: int
    output_tokens: int
    tokens_estimated: bool
    cost_usd: float
    latency_ms: int
    created_at: datetime
    cached: bool = False


class AnalysisRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365)
    force: bool = False


class UsageSummary(BaseModel):
    provider: str
    model: str
    total_analyses: int
    successful_analyses: int
    failed_analyses: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    avg_latency_ms: float
    by_day: list[dict]
    recent: list[dict]


CompanyDetail.model_rebuild()
