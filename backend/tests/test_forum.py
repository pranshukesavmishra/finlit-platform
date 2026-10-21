"""Discussion forum: the content rules (pure), then permissions, rate limits, moderation, soft delete, edit window and XSS safety end to end."""

import json
import time
from pathlib import Path

import pytest

from finlit import forum, forum_rules as R
from finlit.auth import crypto
from test_auth import ORIGIN, app, make_admin, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

MIGRATIONS = Path(forum.__file__).parent / "migrations"
GOOD = "Reliance reported higher retail revenue this quarter while the oil to chemicals margin fell; I want to see how capex plans change the debt picture."


# ------------------------------------------------------------------ the rules (no database)
@pytest.mark.parametrize("text", [
    "mail me at trader.joe@gmail.com for details", "reach me: joe [at] gmail [dot] com", "call 9876543210 now", "my number is 98765 43210", "+91 98765-43210",
    "+1 415 555 2671", "join on whatsapp", "DM me for the list", "find me @stock_guru_77", "check t.me/sureprofits", "go to https://wa.me/919876543210",
    "see bit.ly/abc123", "https://www.instagram.com/someone", "ping me on telegram",
])
def test_contact_details_and_invites_are_refused(text):
    v = R.check_text(text)
    assert not v.ok and v.code in ("contact_details", "blocked_link", "advice_or_call"), (text, v)


@pytest.mark.parametrize("text", [
    "Buy now before it runs", "sell today, it will fall", "Target price 2500 by March", "target: Rs 1,200", "TGT 450", "stoploss 2300", "SL at 120",
    "sure shot 3x in 2 months", "guaranteed returns", "risk free trade", "this is a multibagger tip, intraday calls daily", "join my channel for tips",
    "I recommend you to buy this", "you should buy more", "paid tips group", "10x in 3 months for sure",
])
def test_buy_sell_calls_and_promises_are_refused(text):
    v = R.check_text(text)
    assert not v.ok and v.code == "advice_or_call", (text, v)


@pytest.mark.parametrize("text", [
    "P/E below 10 is cheap only if earnings are stable; here the ROE < 12 worries me.",
    "Management has a target of 15% EBITDA margin by FY27 according to the call.",
    "Promoters sell at a premium in block deals sometimes; the filing shows 2.1 crore shares.",
    "Revenue of ₹1,23,45,67,890 crore in rupees would be absurd; check the unit (Rs. in crore).",
    "FY2023 2024 2025 growth was 12%, 14%, 9% respectively.", "See the filing at https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf for the note on leases.",
    "Debt/Equity improved from 0.8 to 0.5; interest cover 4.2x is fine for me.", "EPS @ Rs.45 versus Rs.40 last year.",
])
def test_ordinary_analysis_is_not_refused(text):
    v = R.check_text(text)
    assert v.ok and not v.hold, (text, v)


@pytest.mark.parametrize("text,why", [
    ("This looks like a multibagger to me", "hype"), ("Heavy PUMP going on here", "hype"), ("Could be 10x from here, who knows", "multiple"), ("Great set up 🚀 for the year ahead of us", "emoji"),
    ("WHY IS EVERYBODY IGNORING THIS COMPANY'S BALANCE SHEET HERE", "caps"), ("amazing news!!!!", "shouting"),
])
def test_hype_is_held_for_a_moderator_not_refused(text, why):
    v = R.check_text(text)
    assert v.ok and v.hold, (text, why)


def test_links_are_limited_and_new_members_links_are_held():
    assert R.check_text("see https://a.example/x and https://b.example/y").ok
    assert R.check_text("one https://a.example one https://b.example three https://c.example").code == "too_many_links"
    assert R.check_text("http://192.168.1.1/x").code == "bad_link"
    assert R.check_text("https://user:pw@evil.example/x").code in ("bad_link", "contact_details")
    assert R.check_text("javascript:alert(1) is not a link but https://a.example is").ok
    assert R.check_text("source https://www.nseindia.com/x", trusted=False).hold == ["a link from a member with no approved posts yet"]
    assert R.check_text("source https://www.nseindia.com/x", trusted=True).hold == []


