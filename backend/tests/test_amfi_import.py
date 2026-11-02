"""Administrators' import of AMFI's expense-ratio workbook and average-AUM answer (finlit/amfi_import.py): admin only, the same checks as the nightly download,
an older file never replaces newer figures. Fixtures are the checked slice of AMFI's own files (tests/fixtures/disclosure)."""
import base64
import json
import time
from datetime import date
from pathlib import Path

import pytest

from finlit import disclosure as d
from test_auth import app, make_admin, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401

FIX = Path(__file__).parent / "fixtures" / "disclosure"
pytestmark = pytest.mark.integration


async def _admin(app):
    from finlit.auth import crypto
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    assert (await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    return admin


def ter_b64() -> str:
    return base64.b64encode((FIX / "ter_sample.xlsx").read_bytes()).decode()


async def test_import_is_admin_only(app):
    user = await signed_in(app, "plain-amfi@example.com")
    for call in (lambda c: c.post("/api/admin/amfi/ter", json={"file": ter_b64()}), lambda c: c.post("/api/admin/amfi/aum", json={"payload": {}})):
        assert (await call(new_client(app))).status_code in (401, 403)
        assert (await call(user)).status_code == 403


async def test_ter_workbook_goes_through_the_nightly_checks(app, monkeypatch):
    admin = await _admin(app)
    monkeypatch.setattr(d, "MIN_TER_SCHEMES", 5)                        # the fixture is a 13-scheme slice of the industry file
    for bad in ("not base64 !!!", base64.b64encode(b"hello, not a workbook").decode(), base64.b64encode(b"PK\x03\x04 but not really a workbook").decode()):
        assert (await admin.post("/api/admin/amfi/ter", json={"file": bad})).status_code == 422
    monkeypatch.setattr(d, "MIN_TER_SCHEMES", 500)                      # a file with too few schemes is refused, nothing is replaced
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_ter")
    r = await admin.post("/api/admin/amfi/ter", json={"file": ter_b64()})
    assert r.status_code == 422 and r.json()["status"] == "refused" and "expected at least 500" in r.json()["why"]
    monkeypatch.setattr(d, "MIN_TER_SCHEMES", 5)
    r = await admin.post("/api/admin/amfi/ter", json={"file": ter_b64()})
    assert r.status_code == 201 and r.json()["status"] == "ok" and r.json()["schemes"] >= 5
    async with app.state.store.pool.acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM mf_ter")
        newest = await conn.fetchval("SELECT max(ter_date) FROM mf_ter")
        assert n == r.json()["schemes"] and newest.isoformat() == r.json()["day"]            # AMFI's own date is kept
        assert await conn.fetchval("SELECT count(*) FROM mf_ter WHERE ter_regular <= 0 OR ter_regular > 5 OR ter_direct <= 0 OR ter_direct > 5") == 0
        # a file older than what is held never replaces it
        await conn.execute("UPDATE mf_ter SET ter_date = $1", date(2099, 1, 1))
    r = await admin.post("/api/admin/amfi/ter", json={"file": ter_b64()})
    assert r.status_code == 422 and "older than the figures already held" in r.json()["why"]
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT max(ter_date) FROM mf_ter") == date(2099, 1, 1)


async def test_aum_answer_goes_through_the_nightly_checks(app, monkeypatch):
    admin = await _admin(app)
    payload = json.loads((FIX / "aum_sample.json").read_text())
    assert (await admin.post("/api/admin/amfi/aum", json={"payload": {"data": "nothing"}})).status_code == 422
    monkeypatch.setattr(d, "MIN_AUM_CODES", 500)
    r = await admin.post("/api/admin/amfi/aum", json={"payload": payload})
    assert r.status_code == 422 and r.json()["status"] == "refused" and "expected at least 500" in r.json()["why"]
    monkeypatch.setattr(d, "MIN_AUM_CODES", 5)
    r = await admin.post("/api/admin/amfi/aum", json={"payload": payload})
    assert r.status_code == 201 and r.json()["status"] == "ok" and r.json()["industryCrore"] > 0 and r.json()["period"]
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE mf_facts SET aum_end = $1 WHERE aum_lakh IS NOT NULL", date(2099, 1, 1))
        if await conn.fetchval("SELECT count(*) FROM mf_facts WHERE aum_end = $1", date(2099, 1, 1)):
            r = await admin.post("/api/admin/amfi/aum", json={"payload": payload})
            assert r.status_code == 422 and "older than the quarter already held" in r.json()["why"]
