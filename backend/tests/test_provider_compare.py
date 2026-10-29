"""compare-provider: raw FinEdge figure against the stored report, with verdicts and rules. No network, no database."""

import asyncio
import copy
import json

import pytest

from conftest import BUNDLE_FILES, load
from finlit import provider_compare as pc
from finlit.snapshot import build

PAYLOAD_KEYS = pc.CALLS


@pytest.fixture(scope="module")
def payloads(reliance_bundle):
    return {k: copy.deepcopy(reliance_bundle[k]) for k in PAYLOAD_KEYS}


def rows_by_key(company):
    return {r["key"]: r for r in company["rows"]}


def test_reliance_report_has_no_unexplained_mismatch(payloads, reliance_sections):
    c = pc.compare_symbol("RELIANCE", "standalone", payloads, reliance_sections)
    r = rows_by_key(c)
    assert [x["key"] for x in c["rows"] if x["verdict"] == "MISMATCH"] == []
    assert r["pe"]["verdict"] == "match" and r["pe"]["ours"]["value"] == r["pe"]["finedge"]["value"] == 41.36
    assert r["pe"]["finedge"]["endpoint"] == "/daily-price-ratios/{symbol}" and "price_ratios[2026-09-28].pe" == r["pe"]["finedge"]["field"]
    assert r["mcap_quote"]["verdict"] == "match" and r["mcap_screener"]["verdict"] == "match"
    # the profile figure differs from the one market cap on the page: explained by the rule, never silent
    assert r["mcap_profile"]["verdict"] == "explained" and "one market cap" in r["mcap_profile"]["why"]
    assert r["ev_ebitda"]["verdict"] == "explained" and "fallback" in r["ev_ebitda"]["rule"]
    assert r["dividend_yield"]["finedge"]["endpoint"] == "(none)"
    assert r["roce"]["finedge"]["field"].startswith("ratios[Mar 2026]")   # looked up in the row for the period we show (FY26), not the TTM row
    for key in ("sales_year", "profit_year", "sales_ttm", "profit_ttm", "eps", "book_value_ps", "shares", "debt_to_equity", "roe", "price"):
        assert r[key]["verdict"] == "match", (key, r[key])


def test_the_old_override_would_be_caught(payloads, reliance_sections):
    s = copy.deepcopy(reliance_sections)
    s["ratios"]["latest"]["pe"].update(value=40.86, period="Today", rule="override")   # what the old rule showed: FinEdge's 41.36 re-priced
    s["ratios"]["latest"]["pe"].pop("note", None)
    c = pc.compare_symbol("RELIANCE", "standalone", payloads, s)
    pe = rows_by_key(c)["pe"]
    assert pe["verdict"] == "MISMATCH" and pe["diffPct"] == pytest.approx(-1.209, abs=0.01)
    assert c["counts"]["MISMATCH"] >= 1


def test_blank_without_reason_and_blank_with_reason(payloads, reliance_sections):
    s = copy.deepcopy(reliance_sections)
    s["ratios"]["latest"].pop("pb")
    assert rows_by_key(pc.compare_symbol("RELIANCE", "standalone", payloads, s))["pb"]["verdict"] == "MISMATCH"   # FinEdge has it, ours is blank
    p = copy.deepcopy(payloads)
    for row in p["daily_price_ratios"]["price_ratios"]:
        row["pb"] = 0
    s["ratios"]["blanks"] = {"pb": "FinEdge sent no P/B and it cannot be worked out: ..."}
    assert rows_by_key(pc.compare_symbol("RELIANCE", "standalone", p, s))["pb"]["verdict"] == "explained"


def test_a_field_finedge_sends_but_we_do_not_use_is_flagged(payloads, reliance_sections):
    p = copy.deepcopy(payloads)
    p["basic"]["ratios"][0]["evToEbitda"] = 17.9
    c = pc.compare_symbol("RELIANCE", "standalone", p, reliance_sections)
    ev = rows_by_key(c)["ev_ebitda"]
    assert ev["finedge"]["field"].endswith("evToEbitda") and ev["verdict"] == "MISMATCH"
    assert c["providerFieldsSeen"][0]["value"] == 17.9


