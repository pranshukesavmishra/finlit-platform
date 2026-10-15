"""Settings from environment variables (see .env.example). No secrets live in code."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _list(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    finedge_base_url: str = field(default_factory=lambda: os.getenv("FINEDGE_BASE_URL", "https://data.finedgeapi.com/api/v1"))
    finedge_api_key: str = field(default_factory=lambda: os.getenv("FINEDGE_API_KEY", ""))
    # "live" calls FinEdge; "fixtures" serves the recorded payloads in tests/fixtures (offline dev + CI).
    finedge_mode: str = field(default_factory=lambda: os.getenv("FINEDGE_MODE", "live"))
    finedge_concurrency: int = field(default_factory=lambda: int(os.getenv("FINEDGE_CONCURRENCY", "8")))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit"))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    cors_origins: List[str] = field(default_factory=lambda: _list(os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")))
    # How long a snapshot is served before the worker should refresh it.
    fundamentals_ttl_hours: int = field(default_factory=lambda: int(os.getenv("FUNDAMENTALS_TTL_HOURS", "24")))
    quote_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("QUOTE_TTL_SECONDS", "60")))


def get_settings() -> Settings:
    return Settings()
