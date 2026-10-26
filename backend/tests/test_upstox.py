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
    b = {"symbol": "X", "quote": {"X": {"current_price": 10}}, "pl_annual": {"financials": [{"period_end": f"{y}-03-31"} for y in range(2021, 2026)]}, "bs_annual": {"financials": [{"period_end": "2025-03-31"}]},
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


# ---- older years from the second source, only where it agrees with the provider on the years both hold
def _fe(years, profit):
    return [{"period_end": f"{y}-03-31", "year": y, "revenueFromOperations": 100.0 * 1e7 * (y - 2020), "profitLossForPeriod": profit(y) * 1e7} for y in years]

def test_older_years_added_when_the_sources_agree_on_the_years_both_have():
    fe = _fe([2025, 2026], lambda y: 10.0 * (y - 2020))
    up = upstox.income_rows({"income_statement": [
        {"category": "revenue", "history": [{"period": f"Mar {y}", "value": 100.0 * (y - 2020)} for y in range(2022, 2027)]},
        {"category": "net_profit", "history": [{"period": f"Mar {y}", "value": 10.0 * (y - 2020)} for y in range(2022, 2027)]}]})
    longer = upstox.extend_history(fe, up)
    assert [r["period_end"][:4] for r in longer] == ["2022", "2023", "2024", "2025", "2026"]
    assert longer[-1] is fe[-1] or longer[-1] == fe[-1]          # the provider's own rows are what is kept for the years it has

def test_second_source_that_disagrees_is_not_used_at_all():
    fe = _fe([2025, 2026], lambda y: 48000.0 if y == 2025 else 57000.0)
    up = upstox.income_rows({"income_statement": [
        {"category": "revenue", "history": [{"period": f"Mar {y}", "value": 100.0 * (y - 2020)} for y in range(2022, 2027)]},
        {"category": "net_profit", "history": [{"period": f"Mar {y}", "value": 10957.0} for y in range(2022, 2027)]}]})
    assert upstox.extend_history(fe, up) is None

def test_no_common_year_means_no_extension():
    fe = _fe([2025], lambda y: 5.0)
    up = upstox.income_rows({"income_statement": [{"category": "revenue", "history": [{"period": "Mar 2022", "value": 1.0}]}, {"category": "net_profit", "history": [{"period": "Mar 2022", "value": 1.0}]}]})
    assert upstox.extend_history(fe, up) is None



def test_a_dec_labelled_year_end_is_aligned_to_march_when_that_is_where_the_numbers_agree():
    fe = [{"period_end": f"{y}-03-31", "year": y, "profitOrLossAttributableToOwners": p * 1e7} for y, p in ((2025, 48151.0), (2026, 57000.0))]
    up = upstox.income_rows({"income_statement": [
        {"category": "revenue", "history": [{"period": f"Dec {y}", "value": 1.0} for y in (2021, 2022, 2023, 2024)]},
        {"category": "net_profit", "history": [{"period": f"Dec {y}", "value": v} for y, v in ((2021, 4043.0), (2022, 36397.0), (2023, 40676.0), (2024, 48151.0))]}]})
    longer = upstox.extend_history(fe, up)
    assert [r["period_end"][:4] for r in longer] == ["2022", "2023", "2024", "2025", "2026"]
    assert [round(upstox._field(r, "profitLossForPeriod") / 1e7) for r in longer][:3] == [4043, 36397, 40676]


def test_provider_dates_written_as_yyyymmdd_are_read():
    fe = [{"period_end": "20250331", "year": 2025, "profitOrLossAttributableToOwners": 48151e7}, {"period_end": "20260331", "year": 2026, "profitOrLossAttributableToOwners": 57000e7}]
    up = upstox.income_rows({"income_statement": [
        {"category": "revenue", "history": [{"period": f"Dec {y}", "value": 1.0} for y in (2022, 2023, 2024)]},
        {"category": "net_profit", "history": [{"period": f"Dec {y}", "value": v} for y, v in ((2022, 36397.0), (2023, 40676.0), (2024, 48151.0))]}]})
    why: list = []
    longer = upstox.extend_history(fe, up, why=why)
    assert longer and len(longer) == 4 and not [w for w in why if "no readable dates" in w]


def test_cash_flow_extends_within_the_wider_margin_and_never_across_a_sign_change():
    fe = [{"period_end": "20250331", "cashFlowsFromOperatingActivities": -6180e7}, {"period_end": "20260331", "cashFlowsFromOperatingActivities": -5000e7}]
    up = [{"period_end": f"{y}-03-31", "cashFlowsFromOperatingActivities": v * 1e7} for y, v in ((2023, -4000.0), (2024, -5200.0), (2025, -6756.0))]
    assert upstox.extend_history(fe, up, keys=("cashFlowsFromOperatingActivities",)) is None                       # 9% apart: refused at the 5% default
    longer = upstox.extend_history(fe, up, keys=("cashFlowsFromOperatingActivities",), tolerance=upstox.CASH_TOLERANCE)
    assert longer and [r["period_end"][:4] for r in longer] == ["2023", "2024", "2025", "2026"]
    flipped = [{**r, "cashFlowsFromOperatingActivities": -r["cashFlowsFromOperatingActivities"]} for r in up]
    assert upstox.extend_history(fe, flipped, keys=("cashFlowsFromOperatingActivities",), tolerance=upstox.CASH_TOLERANCE) is None


def test_token_days_left_reads_the_expiry_inside_the_token():
    import base64, json
    from finlit import upstox

    def jwt(exp):
        part = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
        return f"{part({'alg': 'HS256'})}.{part({'exp': exp})}.sig"
    assert upstox.token_days_left(jwt(1_000_000 + 10 * 86400 + 5), now=1_000_000) == 10
    assert upstox.token_days_left(jwt(1_000_000 - 86400 - 5), now=1_000_000) < 0
    assert upstox.token_days_left("not-a-jwt") is None and upstox.token_days_left("") is None


async def test_an_expired_note_applies_only_to_the_token_it_was_recorded_for():
    from finlit import upstox
    from finlit.config import Settings

    class R:
        def __init__(self, v): self.v = v
        async def get(self, key): return self.v
    old, new = "old.token.value", "new.token.value"
    s = Settings(upstox_access_token=new)
    assert (await upstox.health_line(R(f"expired|1|{upstox.token_tag(old)}"), s))["state"] == "connected"      # a fresh token clears the old note
    assert (await upstox.health_line(R(f"expired|1|{upstox.token_tag(new)}"), s))["state"] == "token_expired"
    assert (await upstox.health_line(R("expired|1"), s))["state"] == "token_expired"                           # a note from before fingerprints still counts
