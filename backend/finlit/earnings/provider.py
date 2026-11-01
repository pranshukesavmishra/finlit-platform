"""The language-model engine behind the summaries, behind one small interface so it can be swapped (docs/EARNINGS-CALLS.md, "Engine").

`LlmProvider.generate(system, user)` returns the model's text. The default is Gemini over its REST API (plain httpx: no new dependency), the same
GEMINI_API_KEY the FinLit AI chat uses. Tests use a fake provider. Nothing here knows about transcripts or questions.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional, Protocol

import httpx

log = logging.getLogger("finlit.earnings.llm")


class NotConfigured(Exception):
    """No API key: the job reports it and stops; the site says the summaries are not available yet."""


class RateLimited(Exception):
    """The provider said 429 (or the daily quota is gone). `retry_after` is in seconds; `daily` is True when waiting a minute will not help."""

    def __init__(self, retry_after: float = 0.0, daily: bool = False, detail: str = ""):
        super().__init__(detail or "rate limited")
        self.retry_after, self.daily = retry_after, daily


class ProviderError(Exception):
    """Any other failure of one request (5xx, malformed reply, blocked content). The caller counts it and moves on."""


class LlmProvider(Protocol):
    name: str
    model: str

    @property
    def configured(self) -> bool: ...

    async def generate(self, system: str, user: str) -> str: ...

    async def aclose(self) -> None: ...


class GeminiProvider:
    """generateContent on the Gemini REST API with JSON output. The key travels in a header, never in the URL, and is never logged."""
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str, transport: Optional[httpx.AsyncBaseTransport] = None, timeout: float = 180.0):
        self.api_key, self.model = (api_key or "").strip(), model
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0), transport=transport, headers={"User-Agent": "FinLit-earnings/1.0 (+https://finlitventures.com)"})

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def generate(self, system: str, user: str) -> str:
        if not self.api_key:
            raise NotConfigured("GEMINI_API_KEY is empty")
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json", "maxOutputTokens": 8192}}
        try:
            r = await self._client.post(f"{self.BASE}/{self.model}:generateContent", json=body, headers={"x-goog-api-key": self.api_key})
        except httpx.TransportError as exc:
            raise ProviderError(f"network: {type(exc).__name__}") from None
        if r.status_code == 429:
            raise RateLimited(*_retry_after(r))
        if r.status_code in (401, 403):
            raise NotConfigured(f"the key was refused ({r.status_code})")
        if r.status_code >= 400:
            raise ProviderError(f"HTTP {r.status_code}")
        try:
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (ValueError, KeyError, IndexError, TypeError):
            reason = ""
            try:
                reason = str(r.json().get("promptFeedback") or r.json()["candidates"][0].get("finishReason") or "")[:80]
            except Exception:
                pass
            raise ProviderError("no text in the reply " + reason) from None

    async def aclose(self) -> None:
        await self._client.aclose()


def _retry_after(r: httpx.Response) -> tuple:
    """(seconds to wait, daily quota gone?) from a 429. Gemini names the wait in the body ("retryDelay": "34s") and a per-day quota in the violation text."""
    wait = 0.0
    try:
        wait = float(r.headers.get("retry-after", 0))
    except ValueError:
        pass
    text = r.text or ""
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text)
    if m:
        wait = max(wait, float(m.group(1)))
    return wait, bool(re.search(r"PerDay|per day|daily", text, re.I))


class Pacer:
    """At most `per_minute` requests a minute and `per_day` a day for this run. The daily count lives in Redis (key per UTC date) so several runs share it;
    when Redis is unavailable it falls back to this process's own count."""

    def __init__(self, per_minute: int, per_day: int, redis=None, clock=time.monotonic, sleep=asyncio.sleep):
        self.gap = 60.0 / max(1, per_minute)
        self.per_day, self.redis, self._clock, self._sleep = per_day, redis, clock, sleep
        self._last: Optional[float] = None
        self._local = 0

    def _key(self) -> str:
        return "earnings:llm:" + time.strftime("%Y-%m-%d", time.gmtime())

    async def used_today(self) -> int:
        if self.redis is not None:
            try:
                return int(await self.redis.get(self._key()) or 0)
            except Exception:
                pass
        return self._local

    async def left_today(self) -> int:
        return max(0, self.per_day - await self.used_today())

    async def take(self) -> bool:
        """Reserve one request: waits for the per-minute gap, returns False when today's budget is spent."""
        if await self.left_today() <= 0:
            return False
        if self._last is not None:
            wait = self.gap - (self._clock() - self._last)
            if wait > 0:
                await self._sleep(wait)
        self._last = self._clock()
        self._local += 1
        if self.redis is not None:
            try:
                key = self._key()
                await self.redis.incr(key)
                await self.redis.expire(key, 3 * 86400)
            except Exception:
                pass
        return True

    async def exhaust(self) -> None:
        """The provider says today's quota is gone: stop for the day, whatever our own count says."""
        self._local = self.per_day
        if self.redis is not None:
            try:
                key = self._key()
                await self.redis.set(key, self.per_day, ex=3 * 86400)
            except Exception:
                pass
