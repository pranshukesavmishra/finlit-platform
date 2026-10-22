"""HTTP security layer for the API: response headers, client IP resolution and rate limiting.

Defence in depth: Cloudflare WAF + rate rules sit in front, these limits hold even if a request
reaches the origin directly, and nothing here trusts client-supplied headers unless configured to.
"""

from __future__ import annotations

import ipaddress
import os
import logging
import time
from functools import lru_cache
from typing import Optional, Tuple

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


# Addresses that are proxies in front of the app, never a visitor: private and internal networks (the host's own load balancer)
# and Cloudflare's published edge ranges (https://www.cloudflare.com/ips, checked October 2026; Render puts Cloudflare in front of every
# service). TRUSTED_PROXIES (comma-separated CIDRs) adds more, for a host whose proxies use other public addresses.
PROXY_NETWORKS = (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20",
    "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
)
MAX_FORWARDED_HOPS = 20


@lru_cache(maxsize=4)
def _proxy_networks(extra: str) -> tuple:
    nets = []
    for cidr in PROXY_NETWORKS + tuple(x.strip() for x in extra.split(",") if x.strip()):
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            log.warning("TRUSTED_PROXIES: ignoring %r (not a network)", cidr)
    return tuple(nets)


def is_proxy(ip: "ipaddress._BaseAddress") -> bool:
    return any(ip.version == n.version and ip in n for n in _proxy_networks(os.getenv("TRUSTED_PROXIES", "")))


def forwarded_client(value: str) -> Optional[str]:
    """The visitor's address in an X-Forwarded-For chain. Each proxy appends the address it received the request from, so the chain is
    read from the right: proxies (private networks, Cloudflare) are skipped and the first other address is the visitor. Whatever a visitor
    writes into the header themselves sits further left and is never reached, so it cannot be used to dodge rate limits or lockouts.
    This holds however many proxy hops the host adds (one, or Cloudflare plus a load balancer)."""
    parts = [x.strip() for x in value.split(",") if x.strip()][-MAX_FORWARDED_HOPS:]
    furthest: Optional[str] = None
    for raw in reversed(parts):
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            return furthest                    # a malformed entry: nothing to its left can be trusted
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped                # "::ffff:49.36.1.2" is the IPv4 visitor 49.36.1.2
        if not is_proxy(ip):
            return str(ip)
        furthest = str(ip)
    return furthest                            # every hop is a proxy (a visitor on a private network): the furthest one


def client_ip(scope: Scope, header: str = "") -> str:
    """Peer address, or the configured proxy header when it holds a valid IP: x-forwarded-for (read as described in forwarded_client)
    or a single-address header such as cf-connecting-ip (only where the origin is reachable through that proxy alone)."""
    if header:
        for key, value in scope.get("headers", []):
            if key.decode("latin-1").lower() == header:
                text = value.decode("latin-1")
                if header == "x-forwarded-for":
                    found = forwarded_client(text)
                    if found:
                        return found
                    break
                try:
                    return str(ipaddress.ip_address(text.strip()))
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

