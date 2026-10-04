from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / backend .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Market Intelligence Platform"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://mip:mip@localhost:5432/mip"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Auth
    jwt_secret: str = Field(default="change-me-in-production-please-use-a-long-random-string")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # Collection
    scheduler_enabled: bool = True
    collection_interval_minutes: int = 60
    collector_demo_mode: bool = False
    enabled_collectors: str = "hackernews,gdelt,rss"
    http_timeout_seconds: float = 15.0
    collector_user_agent: str = "MarketIntelligencePlatform/1.0 (portfolio project; contact: admin@example.com)"
    max_items_per_source: int = 30
    collection_lookback_days: int = 30
    enrichment_enabled: bool = True  # fetch company descriptions from Wikipedia when none given

    # LLM (OpenAI-compatible). "extractive" = offline mode with no LLM calls.
    llm_provider: str = "extractive"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 1200
    llm_max_context_items: int = 25
    llm_max_context_chars: int = 12000
    llm_input_cost_per_million: float = 0.15
    llm_output_cost_per_million: float = 0.60
    analysis_cache_minutes: int = 360

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres providers (Render, Neon, Heroku) hand out postgres:// or postgresql:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def enabled_collector_list(self) -> list[str]:
        return [c.strip() for c in self.enabled_collectors.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
