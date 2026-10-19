"""Launch-notification sign-ups from the website ("Coming soon: get notified")."""

from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from .auth import crypto
from .auth.routes import NO_STORE, admin_ctx, fail, limit
from .security import client_ip

router = APIRouter(prefix="/api")


class NotifyIn(BaseModel):
    email: str = Field(max_length=254)
    source: str = Field(default="home", max_length=24, pattern=r"^[a-z0-9_-]*$")
    website: Optional[str] = Field(default=None, max_length=100)   # hidden field: only bots fill it in


@router.post("/notify", status_code=202)
async def notify(request: Request, body: NotifyIn):
    """Always answers the same way, so nobody can use this to find out who has signed up."""
    ip = client_ip(request.scope, request.app.state.settings.client_ip_header)
    await limit(request, "notify-ip", ip, 8, 3600)
    email = crypto.normalise_email(body.email)
    if not email:
        raise fail(422, "invalid_email", "Please enter a valid email address.")
    if not body.website:
        async with request.app.state.store.pool.acquire() as conn:
            await conn.execute("INSERT INTO notify_signups (email, source) VALUES ($1, $2) ON CONFLICT (email) DO NOTHING", email, body.source or "home")
    return Response(content='{"status":"ok"}', status_code=202, media_type="application/json", headers=NO_STORE)


@router.get("/admin/notify")
async def notify_list(request: Request, format: str = "json", _ctx=Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT email, source, created_at FROM notify_signups ORDER BY created_at DESC LIMIT 5000")
        total = await conn.fetchval("SELECT count(*) FROM notify_signups")
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf); w.writerow(["email", "source", "signed_up"])
        for r in rows:
            w.writerow([r["email"], r["source"], r["created_at"].isoformat()])
        return Response(content=buf.getvalue(), media_type="text/csv", headers={**NO_STORE, "Content-Disposition": 'attachment; filename="finlit-notify-list.csv"'})
    import json
    return Response(content=json.dumps({"total": total, "items": [{"email": r["email"], "source": r["source"], "at": r["created_at"].isoformat()} for r in rows[:200]]}),
                    media_type="application/json", headers=NO_STORE)
