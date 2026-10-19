from datetime import date, timedelta

import pytest

from finlit.calendars import ipo_rows, issue_size_cr, refresh_calendars, result_rows
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
