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

    # ---- security
    # development | production. Production refuses to start with unsafe settings (see validate()).
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    # Host headers the API answers to; anything else gets 400 (stops host-header attacks and stray DNS).
    allowed_hosts: List[str] = field(default_factory=lambda: _list(os.getenv("ALLOWED_HOSTS", "*")))
    # Header carrying the real client IP. Only set this when the origin accepts traffic from that proxy
    # alone (firewall the VPS to Cloudflare's IP ranges), otherwise anyone can spoof it.
    client_ip_header: str = field(default_factory=lambda: os.getenv("CLIENT_IP_HEADER", "").lower())
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "300")))
    # Opening a stock that has no snapshot yet costs ~21 FinEdge calls; cap how many one client can trigger.
    queue_limit_per_hour: int = field(default_factory=lambda: int(os.getenv("QUEUE_LIMIT_PER_HOUR", "30")))
    queue_max_pending: int = field(default_factory=lambda: int(os.getenv("QUEUE_MAX_PENDING", "500")))

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate(self) -> List[str]:
        """Problems that make a production deployment unsafe. Empty list = OK."""
        if not self.is_production:
            return []
        problems = []
        if self.finedge_mode != "live" or not self.finedge_api_key:
            problems.append("FINEDGE_MODE must be live with FINEDGE_API_KEY set")
        if "finlit:finlit@" in self.database_url or "change-me" in self.database_url:
            problems.append("DATABASE_URL uses a default password")
        if "@" not in self.redis_url:
            problems.append("REDIS_URL has no password (use redis://:PASSWORD@host:6379/0)")
        if "*" in self.allowed_hosts:
            problems.append("ALLOWED_HOSTS must list the real API host names")
        if any(not o.startswith("https://") for o in self.cors_origins):
            problems.append("CORS_ORIGINS must all be https:// in production")
        return problems


def get_settings() -> Settings:
    return Settings()