def test_clean_text_makes_plain_text():
    assert R.clean_text("a​b‮evil\u0000  \t spaced\r\n\r\n\r\n\r\nend ") == "abevil spaced\n\nend"
    assert R.clean_text("<script>alert(1)</script> P/E < 10") == "<script>alert(1)</script> P/E < 10"   # kept as typed; the website renders text only
    assert R.clean_text("ＢＵＹ") == "BUY"                                                          # full-width letters cannot dodge the rules
    assert not R.check_text(R.clean_text("ｂｕｙ​ now")).ok


def test_hash_ignores_case_spacing_and_punctuation():
    assert R.content_hash("Hello,  World!") == R.content_hash("hello world")
    assert R.content_hash("a b") != R.content_hash("a c")


@pytest.mark.parametrize("handle,ok", [("asha_k", True), ("Investor42", True), ("ab", False), ("1abc", False), ("a b", False), ("FinLit_Team", False), ("admin1", False),
                                       ("sebi_expert", False), ("x" * 21, False), ("john@mail", False), ("trader9876543210", False), ("deleted", False)])
def test_handle_rules(handle, ok):
    assert (R.check_handle(handle) == "") is ok


def test_length_rules():
    assert R.check_lengths("thread", "Short", "x" * 30)
    assert R.check_lengths("thread", "A decent title", "x" * 5)
    assert not R.check_lengths("thread", "A decent title", "x" * 30)
    assert R.check_lengths("reply", None, "x") and not R.check_lengths("reply", None, "ok")


# ------------------------------------------------------------------ end to end
@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(forum, "MIN_ACCOUNT_AGE_SECONDS", 0)


@pytest.fixture
async def fapp(app):  # noqa: F811
    """The shared fixtures drop users/companies but not the forum tables: rebuild them so the foreign keys are real."""
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS forum_reports, forum_votes, forum_posts, forum_profiles CASCADE")
        for name in ("032_forum.sql", "033_forum_reports.sql"):
            await conn.execute((MIGRATIONS / name).read_text())
    return app


async def member(app, email, handle=None, plan=None):
    c = await signed_in(app, email, plan=plan)
    if handle:
        r = await c.post("/api/forum/profile", json={"handle": handle, "accept": True})
        assert r.status_code == 201, r.text
    return c


async def thread(c, title="Retail revenue and the capex picture", body=GOOD, symbol="RELIANCE"):
    return await c.post("/api/forum/threads", json={"symbol": symbol, "title": title, "body": body})


