import pytest

from test_auth import app, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401

pytestmark = pytest.mark.integration


async def test_notify_signup_is_stored_once_and_never_reveals_who_signed_up(app):  # noqa: F811
    async with new_client(app) as c:
        a = await c.post("/api/notify", json={"email": " New.Person@Example.com "})
        b = await c.post("/api/notify", json={"email": "new.person@example.com"})
        assert a.status_code == b.status_code == 202 and a.json() == b.json()           # same answer for a new and a repeat address
        bad = await c.post("/api/notify", json={"email": "not-an-email"})
        assert bad.status_code == 422
        bot = await c.post("/api/notify", json={"email": "bot@example.com", "website": "http://spam"})
        assert bot.status_code == 202                                                    # looks fine to the bot, nothing stored
        assert (await c.get("/api/admin/notify")).status_code == 401                     # the list is for administrators only
    async with app.state.store.pool.acquire() as conn:
        rows = [r["email"] for r in await conn.fetch("SELECT email FROM notify_signups")]
    assert rows == ["new.person@example.com"]
    member = await signed_in(app, "m@example.com", plan="gold")
    assert (await member.get("/api/admin/notify")).status_code == 403                    # not even Gold members
