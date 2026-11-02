"""Administrators' import of AMFI's expense-ratio workbook and average-AUM answer, for a server AMFI's website will not talk to.

The nightly job (finlit/disclosure.py `refresh`) downloads these two files itself. From some hosts (the AWS address among them) www.amfiindia.com does not answer at all
(ConnectTimeout), so no expense ratio or fund size is ever stored. An administrator can then download the SAME two files in a browser and upload them here.
Nothing is trusted more because a person sent it: the bytes go through the very parsers and checks the nightly job uses (the checked column names, 0 < TER <= 5,
at least MIN_TER_SCHEMES / MIN_AUM_CODES rows, a quarter's end date) and the very writers (`store_ter`, `store_aum`), and a file older than the figures already held
is refused. The dates shown with each figure stay AMFI's own. Admin only, no secrets involved; every call is recorded at /api/mf/status (run:import-amfi)."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import tempfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import disclosure, mf
from .auth.routes import NO_STORE, Ctx, admin_ctx, fail

log = logging.getLogger("finlit.amfi_import")
router = APIRouter(prefix="/api/admin/amfi")
MAX_BODY = 30 * 1024 * 1024        # the TER workbook is about 3 MB (4 MB as base64); the AUM answer a few MB of JSON


class TerIn(BaseModel):
    file: str = Field(min_length=8, max_length=16_000_000, description="the TER workbook (.xlsx) downloaded from AMFI, as base64")


class AumIn(BaseModel):
    payload: dict = Field(description="the answer of AMFI's average-AUM address, exactly as downloaded")


def _too_big(request: Request) -> bool:
    try:
        return int(request.headers.get("content-length") or 0) > MAX_BODY
    except ValueError:
        return True


async def _finish(request: Request, kind: str, result: dict) -> JSONResponse:
    store = request.app.state.store
    await mf.record_run(store, "import-amfi", {"kind": kind, **result})
    if result.get("status") == "ok":
        await disclosure.after_import(store)
        return JSONResponse(result, status_code=201, headers=NO_STORE)
    return JSONResponse(result, status_code=422, headers=NO_STORE)


@router.post("/ter")
async def import_ter(request: Request, body: TerIn, ctx: Ctx = Depends(admin_ctx)) -> JSONResponse:
    if _too_big(request):
        raise fail(413, "too_large", "This file is too large.")
    try:
        data = base64.b64decode(body.file, validate=True)
    except (binascii.Error, ValueError):
        raise fail(422, "bad_file", "The file could not be read. Send the .xlsx file as base64.")
    if not data.startswith(b"PK\x03\x04"):
        raise fail(422, "bad_file", "This is not an Excel (.xlsx) workbook.")

    def parse():
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as fh:
            fh.write(data)
            fh.flush()
            return disclosure.parse_ter_xlsx(fh.name)
    try:
        rows = await asyncio.to_thread(parse)
    except Exception as exc:   # a damaged or unexpected workbook: say so, store nothing
        log.warning("TER import: workbook not readable: %r", exc)
        raise fail(422, "bad_file", "The workbook could not be read. Download it again from AMFI (the Excel export of the expense-ratio page).")
    if not rows:
        raise fail(422, "bad_file", "No expense-ratio table with the expected columns was found in this workbook: " + ", ".join(disclosure.TER_HEAD) + ".")
    result = await disclosure.store_ter(request.app.state.store, rows, None, min_schemes=disclosure.MIN_TER_SCHEMES, newer_only=True)
    return await _finish(request, "ter", result)


@router.post("/aum")
async def import_aum(request: Request, body: AumIn, ctx: Ctx = Depends(admin_ctx)) -> JSONResponse:
    if _too_big(request):
        raise fail(413, "too_large", "This file is too large.")
    label, end, codes = disclosure.parse_aum(body.payload)
    if not codes:
        raise fail(422, "bad_file", "No scheme-wise average AUM was found in this file. Save the page's answer as it is, without editing it.")
    result = await disclosure.store_aum(request.app.state.store, label, end, codes, min_codes=disclosure.MIN_AUM_CODES, newer_only=True)
    return await _finish(request, "aum", result)
