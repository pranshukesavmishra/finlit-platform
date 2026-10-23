"""Alert and notification endpoints for signed-in members. Plan limits and metric access are enforced here, not in the browser."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from . import alertengine as eng
from .auth.routes import NO_STORE, SYMBOL, Ctx, fail, limit, secure_ctx

router = APIRouter(prefix="/api")


class AlertIn(BaseModel):
    symbol: str = Field(max_length=24)
    metric: str = Field(max_length=40)
    op: Literal["above", "below", "event"]
    value: Optional[float] = Field(default=None, ge=-1e9, le=1e12)
    keyword: Optional[str] = Field(default=None, max_length=40)
    channels: List[str] = Field(default_factory=lambda: ["app"], max_length=4)
    repeat: Literal["once", "every"] = "once"
    note: Optional[str] = Field(default=None, max_length=140)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        v = v.strip().upper()
        if not SYMBOL.match(v):
            raise ValueError("bad symbol")
        return v


class AlertPatch(BaseModel):
    status: Optional[Literal["active", "paused"]] = None
    value: Optional[float] = Field(default=None, ge=-1e9, le=1e12)
    channels: Optional[List[str]] = Field(default=None, max_length=4)
    repeat: Optional[Literal["once", "every"]] = None
    note: Optional[str] = Field(default=None, max_length=140)


def alert_json(r: Any) -> Dict[str, Any]:
    meta = eng.METRICS.get(r["metric"], {})
    return {"id": str(r["id"]), "symbol": r["symbol"], "metric": r["metric"], "label": meta.get("label", r["metric"]), "unit": meta.get("unit", ""), "op": r["op"],
            "value": float(r["value"]) if r["value"] is not None else None, "keyword": r["keyword"], "channels": list(r["channels"]), "repeat": r["repeat"],
            "status": r["status"], "note": r["note"], "lastValue": float(r["last_value"]) if r["last_value"] is not None and r["op"] != "event" else None,
            "met": r["met"], "lastCheckedAt": r["last_checked"].isoformat() if r["last_checked"] else None,
            "lastFiredAt": r["last_fired_at"].isoformat() if r["last_fired_at"] else None, "firedCount": r["fired_count"], "createdAt": r["created_at"].isoformat()}


def notification_json(r: Any) -> Dict[str, Any]:
    return {"id": r["id"], "alertId": str(r["alert_id"]) if r["alert_id"] else None, "symbol": r["symbol"], "kind": r["kind"], "title": r["title"], "body": r["body"],
            "link": r["link"], "push": r["push"], "read": r["read_at"] is not None, "createdAt": r["created_at"].isoformat()}


def clean_channels(ch: List[str]) -> List[str]:
    bad = [c for c in ch if c not in eng.CHANNELS]
    if bad:
        raise fail(422, "bad_channel", "Notify via in-app, email or browser. The mobile app is not available yet.")
    return ["app"] + [c for c in eng.CHANNELS[1:] if c in ch]  # in-app is always on: it is where every alert is kept


def json_response(body: Any, status: int = 200) -> Response:
    return Response(content=json.dumps(body), media_type="application/json", headers=NO_STORE, status_code=status)


@router.get("/alerts")
async def list_alerts(request: Request, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM alerts WHERE user_id = $1 ORDER BY created_at DESC", ctx.user_id)
    return json_response({"alerts": [alert_json(r) for r in rows], "limit": eng.ALERT_LIMITS[ctx.plan]})


@router.get("/alerts/value")
async def alert_value(request: Request, symbol: str = Query(max_length=24), metric: str = Query(max_length=40), ctx: Ctx = Depends(secure_ctx)):
    """Where a metric stands right now, so the form can say "currently 31.2" before the member picks a target."""
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol) or metric not in eng.METRICS:
        raise fail(422, "bad_request")
    if not eng.allowed(ctx.plan, metric):
        raise fail(403, "plan_required", "This metric is part of the Silver plan.", plan="silver")
    async with request.app.state.store.pool.acquire() as conn:
        v = await eng.current_value(conn, symbol, metric)
    return json_response({"value": v})


@router.post("/alerts", status_code=201)
async def create_alert(request: Request, body: AlertIn, ctx: Ctx = Depends(secure_ctx)):
    await limit(request, "alertw", ctx.user_id, 60, 600)
    meta = eng.METRICS.get(body.metric)
    if not meta or body.op not in meta["ops"]:
        raise fail(422, "bad_metric", "That condition does not apply to this metric.")
    if not eng.allowed(ctx.plan, body.metric):
        raise fail(403, "plan_required", f"{meta['label']} alerts are part of the Silver plan.", plan="silver")
    keyword = (body.keyword or "").strip().lower() or None
    if body.metric in eng.FIXED_TARGET:   # "hits the upper circuit" has no number to choose: the target is set here, whatever was sent
        body.value = eng.FIXED_TARGET[body.metric][body.op]
    if body.op == "event":
        if body.metric == "news_keyword" and (keyword is None or len(keyword) < 2):
            raise fail(422, "keyword_required", "Type the word or phrase to watch for (at least 2 characters).")
        if body.metric == "result_soon" and not (body.value and 1 <= body.value <= 60):
            raise fail(422, "bad_value", "Choose between 1 and 60 days.")
    elif body.value is None:
        raise fail(422, "value_required", "Enter the target value.")
    if body.metric != "news_keyword":
        keyword = None
    channels = clean_channels(body.channels)
    pool = request.app.state.store.pool
    async with pool.acquire() as conn:
        if not await conn.fetchval("SELECT EXISTS(SELECT 1 FROM companies WHERE symbol = $1) OR EXISTS(SELECT 1 FROM scores WHERE symbol = $1)", body.symbol):
            raise fail(404, "unknown_stock", "We could not find that company.")
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM alerts WHERE user_id = $1 AND symbol = $2 AND metric = $3 AND op = $4 AND status <> 'done' "
                               "AND value IS NOT DISTINCT FROM $5::numeric AND keyword IS NOT DISTINCT FROM $6)", ctx.user_id, body.symbol, body.metric, body.op, body.value, keyword):
            raise fail(409, "duplicate", "You already have this alert.")
        cap = eng.ALERT_LIMITS[ctx.plan]
        if await conn.fetchval("SELECT count(*) FROM alerts WHERE user_id = $1 AND status <> 'done'", ctx.user_id) >= cap:
            raise fail(403, "plan_limit", f"Your plan includes {cap} alerts at a time. Remove one that has finished, or upgrade.", plan="gold" if ctx.plan == "silver" else "silver")
        met, current, seen = None, None, None
        if body.op == "event":
            seen = await eng.newest_feed_id(conn, body.symbol)  # only things published from now on count
        else:
            current = await eng.current_value(conn, body.symbol, body.metric)
            if current is not None:
                met = current >= body.value if body.op == "above" else current <= body.value
            else:
                met = False
        row = await conn.fetchrow(
            "INSERT INTO alerts (user_id, symbol, metric, op, value, keyword, channels, repeat, note, met, last_value) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *",
            ctx.user_id, body.symbol, body.metric, body.op, body.value, keyword, channels, body.repeat, (body.note or "").strip() or None, met, current if current is not None else seen)
    out = alert_json(row)
    out["alreadyMet"] = bool(met) if body.op != "event" else False
    out["current"] = current
    return json_response(out, 201)


@router.patch("/alerts/{aid}")
async def patch_alert(request: Request, aid: str, body: AlertPatch, ctx: Ctx = Depends(secure_ctx)):
    await limit(request, "alertw", ctx.user_id, 60, 600)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise fail(422, "nothing_to_change")
    if "channels" in fields:
        fields["channels"] = clean_channels(fields["channels"] or [])
    async with request.app.state.store.pool.acquire() as conn:
        a = await conn.fetchrow("SELECT * FROM alerts WHERE id::text = $1 AND user_id = $2", aid, ctx.user_id)
        if not a:
            raise fail(404, "not_found")
        if "value" in fields and a["metric"] in eng.FIXED_TARGET:
            raise fail(422, "bad_value", "This alert has no target value to change.")
        sets, args = [], []
        for k, v in fields.items():
            args.append(v)
            sets.append(f"{k} = ${len(args) + 2}")  # nosec B608 - names come from the AlertPatch model, never from the request
        if fields.get("status") == "active" or "value" in fields:
            sets.append("met = NULL")  # re-learn which side of the target we are on, so resuming never fires by itself
        if fields.get("status") == "active" and a["status"] == "done":
            sets.append("fired_count = 0")
        row = await conn.fetchrow(f"UPDATE alerts SET {', '.join(sets)} WHERE id = $1 AND user_id = $2 RETURNING *", a["id"], ctx.user_id, *args)  # nosec B608
        if row["op"] != "event" and row["met"] is None:
            cur = await eng.current_value(conn, row["symbol"], row["metric"])
            met = None if cur is None else (cur >= float(row["value"]) if row["op"] == "above" else cur <= float(row["value"]))
            row = await conn.fetchrow("UPDATE alerts SET met = $2, last_value = $3 WHERE id = $1 RETURNING *", row["id"], bool(met), cur)
    return json_response(alert_json(row))


@router.delete("/alerts/{aid}")
async def delete_alert(request: Request, aid: str, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        n = await conn.fetchval("WITH d AS (DELETE FROM alerts WHERE id::text = $1 AND user_id = $2 RETURNING 1) SELECT count(*) FROM d", aid, ctx.user_id)
    if not n:
        raise fail(404, "not_found")
    return json_response({"status": "deleted"})


@router.get("/notifications")
async def list_notifications(request: Request, limit_: int = Query(30, alias="limit", ge=1, le=100), before: Optional[int] = Query(None, ge=0), unread: bool = False,
                             ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM notifications WHERE user_id = $1 AND ($2::bigint IS NULL OR id < $2) AND (NOT $3 OR read_at IS NULL) ORDER BY id DESC LIMIT $4",
                                ctx.user_id, before, unread, limit_)
        count = await conn.fetchval("SELECT count(*) FROM notifications WHERE user_id = $1 AND read_at IS NULL", ctx.user_id)
    return json_response({"notifications": [notification_json(r) for r in rows], "unread": count})


class ReadIn(BaseModel):
    ids: Optional[List[int]] = Field(default=None, max_length=200)


@router.post("/notifications/read")
async def mark_read(request: Request, body: ReadIn, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        if body.ids is None:
            await conn.execute("UPDATE notifications SET read_at = now() WHERE user_id = $1 AND read_at IS NULL", ctx.user_id)
        else:
            await conn.execute("UPDATE notifications SET read_at = now() WHERE user_id = $1 AND id = ANY($2::bigint[]) AND read_at IS NULL", ctx.user_id, body.ids)
        count = await conn.fetchval("SELECT count(*) FROM notifications WHERE user_id = $1 AND read_at IS NULL", ctx.user_id)
    return json_response({"unread": count})


@router.delete("/notifications")
async def clear_notifications(request: Request, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM notifications WHERE user_id = $1", ctx.user_id)
    return json_response({"unread": 0})
