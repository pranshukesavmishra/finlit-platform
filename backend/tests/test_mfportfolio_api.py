"""/api/me/mf-portfolio against real Postgres and Redis: plan gating (the Health Score is Gold and the server decides), per-member ownership, the plan's limit on
funds, add / merge / update / delete, validation, Origin and CSRF checks, rate limits, the import preview (matched / choose / not_found / ignored / invalid /
duplicate, with CAMS-style and messy files) and the import commit (nothing unmatched is stored, existing holdings are skipped or replaced)."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from finlit.mfportfolio import api as mfp
from test_auth import PW, app, make_admin, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401

pytestmark = pytest.mark.integration
URL = "/api/me/mf-portfolio"
BASE = 910000
MIGRATION = Path(mfp.__file__).parent.parent / "migrations" / "078_mf_portfolio.sql"
LARGE = "Equity Scheme - Large Cap Fund"
TODAY = date.today()
NAV_DATE = TODAY - timedelta(days=1)
LONG_AGO = (TODAY - timedelta(days=3 * 365)).isoformat()

# code, name, plan, option, isin, nav, active, category, r1y, r3y, r5y, ter, aum_lakh
SCHEMES = [
    (BASE + 1, "Alpha Bluechip Fund - Direct Plan - Growth", "Direct", "Growth", "INF000A01011", 150.0, True, LARGE, 12.5, 14.1, 15.2, 0.62, 1234500.0),
    (BASE + 2, "Alpha Bluechip Fund - Regular Plan - Growth", "Regular", "Growth", "INF000A01029", 140.0, True, LARGE, 11.5, 13.1, 14.2, 1.62, 1234500.0),
    (BASE + 3, "Beta Flexi Cap Fund - Direct Plan - Growth", "Direct", "Growth", "INF000B01012", 80.5, True, "Equity Scheme - Flexi Cap Fund", None, None, None, None, None),
    (BASE + 4, "Gamma Liquid Fund - Direct Plan - Growth", "Direct", "Growth", "INF000G01011", None, False, "Debt Scheme - Liquid Fund", None, None, None, 0.2, None),
    (BASE + 5, "Delta Small Cap Fund - Direct Plan - Growth", "Direct", "Growth", "INF000D01013", 60.0, True, "Equity Scheme - Small Cap Fund", 20.0, 22.0, 25.0, 0.4, 500000.0),
]


@pytest.fixture(autouse=True)
async def schemes(app):  # noqa: F811
    mfp._index_cache.update(ver=None, index=None)
    async with app.state.store.pool.acquire() as conn:
        # the shared test fixture drops `users` (and with it the foreign keys onto it) but not our tables: make them again from the migration itself
        await conn.execute("DROP TABLE IF EXISTS mf_holding_lots, mf_holdings CASCADE")
        await conn.execute(MIGRATION.read_text())
        await conn.execute("DELETE FROM mf_scores WHERE code >= $1", BASE)
        await conn.execute("DELETE FROM mf_schemes WHERE code >= $1", BASE)
        for c, name, plan, opt, isin, nav, active, cat, r1, r3, r5, ter, aum in SCHEMES:
            await conn.execute(
                "INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, option_label, family, isin, nav, nav_date, active, r1y, r3y, r5y, ter, aum_lakh, metrics_date, has_hist) "
                "VALUES ($1,$2,$3,'Open Ended',$4,$5,$6,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)",
                c, name, name.split()[0] + " Mutual Fund", cat, plan, opt, name.split(" - ")[0], isin, nav, NAV_DATE if nav else None, active, r1, r3, r5, ter, aum, NAV_DATE, True)
        for code, final, label, perf, risk, cost, quality in ((BASE + 1, 83.0, "Strong", 80.0, 85.0, 90.0, 77.0), (BASE + 2, 61.5, "Average", 60.0, 62.0, 40.0, 70.0),
                                                              (BASE + 5, 52.0, "Average", 55.0, 45.0, 60.0, 48.0)):
            await conn.execute(
                "INSERT INTO mf_scores (key, kind, code, plan, grp, mtype, sub, category, run_date, nav_date, final, raw_final, perf, risk, cost, quality, label, status, model) "
                "VALUES ($1,'mf',$2,'Direct','EQ-LARGE','Equity','large-cap',$3,$4,$5,$6,$6,$7,$8,$9,$10,$11,'RATED','v1')",
                f"mf:{code}", code, LARGE, TODAY, NAV_DATE, final, perf, risk, cost, quality, label)
    yield
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_scores WHERE code >= $1", BASE)
        await conn.execute("DELETE FROM mf_schemes WHERE code >= $1", BASE)


async def add(c, code, units="100", **kw):
    return await c.post(URL, json={"code": code, "units": units, **kw})


# ------------------------------------------------------------------------------------------------------------------ plan gating

async def test_visitors_and_basic_are_refused_silver_and_gold_are_not(app):
    assert (await new_client(app).get(URL)).status_code == 401
    basic = await signed_in(app, "b@example.com")
    r = await basic.get(URL)
    assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_required"
    assert (await add(basic, BASE + 1)).status_code == 403
    assert (await (await signed_in(app, "s@example.com", plan="silver")).get(URL)).status_code == 200


async def test_the_score_is_gold_and_the_server_decides(app):
    silver = await signed_in(app, "s@example.com", plan="silver")
    gold = await signed_in(app, "g@example.com", plan="gold")
    for c in (silver, gold):
        assert (await add(c, BASE + 1, "100", invested="12000", boughtOn=LONG_AGO)).status_code == 201
        assert (await add(c, BASE + 2, "10", invested="1000")).status_code == 201
    s = await silver.get(URL)
    assert s.headers["cache-control"] == "private, no-store" and "Cookie" in s.headers["vary"]
    body = s.json()
    assert body["scoreLocked"] is True and body["summary"]["score"] == {"locked": True, "value": None, "label": None, "why": None}
    for h in body["holdings"]:                     # returns and values come, the score does not: locked, with null fields
        assert h["score"] == mfp.LOCKED_SCORE and h["current"] and h["returns"]["r1y"] is not None
    raw = s.text
    for number in ("83.0", "61.5", "85.0", "Strong", "Average"):
        assert number not in raw, f"{number} leaked to a Silver response"
    g = (await gold.get(URL)).json()
    assert g["scoreLocked"] is False
    one = next(h for h in g["holdings"] if h["code"] == BASE + 1)["score"]
    assert one["final"] == 83.0 and one["label"] == "Strong" and one["parts"] == {"performance": 80.0, "risk": 85.0, "cost": 90.0, "quality": 77.0} and one["status"] == "RATED"
    assert g["summary"]["score"]["value"] is not None and g["summary"]["score"]["label"] in ("Strong", "Healthy", "Average")


async def test_admin_sees_everything_and_is_not_limited_like_silver(app):
    admin = await make_admin(app)
    assert (await add(admin, BASE + 1)).status_code == 201
    body = (await admin.get(URL)).json()
    assert body["scoreLocked"] is False and body["limit"] == 500 and body["holdings"][0]["score"]["final"] == 83.0


async def test_a_downgraded_member_keeps_the_holdings_and_loses_the_score(app):
    c = await signed_in(app, "g@example.com", plan="gold")
    await add(c, BASE + 1)
    assert (await c.get(URL)).json()["holdings"][0]["score"]["final"] == 83.0
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan = 'silver' WHERE email = 'g@example.com'")
    await app.state.store.redis.flushdb()
    body = (await c.get(URL)).json()
    assert body["count"] == 1 and body["holdings"][0]["score"]["locked"] is True and body["holdings"][0]["score"]["final"] is None


async def test_a_gold_fund_with_no_score_says_why(app):
    gold = await signed_in(app, "g@example.com", plan="gold")
    await add(gold, BASE + 3)
    sc = (await gold.get(URL)).json()["holdings"][0]["score"]
    assert sc["final"] is None and sc["status"] == "NOT SCORED" and sc["reason"] and not sc["locked"]
    summary = (await gold.get(URL)).json()["summary"]["score"]
    assert summary["value"] is None and "no score" in summary["why"]


# ------------------------------------------------------------------------------------------------------------------ the numbers

async def test_values_use_the_latest_nav_and_show_its_date(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    await add(c, BASE + 1, "100.5", invested="10000", boughtOn=LONG_AGO)
    h = (await c.get(URL)).json()["holdings"][0]
    assert h["name"] == SCHEMES[0][1] and h["amc"] == "Alpha Mutual Fund" and h["plan"] == "Direct" and h["categoryLabel"] == "Large Cap"
    assert h["nav"] == 150.0 and h["navDate"] == NAV_DATE.isoformat() and h["navStale"] is False
    assert h["units"] == 100.5 and h["invested"] == 10000.0 and h["current"] == 15075.0
    assert h["gain"] == 5075.0 and h["gainPct"] == 50.75 and h["gainWhy"] is None
    assert h["xirr"] is not None and 12 < h["xirr"] < 18 and h["xirrKind"] == "cagr"                        # (1.5075)^(1/3.0) - 1 about 14.7 %
    assert h["returns"] == {"r1y": 12.5, "r3y": 14.1, "r5y": 15.2, "asOf": NAV_DATE.isoformat(), "why": None, "partialWhy": None}
    assert h["ter"] == 0.62 and h["aum"] == 12345.0 and h["weight"] == 100.0


async def test_every_blank_has_its_reason(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    await add(c, BASE + 3, "10")                              # no cost, no date, no returns, no expense ratio, no size
    await add(c, BASE + 4, "10", invested="500")              # stopped scheme with no NAV
    body = (await c.get(URL)).json()
    flexi = next(h for h in body["holdings"] if h["code"] == BASE + 3)
    assert flexi["invested"] is None and "not known" in flexi["investedWhy"] and flexi["gain"] is None and flexi["gainWhy"]
    assert flexi["xirr"] is None and "purchase date" in flexi["xirrWhy"]
    assert flexi["returns"]["r1y"] is None and flexi["returns"]["why"] and flexi["terWhy"] and flexi["aumWhy"]
    assert flexi["current"] == 805.0 and flexi["weight"] == 100.0
    liquid = next(h for h in body["holdings"] if h["code"] == BASE + 4)
    assert liquid["current"] is None and liquid["currentWhy"] and liquid["weight"] is None and liquid["weightWhy"] and liquid["gainWhy"]
    s = body["summary"]
    assert s["funds"] == 2 and s["valued"] == 1 and s["withCost"] == 0 and s["invested"] is None and s["gain"] is None and any("could not be valued" in n for n in s["notes"])


async def test_summary_allocation_and_concentration(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    await add(c, BASE + 1, "100", invested="10000", boughtOn=LONG_AGO)       # 15,000
    await add(c, BASE + 2, "50", invested="5000")                           # 7,000
    await add(c, BASE + 5, "100", invested="4000")                          # 6,000
    b = (await c.get(URL)).json()
    s = b["summary"]
    assert s["invested"] == 19000.0 and s["current"] == 28000.0 and s["gain"] == 9000.0 and s["gainPct"] == 47.37 and s["funds"] == 3
    assert s["xirrFunds"] == 1 and s["xirr"] is not None
    weights = {h["code"]: h["weight"] for h in b["holdings"]}
    assert weights == {BASE + 1: 53.6, BASE + 2: 25.0, BASE + 5: 21.4}
    cat = {p["label"]: p["pct"] for p in b["allocation"]["byCategory"]}
    assert cat == {"Large Cap": 78.6, "Small Cap": 21.4}
    assert b["allocation"]["byAmc"][0] == {"label": "Alpha Mutual Fund", "value": 22000.0, "pct": 78.6}
    assert b["concentration"]["top1Pct"] == 53.6 and "Alpha Bluechip" in b["concentration"]["text"] and "not investment" not in b["concentration"]["text"].lower()
    assert b["disclaimer"] == "Information only, not investment advice." and b["scoreDisclaimer"].startswith("Describes the fund's health")


# ------------------------------------------------------------------------------------------------------------------ ownership

async def test_one_member_cannot_see_change_or_delete_anothers_holdings(app):
    a = await signed_in(app, "a@example.com", plan="silver")
    b = await signed_in(app, "b2@example.com", plan="silver")
    hid = (await add(a, BASE + 1)).json()["id"]
    assert (await b.get(URL)).json()["count"] == 0
    assert (await b.put(f"{URL}/{hid}", json={"lots": [{"units": "1"}]})).status_code == 404
    assert (await b.delete(f"{URL}/{hid}")).status_code == 404
    assert (await a.get(URL)).json()["holdings"][0]["units"] == 100.0
    assert (await a.delete(f"{URL}/not-a-uuid")).status_code == 404
    assert (await a.delete(f"{URL}/{hid}")).status_code == 200 and (await a.get(URL)).json()["count"] == 0


async def test_deleting_the_account_deletes_the_holdings(app):
    c = await signed_in(app, "gone@example.com", plan="silver")
    await add(c, BASE + 1)
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_holdings") == 1
    r = await c.request("DELETE", "/api/me", json={"password": PW})            # the real "delete my account" route
    assert r.status_code == 200
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_holdings") == 0 and await conn.fetchval("SELECT count(*) FROM mf_holding_lots") == 0


# ------------------------------------------------------------------------------------------------------------------ writes

async def test_origin_and_csrf_are_required_for_writes(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    good = {"code": BASE + 1, "units": "1"}
    assert (await c.post(URL, json=good, headers={"Origin": "https://evil.example"})).status_code == 403
    r = await c.post(URL, json=good, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403 and r.json()["detail"]["status"] == "bad_csrf"
    c2 = new_client(app, cookies=c.cookies)           # same session, no Origin and no token at all
    assert (await c2.post(URL, json=good)).status_code == 403
    assert (await c2.post(f"{URL}/import-preview", json={"rows": []})).status_code == 403
    assert (await c2.delete(f"{URL}/{'0' * 8}-0000-0000-0000-{'0' * 12}")).status_code == 403
    assert (await c.get(URL)).json()["count"] == 0


@pytest.mark.parametrize("bad", [
    {"units": "0"}, {"units": "-5"}, {"units": ""}, {"units": "abc"}, {"units": None}, {"units": "1", "invested": "-1"}, {"units": "1", "invested": "x"},
    {"units": "1", "invested": "10", "avgCost": "10"}, {"units": "1", "boughtOn": "2999-01-01"}, {"units": "1", "boughtOn": "garbage"}, {"units": "99999999999"},
    {"units": "0.00001"}, {"units": "1", "invested": "99999999999999999"},
])
async def test_bad_numbers_are_refused_with_a_reason(app, bad):
    c = await signed_in(app, "s@example.com", plan="silver")
    r = await c.post(URL, json={"code": BASE + 1, **bad})
    assert r.status_code == 422 and r.json()["detail"]["status"] == "invalid_holding" and r.json()["detail"]["detail"]
    assert (await c.get(URL)).json()["count"] == 0


async def test_unknown_scheme_and_bad_codes(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    assert (await add(c, 999999)).status_code == 404
    assert (await add(c, 0)).status_code == 422 and (await c.post(URL, json={"units": "1"})).status_code == 422


async def test_decimal_precision_is_kept_and_rounded_half_up(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    await add(c, BASE + 1, "12.34565", avgCost="10.005")
    h = (await c.get(URL)).json()["holdings"][0]
    assert h["units"] == 12.3457                                    # 4 places, half up
    assert h["invested"] == 123.52                                  # 12.3457 x 10.005 = 123.5187... -> 123.52


async def test_same_fund_and_folio_merges_as_a_new_purchase_other_folio_is_separate(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    first = (await add(c, BASE + 1, "10", invested="1000", folio="123/45", boughtOn="2022-01-01")).json()
    second = (await add(c, BASE + 1, "5", invested="600", folio=" 123 / 45 ", boughtOn="2023-01-01")).json()
    assert second["merged"] is True and second["id"] == first["id"]
    other = (await add(c, BASE + 1, "1", folio="999")).json()
    assert other["merged"] is False and other["id"] != first["id"]
    b = (await c.get(URL)).json()
    assert b["count"] == 2
    h = next(h for h in b["holdings"] if h["id"] == first["id"])
    assert h["units"] == 15.0 and h["invested"] == 1600.0 and len(h["lots"]) == 2 and h["folio"] == "123/45"
    assert h["xirr"] is not None and h["xirrKind"] == "xirr"


async def test_update_replaces_the_purchases_and_guards_the_folio(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    a = (await add(c, BASE + 1, "10", folio="A1")).json()["id"]
    b = (await add(c, BASE + 1, "10", folio="B1")).json()["id"]
    r = await c.put(f"{URL}/{a}", json={"folio": "b1", "lots": [{"units": "1"}]})
    assert r.status_code == 409
    r = await c.put(f"{URL}/{a}", json={"lots": [{"units": "4", "invested": "400", "boughtOn": "2020-05-05"}, {"units": "6", "avgCost": "100"}]})
    assert r.status_code == 200
    h = next(h for h in (await c.get(URL)).json()["holdings"] if h["id"] == a)
    assert h["units"] == 10.0 and h["invested"] == 1000.0 and [l["boughtOn"] for l in h["lots"]] == ["2020-05-05", None]
    assert (await c.put(f"{URL}/{a}", json={"lots": []})).status_code == 422
    assert (await c.put(f"{URL}/{a}", json={"lots": [{"units": "-1"}]})).status_code == 422
    assert next(h for h in (await c.get(URL)).json()["holdings"] if h["id"] == a)["units"] == 10.0          # a refused update changes nothing
    assert b


async def test_the_plan_limit_on_funds(app, monkeypatch):
    monkeypatch.setitem(mfp.LIMITS["silver"], "mf_holdings", 2)
    c = await signed_in(app, "s@example.com", plan="silver")
    assert (await add(c, BASE + 1)).status_code == 201 and (await add(c, BASE + 2)).status_code == 201
    r = await add(c, BASE + 3)
    assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_limit"
    assert (await add(c, BASE + 1, "1")).status_code == 201                    # another purchase of a fund already held is not a new fund
    assert (await c.get(URL)).json()["limit"] == 2


async def test_write_rate_limit(app, monkeypatch):
    c = await signed_in(app, "s@example.com", plan="silver")
    codes = []
    for i in range(121):
        codes.append((await add(c, BASE + 1, "1")).status_code)
        if codes[-1] == 429:
            break
    assert codes[-1] == 429 and codes.count(201) == 120


# ------------------------------------------------------------------------------------------------------------------ import

def preview(c, rows):
    return c.post(f"{URL}/import-preview", json={"rows": rows})


def by_status(body):
    out = {}
    for r in body["rows"]:
        out.setdefault(r["status"], []).append(r)
    return out


async def test_preview_classifies_every_row_and_stores_nothing(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    rows = [
        {"row": 2, "name": "Alpha Bluechip Fund - Direct Plan - Growth", "isin": "INF000A01011", "folio": "111", "units": "1,000.500", "invested": "1,20,000.00", "date": "15-03-2021"},   # matched by ISIN
        {"row": 3, "name": "Beta Flexi Cap Fund - Direct Plan - Growth", "amfi": str(BASE + 3), "units": "50", "avgCost": "70"},                                                       # matched by AMFI code
        {"row": 4, "name": "Delta Small Cap Fund", "units": "10"},                                                                                                                         # only one scheme of that fund: matched by name
        {"row": 5, "name": "Alpha Bluechip Fund", "units": "10"},                                                                                                                          # direct or regular? choose
        {"row": 6, "name": "Zzz Imaginary Fund", "units": "10"},                                                                                                                           # not found
        {"row": 7, "name": "Reliance Industries Ltd", "isin": "INE002A01018", "units": "10"},                                                                                              # a share
        {"row": 8, "name": "Alpha Bluechip Fund - Direct Plan - Growth", "isin": "INF000A01011", "units": "0"},                                                                           # nothing held
        {"row": 9, "name": "Alpha Bluechip Fund - Direct Plan - Growth", "isin": "INF000A01011", "units": "-5"},                                                                          # a sale line
        {"row": 10, "name": "Alpha Bluechip Fund - Direct Plan - Growth", "isin": "INF000A01011", "folio": "111", "units": "1000.5", "invested": "120000", "date": "2021-03-15"},      # the same line again
        {"row": 11, "name": "Beta Flexi Cap Fund", "units": ""},                                                                                                                          # units missing
    ]
    r = await preview(c, rows)
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    st = by_status(body)
    assert body["counts"] == {"matched": 3, "choose": 1, "not_found": 1, "ignored": 2, "invalid": 2, "duplicate": 1} and body["total"] == 10
    first = body["rows"][0]
    assert first["status"] == "matched" and first["via"] == "isin" and first["fund"]["code"] == BASE + 1 and first["units"] == 1000.5 and first["invested"] == 120000.0
    assert first["boughtOn"] == "2021-03-15" and first["folio"] == "111" and first["existing"] is False
    assert body["rows"][1]["via"] == "amfi" and body["rows"][1]["invested"] == 3500.0
    assert body["rows"][2]["via"] == "name" and body["rows"][2]["fund"]["code"] == BASE + 5
    ch = st["choose"][0]
    assert {s["code"] for s in ch["candidates"]} == {BASE + 1, BASE + 2} and ch["fund"] is None and ch["reason"]
    assert st["not_found"][0]["fund"] is None and st["not_found"][0]["candidates"] == [] and st["not_found"][0]["reason"]
    assert [x["reason"] for x in st["ignored"]][0].startswith("A company share") and "Zero units" in st["ignored"][1]["reason"]
    assert any("redemption" in x["reason"] for x in st["invalid"]) and any("missing" in x["reason"] for x in st["invalid"])
    assert st["duplicate"][0]["row"] == 10 and "row 2" in st["duplicate"][0]["reason"]
    assert body["capacity"] == {"limit": 30, "used": 0, "room": 30}
    assert (await c.get(URL)).json()["count"] == 0                                   # a preview stores nothing


async def test_preview_marks_funds_already_held(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    await add(c, BASE + 1, "10", folio="111")
    body = (await preview(c, [{"row": 1, "isin": "INF000A01011", "folio": "111", "units": "5"}, {"row": 2, "isin": "INF000A01011", "folio": "222", "units": "5"}])).json()
    assert [r["existing"] for r in body["rows"]] == [True, False] and body["capacity"]["used"] == 1


async def test_cams_style_statement_rows(app):
    """What a CAMS / KFintech consolidated holdings export looks like once the browser has mapped its columns (the sample is typical, not a real file)."""
    c = await signed_in(app, "s@example.com", plan="silver")
    rows = [
        {"row": 12, "folio": "1234567890 / 12", "name": "Alpha Bluechip Fund - Direct Plan - Growth (Erstwhile Old Bluechip Fund)", "isin": "INF000A01011", "units": "2,345.678", "nav": "150.0000", "invested": "2,50,000.00", "current": "3,51,851.70"},
        {"row": 13, "folio": "NA", "name": "Delta Small Cap Fund - Direct Growth", "units": "10.000", "invested": "₹ 500"},
        {"row": 14, "folio": "", "name": "Total", "units": ""},
    ]
    body = (await preview(c, rows)).json()
    assert [r["status"] for r in body["rows"]] == ["matched", "matched", "invalid"]
    assert body["rows"][0]["folio"] == "1234567890/12" and body["rows"][0]["units"] == 2345.678 and body["rows"][1]["folio"] == "" and body["rows"][1]["invested"] == 500.0


async def test_preview_limits(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    assert (await preview(c, [{"units": "1"}] * 2001)).status_code == 422
    assert (await preview(c, [{"name": "x" * 301, "units": "1"}])).status_code == 422
    assert (await preview(c, [])).json()["total"] == 0
    big = await preview(c, [{"row": i, "name": "Alpha Bluechip Fund - Direct Plan - Growth", "units": "1", "folio": str(i)} for i in range(2000)])
    assert big.status_code == 200 and big.json()["counts"]["matched"] == 2000                      # 2,000 rows are above the 64 KB default and within the import allowance
    row = b'{"units": "1", "name": "' + b"x" * 250 + b'"},'
    over = await c.post(f"{URL}/import-preview", content=b'{"rows": [' + row * 9000 + b'{}]}', headers={"Content-Type": "application/json"})
    assert over.status_code == 413
    assert (await c.post(URL, content=b'{"code": 1, "units": "' + b"1" * 70000 + b'"}', headers={"Content-Type": "application/json"})).status_code == 413    # other routes keep 64 KB


async def test_commit_stores_only_what_was_confirmed(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    items = [{"code": BASE + 1, "folio": "111", "units": 100.5, "invested": 12000.0, "boughtOn": "2021-03-15"},
             {"code": BASE + 1, "folio": "111", "units": 20, "invested": 2500.0, "boughtOn": "2022-03-15"},
             {"code": BASE + 1, "folio": "111", "units": 20, "invested": 2500.0, "boughtOn": "2022-03-15"},          # the same line twice: once
             {"code": BASE + 5, "folio": "", "units": 10, "invested": None, "boughtOn": None}]
    r = await c.post(f"{URL}/import-commit", json={"items": items})
    assert r.status_code == 201 and r.json() == {"status": "saved", "added": 2, "replaced": 0, "skipped": 0, "duplicates": 1}
    b = (await c.get(URL)).json()
    assert b["count"] == 2
    h = next(h for h in b["holdings"] if h["code"] == BASE + 1)
    assert h["units"] == 120.5 and h["invested"] == 14500.0 and len(h["lots"]) == 2 and h["folio"] == "111"
    d = next(h for h in b["holdings"] if h["code"] == BASE + 5)
    assert d["invested"] is None and d["gain"] is None and d["current"] == 600.0            # no cost given stays unknown


async def test_commit_refuses_rows_without_a_real_scheme_or_with_bad_numbers(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    r = await c.post(f"{URL}/import-commit", json={"items": [{"code": BASE + 1, "units": 1}, {"code": 4242424, "units": 1}]})
    assert r.status_code == 422 and r.json()["detail"]["status"] == "unknown_scheme"
    assert (await c.post(f"{URL}/import-commit", json={"items": [{"units": 1}]})).status_code == 422                       # no scheme chosen: never imported
    r = await c.post(f"{URL}/import-commit", json={"items": [{"code": BASE + 1, "units": 1}, {"code": BASE + 1, "folio": "2", "units": -3}]})
    assert r.status_code == 422 and "Line 2" in r.json()["detail"]["detail"]
    assert (await c.post(f"{URL}/import-commit", json={"items": []})).status_code == 422
    assert (await c.get(URL)).json()["count"] == 0                                                                           # all or nothing


async def test_commit_skips_or_replaces_funds_already_held(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    await add(c, BASE + 1, "10", invested="100", folio="111")
    item = {"code": BASE + 1, "folio": "111", "units": 99, "invested": 9900.0}
    r = await c.post(f"{URL}/import-commit", json={"items": [item, {"code": BASE + 2, "units": 1}]})
    assert r.json() == {"status": "saved", "added": 1, "replaced": 0, "skipped": 1, "duplicates": 0}
    assert next(h for h in (await c.get(URL)).json()["holdings"] if h["code"] == BASE + 1)["units"] == 10.0              # untouched: a re-import never double counts
    r = await c.post(f"{URL}/import-commit", json={"items": [item], "existing": "replace"})
    assert r.json()["replaced"] == 1
    assert next(h for h in (await c.get(URL)).json()["holdings"] if h["code"] == BASE + 1)["units"] == 99.0


async def test_commit_respects_the_plan_limit_all_or_nothing(app, monkeypatch):
    monkeypatch.setitem(mfp.LIMITS["silver"], "mf_holdings", 2)
    c = await signed_in(app, "s@example.com", plan="silver")
    await add(c, BASE + 1)
    r = await c.post(f"{URL}/import-commit", json={"items": [{"code": BASE + 2, "units": 1}, {"code": BASE + 3, "units": 1}]})
    assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_limit" and "adds 2" in r.json()["detail"]["detail"]
    assert (await c.get(URL)).json()["count"] == 1


async def test_import_rate_limit(app):
    c = await signed_in(app, "s@example.com", plan="silver")
    codes = [(await preview(c, [])).status_code for _ in range(31)]
    assert codes[-1] == 429 and codes.count(200) == 30
