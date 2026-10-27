"""Calls the site's own routes in-process, as an anonymous visitor: a request through httpx's ASGI transport to the same FastAPI app.
Plan limits, validation, caching and numbers are therefore exactly the website's. No cookie and no Authorization header is ever sent."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("finlit.mcp")
TIMEOUT = 25.0


class ToolError(Exception):
    """A failure the model should be told about in plain words (becomes an isError tool result)."""


class Gateway:
    def __init__(self, app, host: str, ip: str):
        self.app, self.host, self.ip = app, host or "localhost", ip
        self._client: Optional[httpx.AsyncClient] = None

    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            # The caller's address is tagged "mcp:" so the site's own per-address limits count server-side use apart from the same person's browsing.
            transport = httpx.ASGITransport(app=self.app, client=(f"mcp:{self.ip}", 0))
            self._client = httpx.AsyncClient(transport=transport, base_url=f"http://{self.host}", timeout=TIMEOUT,
                                             headers={"accept": "application/json", "accept-encoding": "identity", "user-agent": "finlit-mcp"})
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def json(self, path: str, params: Optional[Dict[str, Any]] = None, *, method: str = "GET", body: Any = None, subject: str = "That") -> Any:
        try:
            r = await self.client().request(method, path, params=params, json=body)
        except (httpx.TimeoutException, TimeoutError):
            raise ToolError("The data service took too long to answer. Please try again.")
        except Exception as exc:    # a bug or an outage inside the app must not leak details
            log.warning("mcp internal call %s failed: %s", path, type(exc).__name__)
            raise ToolError("The data service is not available right now. Please try again shortly.")
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                raise ToolError("The data service returned something unreadable.")
        detail = ""
        try:
            j = r.json()
            d = j.get("detail") if isinstance(j, dict) else None
            detail = (d.get("detail") if isinstance(d, dict) else d) if d else ""
            detail = detail if isinstance(detail, str) else ""
        except ValueError:
            pass
        if r.status_code == 202:
            raise ToolError(f"{subject} is being prepared by FinLit right now. Try again in a few seconds.")
        if r.status_code == 404:
            raise ToolError(f"{subject} was not found in FinLit's data.")
        if r.status_code == 403:
            raise ToolError((detail or "This is part of a paid FinLit plan on the website.") + " It is not available through this free server.")
        if r.status_code == 429:
            raise ToolError("FinLit is receiving a lot of requests. Please try again in a minute.")
        if r.status_code in (400, 422):
            raise ToolError(f"The request was not accepted: {detail or 'check the arguments'}.")
        if r.status_code == 503:
            raise ToolError(detail or f"{subject} is temporarily unavailable. Please try again shortly.")
        log.warning("mcp internal call %s answered %s", path, r.status_code)
        raise ToolError(f"{subject} could not be loaded right now.")
