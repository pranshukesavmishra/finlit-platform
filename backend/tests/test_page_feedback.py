"""Page queries and feedback ("Raise a Query" in the banner, "Share Feedback" at the foot of every page): tagging, who may send, limits, and the team's inbox."""

import time
from pathlib import Path

import pytest

from finlit import page_feedback as pf
from finlit.auth import crypto
from test_auth import ORIGIN, app, last_mail, make_admin, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

MIGRATIONS = Path(pf.__file__).parent / "migrations"
Q = "On the stock screener, how is the Sector filter counted when I also pick a market cap band?"


@pytest.fixture
async def papp(app):  # noqa: F811
    """The shared fixtures drop users but not this table: rebuild it so the foreign keys are real."""
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS page_feedback CASCADE")
        await conn.execute((MIGRATIONS / "095_page_feedback.sql").read_text())
    return app


def query(**over):
    return {"kind": "query", "page": "/score-screener", "pageName": "Basic score screener", "context": {"title": "Basic score screener", "screen": "desktop"}, "category": "question", "message": Q, "email": "visitor@example.com", **over}


async def rows(app):
    async with app.state.store.pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM page_feedback ORDER BY id")


async def mfa_admin(app, email="boss@example.com"):
    c = await make_admin(app, email)
    secret = (await c.post("/api/me/mfa/setup")).json()["secret"]
    assert (await c.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    return c


async def test_a_visitor_can_raise_a_query_with_an_email_and_it_is_tagged_with_the_page(papp):
    async with new_client(papp) as anon:
        r = await anon.post("/api/page-feedback", json=query(), headers=ORIGIN)
        assert r.status_code == 201 and r.json()["status"] == "received"
    [row] = await rows(papp)
    assert row["kind"] == "query" and row["page_path"] == "/score-screener" and row["page_name"] == "Basic score screener"
    assert row["email"] == "visitor@example.com" and row["user_id"] is None and row["status"] == "new" and row["message"] == Q


async def test_a_visitor_must_leave_an_email_and_a_query_needs_a_few_words(papp):
    async with new_client(papp) as anon:
        assert (await anon.post("/api/page-feedback", json=query(email=None), headers=ORIGIN)).json()["detail"]["status"] == "email_required"
        assert (await anon.post("/api/page-feedback", json=query(email="not-an-email"), headers=ORIGIN)).json()["detail"]["status"] == "email_required"
        assert (await anon.post("/api/page-feedback", json=query(message="short"), headers=ORIGIN)).json()["detail"]["status"] == "message_short"
    assert await rows(papp) == []


async def test_requests_must_come_from_our_own_pages_and_a_member_must_prove_it_with_the_csrf_token(papp):
    async with new_client(papp) as anon:
        assert (await anon.post("/api/page-feedback", json=query())).json()["detail"]["status"] == "bad_origin"                       # no Origin
        assert (await anon.post("/api/page-feedback", json=query(), headers={"Origin": "https://evil.example"})).status_code == 403
    c = await signed_in(papp, "csrf@example.com")
    del c.headers["X-CSRF-Token"]
    assert (await c.post("/api/page-feedback", json=query(email=None))).json()["detail"]["status"] == "bad_csrf"
    c.headers["X-CSRF-Token"] = "wrong"
    assert (await c.post("/api/page-feedback", json=query(email=None))).status_code == 403
    assert await rows(papp) == []
    await c.aclose()


async def test_a_member_needs_no_email_and_is_recorded_with_the_plan_held_now(papp):
    c = await signed_in(papp, "gold@example.com", plan="gold")
    r = await c.post("/api/page-feedback", json=query(email=None))
    assert r.status_code == 201
    [row] = await rows(papp)
    assert row["user_id"] is not None and row["email"] is None and row["plan"] == "gold"
    await c.aclose()


async def test_feedback_takes_a_rating_alone_or_words_alone_but_not_nothing(papp):
    c = await signed_in(papp, "fb@example.com")
    ok = {"kind": "feedback", "page": "/dcf", "pageName": "DCF calculator"}
    assert (await c.post("/api/page-feedback", json={**ok, "rating": 4})).status_code == 201
    assert (await c.post("/api/page-feedback", json={**ok, "message": "The sliders are easy to use.", "category": "praise"})).status_code == 201
    assert (await c.post("/api/page-feedback", json={**ok})).json()["detail"]["status"] == "empty_feedback"
    assert (await c.post("/api/page-feedback", json={**ok, "rating": 9})).status_code == 422
    assert (await c.post("/api/page-feedback", json={**ok, "rating": 0})).status_code == 422
    got = await rows(papp)
    assert [(r["rating"], r["category"]) for r in got] == [(4, "other"), (None, "praise")]
    await c.aclose()


async def test_a_query_never_stores_a_rating_and_unknown_categories_fall_back(papp):
    async with new_client(papp) as anon:
        await anon.post("/api/page-feedback", json=query(rating=5, category="hack"), headers=ORIGIN)
    [row] = await rows(papp)
    assert row["rating"] is None and row["category"] == "question"


async def test_the_page_address_is_cleaned_and_the_context_keeps_only_short_known_facts(papp):
    async with new_client(papp) as anon:
        ctx = {"title": "T" * 500, "symbol": "RELIANCE", "evil": "<script>x</script>", "nested": {"a": 1}, "section": ["list"], "plan": True, "screen": "phone"}
        r = await anon.post("/api/page-feedback", json=query(page="/stocks/RELIANCE/?tab=x&token=secret#frag", context=ctx), headers=ORIGIN)
        assert r.status_code == 201
        assert (await anon.post("/api/page-feedback", json=query(page="https://evil.example/x"), headers=ORIGIN)).json()["detail"]["status"] == "bad_page"
        assert (await anon.post("/api/page-feedback", json=query(page="no-slash"), headers=ORIGIN)).json()["detail"]["status"] == "bad_page"
        assert (await anon.post("/api/page-feedback", json=query(page="/a b"), headers=ORIGIN)).json()["detail"]["status"] == "bad_page"
    [row] = await rows(papp)
    import json
    context = json.loads(row["context"]) if isinstance(row["context"], str) else dict(row["context"])
    assert row["page_path"] == "/stocks/RELIANCE" and "token" not in row["page_path"]          # no query string, no fragment
    assert set(context) == {"title", "symbol", "screen"} and len(context["title"]) == 120


async def test_text_is_stored_as_plain_text_and_an_identical_message_is_stored_once(papp):
    async with new_client(papp) as anon:
        body = query(message="Hello​ there,   what does   this page show?\n\n\n\nThanks")
        assert (await anon.post("/api/page-feedback", json=body, headers=ORIGIN)).status_code == 201
        again = await anon.post("/api/page-feedback", json=body, headers=ORIGIN)
        assert again.status_code == 201 and again.json().get("duplicate") is True
    got = await rows(papp)
    assert len(got) == 1 and got[0]["message"] == "Hello there, what does this page show?\n\nThanks"


async def test_the_limits_are_per_address_and_enforced_on_the_server(papp):
    async with new_client(papp) as anon:
        codes = [(await anon.post("/api/page-feedback", json=query(message=f"{Q} Variation number {i} of the question."), headers=ORIGIN)).status_code for i in range(22)]
    assert codes[:20] == [201] * 20 and 429 in codes[20:]


async def test_a_query_is_emailed_to_the_team_mailbox_by_default(papp):
    assert papp.state.settings.feedback_notify_email == "finlit.start@gmail.com"
    async with new_client(papp) as anon:
        assert (await anon.post("/api/page-feedback", json=query(), headers=ORIGIN)).status_code == 201
    mail = await last_mail(papp, "finlit.start@gmail.com")
    assert mail and "Basic score screener" in mail["subject"] and "/score-screener" in mail["body"] and Q in mail["body"] and "visitor@example.com" in mail["body"]


async def test_feedback_is_stored_but_not_emailed_and_the_email_can_be_switched_off_or_moved(papp, monkeypatch):
    from dataclasses import replace
    async with new_client(papp) as anon:
        r = await anon.post("/api/page-feedback", json={"kind": "feedback", "page": "/dcf", "pageName": "DCF calculator", "rating": 5, "email": "v@example.com"}, headers=ORIGIN)
        assert r.status_code == 201
    assert await last_mail(papp, "finlit.start@gmail.com") is None
    papp.state.settings = replace(papp.state.settings, feedback_notify_email="other@example.com")
    async with new_client(papp) as anon:
        assert (await anon.post("/api/page-feedback", json=query(message=Q + " Sent to another mailbox."), headers=ORIGIN)).status_code == 201
    assert await last_mail(papp, "other@example.com")
    papp.state.settings = replace(papp.state.settings, feedback_notify_email="")
    async with new_client(papp) as anon:
        assert (await anon.post("/api/page-feedback", json=query(message=Q + " Nothing is emailed now."), headers=ORIGIN)).status_code == 201
    assert len(await rows(papp)) == 3


async def test_a_mail_problem_never_fails_the_members_request(papp, monkeypatch):
    async def broken(*a, **k):
        raise RuntimeError("mail down")
    monkeypatch.setattr(papp.state.mailer, "send", broken)
    async with new_client(papp) as anon:
        assert (await anon.post("/api/page-feedback", json=query(message=Q + " A second, different question."), headers=ORIGIN)).status_code == 201   # stored; the mail problem is not the member's
    assert len(await rows(papp)) == 1


async def test_only_an_administrator_with_the_two_step_sign_in_reads_the_inbox(papp):
    async with new_client(papp) as anon:
        for path in ("/api/admin/page-feedback", "/api/admin/page-feedback/summary"):
            assert (await anon.get(path)).status_code == 401
    member = await signed_in(papp, "member@example.com", plan="gold")
    assert (await member.get("/api/admin/page-feedback")).status_code == 403
    assert (await member.patch("/api/admin/page-feedback/1", json={"status": "read"})).status_code == 403
    await member.aclose()


async def test_the_inbox_filters_by_kind_status_and_page_and_the_team_can_close_a_message(papp):
    member = await signed_in(papp, "m@example.com", plan="silver")
    await member.post("/api/page-feedback", json=query(email=None))
    await member.post("/api/page-feedback", json={"kind": "feedback", "page": "/dcf", "pageName": "DCF calculator", "rating": 2, "message": "The slider range is too wide.", "category": "ui_ux"})
    admin = await mfa_admin(papp)
    got = (await admin.get("/api/admin/page-feedback")).json()
    assert got["total"] == 2 and got["counts"] == {"new": 2, "openQueries": 1}
    assert [i["kind"] for i in got["items"]] == ["feedback", "query"]                           # newest first
    q = [i for i in got["items"] if i["kind"] == "query"][0]
    assert q["page"] == "/score-screener" and q["pageName"] == "Basic score screener" and q["email"] == "m@example.com" and q["member"] is True and q["plan"] == "silver"
    assert (await admin.get("/api/admin/page-feedback?kind=feedback")).json()["total"] == 1
    assert (await admin.get("/api/admin/page-feedback?page=/dcf")).json()["items"][0]["rating"] == 2
    assert (await admin.patch(f"/api/admin/page-feedback/{q['id']}", json={"status": "resolved", "note": "Answered by email."})).json()["status"] == "saved"
    after = (await admin.get("/api/admin/page-feedback?status=resolved")).json()
    assert after["total"] == 1 and after["items"][0]["note"] == "Answered by email." and after["items"][0]["handledAt"]
    assert (await admin.get("/api/admin/page-feedback")).json()["counts"] == {"new": 1, "openQueries": 0}
    assert (await admin.patch("/api/admin/page-feedback/999999", json={"status": "read"})).status_code == 404
    assert (await admin.patch(f"/api/admin/page-feedback/{q['id']}", json={"status": "bogus"})).status_code == 422
    for c in (member, admin):
        await c.aclose()


async def test_the_summary_says_which_pages_people_write_about_most(papp):
    c = await signed_in(papp, "s@example.com")
    for i, rating in enumerate((5, 3, 4)):
        await c.post("/api/page-feedback", json={"kind": "feedback", "page": "/dcf", "pageName": "DCF calculator", "rating": rating, "message": f"Opinion number {i} on this page."})
    await c.post("/api/page-feedback", json=query(email=None))
    admin = await mfa_admin(papp)
    pages = (await admin.get("/api/admin/page-feedback/summary")).json()["pages"]
    assert pages[0] == {"page": "/dcf", "name": "DCF calculator", "total": 3, "queries": 0, "feedback": 3, "new": 3, "avgRating": 4.0, "rated": 3}
    assert pages[1]["page"] == "/score-screener" and pages[1]["avgRating"] is None and pages[1]["queries"] == 1
    for x in (c, admin):
        await x.aclose()
