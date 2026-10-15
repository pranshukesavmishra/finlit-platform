"""HTTP security layer for the API: response headers, client IP resolution and rate limiting.

Defence in depth: Cloudflare WAF + rate rules sit in front, these limits hold even if a request
reaches the origin directly, and nothing here trusts client-supplied headers unless configured to.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import Tuple

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("finlit.security")

# The API only ever returns JSON, so the strictest browser policy is safe for it.
API_HEADERS = [
    (b"strict-transport-security", b"max-age=63072000; includeSubDomains; preload"),
    (b"x-content-type-options", b"nosniff"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-site"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
]
DOCS_PREFIXES = ("/api/docs", "/api/openapi.json")


class SecurityHeadersMiddleware:
    """Pure ASGI (no BaseHTTPMiddleware) so it adds no measurable latency."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        docs = scope.get("path", "").startswith(DOCS_PREFIXES)

        async def wrapped(message: Message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"server"]
                present = {k.lower() for k, _ in headers}
                for key, value in API_HEADERS:
                    if docs and key in (b"content-security-policy", b"cross-origin-resource-policy"):
                        continue  # Swagger UI loads its own assets; docs are disabled in production anyway
                    if key not in present:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, wrapped)


def client_ip(scope: Scope, header: str = "") -> str:
    """Peer address, or the configured proxy header (e.g. cf-connecting-ip) when it holds a valid IP."""
    if header:
        for key, value in scope.get("headers", []):
            if key.decode("latin-1").lower() == header:
                candidate = value.decode("latin-1").split(",")[0].strip()
                try:
                    return str(ipaddress.ip_address(candidate))
                except ValueError:
                    break
    peer = scope.get("client")
    return peer[0] if peer else "unknown"


def _bucket_ip(ip: str) -> str:
    """IPv6 users get a /64 each, so limit per /64 rather than per address."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)
    return ip


class RateLimiter:
    """Fixed-window counters in Redis: one pipelined INCR+EXPIRE per check (~0.1 ms)."""

    def __init__(self, redis, prefix: str = "rl"):
        self.redis, self.prefix = redis, prefix

    async def hit(self, scope_name: str, ip: str, limit: int, window_seconds: int, fail_open: bool = True) -> Tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        if limit <= 0:
            return True, 0
        now = int(time.time())
        window = now // window_seconds
        key = f"{self.prefix}:{scope_name}:{_bucket_ip(ip)}:{window}"
        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                pipe.incr(key)
                pipe.expire(key, window_seconds + 1)
                count, _ = await pipe.execute()
        except Exception:  # Redis down: reads stay up (Cloudflare still limits), costly paths close
            log.warning("rate limiter unavailable (%s)", scope_name)
            return fail_open, 0 if fail_open else 30
        if count > limit:
            return False, (window + 1) * window_seconds - now
        return True, 0

