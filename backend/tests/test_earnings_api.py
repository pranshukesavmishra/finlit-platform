"""The earnings-call API: the list is open, the answers are Gold (server-enforced), five different calls a member a month, the member is stored as a hash."""
import pytest

from finlit.earnings import service as S
from finlit.earnings.questions import QUESTIONS
from test_auth import ORIGIN, anon, app, login, new_client, signed_in, signup  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration

SENTENCE = "Management expects margins of 20 to 22 percent for the rest of the year."
QUOTE = "We expect margins to stay in a range of 20 to 22 percent for the rest of the year"


async def seed_calls(st, n=7, answered=True):
    """ACME with n calls (Q1..Q4 of FY27, then FY26), each with one validated answer and one 'not covered'; a call with no answers; another company."""
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE earnings_calls RESTART IDENTITY CASCADE")
        await conn.execute("INSERT INTO companies (symbol, name) VALUES ('ACME', 'Acme Industries Limited') ON CONFLICT DO NOTHING")
        periods = [(2027, 2), (2027, 1), (2026, 4), (2026, 3), (2026, 2), (2026, 1), (2025, 4)][:n]
        for fy, q in periods:
            cid = await conn.fetchval("INSERT INTO earnings_calls (symbol, fiscal_year, quarter, call_date, filed_at, transcript_url, status, pages, text_chars) "
                                      "VALUES ('ACME', $1, $2, '2026-10-20', '2026-10-23 12:00+05:30', 'https://nsearchives.nseindia.com/corporate/a.pdf', 'answered', 3, 5000) RETURNING id", fy, q)
            if answered:
                await conn.execute("INSERT INTO earnings_call_answers (call_id, question_id, answer, model, prompt_version, last_version, validated) VALUES ($1,'guidance-outlook',$2::jsonb,'fake','v1','v1',true)",
                                   cid, '{"covered": true, "sentences": [{"text": "%s", "quote": "%s", "quote_ref": "page 2", "source": "current"}]}' % (SENTENCE, QUOTE))
                await conn.execute("INSERT INTO earnings_call_answers (call_id, question_id, answer, model, prompt_version, last_version, validated) VALUES ($1,'risks-raised','{\"covered\": false, \"sentences\": []}','fake','v1','v1',true)", cid)
                await conn.execute("INSERT INTO earnings_call_answers (call_id, question_id, answer, model, prompt_version, last_version, validated, reject_reason) VALUES ($1,'margins-costs','{\"covered\": true, \"sentences\": [{\"text\": \"REJECTED TEXT\", \"quote\": \"x\", \"quote_ref\": \"p\", \"source\": \"current\"}]}','fake','v1','v1',false,'x')", cid)
        await conn.execute("INSERT INTO earnings_calls (symbol, fiscal_year, quarter, status) VALUES ('ACME', 2028, 1, 'text_ok')")      # text read, no answers yet: not offered


async def admin_client(app, email="root@example.com"):
    c = new_client(app)
    await signup(app, c, email)
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET role = 'admin', plan = 'gold' WHERE lower(email) = $1", email)
    r = await login(c, email)
    assert r.status_code == 200, r.text
    c.headers.update({**ORIGIN, "X-CSRF-Token": r.json()["csrf"]})
    return c


async def test_the_list_is_open_but_carries_no_answer_and_the_detail_needs_gold(app, anon):  # noqa: F811
    await seed_calls(app.state.store)
    r = await anon.get("/api/earnings-calls/acme")
    b = r.json()
    assert r.status_code == 200 and b["locked"] is True and b["usage"] is None and b["symbol"] == "ACME" and b["name"] == "Acme Industries Limited"
    assert [c["label"] for c in b["calls"]][:2] == ["Q2 FY27", "Q1 FY27"] and len(b["calls"]) == 7                       # the call with no answers is not offered
    assert b["calls"][0] == {"fiscalYear": 2027, "quarter": 2, "label": "Q2 FY27", "callDate": "2026-10-20", "filedAt": "2026-10-23",
                             "transcriptUrl": "https://nsearchives.nseindia.com/corporate/a.pdf", "pages": 3}
    assert [q["id"] for q in b["questions"]] == [q.id for q in QUESTIONS] and b["questions"][0]["label"] == "Strategy & moat"
    assert b["disclaimer"] == "Information only, not investment advice." and b["note"] == "AI-summarised from the transcript. Check the quotes."
    assert SENTENCE not in r.text and QUOTE not in r.text and "sentences" not in r.text
    d = await anon.get("/api/earnings-calls/ACME/2027/2")
    assert d.status_code == 403 and d.json()["detail"]["status"] == "plan_required" and d.json()["detail"]["plan"] == "gold" and SENTENCE not in d.text
    for plan in ("basic", "silver"):
        c = await signed_in(app, f"{plan}@example.com", plan=plan)
        assert (await c.get("/api/earnings-calls/ACME/2027/2")).status_code == 403
        assert (await c.get("/api/earnings-calls/ACME")).json()["locked"] is True
        await c.aclose()


