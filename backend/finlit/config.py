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
    # Secondary data source (Upstox). Empty = switched off entirely: no calls, nothing shown. Secret: set only in the host's dashboard.
    upstox_access_token: str = field(default_factory=lambda: os.getenv("UPSTOX_ACCESS_TOKEN", "").strip())
    upstox_base_url: str = field(default_factory=lambda: os.getenv("UPSTOX_BASE_URL", "https://api.upstox.com"))
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
    # Staging and test deployments that cannot send mail: new accounts are confirmed at sign-up instead of by emailed link. Never in production.
    auto_verify_email: bool = field(default_factory=lambda: os.getenv("AUTO_VERIFY_EMAIL", "").lower() in ("1", "true", "yes"))
    mail_mode: str = field(default_factory=lambda: os.getenv("MAIL_MODE", "console"))
    resend_api_key: str = field(default_factory=lambda: os.getenv("RESEND_API_KEY", ""))
    mail_from: str = field(default_factory=lambda: os.getenv("MAIL_FROM", "FinLit <hello@finlitventures.com>"))
    # Free sample reports shown in full to everyone (the home page example).
    # The separate site backend (blog/CMS, portfolio report, contact forms, chat, ticker). Empty = those /api routes answer 404.
    site_api_url: str = field(default_factory=lambda: os.getenv("SITE_API_URL", "").rstrip("/"))
    # Same secret the site backend verifies CMS tokens with: signed-in administrators get a CMS session without a second password.
    cms_jwt_secret: str = field(default_factory=lambda: os.getenv("CMS_JWT_SECRET", ""))
    # Folder holding the built website (frontend/dist). Empty = API only (the website is then hosted elsewhere).
    frontend_dist: str = field(default_factory=lambda: os.getenv("FRONTEND_DIST", ""))
    showcase_symbols: List[str] = field(default_factory=lambda: _list(os.getenv("SHOWCASE_SYMBOLS", "RELIANCE")))
    session_days: int = field(default_factory=lambda: int(os.getenv("SESSION_DAYS", "30")))
    session_idle_days: int = field(default_factory=lambda: int(os.getenv("SESSION_IDLE_DAYS", "7")))
    admin_session_hours: int = field(default_factory=lambda: int(os.getenv("ADMIN_SESSION_HOURS", "12")))
    # "0" lets administrators in with the password alone (an account that already has an authenticator is still asked for its code). Default: required.
    admin_require_mfa: bool = field(default_factory=lambda: os.getenv("ADMIN_REQUIRE_MFA", "1").strip().lower() not in ("0", "false", "no", "off"))

    # "lax" when the site and API share a registrable domain (production). The domainless staging setup (pages.dev + sslip.io) is
    # cross-site, so it needs "none"; CSRF tokens and the Origin check still apply.
    cookie_samesite: str = field(default_factory=lambda: os.getenv("COOKIE_SAMESITE", "lax").lower())

    @property
    def cookie_secure(self) -> bool:
        # Secure cookies in production, and on any site served over https (the free Render address, staging) so a session
        # cookie is never sent over plain http. Local development over http keeps working.
        return self.is_production or self.public_site_url.startswith("https://")

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
        redis_host = self.redis_url.split("://", 1)[-1].split("/", 1)[0].rsplit("@", 1)[-1].split(":", 1)[0]
        if "@" not in self.redis_url and redis_host in ("localhost", "127.0.0.1"):
            problems.append("REDIS_URL has no password (use redis://:PASSWORD@host:6379/0)")  # a private-network host (e.g. Render's) is fine without one
        if self.auto_verify_email:
            problems.append("AUTO_VERIFY_EMAIL must be off in production (members must confirm their email)")
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
