"""Admin fund-load buttons: permissions, allow-list, busy refusal, audit."""
import fcntl
import os
import time

import pytest

from finlit import fundjobs
from test_auth import make_admin, new_client, signed_in
from test_auth import app  # noqa: F401
from test_integration import ingested, store  # noqa: F401


class FakePopen:
    calls = []

    def __init__(self, args, **kw):
        FakePopen.calls.append((args, kw))


@pytest.mark.integration
async def test_fund_buttons(app, monkeypatch, tmp_path):  # noqa: F811
    from finlit.auth import crypto
    monkeypatch.setattr(fundjobs, "FUNDS_LOCK", str(tmp_path / "funds.lock"))
    monkeypatch.setattr(fundjobs.subprocess, "Popen", FakePopen)
    async with new_client(app) as anon:
        assert (await anon.get("/api/admin/funds/status")).status_code == 401
    user = await signed_in(app, "fund-member@example.com")
    assert (await user.get("/api/admin/funds/status")).json()["detail"]["status"] == "forbidden"
    boss = await make_admin(app, "fund-boss@example.com")
    secret = (await boss.post("/api/me/mfa/setup")).json()["secret"]
    await boss.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})
    assert (await boss.post("/api/admin/funds/run", json={"job": "rm -rf /"})).status_code == 422
    assert (await boss.post("/api/admin/funds/run", json={"job": "ingest-all"})).status_code == 422
    assert FakePopen.calls == []
    r = await boss.post("/api/admin/funds/run", json={"job": "refresh-mf"})
    assert r.status_code == 200
    args, kw = FakePopen.calls[0]
    assert args[1:] == ["-m", "finlit.fundjobs", "refresh-mf"] and kw["env"]["MALLOC_ARENA_MAX"] == "2" and kw["start_new_session"] is True
    st = (await boss.get("/api/admin/funds/status")).json()
    assert st["running"] is False and st["jobs"]["refresh-mf"]["state"] == "starting"
    fd = os.open(fundjobs.FUNDS_LOCK, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        assert (await boss.get("/api/admin/funds/status")).json()["running"] is True
        assert (await boss.post("/api/admin/funds/run", json={"job": "refresh-etf"})).status_code == 409
        assert len(FakePopen.calls) == 1
    finally:
        os.close(fd)
    ev = (await boss.get("/api/admin/audit")).json()["events"]
    assert any(e["action"] == "admin_fund_load_started" and e["target"] == "refresh-mf" for e in ev)
    for c in (user, boss):
        await c.aclose()