async def test_gold_gets_the_checked_answers_with_quotes_and_never_a_rejected_one(app):  # noqa: F811
    await seed_calls(app.state.store)
    gold = await signed_in(app, "g@example.com", plan="gold")
    r = await gold.get("/api/earnings-calls/ACME/2027/2")
    b = r.json()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and "Cookie" in r.headers["vary"]
    assert b["label"] == "Q2 FY27" and b["name"] == "Acme Industries Limited" and b["pages"] == 3 and b["summarisedByAi"] is True and b["notCovered"] == "The call did not cover this."
    by = {q["id"]: q for q in b["questions"]}
    assert len(by) == 10 and by["guidance-outlook"]["ready"] and by["guidance-outlook"]["sentences"] == [{"text": SENTENCE, "quote": QUOTE, "quoteRef": "page 2"}]
    assert by["risks-raised"]["ready"] and by["risks-raised"]["covered"] is False and by["risks-raised"]["sentences"] == []
    assert by["margins-costs"]["ready"] is False and "REJECTED TEXT" not in r.text and by["strategy-moat"]["ready"] is False
    assert (await gold.get("/api/earnings-calls/ACME/2027/3")).status_code == 404 and (await gold.get("/api/earnings-calls/ACME/2028/1")).status_code == 404
    assert (await gold.get("/api/earnings-calls/NOPE/2027/2")).status_code == 404 and (await gold.get("/api/earnings-calls/ACME/1999/9")).status_code == 404
    await gold.aclose()


async def test_five_different_calls_a_month_and_reopening_one_is_free(app):  # noqa: F811
    await seed_calls(app.state.store)
    gold = await signed_in(app, "g@example.com", plan="gold")
    assert (await gold.get("/api/earnings-calls/ACME")).json()["usage"] == {"used": 0, "limit": 5}
    periods = [(2027, 2), (2027, 1), (2026, 4), (2026, 3), (2026, 2)]
    for i, (fy, q) in enumerate(periods, 1):
        r = await gold.get(f"/api/earnings-calls/ACME/{fy}/{q}")
        assert r.status_code == 200 and r.json()["usage"] == {"used": i, "limit": 5}
    again = await gold.get("/api/earnings-calls/ACME/2027/2")                     # already counted: free
    assert again.status_code == 200 and again.json()["usage"] == {"used": 5, "limit": 5}
    sixth = await gold.get("/api/earnings-calls/ACME/2026/1")
    assert sixth.status_code == 403 and sixth.json()["detail"] == {"status": "limit_reached", "detail": sixth.json()["detail"]["detail"], "used": 5, "limit": 5, "plan": "gold"}
    assert SENTENCE not in sixth.text
    assert (await gold.get("/api/earnings-calls/ACME")).json()["usage"] == {"used": 5, "limit": 5}
    assert (await gold.get("/api/earnings-calls/ACME/2026/2")).status_code == 200                # an opened call stays open
    other = await signed_in(app, "h@example.com", plan="gold")                       # the count is per member
    assert (await other.get("/api/earnings-calls/ACME/2026/1")).status_code == 200
    await gold.aclose()
    await other.aclose()


async def test_the_allowance_starts_again_next_month(app, monkeypatch):  # noqa: F811
    await seed_calls(app.state.store)
    gold = await signed_in(app, "g@example.com", plan="gold")
    for fy, q in [(2027, 2), (2027, 1), (2026, 4), (2026, 3), (2026, 2)]:
        assert (await gold.get(f"/api/earnings-calls/ACME/{fy}/{q}")).status_code == 200
    assert (await gold.get("/api/earnings-calls/ACME/2026/1")).status_code == 403
    monkeypatch.setattr(S, "month_key", lambda now=None: "2099-01")
    assert (await gold.get("/api/earnings-calls/ACME/2026/1")).json()["usage"] == {"used": 1, "limit": 5}
    await gold.aclose()


async def test_an_administrator_sees_everything_and_is_not_counted(app):  # noqa: F811
    await seed_calls(app.state.store)
    admin = await admin_client(app)
    for fy, q in [(2027, 2), (2027, 1), (2026, 4), (2026, 3), (2026, 2), (2026, 1), (2025, 4)]:
        assert (await admin.get(f"/api/earnings-calls/ACME/{fy}/{q}")).status_code == 200
    assert (await admin.get("/api/earnings-calls/ACME")).json()["usage"] == {"used": 0, "limit": None}
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM earnings_call_usage") == 0
    await admin.aclose()


async def test_the_member_is_stored_as_a_keyed_hash_never_as_an_id_or_an_email(app):  # noqa: F811
    await seed_calls(app.state.store)
    gold = await signed_in(app, "private.person@example.com", plan="gold")
    uid = (await gold.get("/api/auth/me")).json()["user"]["id"]
    assert (await gold.get("/api/earnings-calls/ACME/2027/2")).status_code == 200
    async with app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM earnings_call_usage")
        dump = " ".join(str(v) for r in rows for v in r.values())
    assert len(rows) == 1 and uid not in dump and "private.person" not in dump and len(rows[0]["user_hash"]) == 32
    secret = app.state.settings.secret_key
    assert rows[0]["user_hash"] == S.user_hash(secret, uid) and S.user_hash("another-secret", uid) != rows[0]["user_hash"]
    assert rows[0]["month"] == S.month_key()
    await gold.aclose()


async def test_nothing_is_offered_before_the_first_summary_exists(app, anon):  # noqa: F811
    await seed_calls(app.state.store, answered=False)
    b = (await anon.get("/api/earnings-calls/ACME")).json()
    assert b["available"] is False and b["calls"] == [] and len(b["questions"]) == 10
    assert (await anon.get("/api/earnings-calls/UNKNOWN")).json()["available"] is False