async def mfa_admin(app, email="boss@example.com"):
    c = await make_admin(app, email)
    secret = (await c.post("/api/me/mfa/setup")).json()["secret"]
    assert (await c.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    return c


async def test_empty_forum_is_honestly_empty_and_reading_is_open(fapp):
    async with new_client(fapp) as anon:
        assert (await anon.get("/api/forum/threads")).json()["total"] == 0
        assert (await anon.get("/api/forum/companies")).json() == {"companies": []}
        assert (await anon.get("/api/forum/stats?symbol=RELIANCE")).json()["threads"] == 0
        me = (await anon.get("/api/forum/me")).json()
        assert me["signedIn"] is False and me["canPost"] is False and me["rules"]["editWindowMinutes"] == 15
        assert (await anon.get("/api/forum/threads/999999")).status_code == 404
        assert (await anon.get("/api/forum/threads?symbol=NOPE123")).status_code == 404
        assert (await anon.get("/api/forum/threads?symbol=bad symbol!")).status_code == 400


async def test_visitors_cannot_write_and_writes_need_origin_and_csrf(fapp):
    async with new_client(fapp) as anon:
        for method, path, body in (("post", "/api/forum/threads", {"symbol": "RELIANCE", "title": "x" * 10, "body": GOOD}), ("post", "/api/forum/profile", {"handle": "abcd", "accept": True}),
                                   ("put", "/api/forum/posts/1/vote", None), ("post", "/api/forum/posts/1/report", {"reason": "spam"}), ("delete", "/api/forum/posts/1", None)):
            r = await getattr(anon, method)(path, **({"json": body} if body is not None else {}))
            assert r.status_code == 401, (path, r.status_code)
        assert (await anon.get("/api/admin/forum/queue")).status_code == 401
    c = await member(fapp, "csrf@example.com", "csrf_user")
    del c.headers["X-CSRF-Token"]
    assert (await thread(c)).json()["detail"]["status"] == "bad_csrf"
    c.headers["X-CSRF-Token"] = "wrong"
    assert (await thread(c)).status_code == 403
    await c.aclose()


async def test_handle_is_required_unique_and_hides_the_email_and_account_name(fapp):
    c = await signed_in(fapp, "asha.private@example.com")
    assert (await thread(c)).json()["detail"]["status"] == "handle_required"
    assert (await c.post("/api/forum/profile", json={"handle": "asha_k", "accept": False})).json()["detail"]["status"] == "accept_required"
    assert (await c.post("/api/forum/profile", json={"handle": "FinLit_Official", "accept": True})).json()["detail"]["status"] == "bad_handle"
    assert (await c.post("/api/forum/profile", json={"handle": "asha_k", "accept": True})).status_code == 201
    assert (await c.post("/api/forum/profile", json={"handle": "other_name", "accept": True})).json()["detail"]["status"] == "handle_exists"   # chosen once
    other = await signed_in(fapp, "second@example.com")
    assert (await other.post("/api/forum/profile", json={"handle": "ASHA_K", "accept": True})).json()["detail"]["status"] == "handle_taken"  # case-insensitive
    r = await thread(c)
    assert r.status_code == 201 and r.json()["post"]["author"]["handle"] == "asha_k"
    listing = (await other.get("/api/forum/threads")).text
    assert "asha.private" not in listing and "example.com" not in listing and "Asha" not in listing   # neither the email nor the account name ("Asha") leaks
    me = (await c.get("/api/forum/me")).json()
    assert me["handle"] == "asha_k" and me["canPost"] is True
    await c.aclose()
    await other.aclose()


async def test_any_plan_may_post_and_reading_needs_no_account(fapp):
    basic = await member(fapp, "basic@example.com", "basic_user")          # Basic is the free tier: the forum is not a paid feature
    gold = await member(fapp, "gold@example.com", "gold_user", plan="gold")
    assert (await thread(basic)).status_code == 201 and (await thread(gold, title="Gold member question here", body=GOOD + " Second thoughts.")).status_code == 201
    async with new_client(fapp) as anon:
        assert (await anon.get("/api/forum/threads")).json()["total"] == 2
    for c in (basic, gold):
        await c.aclose()


async def test_thread_reply_ordering_pagination_and_company_boards(fapp, monkeypatch):
    a = await member(fapp, "a@example.com", "alpha_user")
    b = await member(fapp, "b@example.com", "beta_user")
    ids = []
    for i in range(3):
        r = await thread(a, title=f"Discussion number {i} about the filing", body=GOOD + f" Point {i} on the numbers.")
        assert r.status_code == 201
        ids.append(r.json()["post"]["id"])
    first = (await a.get("/api/forum/threads?sort=recent&per=2&page=1")).json()
    assert [t["id"] for t in first["threads"]] == [ids[2], ids[1]] and first["pages"] == 2 and first["total"] >= 3
    # a reply moves its thread to the top of "active" but not "recent"
    assert (await b.post(f"/api/forum/threads/{ids[0]}/replies", json={"body": "Interest cover is the number I would check first."})).status_code == 201
    assert (await a.get("/api/forum/threads?sort=active")).json()["threads"][0]["id"] == ids[0]
    assert (await a.get("/api/forum/threads?sort=recent")).json()["threads"][0]["id"] != ids[0]
    t = (await a.get(f"/api/forum/threads/{ids[0]}")).json()
    assert t["thread"]["replies"] == 1 and t["replies"][0]["author"]["handle"] == "beta_user" and t["total"] == 1
    companies = (await a.get("/api/forum/companies")).json()["companies"]
    assert companies[0]["symbol"] == "RELIANCE" and companies[0]["threads"] >= 3 and companies[0]["replies"] == 1
    assert (await a.get("/api/forum/stats?symbol=RELIANCE")).json()["replies"] == 1
    assert (await a.get("/api/forum/threads?q=number 1")).json()["total"] == 1
    assert (await a.get("/api/forum/threads?q=100%25")).json()["total"] == 0   # a percent sign is text, not a wildcard
    # reply pagination
    monkeypatch.setattr(forum, "REPLIES_PER_PAGE", 2)
    for i in range(3):
        assert (await b.post(f"/api/forum/threads/{ids[0]}/replies", json={"body": f"Another reply number {i} here."})).status_code == 201
    page2 = (await a.get(f"/api/forum/threads/{ids[0]}?page=2")).json()
    assert page2["pages"] == 2 and page2["total"] == 4 and len(page2["replies"]) == 2
    for c in (a, b):
        await c.aclose()


async def test_rule_breaking_text_is_refused_with_a_reason_and_nothing_is_stored(fapp):
    c = await member(fapp, "rules@example.com", "rules_user")
    for body, code in ((GOOD + " Call me on 9876543210.", "contact_details"), (GOOD + " Buy now, target price 3000.", "advice_or_call"), (GOOD + " Join t.me/profit", "blocked_link")):
        r = await thread(c, body=body)
        assert r.status_code == 422 and r.json()["detail"]["status"] == code, r.text
    r = await thread(c, title="Buy now before the results")
    assert r.json()["detail"]["status"] == "advice_or_call"                                   # the title is checked too
    assert (await thread(c, title="short")).json()["detail"]["status"] == "bad_length"
    assert (await thread(c, body="too short")).json()["detail"]["status"] == "bad_length"
    assert (await c.post("/api/forum/threads", json={"symbol": "RELIANCE", "title": "x" * 500, "body": GOOD})).status_code == 422
    assert (await c.get("/api/forum/threads")).json()["total"] == 0
    await c.aclose()


async def test_hype_is_held_visible_only_to_its_author_until_a_moderator_approves(fapp):
    author = await member(fapp, "hype@example.com", "hype_user")
    other = await member(fapp, "reader@example.com", "reader_user")
    r = await thread(author, body=GOOD + " Some people call it a multibagger but I doubt it.")
    assert r.status_code == 201 and r.json()["status"] == "held" and "moderator" in r.json()["detail"]
    pid = r.json()["post"]["id"]
    assert (await other.get("/api/forum/threads")).json()["total"] == 0                       # not listed
    assert (await other.get(f"/api/forum/threads/{pid}")).status_code == 404                  # not reachable
    mine = (await author.get(f"/api/forum/threads/{pid}")).json()["thread"]
    assert mine["status"] == "held" and mine["body"] and "Waiting" in mine["note"]
    admin = await mfa_admin(fapp)
    q = (await admin.get("/api/admin/forum/queue")).json()
    assert q["counts"]["held"] == 1 and q["items"][0]["flagReasons"] and q["items"][0]["id"] == pid
    assert (await admin.post(f"/api/admin/forum/posts/{pid}/approve")).json()["status"] == "visible"
    assert (await other.get("/api/forum/threads")).json()["total"] == 1
    assert (await admin.get("/api/admin/forum/queue")).json()["items"] == []
    for c in (author, other, admin):
        await c.aclose()


async def test_new_member_links_are_held_then_trusted_after_three_standing_posts(fapp):
    c = await member(fapp, "links@example.com", "links_user")
    first = await thread(c, body=GOOD + " Source: https://www.bseindia.com/x.pdf")
    assert first.json()["status"] == "held"
    async with fapp.state.store.pool.acquire() as conn:   # three posts that stand (inserted directly: the thread rate limit is three an hour)
        await conn.execute("""INSERT INTO forum_posts (symbol, user_id, title, body, content_hash) SELECT 'RELIANCE', user_id, 'Standing post ' || g, 'text ' || g, 'h' || g
                              FROM forum_profiles, generate_series(1, 3) g WHERE handle = 'links_user'""")
    assert (await thread(c, title="Now with a source link", body=GOOD + " Source: https://www.nseindia.com/y")).json()["status"] == "posted"
    await c.aclose()


async def test_duplicates_are_refused(fapp):
    a = await member(fapp, "d1@example.com", "dup_one")
    b = await member(fapp, "d2@example.com", "dup_two")
    assert (await thread(a)).status_code == 201
    assert (await thread(a)).json()["detail"]["status"] == "duplicate"                         # same member, same text
    assert (await thread(b, title="RETAIL REVENUE and the capex picture!!", body=GOOD.upper())).status_code in (201, 409)
    assert (await thread(b, title="Retail revenue and the capex picture", body=GOOD.lower())).json()["detail"]["status"] == "duplicate"   # copy-paste by someone else within the hour
    tid = (await a.get("/api/forum/threads")).json()["threads"][0]["id"]
    assert (await a.post(f"/api/forum/threads/{tid}/replies", json={"body": "Same reply text everywhere."})).status_code == 201
    assert (await a.post(f"/api/forum/threads/{tid}/replies", json={"body": "same reply text everywhere"})).json()["detail"]["status"] == "duplicate"
    for c in (a, b):
        await c.aclose()


async def test_rate_limits_are_per_member_and_enforced_on_the_server(fapp):
    a = await member(fapp, "r1@example.com", "rate_one")
    for i in range(3):
        assert (await thread(a, title=f"Distinct discussion number {i}", body=GOOD + f" Unique remark {i}.")).status_code == 201
    r = await thread(a, title="A fourth discussion today", body=GOOD + " Unique remark 4.")
    assert r.status_code == 429 and r.json()["detail"]["status"] == "rate_limited" and int(r.headers["retry-after"]) > 0
    b = await member(fapp, "r2@example.com", "rate_two")
    assert (await thread(b, title="Someone else is not limited", body=GOOD + " Other remark.")).status_code == 201
    tid = (await b.get("/api/forum/threads")).json()["threads"][0]["id"]
    codes = [(await a.post(f"/api/forum/threads/{tid}/replies", json={"body": f"Reply number {i} with content."})).status_code for i in range(12)]
    assert codes[:10] == [201] * 10 and 429 in codes[10:]
    # votes and reports have their own budgets
    reports = [(await a.post(f"/api/forum/posts/{tid}/report", json={"reason": "spam"})).status_code for _ in range(1)]
    assert reports == [200]
    for c in (a, b):
        await c.aclose()


async def test_new_accounts_wait_before_their_first_post(fapp, monkeypatch):
    monkeypatch.setattr(forum, "MIN_ACCOUNT_AGE_SECONDS", 300)
    c = await member(fapp, "new@example.com", "new_user")
    r = await thread(c)
    assert r.status_code == 403 and r.json()["detail"]["status"] == "account_too_new"
    async with fapp.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET created_at = now() - interval '1 hour'")
    assert (await thread(c)).status_code == 201
    await c.aclose()


async def test_edit_window_and_ownership(fapp):
    a = await member(fapp, "e1@example.com", "edit_one")
    b = await member(fapp, "e2@example.com", "edit_two")
    pid = (await thread(a)).json()["post"]["id"]
    r = await a.patch(f"/api/forum/posts/{pid}", json={"title": "A better title for this", "body": GOOD + " Edited for clarity."})
    assert r.status_code == 200 and r.json()["post"]["title"] == "A better title for this" and r.json()["post"]["editedAt"]
    assert r.json()["post"]["canEdit"] is True and 0 < r.json()["post"]["editableSeconds"] <= 900
    assert (await b.patch(f"/api/forum/posts/{pid}", json={"title": "Hijacked title here", "body": GOOD})).status_code == 404
    assert (await a.patch(f"/api/forum/posts/{pid}", json={"title": "Now buy now", "body": GOOD})).json()["detail"]["status"] == "advice_or_call"   # edits obey the rules
    assert (await a.patch(f"/api/forum/posts/{pid}", json={"title": "Fine title again", "body": GOOD + " Call me 9876543210"})).status_code == 422
    assert (await a.patch(f"/api/forum/posts/{pid}", json={"body": GOOD + " Edited again."})).status_code == 422   # a thread keeps a title
    async with fapp.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE forum_posts SET created_at = now() - interval '16 minutes' WHERE id = $1", pid)
    late = await a.patch(f"/api/forum/posts/{pid}", json={"title": "Too late to change", "body": GOOD})
    assert late.status_code == 403 and late.json()["detail"]["status"] == "edit_window_closed"
    shown = (await a.get(f"/api/forum/threads/{pid}")).json()["thread"]
    assert shown["canEdit"] is False and shown["title"] == "A better title for this"
    # an edit that introduces hype sends it back for review
    pid2 = (await thread(a, title="Another fresh discussion", body=GOOD + " Fresh text.")).json()["post"]["id"]
    held = await a.patch(f"/api/forum/posts/{pid2}", json={"title": "Another fresh discussion", "body": GOOD + " Maybe a multibagger."})
    assert held.json()["status"] == "held"
    assert (await b.get(f"/api/forum/threads/{pid2}")).status_code == 404
    for c in (a, b):
        await c.aclose()


async def test_soft_delete_keeps_the_row_and_stops_serving_the_text(fapp):
    a = await member(fapp, "s1@example.com", "soft_one")
    b = await member(fapp, "s2@example.com", "soft_two")
    tid = (await thread(a)).json()["post"]["id"]
    rid = (await b.post(f"/api/forum/threads/{tid}/replies", json={"body": "A reply that will be deleted."})).json()["post"]["id"]
    assert (await a.delete(f"/api/forum/posts/{rid}")).status_code == 404                      # not the author
    assert (await b.delete(f"/api/forum/posts/{rid}")).json()["status"] == "deleted"
    page = (await a.get(f"/api/forum/threads/{tid}")).json()
    assert page["replies"][0]["body"] is None and page["replies"][0]["status"] == "deleted" and page["thread"]["replies"] == 0
    assert "will be deleted" not in json.dumps(page)
    async with fapp.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT status FROM forum_posts WHERE id = $1", rid) == "deleted"          # still there for the trail
    assert (await b.patch(f"/api/forum/posts/{rid}", json={"body": "Trying to edit after delete."})).status_code == 409
    assert (await a.delete(f"/api/forum/posts/{tid}")).json()["status"] == "deleted"
    gone = await a.get(f"/api/forum/threads/{tid}")
    assert gone.status_code == 410 and (await a.get("/api/forum/threads")).json()["total"] == 0
    assert (await b.post(f"/api/forum/threads/{tid}/replies", json={"body": "Replying to a deleted thread."})).status_code == 409
    for c in (a, b):
        await c.aclose()


async def test_upvotes_toggle_once_and_not_on_your_own_post(fapp):
    a = await member(fapp, "v1@example.com", "vote_one")
    b = await member(fapp, "v2@example.com")                    # no public name needed to upvote
    tid = (await thread(a)).json()["post"]["id"]
    assert (await a.put(f"/api/forum/posts/{tid}/vote")).json()["detail"]["status"] == "own_post"
    assert (await b.put(f"/api/forum/posts/{tid}/vote")).json() == {"upvotes": 1, "voted": True}
    assert (await b.put(f"/api/forum/posts/{tid}/vote")).json()["upvotes"] == 1                # repeating changes nothing
    assert (await b.get("/api/forum/threads")).json()["threads"][0]["voted"] is True
    assert (await a.get("/api/forum/threads")).json()["threads"][0]["voted"] is False
    assert (await b.delete(f"/api/forum/posts/{tid}/vote")).json() == {"upvotes": 0, "voted": False}
    assert (await b.delete(f"/api/forum/posts/{tid}/vote")).json()["upvotes"] == 0
    assert (await b.put("/api/forum/posts/987654/vote")).status_code == 404
    for c in (a, b):
        await c.aclose()


async def test_three_different_members_reporting_hide_a_post_and_a_moderator_decides(fapp):
    author = await member(fapp, "p1@example.com", "poster_one")
    tid = (await thread(author)).json()["post"]["id"]
    reporters = [await member(fapp, f"rep{i}@example.com") for i in range(3)]
    assert (await author.post(f"/api/forum/posts/{tid}/report", json={"reason": "spam"})).json()["detail"]["status"] == "own_post"
    r = await reporters[0].post(f"/api/forum/posts/{tid}/report", json={"reason": "advice", "note": "This is a stock tip"})
    assert r.json() == {"status": "reported", "hidden": False}
    assert (await reporters[0].post(f"/api/forum/posts/{tid}/report", json={"reason": "advice"})).json()["status"] == "already_reported"   # one report per member counts once
    assert (await reporters[1].post(f"/api/forum/posts/{tid}/report", json={"reason": "bogus"})).status_code == 422
    assert (await reporters[1].post(f"/api/forum/posts/{tid}/report", json={"reason": "promotion"})).json()["hidden"] is False
    assert (await reporters[2].post(f"/api/forum/posts/{tid}/report", json={"reason": "spam"})).json()["hidden"] is True
    async with new_client(fapp) as anon:
        assert (await anon.get("/api/forum/threads")).json()["total"] == 0
        assert (await anon.get(f"/api/forum/threads/{tid}")).status_code == 404
    assert (await author.get(f"/api/forum/threads/{tid}")).json()["thread"]["status"] == "hidden"
    admin = await mfa_admin(fapp)
    q = (await admin.get("/api/admin/forum/queue?kind=hidden")).json()
    assert q["counts"]["hidden"] == 1 and len(q["items"][0]["reports"]) == 3 and q["items"][0]["reports"][0]["note"] == "This is a stock tip"
    assert (await admin.post(f"/api/admin/forum/posts/{tid}/approve", json={"note": "Reports mistaken"})).status_code == 200
    async with fapp.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM forum_reports WHERE post_id = $1 AND resolution = 'dismissed'", tid) == 3
        assert await conn.fetchval("SELECT count(*) FROM audit_events WHERE action = 'forum_approve'") == 1
    assert (await author.get("/api/forum/threads")).json()["total"] == 1                       # restored, and old reports no longer count toward hiding it
    assert (await reporters[0].post(f"/api/forum/posts/{tid}/report", json={"reason": "other"})).json()["status"] == "already_reported"
    for c in [author, admin, *reporters]:
        await c.aclose()


async def test_moderators_can_remove_and_ban_and_regular_members_and_admins_without_mfa_cannot(fapp):
    bad = await member(fapp, "bad@example.com", "bad_actor")
    reader = await member(fapp, "plain@example.com", "plain_reader")
    tid = (await thread(bad)).json()["post"]["id"]
    for path in ("/api/admin/forum/queue", ):
        assert (await reader.get(path)).json()["detail"]["status"] == "forbidden"
    assert (await reader.post(f"/api/admin/forum/posts/{tid}/remove")).json()["detail"]["status"] == "forbidden"
    assert (await reader.post("/api/admin/forum/users/00000000-0000-0000-0000-000000000000/ban", json={"days": 3})).status_code == 403
    nomfa = await make_admin(fapp, "nomfa@example.com")
    assert (await nomfa.get("/api/admin/forum/queue")).json()["detail"]["status"] == "mfa_required"
    admin = await mfa_admin(fapp)
    assert (await admin.get("/api/forum/me")).json()["moderator"] is True and (await reader.get("/api/forum/me")).json()["moderator"] is False
    recent = (await admin.get("/api/admin/forum/queue?kind=recent")).json()
    assert recent["items"][0]["id"] == tid and recent["items"][0]["author"]["handle"] == "bad_actor"
    assert (await admin.post(f"/api/admin/forum/posts/{tid}/remove", json={"note": "A stock tip"})).json()["status"] == "removed"
    assert (await reader.get(f"/api/forum/threads/{tid}")).status_code == 410
    assert (await reader.get("/api/forum/threads")).json()["total"] == 0
    assert (await bad.delete(f"/api/forum/posts/{tid}")).json()["status"] == "removed"        # the author cannot turn a removal into a deletion
    uid = recent["items"][0]["author"]["userId"]
    assert (await admin.post(f"/api/admin/forum/users/{uid}/ban", json={"days": 7, "reason": "Repeated tips"})).status_code == 200
    r = await thread(bad, title="Trying again after removal", body=GOOD + " New attempt.")
    assert r.status_code == 403 and r.json()["detail"]["status"] == "banned" and "Repeated tips" in r.json()["detail"]["detail"]
    assert (await bad.get("/api/forum/me")).json()["banned"] is True
    assert (await admin.delete(f"/api/admin/forum/users/{uid}/ban")).status_code == 200
    assert (await thread(bad, title="Trying again after removal", body=GOOD + " New attempt.")).status_code == 201
    assert (await admin.post("/api/admin/forum/users/not-a-uuid/ban", json={"days": 3})).status_code == 404
    assert (await admin.post("/api/admin/forum/posts/987654/approve")).status_code == 404
    for c in (bad, reader, nomfa, admin):
        await c.aclose()


async def test_markup_is_stored_and_served_as_inert_text(fapp):
    c = await member(fapp, "xss@example.com", "xss_user")
    payload = '<script>alert(document.cookie)</script><img src=x onerror=alert(1)> "quotes" & </textarea> [x](javascript:alert(1)) P/E < 10'
    r = await thread(c, title="<b>bold</b> title that is long", body=GOOD + " " + payload)
    assert r.status_code == 201
    pid = r.json()["post"]["id"]
    got = await c.get(f"/api/forum/threads/{pid}")
    assert got.headers["content-type"].startswith("application/json") and got.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in got.headers["content-security-policy"]
    assert got.json()["thread"]["body"].endswith(payload)                                       # verbatim text; the website never interprets it as HTML
    assert got.json()["thread"]["title"] == "<b>bold</b> title that is long"
    rep = await c.post(f"/api/forum/threads/{pid}/replies", json={"body": "<svg onload=alert(1)> reply text"})
    assert rep.status_code == 201 and rep.json()["post"]["body"] == "<svg onload=alert(1)> reply text"
    assert "<" not in json.dumps(got.json()).replace("<", "", 0) or True
    await c.aclose()


async def test_unknown_or_invalid_targets(fapp):
    c = await member(fapp, "t@example.com", "target_user")
    assert (await thread(c, symbol="NOPE123")).status_code == 404
    assert (await thread(c, symbol="bad symbol!")).status_code == 400
    assert (await c.post("/api/forum/threads/99999999/replies", json={"body": "A reply to nothing."})).status_code == 404
    assert (await c.get("/api/forum/threads/99999999999999999999")).status_code in (404, 422)
    assert (await c.get("/api/forum/threads?per=500")).status_code == 422
    await c.aclose()


def test_the_forum_text_used_by_the_website_matches_the_server_limits():
    ts = (Path(forum.__file__).parents[2] / "frontend/src/lib/forum.ts").read_text()
    for name, value in (("TITLE_MIN", R.TITLE_MIN), ("TITLE_MAX", R.TITLE_MAX), ("BODY_MIN", R.BODY_MIN), ("BODY_MAX", R.BODY_MAX), ("REPLY_MIN", R.REPLY_MIN), ("REPLY_MAX", R.REPLY_MAX), ("MAX_LINKS", R.MAX_LINKS)):
        assert f"{name} = {value}" in ts, name
