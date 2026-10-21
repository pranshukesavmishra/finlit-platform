"""Secondary source. Fixtures are synthetic, built from the request/response shapes of the old site (site-api/backend/server.py);
live Upstox behaviour is unverified."""
import asyncio
import httpx
import pytest

from finlit import snapshot, upstox
from finlit.config import Settings

def S(token="t"):
    return Settings(upstox_access_token=token)

PERIODS = ["Mar 2023", "Mar 2024", "Mar 2025"]
def hist(vals):
    return [{"period": p, "value": v, "change": None} for p, v in zip(PERIODS, vals)]
INCOME = {"income_statement": [
    {"category": "revenue", "history": hist([100.0, 120.0, 150.0])},
    {"category": "other_income", "history": hist([1.0, 2.0, 2.0])},
    {"category": "interest", "history": hist([1.0, 1.0, 1.0])},
    {"category": "depreciation", "history": hist([2.0, 2.0, 3.0])},
    {"category": "profit_before_tax", "history": hist([20.0, 25.0, 30.0])},
    {"category": "tax_expense", "history": hist([5.0, 6.0, 7.0])},
    {"category": "net_profit", "history": hist([15.0, 19.0, 23.0])},
    {"category": "eps", "history": hist([1.5, 1.9, 2.3])}]}
BS = {"history": [{"period": p, "total_asset": a, "total_liability": a} for p, a in zip(PERIODS, [90.0, 100.0, 120.0])]}
CF = {"cash_flow": [{"category": "operating", "history": hist([10.0, 12.0, 14.0])}, {"category": "investing", "history": hist([-5.0, -6.0, -7.0])}, {"category": "financing", "history": hist([-1.0, -1.0, -2.0])}]}
INST = [{"name": "SPICY ENTERTAINMENT & MEDIA LTD", "trading_symbol": "SPICY", "isin": "INE0TEST0001", "instrument_key": "BSE_EQ|INE0TEST0001", "segment": "BSE_EQ"}]

def handler_factory(calls, status=200):
    def h(req: httpx.Request):
        calls.append(req.url.path)
        if status != 200:
            return httpx.Response(status, json={"status": "error"})
        pth = req.url.path
        data = INST if "search" in pth else INCOME if "income" in pth else BS if "balance" in pth else CF if "cash" in pth else \
            {"BSE_EQ:SPICY": {"last_price": 58.4, "cp": 57.0, "instrument_token": "BSE_EQ|INE0TEST0001"}} if "ltp" in pth else \
            {"candles": [["2026-10-19T00:00:00+05:30", 57, 59, 56, 57.5, 1000], ["2026-10-20T00:00:00+05:30", 57.5, 59, 57, 58.4, 900]]} if "candle" in pth else \
            [{"name": "ROE", "company_value": 15.44}, {"name": "ROCE", "company_value": 16.58}] if "key-ratios" in pth else {}
        return httpx.Response(200, json={"status": "success", "data": data})
    return h

def empty_bundle(symbol="540084"):
    return {"symbol": symbol, "statement": "consolidated", "quote": {}, "pl_annual": {"financials": []}, "bs_annual": [], "daily_quotes": {"price": []}, "errors": {}}

def run(c): return asyncio.run(c)

def test_empty_finedge_filled_from_upstox_with_right_units():
    calls = []
    cl = upstox.UpstoxClient(S(), transport=httpx.MockTransport(handler_factory(calls)))
    b = run(upstox.supplement(empty_bundle(), cl, {"name": "Spicy Entertainment & Media", "bse_code": "540084"}))
    assert b["_source"]["pl_annual"] == "upstox" and b["_source"]["quote"] == "upstox"
    r = b["pl_annual"]["financials"][-1]
    assert r["revenueFromOperations"] == 150.0 * 1e7 and r["profitLossForPeriod"] == 23.0 * 1e7 and r["eps"] == 2.3
    sec = snapshot.build(b)
    fin = sec["financials"]["yearly"]["pl"]
    assert fin["periods"] == ["FY23", "FY24", "FY25"]
    assert fin["rows"]["revenue"][-1] == 150.0 and fin["rows"]["net_profit"][-1] == 23.0
    assert fin["rows"]["operating_profit"][-1] == pytest.approx(30 + 1 + 3 - 2)   # pbt + interest + depreciation - other income
    assert sec["summary"]["quote"]["price"] == 58.4
    dq = sec["summary"]["dataQuality"]
    assert dq["secondarySource"]["pl_annual"] == "upstox" and any("secondary data source" in n for n in dq["notes"])
    assert dq["coverage"]["state"] == "complete" and any("secondary source" in x for x in dq["coverage"]["reasons"])
    assert sec["financials"]["yearly"]["bs"]["rows"]["total_assets"][-1] == 120.0

def test_good_finedge_untouched_no_calls():
    calls = []
    cl = upstox.UpstoxClient(S(), transport=httpx.MockTransport(handler_factory(calls)))
    b = {"symbol": "X", "quote": {"X": {"current_price": 10}}, "pl_annual": {"financials": [{"period_end": "2025-03-31"}]}, "bs_annual": {"financials": [{"period_end": "2025-03-31"}]},
         "cf_annual": {"financials": [{"period_end": "2025-03-31"}]}, "pl_quarterly": {"financials": [{"period_end": "2025-03-31"}]}}
    before = dict(b)
    run(upstox.supplement(b, cl, {}))
    assert calls == [] and b == before

def test_no_token_no_calls():
    calls = []
    cl = upstox.UpstoxClient(S(""), transport=httpx.MockTransport(handler_factory(calls)))
    b = run(upstox.supplement(empty_bundle(), cl, {"name": "Spicy"}))
    assert calls == [] and "_source" not in b and not cl.enabled
    assert run(upstox.health_line(None, S("")))["state"] == "not_configured"

def test_401_flags_token_expired():
    calls = []
    class R:
        v = None
        async def set(self, k, v): R.v = v
        async def get(self, k): return R.v
    cl = upstox.UpstoxClient(S(), redis=R(), transport=httpx.MockTransport(handler_factory(calls, 401)))
    b = run(upstox.supplement(empty_bundle(), cl, {"name": "Spicy"}))
    assert "_source" not in b and cl.expired and len(calls) == 1
    h = run(upstox.health_line(R(), S()))
    assert h["state"] == "token_expired" and "token expired" in h["text"]

def test_wrong_company_never_accepted():
    cl = upstox.UpstoxClient(S(), transport=httpx.MockTransport(handler_factory([])))
    assert run(cl.resolve("OTHER", ["Completely Different Ltd"])) is None

def test_period_and_units():
    assert str(upstox.period_end("Mar 2024")) == "2024-03-31" and str(upstox.period_end("FY24")) == "2024-03-31"
    assert str(upstox.period_end("2024-12-31")) == "2024-12-31" and upstox.period_end("garbage") is None
    assert upstox.balance_rows(BS)[0]["assets"] == 90.0 * 1e7

def test_reconcile_flags_but_keeps_finedge():
    b = {"symbol": "X", "pl_annual": {"financials": [{"period_end": "2025-03-31", "revenueFromOperations": 100e7, "profitLossForPeriod": 20e7}]}, "quote": {"X": {"current_price": 100}}}
    up = [{"period_end": "2025-03-31", "revenueFromOperations": 120e7, "profitLossForPeriod": 20.5e7}]
    out = upstox.reconcile(b, up, 100.5)
    assert [o["item"] for o in out] == ["revenue"] and out[0]["finedge"] == 100.0 and out[0]["secondary"] == 120.0
