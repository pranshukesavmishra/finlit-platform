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

    # ---- accounts
    # Signs nothing directly; derives the key that encrypts stored authenticator secrets. Must be long and random in production.
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "dev-only-secret-key-do-not-use-in-production"))
    # Where emailed links point (the website, not the API).
    public_site_url: str = field(default_factory=lambda: os.getenv("PUBLIC_SITE_URL", "http://localhost:5173").rstrip("/"))
    # console = write mails to the outbox table (development); resend = send through Resend.
    mail_mode: str = field(default_factory=lambda: os.getenv("MAIL_MODE", "console"))
    resend_api_key: str = field(default_factory=lambda: os.getenv("RESEND_API_KEY", ""))
    mail_from: str = field(default_factory=lambda: os.getenv("MAIL_FROM", "FinLit <hello@finlitventures.com>"))
    # Free sample reports shown in full to everyone (the home page example).
    showcase_symbols: List[str] = field(default_factory=lambda: _list(os.getenv("SHOWCASE_SYMBOLS", "RELIANCE")))
    session_days: int = field(default_factory=lambda: int(os.getenv("SESSION_DAYS", "30")))
    session_idle_days: int = field(default_factory=lambda: int(os.getenv("SESSION_IDLE_DAYS", "7")))
    admin_session_hours: int = field(default_factory=lambda: int(os.getenv("ADMIN_SESSION_HOURS", "12")))

    # "lax" when the site and API share a registrable domain (production). The domainless staging setup (pages.dev + sslip.io) is
    # cross-site, so it needs "none"; CSRF tokens and the Origin check still apply.
    cookie_samesite: str = field(default_factory=lambda: os.getenv("COOKIE_SAMESITE", "lax").lower())

    @property
    def cookie_secure(self) -> bool:
        return self.is_production

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
        if len(self.secret_key) < 32 or self.secret_key.startswith("dev-only"):
            problems.append("SECRET_KEY must be a long random value (32+ characters)")
        if self.mail_mode != "resend" or not self.resend_api_key:
            problems.append("MAIL_MODE must be resend with RESEND_API_KEY set (sign-up and reset emails)")
        if not self.public_site_url.startswith("https://"):
            problems.append("PUBLIC_SITE_URL must be https:// in production")
        if any(not o.startswith("https://") for o in self.cors_origins):
            problems.append("CORS_ORIGINS must all be https:// in production")
        return problems


def get_settings() -> Settings:
    return Settings()
