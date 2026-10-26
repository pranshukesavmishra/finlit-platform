"""Admin site controls: permissions, the persisted loads switch, restart only through the (mocked) exit function, scheduler script syntax."""
import asyncio
import subprocess
import time
from pathlib import Path

import pytest

from finlit import sysctl
from test_auth import make_admin, new_client, signed_in
from test_auth import app  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401


def test_scheduler_syntax_and_checks():
    sh = Path(__file__).resolve().parents[2] / "deploy" / "scheduler.sh"
    assert subprocess.run(["bash", "-n", str(sh)]).returncode == 0
    assert sh.read_text().count("loads_paused") >= 6


def test_memory_shape():
    m = sysctl.memory()
    assert set(m) == {"totalMb", "usedMb", "availableMb"}


@pytest.mark.integration
async def test_system_controls(app, monkeypatch):  # noqa: F811
    from finlit.auth import crypto
    calls = []
    monkeypatch.setattr(sysctl, "_exit_process", lambda: calls.append(1))
    async with new_client(app) as anon:
        for m, u in (("get", "/api/admin/system/status"), ("post", "/api/admin/system/restart")):
            assert (await getattr(anon, m)(u)).status_code == 401
    user = await signed_in(app, "sys-member@example.com")
    assert (await user.get("/api/admin/system/status")).status_code == 403
    assert (await user.post("/api/admin/system/loads", json={"enabled": False})).status_code == 403
    assert (await user.post("/api/admin/system/restart")).status_code == 403
    boss = await make_admin(app, "sys-boss@example.com")
    assert (await boss.get("/api/admin/system/status")).json()["detail"]["status"] == "mfa_required"
    secret = (await boss.post("/api/me/mfa/setup")).json()["secret"]
    await boss.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})
    st = (await boss.get("/api/admin/system/status")).json()
    assert st["loadsEnabled"] is True and st["uptimeSeconds"] >= 0 and "memory" in st
    assert (await boss.post("/api/admin/system/loads", json={"enabled": "maybe"})).status_code == 422
    assert (await boss.post("/api/admin/system/loads", json={"enabled": False})).json()["loadsEnabled"] is False
    assert (await boss.get("/api/admin/system/status")).json()["loadsEnabled"] is False
    pool = app.state.store.pool
    assert await sysctl.loads_enabled(pool) is False
    assert await sysctl.switch_get(make_settings(), "loads") == 0       # what the scheduler sees, via its own connection
    await boss.post("/api/admin/system/loads", json={"enabled": True})
    assert await sysctl.switch_get(make_settings(), "loads") == 1
    assert calls == []
    r = await boss.post("/api/admin/system/restart")
    assert r.status_code == 202 and calls == []
    await asyncio.sleep(1.4)
    assert calls == [1]
    ev = (await boss.get("/api/admin/audit")).json()["events"]
    assert {"admin_loads_paused", "admin_loads_resumed", "admin_restart"} <= {e["action"] for e in ev}
    for c in (user, boss):
        await c.aclose()


async def test_switch_get_unreadable_database():
    class S:
        database_url = "postgresql://nobody:x@127.0.0.1:1/none"
    assert await sysctl.switch_get(S(), "loads") == 0   # unreadable = paused for the heavy loads
    assert await sysctl.switch_get(S(), "web") == 1     # but on for anything web-facing
