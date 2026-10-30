from datetime import date, timedelta

import pytest

from finlit.calendars import ipo_rows, issue_size_cr, refresh_calendars, result_rows
from test_auth import anon, app  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401

pytestmark = pytest.mark.integration


def test_parsing_is_forgiving_about_the_providers_shapes():
    assert issue_size_cr("₹1,250 Cr") == 1250 and issue_size_cr("48 crore") == 48 and issue_size_cr("12.5 lakh") == 0.12 and issue_size_cr("2,19,69,695", 693) == 1522.5 and issue_size_cr("2500000000") is None and issue_size_cr("n/a") is None
    rows = result_rows({"data": [{"symbol": "tcs", "company_name": "Tata  Consultancy", "expected_result_date": "2026-10-20"}, {"symbol": "TCS", "expected_result_date": "2026-10-20"}, {"symbol": "", "expected_result_date": "2026-10-21"}, {"symbol": "X", "expected_result_date": "bad"}]})
    assert len(rows) == 1 and rows[0][2] == "TCS" and rows[0][6] == date(2026, 10, 20) and rows[0][3] == "Tata Consultancy"
    ipo = ipo_rows([{"company_name": "Acme Ltd", "symbol": None, "security_type": "SME", "ipo_status": "Open", "start_date": "2026-10-19", "end_date": "2026-10-22", "price_range": "₹ 95 - 100", "issue_size": "48 Cr", "exchange": ["NSE"]},
                    {"company_name": "Backwards", "start_date": "2026-10-22", "end_date": "2026-10-19"}])
    assert len(ipo) == 1 and ipo[0][2] == "sme" and (ipo[0][7], ipo[0][8]) == (95.0, 100.0) and ipo[0][10] == 48.0


class Fake:
    def __init__(self, results, ipos): self.results, self.ipos, self.fail = results, ipos, False
    async def get(self, path, params=None, timeout=10, retries=3):
        if self.fail: raise RuntimeError("provider down")
        return self.results if path == "/results-calendar" else self.ipos


async def test_refresh_replaces_provider_rows_and_keeps_hand_entered_ipos(store):  # noqa: F811
    t = date.today()
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO ipos (name, open_date, close_date) VALUES ('Hand entered', $1, $2)", t, t + timedelta(days=2))
        await conn.execute("DELETE FROM feed_items WHERE source = 'FinEdge results calendar'")
    day = lambda n: (t + timedelta(days=n)).isoformat()
    f = Fake({"data": [{"symbol": "AAA", "company_name": "Aaa Ltd", "expected_result_date": day(20)}, {"symbol": "BBB", "company_name": "Bbb Ltd", "expected_result_date": day(45)}]},
             [{"company_name": "Acme", "start_date": day(1), "end_date": day(3), "price_range": "90-95", "security_type": "mainboard"}])
    assert await refresh_calendars(store=store, client=f) == {"results": 2, "ipos": 1}
    f.results = {"data": [{"symbol": "AAA", "company_name": "Aaa Ltd", "expected_result_date": day(25)}]}   # AAA's date moved, BBB was dropped
    f.ipos = [{"company_name": "Acme", "start_date": day(1), "end_date": day(4), "price_range": "90-96"}]
    await refresh_calendars(store=store, client=f)
    async with store.pool.acquire() as conn:
        dates = {r["symbol"]: r["item_date"] for r in await conn.fetch("SELECT symbol, item_date FROM feed_items WHERE source = 'FinEdge results calendar'")}
        ipos = {r["name"]: r for r in await conn.fetch("SELECT name, close_date, price_high, source FROM ipos")}
    assert dates == {"AAA": t + timedelta(days=25)}
    assert ipos["Acme"]["close_date"] == t + timedelta(days=4) and float(ipos["Acme"]["price_high"]) == 96 and "Hand entered" in ipos
    f.fail = True
    assert await refresh_calendars(store=store, client=f) == {"results": 0, "ipos": 0}      # provider down: old data stays
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM feed_items WHERE source = 'FinEdge results calendar'") == 1