def test_old_quote_is_explained_by_its_date(payloads, reliance_sections):
    p = copy.deepcopy(payloads)
    p["quote"]["RELIANCE"].update(current_price=1250.0, market_cap=1_690_000.0, tradetime="2026-09-30T15:59:02Z")
    r = rows_by_key(pc.compare_symbol("RELIANCE", "standalone", p, reliance_sections))
    assert r["price"]["verdict"] == "explained" and "2026-09-30" in r["price"]["why"]


class FakeClient:
    def __init__(self):
        self.calls = []

    async def get(self, path, params=None, timeout=10, **kw):
        self.calls.append((path, params))
        name = {
            "/company-profile/": "profile", "/quote": "quote", "/daily-price-ratios/": "daily_price_ratios", "/basic-financials/": "basic",
        }
        for prefix, key in name.items():
            if path.startswith(prefix):
                return load(BUNDLE_FILES[key])
        if path.startswith("/ratios/"):
            return load(BUNDLE_FILES["ratios_" + params["ratio_type"]])
        if path.startswith("/financials/"):
            return load(BUNDLE_FILES[f"{params['statement_code']}_{params['period']}"]) if False else load(
                {("pl", "annual"): BUNDLE_FILES["pl_annual"], ("bs", "annual"): BUNDLE_FILES["bs_annual"], ("pl", "quarterly"): BUNDLE_FILES["pl_quarterly"]}[(params["statement_code"], params["period"])])
        return {}


def test_provider_calls_are_few_and_listed():
    client = FakeClient()
    payloads, n, errors = asyncio.run(pc.fetch_payloads(client, "RELIANCE", "standalone", pause=0))
    assert n == len(client.calls) == 9 and not errors and set(payloads) == set(pc.CALLS)
    client = FakeClient()
    _, n, _ = asyncio.run(pc.fetch_payloads(client, "RELIANCE", "standalone", discover_fields=True, pause=0))
    assert n == 11 and any(p.startswith("/financial-metrics/") for p, _ in client.calls)


class FakeConn:
    def __init__(self, db):
        self.db = db

    async def fetch(self, sql, *args):
        wanted = args[0] if args else ["RELIANCE"]
        return [{"symbol": "RELIANCE", "statement": "standalone"}] if "RELIANCE" in wanted else []

    async def execute(self, sql, key, body):
        self.db[key] = json.loads(body)


class FakePool:
    def __init__(self):
        self.db = {}

    def acquire(self):
        pool = self

        class Ctx:
            async def __aenter__(self_):
                return FakeConn(pool.db)

            async def __aexit__(self_, *a):
                return False
        return Ctx()


class FakeStore:
    def __init__(self, sections):
        self.pool, self.sections = FakePool(), sections

    async def get_section(self, symbol, statement, name):
        import orjson
        return (orjson.dumps(self.sections[name]), "etag")


def test_run_stores_result_and_counts_mismatches(reliance_sections):
    store = FakeStore(reliance_sections)
    res = asyncio.run(pc.run(store, FakeClient(), ["RELIANCE"], pause=0))
    assert res["mismatches"] == 0 and res["level"] == "green" and res["calls"] == 9
    assert store.pool.db[pc.META_LAST]["companies"][0]["symbol"] == "RELIANCE"
    text = pc.render(res)
    assert "FinEdge" in text and "/daily-price-ratios/{symbol}" in text and "MISMATCH 0" in text
    bad = copy.deepcopy(reliance_sections)
    bad["ratios"]["latest"]["pe"]["value"] = 30.0
    res = asyncio.run(pc.run(FakeStore(bad), FakeClient(), ["RELIANCE"], pause=0))
    assert res["mismatches"] >= 1 and res["level"] == "red"


def test_missing_report_is_an_error_row_not_a_silent_skip(reliance_sections):
    store = FakeStore(reliance_sections)
    res = asyncio.run(pc.run(store, FakeClient(), ["NOSUCH"], pause=0))
    assert res["mismatches"] == 1 and "no stored report" in res["companies"][0]["error"]
