"""Errors the website itself hits in a visitor's browser (a page that failed to draw, a file that would not load), sent by the page as it shows its
"Something went wrong" message. Written to the service log, short and rate-limited, so a recurring problem can be seen and fixed instead of guessed at.
Nothing personal is kept: the page address without its query, the error text, the top of its stack, the build name and the browser's name."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

log = logging.getLogger("finlit.client")
router = APIRouter(prefix="/api/client-errors")
PER_MINUTE = 40                                 # across all visitors: a broken release must not flood the log
CLEAN = re.compile(r"[\r\n\t]+")


class ClientError(BaseModel):
    message: str = Field(max_length=300)
    stack: str = Field(default="", max_length=900)
    path: str = Field(default="", max_length=200)
    kind: str = Field(default="render", max_length=20)     # render | chunk | script | promise
    build: str = Field(default="", max_length=40)


def _one_line(s: str, n: int) -> str:
    return CLEAN.sub(" | ", s)[:n]


@router.post("", status_code=204)
async def report(request: Request, body: ClientError) -> Response:
    ok = True
    try:
        ok, _ = await request.app.state.limiter.hit("client-error", "all", PER_MINUTE, 60)
    except Exception:       # the limiter being unavailable must never turn a report into an error
        ok = True
    if ok:
        ua = request.headers.get("user-agent", "")[:120]
        log.warning("client %s error on %s (build %s): %s :: %s :: %s", body.kind, _one_line(body.path.split("?")[0], 120), _one_line(body.build, 40),
                    _one_line(body.message, 300), _one_line(body.stack, 500), _one_line(ua, 120))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