def test_provider_date_and_band_formats():
    """The provider writes IPO dates as 21-Oct-2026 and bands as 'Rs.1065 to Rs.1119': both must be read, or the whole calendar comes out empty."""
    from finlit.calendars import parse_date
    from datetime import date
    assert parse_date("21-Oct-2026") == date(2026, 10, 21) and parse_date("2026-07-21T00:00:00") == date(2026, 7, 21)
    rows = ipo_rows({"data": [{"symbol": "JPL", "company_name": "Jio Platforms Limited", "security_type": "Equity", "ipo_status": "Forthcoming", "start_date": "21-Oct-2026", "end_date": "23-Oct-2026",
                               "price_range": "Rs.1065 to Rs.1119", "issue_size": "27,00,00,000", "exchange": ["NSE", "BSE"]}]})
    assert len(rows) == 1 and rows[0][7:9] == (1065.0, 1119.0) and rows[0][10] == 30213.0


# ---------------------------------------------------------------- tolerant IPO fields, raw row, discovery
def _row(**kw):
    base = {"company_name": "Zenith Foods Ltd", "start_date": "2026-10-19", "end_date": "2026-10-22", "price_range": "Rs.95 to Rs.100"}
    base.update(kw)
    return base


def _one(**kw):
    rows = ipo_rows({"data": [_row(**kw)]})
    assert len(rows) == 1
    import json as _j
    return rows[0], _j.loads(rows[0][14]), _j.loads(rows[0][15])


def test_original_columns_are_unchanged_and_two_json_columns_follow():
    r, raw, det = _one()
    assert len(r) == 16 and r[0] == "Zenith Foods Ltd" and r[2] == "mainboard" and r[7:9] == (95.0, 100.0) and r[9] is None and r[11] is None
    assert raw["company_name"] == "Zenith Foods Ltd" and det == {}          # nothing sent: nothing invented


def test_aliases_renamed_keys_and_mixed_types():
    r, raw, det = _one(**{"Lead Managers": "Axis Capital Limited, JM Financial & ICICI Securities", "RegistrarName": "Link Intime India Pvt Ltd", "exchange": ["NSE", "BSE"],
                          "Market Lot": "150", "Face_Value": "10", "ListingPrice": "132.5", "Industry": "Packaged foods", "issue_type": "Book Built",
                          "allotment_date": "23-Oct-2026", "refund_date": "26/10/2026", "listing_date": "2026-10-27T00:00:00", "credit_of_shares_date": "26 Oct 2026",
                          "fresh_issue": "400 Cr", "offer_for_sale": "2,00,00,000", "promoter_holding_pre": "81.2%", "promoter_holding_post": 62.5,
                          "objectives": "Repay borrowings; Fund capex | General corporate purposes", "drhp": "https://example.org/d.pdf", "rhp": "javascript:alert(1)"})
    assert r[3] == "Packaged foods" and r[9] == 150 and r[11] == 132.5 and str(r[6]) == "2026-10-27"
    assert det["leadManagers"] == ["Axis Capital Limited", "JM Financial", "ICICI Securities"] and det["registrar"] == "Link Intime India Pvt Ltd" and det["exchange"] == ["NSE", "BSE"]
    assert det["faceValue"] == 10 and det["issueType"] == "Book Built"
    assert (det["allotmentDate"], det["refundDate"], det["creditDate"]) == ("2026-10-23", "2026-10-26", "2026-10-26")
    assert det["freshIssueCr"] == 400 and det["ofsCr"] == 200.0          # 2 crore shares x Rs 100
    assert (det["promoterPrePct"], det["promoterPostPct"]) == (81.2, 62.5)
    assert det["objectives"] == ["Repay borrowings", "Fund capex", "General corporate purposes"]
    assert det["docs"] == {"drhp": "https://example.org/d.pdf"}          # a non-https link is dropped


def test_subscription_shapes():
    assert _one(subscription=12.5)[2]["subscription"] == {"overall": 12.5}
    assert _one(subscription="3.4x")[2]["subscription"] == {"overall": 3.4}
    assert _one(subscription={"QIB": "45.1x", "NII": 20, "Retail": {"times": "8.2"}, "Total": 22.9})[2]["subscription"] == {"qib": 45.1, "nii": 20.0, "retail": 8.2, "overall": 22.9}
    assert _one(subscription=[{"category": "Qualified Institutional Buyers", "times": 5}, {"category": "Retail Individual Investors", "times": 1.5}])[2]["subscription"] == {"qib": 5.0, "retail": 1.5}
    assert _one(qib_subscription=1.1, rii_subscription="2.2", total_subscription=1.9)[2]["subscription"] == {"overall": 1.9, "qib": 1.1, "retail": 2.2}
    assert "subscription" not in _one(subscription="Not available")[2] and "subscription" not in _one(subscription=None)[2]


