"""Company brief routes: the public endpoint serves ONLY a published brief that still passes the gates and otherwise a reasoned empty state; the admin actions."""
import json
import time
from pathlib import Path

import pytest

from finlit.company_brief import core as B
from test_auth import anon, app, make_admin, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration
RELIANCE = json.loads((Path(__file__).parent / "fixtures" / "company_brief" / "reliance_brief.json").read_text(encoding="utf-8"))   # a prototype: fixtures only


def checks_ok(brief):
    n = len(B.citations(brief))
    return {"ok": True, "date": "2026-11-04", "citations": n, "passed": n, "failed": [], "unchecked": [], "method": "m"}


async def admin(app):
    from finlit.auth import crypto
    a = await make_admin(app, "brief-boss@example.com")
    secret = (await a.post("/api/me/mfa/setup")).json()["secret"]
    assert (await a.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    return a


async def put(st, symbol="RELIANCE", status="draft", brief=None, publish=False, **kw):
    brief = brief or RELIANCE
    async with st.pool.acquire() as conn:
        await conn.execute("INSERT INTO companies (symbol, name) VALUES ($1, 'Reliance Industries Ltd') ON CONFLICT DO NOTHING", symbol)
        await conn.execute("DELETE FROM company_briefs WHERE symbol = $1", symbol)
        await conn.execute("INSERT INTO company_briefs (symbol, status, brief, as_of, checks, parts_written, published, published_checks, published_at, reviewed_at) "
                           "VALUES ($1, $2, $3::jsonb, '2026-11-04', $4::jsonb, '{about}', $5::jsonb, $6::jsonb, $7, $7)", symbol, status, json.dumps(brief), json.dumps(kw.get("checks") or checks_ok(brief)),
                           json.dumps(brief) if publish else None, json.dumps(kw["pchecks"] if "pchecks" in kw else checks_ok(brief)) if publish else None, __import__("datetime").datetime.now(__import__("datetime").timezone.utc) if publish else None)


async def test_a_draft_is_never_public_and_the_empty_state_says_why(app, anon):  # noqa: F811
    st = app.state.store
    async with st.pool.acquire() as conn:
        await conn.execute("INSERT INTO companies (symbol, name) VALUES ('RELIANCE', 'Reliance Industries Ltd') ON CONFLICT DO NOTHING")
        await conn.execute("DELETE FROM company_briefs"); await conn.execute("DELETE FROM company_brief_sources")
    b = (await anon.get("/api/stocks/RELIANCE/brief")).json()
    assert b["state"] == "empty" and b["code"] == "not_written" and "Not written yet" in b["reason"] and "brief" not in b
    async with st.pool.acquire() as conn:
        await conn.execute("INSERT INTO company_brief_sources (symbol, last_state) VALUES ('RELIANCE', 'no_annual_report')")
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["code"] == "no_annual_report"
    await put(st, status="draft")
    r = await anon.get("/api/stocks/RELIANCE/brief")
    assert r.json()["code"] == "in_review" and "Jio" not in r.text and r.headers["cache-control"] == "public, max-age=60"
    await put(st, status="rejected")
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["code"] == "held_back"


async def test_a_published_brief_is_served_with_its_checks_and_the_standard_lines(app, anon):  # noqa: F811
    st = app.state.store
    await put(st, status="published", publish=True)
    r = await anon.get("/api/stocks/reliance/brief")
    b = r.json()
    assert r.status_code == 200 and b["state"] == "published" and b["brief"]["status"] == "reviewed" and b["asOf"] == "2026-11-04"
    assert b["checks"]["citations"] == 65 and b["checks"]["passed"] == 65 and b["chips"]["MR"] == "PR" and b["chips"]["AR"] == "AR"
    assert b["disclaimer"] == RELIANCE["disclaimer"] and "not a recommendation" in b["compliance"] and "max-age=300" in r.headers["cache-control"]
    assert b["waiting"] is False and "failed" not in json.dumps(b["checks"])


async def test_a_published_copy_that_stops_passing_the_gates_disappears(app, anon):  # noqa: F811
    st = app.state.store
    bad = json.loads(json.dumps(RELIANCE))
    bad["about"][0]["text"] = "A strong buy for long-term investors."
    await put(st, status="published", publish=True, brief=bad)
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["code"] == "failed_checks"
    await put(st, status="published", publish=True, pchecks={"ok": False, "citations": 65, "failed": [{"path": "x"}]})
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["state"] == "empty"
    await put(st, status="published", publish=True, pchecks={})
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["state"] == "empty"


async def test_a_new_draft_waits_while_the_published_copy_stays_up(app, anon):  # noqa: F811
    st = app.state.store
    await put(st, status="published", publish=True)
    async with st.pool.acquire() as conn:
        await conn.execute("UPDATE company_briefs SET status = 'draft', written_at = now() + interval '1 hour'")
    b = (await anon.get("/api/stocks/RELIANCE/brief")).json()
    assert b["state"] == "published" and b["waiting"] is True


async def test_admin_routes_need_an_administrator_with_mfa(app, anon):  # noqa: F811
    st = app.state.store
    await put(st)
    for method, path in (("get", "/api/admin/company-brief/drafts"), ("get", "/api/admin/company-brief/RELIANCE"), ("post", "/api/admin/company-brief/RELIANCE/approve"), ("put", "/api/admin/company-brief/RELIANCE/source")):
        assert getattr(anon, method)is not None
        assert (await getattr(anon, method)(path)).status_code in (401, 403, 422), path
    user = await signed_in(app, "member@example.com")
    assert (await user.get("/api/admin/company-brief/drafts")).status_code == 403
    assert (await user.post("/api/admin/company-brief/RELIANCE/approve")).status_code == 403


async def test_review_flow_approve_publish_reject_unpublish_rewrite_and_what_changed(app, anon):  # noqa: F811
    st = app.state.store
    a = await admin(app)
    await put(st)
    lst = (await a.get("/api/admin/company-brief/drafts")).json()
    row = lst["briefs"][0]
    assert row["symbol"] == "RELIANCE" and row["status"] == "draft" and row["canPublish"] and row["citations"] == 65 and len(row["flags"]) == 0 and lst["counts"]["draft"] == 1
    one = (await a.get("/api/admin/company-brief/RELIANCE")).json()
    assert one["brief"]["symbol"] == "RELIANCE" and "Sources" in one["text"] and one["checks"]["passed"] == 65
    assert (await a.post("/api/admin/company-brief/RELIANCE/reviewed", json={"note": "read"})).status_code == 200
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["code"] == "in_review"
    assert (await a.post("/api/admin/company-brief/RELIANCE/approve", json={"note": "ok"})).status_code == 200
    pub = (await anon.get("/api/stocks/RELIANCE/brief")).json()
    assert pub["state"] == "published" and pub["changes"] is None and pub["reviewedAt"]
    # a rewrite arrives, the second approval says what changed
    async with st.pool.acquire() as conn:
        newer = json.loads(json.dumps(RELIANCE)); newer["as_of"] = "2027-01-20"
        await conn.execute("UPDATE company_briefs SET status = 'draft', brief = $1::jsonb, parts_written = '{key_figures,mix,gaps}' WHERE symbol = 'RELIANCE'", json.dumps(newer))
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["asOf"] == "2026-11-04"
    assert (await a.post("/api/admin/company-brief/RELIANCE/approve")).status_code == 200
    ch = (await anon.get("/api/stocks/RELIANCE/brief")).json()["changes"]
    assert ch == {"since": "2026-11-04", "now": "2027-01-20", "parts": ["key_figures", "mix"]}
    assert (await a.post("/api/admin/company-brief/RELIANCE/rewrite")).status_code == 200
    async with st.pool.acquire() as conn:
        assert await conn.fetchval("SELECT rewrite_asked FROM company_briefs WHERE symbol = 'RELIANCE'") is True
    assert (await a.post("/api/admin/company-brief/RELIANCE/unpublish", json={"note": "wrong"})).status_code == 200
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["state"] == "empty"
    assert (await a.post("/api/admin/company-brief/RELIANCE/reject", json={"note": "no"})).status_code == 200
    assert (await anon.get("/api/stocks/RELIANCE/brief")).json()["code"] == "held_back"
    async with st.pool.acquire() as conn:
        acts = [r["action"] for r in await conn.fetch("SELECT action FROM audit_events WHERE action LIKE 'company_brief.%' ORDER BY id")]
    assert acts == ["company_brief.reviewed", "company_brief.approve", "company_brief.approve", "company_brief.rewrite", "company_brief.unpublish", "company_brief.reject"]
    assert (await a.post("/api/admin/company-brief/NOPE/approve")).status_code == 404


async def test_a_brief_with_failed_citations_or_advice_cannot_be_approved(app):  # noqa: F811
    st = app.state.store
    a = await admin(app)
    await put(st, checks={"ok": False, "citations": 65, "passed": 64, "failed": [{"path": "about[0].cites[0]", "doc": "AR", "page": 3, "missing": ["x"], "found_on": []}]})
    r = await a.post("/api/admin/company-brief/RELIANCE/approve")
    assert r.status_code == 409 and r.json()["detail"]["status"] == "not_publishable"
    bad = json.loads(json.dumps(RELIANCE)); bad["segments"][0]["points"][0]["text"] = "The shares look undervalued."
    await put(st, brief=bad)
    assert (await a.post("/api/admin/company-brief/RELIANCE/approve")).status_code == 409
    async with st.pool.acquire() as conn:
        assert await conn.fetchval("SELECT published FROM company_briefs WHERE symbol = 'RELIANCE'") is None


async def test_the_annual_report_address_is_admin_set_and_checked(app):  # noqa: F811
    st = app.state.store
    a = await admin(app)
    await put(st)
    for bad in ("http://x.com/a.pdf", "https://127.0.0.1/a.pdf", "https://intranet/a"):
        assert (await a.put("/api/admin/company-brief/RELIANCE/source", json={"annual_report_url": bad})).status_code == 422
    assert (await a.put("/api/admin/company-brief/NOPE1/source", json={"annual_report_url": "https://www.ril.com/ar.pdf"})).status_code == 404
    r = await a.put("/api/admin/company-brief/RELIANCE/source", json={"annual_report_url": "https://www.ril.com/ar.pdf"})
    assert r.status_code == 200
    assert (await a.get("/api/admin/company-brief/RELIANCE")).json()["source"]["annual_report_url"] == "https://www.ril.com/ar.pdf"
    miss = (await a.get("/api/admin/company-brief/sources")).json()["missing"]
    assert all(m["symbol"] != "RELIANCE" for m in miss)