def test_nulls_garbage_and_board_detection():
    r, _, det = _one(registrar=None, lead_managers=[], market_lot="n/a", listing_price=0, face_value="abc", promoter_holding_pre=140, exchange="NSE SME", refund_date="soon")
    assert r[2] == "sme" and r[9] is None and r[11] is None and det == {"exchange": ["NSE"]}
    assert _one(category="SME")[0][2] == "sme" and _one(price_range="₹100")[0][7:9] == (100.0, 100.0)
    assert _one(price_low=90, price_high="95")[0][7:9] == (90.0, 95.0)
    assert ipo_rows({"data": [{"name": "X", "open_date": "2026-10-19", "close_date": "2026-10-20"}]})[0][5] == date(2026, 10, 20)       # renamed date keys


def test_raw_is_small_and_has_no_secrets():
    import json as _j
    r, raw, _ = _one(about="x" * 5000, api_key="s3cret", nested={"a": {"b": {"c": {"d": 1}}}}, blob=["y" * 500] * 30, ok="fine")
    assert len(raw["about"]) <= 601 and "blob" not in raw and "api_key" not in raw and raw["ok"] == "fine" and len(_j.dumps(raw)) <= 6000


def test_ipo_fields_discovery_lists_keys_and_one_full_sample():
    from finlit.calendars import ipo_fields
    f = ipo_fields({"data": [{"a": 1, "b": None}, {"a": 2, "b": "x" * 900, "c": [1, 2]}]}, date(2026, 7, 1), date(2026, 12, 1))
    assert f["seenKeys"] == ["a", "b", "c"] and f["rowCount"] == 2 and f["sample"]["a"] == 2 and len(f["sample"]["b"]) < 250 and f["windowFrom"] == "2026-07-01" and f["at"]
    assert ipo_fields([], date(2026, 7, 1), date(2026, 7, 2))["sample"] is None


async def test_refresh_stores_raw_details_and_publishes_fields_at_status(store):  # noqa: F811
    from finlit.results import pipeline_status
    from finlit.worker import _record_results_run
    from finlit.auth.routes import ipo_json
    t = date.today()
    day = lambda n: (t + timedelta(days=n)).isoformat()
    f = Fake({"data": []}, {"data": [_row(start_date=day(1), end_date=day(3), registrar="Kfin", subscription={"qib": 2}, secret_token="zzz")]})
    rep = {}
    counts = await refresh_calendars(store=store, client=f, report=rep)
    assert counts["ipos"] == 1 and rep["ipoFields"]["rowCount"] == 1 and "registrar" in rep["ipoFields"]["seenKeys"]
    await _record_results_run(store, "refresh-calendars", "ok", counts, rep)
    st = await pipeline_status(store)
    assert st["ipoFields"]["sample"]["registrar"] == "Kfin" and "ipoFields" not in st["lastRun"]["calendars"] and st["ipoFields"]["at"]
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM ipos WHERE name = 'Zenith Foods Ltd'")
        assert "secret_token" not in str(row["raw"]) and row["raw"] is not None
        listed = await conn.fetch("SELECT id, name, symbol, kind, sector, open_date, close_date, listing_date, price_low, price_high, lot_size, issue_size_cr, listing_price, note, link, details, updated_at, source FROM ipos WHERE name = 'Zenith Foods Ltd'")
    j = ipo_json(listed[0], t)
    assert j["details"]["registrar"] == "Kfin" and j["details"]["subscription"] == {"qib": 2.0} and j["source"] == "FinEdge" and j["updatedAt"] and "raw" not in j


async def test_ipos_api_has_details_and_no_raw(anon, app):  # noqa: F811
    t = date.today()
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM ipos")
        await conn.execute("INSERT INTO ipos (name, open_date, close_date, raw, details) VALUES ('Api Co', $1, $2, '{\"a\":1}', '{\"registrar\":\"Kfin\"}')", t, t + timedelta(days=2))
        await conn.execute("INSERT INTO ipos (name, open_date, close_date) VALUES ('Hand Co', $1, $2)", t - timedelta(days=1), t + timedelta(days=2))
    rows = {r["name"]: r for r in (await anon.get("/api/ipos")).json()["ipos"]}
    assert rows["Api Co"]["details"] == {"registrar": "Kfin"} and rows["Hand Co"]["details"] == {} and "raw" not in rows["Api Co"] and rows["Api Co"]["status"] == "open"
    body = (await anon.get("/api/results/status")).json()
    assert "ipoFields" in body
