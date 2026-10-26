import asyncio
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import jwt
import pytest
from pypdf import PdfReader
from backend import server
from backend.premium_engine import score_company
from backend.premium_data import adapt_inputs, resolve_group, peer_benchmark
from backend.premium_pdf import render_premium_pdf
def asgi_request(app, method, path, payload=None, headers=None):
    async def run():
        finished = asyncio.Event()
        sent = False
        messages = []
        async def receive():
            nonlocal sent
            if sent:
                await finished.wait()
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": json.dumps(payload).encode() if payload is not None else b"", "more_body": False}
        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False): finished.set()
        request_headers = {"host": "localhost", "content-type": "application/json", **(headers or {})}
        await app({"type": "http", "http_version": "1.1", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"", "headers": [(k.lower().encode(),v.encode()) for k,v in request_headers.items()], "scheme": "http", "server": ("localhost",80), "client": ("127.0.0.1",123), "root_path": ""}, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body",b"") for m in messages if m["type"] == "http.response.body")
        try: return status, json.loads(body)
        except (ValueError, UnicodeDecodeError): return status, body
    return asyncio.run(run())


@pytest.fixture
def example():
    return json.loads(Path(__file__).with_name("premium_example.json").read_text())


def sample_report(example):
    rating = score_company(example, "MFG")
    return {"id": "a" * 32, "state": "ready", "company": {"symbol": "EXAMPLE", "name": "Sample Engineering Ltd", "industry": "Capital Goods / Engineering"},
            "statementType": "consolidated", "createdAt": "2026-10-18T00:00:00+00:00", "rating": rating,
            "inputMeta": {"quarterlyAsOf": "2026-06-30", "annualAsOf": "2026-03-31", "balanceAsOf": "2026-03-31", "ownershipAsOf": "2026-06-30", "priceAsOf": "2026-10-16"},
            "trends": [{"period": "2026", "revenue": 4295, "profit": 346, "eps": 36.2}],
            "benchmark": {"source": "Test universe", "asOf": "2026-10-16", "universeCount": 6, "fetchedCount": 6, "note": "Verified test fixture"},
            "warnings": ["Test warning"], "sources": [{"section": "annual", "available": True, "retrievedAt": "2026-10-18T00:00:00+00:00"}], "inputHash": "f" * 64}


def test_engine_preserves_full_history_and_uses_available_cagr_in_short_history(example):
    result = score_company(example, "MFG")
    assert result["final"] == pytest.approx(54.496, abs=.001)
    assert result["label"] == "AVERAGE" and result["status"] == "RATED"
    assert result["confidence"] == 1
    assert sum(row["pointsEarned"] for row in result["metrics"]) - result["capPointsLost"] == pytest.approx(result["final"])
    assert sum(row["pointsLost"] for row in result["metrics"]) + result["capPointsLost"] == pytest.approx(100 - result["final"])
    for key in ("sales_q", "net_profit_q", "operating_profit_q", "eps_q"): example[key] = example[key][-6:]
    for key in ("sales_y", "net_profit_y"): example[key] = example[key][-3:]
    example["own_5y_median_pe"] = None
    result = score_company(example, "MFG")
    # Two-year annual growth now replaces both former group fills, and PEG
    # consumes the available profit CAGR under its existing preference rule.
    rows={row['metric']:row for row in result['metrics']}
    assert rows['SALES_CAGR']['value']==pytest.approx(((4295/3200)**.5-1)*100)
    assert rows['PROFIT_CAGR']['value']==pytest.approx(((346/240)**.5-1)*100)
    assert result["final"] == pytest.approx(53.4388, abs=.001)
    assert result["status"] == "PROVISIONAL"
    assert result["confidence"] == pytest.approx(.872)


def test_engine_zero_inputs_missing_histories_and_loss_rules(example):
    example.update(volatility_pct=0, biggest_fall_pct=0, trading_value_cr=0)
    result = score_company(example, "MFG")
    rows = {row["metric"]: row for row in result["metrics"]}
    assert rows["VOLATILITY"]["value"] == 0 and rows["VOLATILITY"]["points"] == 100
    assert rows["TRADING_VALUE"]["points"] == 0
    example.update(eps_q=[-1] * 14, industry_median_pe=None, own_5y_median_pe=None)
    result = score_company(example, "MFG")
    rows = {row["metric"]: row for row in result["metrics"]}
    assert all(rows[m]["status"] == "Z" and rows[m]["points"] == 0 for m in ("PE_VS_INDUSTRY", "PE_VS_HISTORY", "PEG"))
    example["net_profit_y"] = []
    assert score_company(example, "MFG")["metrics"]
    result = score_company({}, "BANK")
    assert result["status"] == "NOT RATED" and result["final"] is None
    assert "score " not in result["headline"].lower()


def test_missing_pledge_lowers_confidence_and_fills_never_become_strengths(example):
    example["promoter_pledged_pct"] = None
    result = score_company(example, "MFG")
    assert result["confidence"] == pytest.approx(.98)
    pledge = next(row for row in result["metrics"] if row["metric"] == "PLEDGE")
    assert pledge["status"] == "L" and pledge["share"] == 0
    assert all(row["status"] not in ("F", "L", "N") for row in result["strengths"] + result["weaknesses"] + result["flags"])


@pytest.mark.parametrize("group", ["LIGHT", "MFG", "HEAVY", "UTILITY", "REALTY", "BANK", "NBFC", "INSURANCE"])
def test_every_group_handles_empty_inputs_without_crashing(group):
    result = score_company({}, group)
    assert result["final"] is None and result["status"] == "NOT RATED"
    json.dumps(result, allow_nan=False)


def test_adapter_retains_quarter_gaps_uses_crore_shares_and_owner_profit():
    raw = {"profile": {"industry": "IT - Software"},
           "quarterly": {"financials": [{"period_end": 20260331, "revenueFromOperations": 100_000_000, "profitAttributableToOwnersOfParent": 10_000_000, "profitLossForPeriod": 99_000_000, "basicReInr": 2},
                                        {"period_end": 20250930, "revenueFromOperations": 90_000_000}]},
           "annual": {"financials": [{"year": 2026, "revenueFromOperations": 100_000_000}]},
           "summary": {"summary": [{"header": "Mar 2026", "paidUpEquityShares": 20_000_000}]},
           "declaration": {"declaration": [{"header": "Mar 2026", "pledgedSharesForPromoterAndGroup": False}]},
           "quote": {"TEST": {"price": 100, "shares": 99_000_000, "tradetime": "2026-10-16T15:30:00Z"}}}
    d, group, _, meta, _, _ = adapt_inputs(raw, "TEST", date(2026,10,18), "consolidated")
    assert group == "LIGHT"
    assert d["sales_q"] == [9, None, 10]
    assert d["net_profit_q"][-1] == 1
    assert d["shares"] == 2
    assert d["promoter_pledged_pct"] == 0
    assert meta["statementType"] == "consolidated"
    assert d["eps_q"][-1] == 2


def test_lender_does_not_substitute_revenue_or_cet1_for_model_inputs():
    raw = {"profile": {"industry": "Banks", "sector": "Private Sector Bank"}, "quarterly": {"financials": [{"period_end": 20260630, "interestEarned": 100_000_000, "cET1Ratio": .19, "percentageOfGrossNpa": .011, "percentageOfNpa": .002}]}}
    d, group, *_ = adapt_inputs(raw, "BANK", date(2026,10,18), "consolidated")
    assert group == "BANK" and d["sales_q"] == [None]
    assert d["capital_adequacy_pct"] is None
    assert d["gross_npa_pct"] == pytest.approx(1.1)
    assert d["net_npa_pct"] == pytest.approx(.2)
    assert resolve_group({"industry": "Finance", "sector": "Non Banking Financial Company (NBFC)"})[0] == "NBFC"


def test_benchmarks_require_full_universe_current_data_and_five_positive_peers():
    peers = {"peers": ["A", "B", "C", "D", "E"]}
    def get(path, params):
        index = ord(path.rsplit("/",1)[-1]) - ord("A")
        return {"price_ratios": [{"quote_date": "2026-10-16", "pe": 10 + index, "pb": 1 + index}]}
    data, meta = peer_benchmark(get, peers, "consolidated", date(2026,10,18))
    assert data["industry_median_pe"] == 12 and data["industry_median_pb"] == 3
    assert meta["fetchedCount"] == 5
    assert peer_benchmark(get, {"peers": ["A", "B", "C", "D"]}, "consolidated", date(2026,10,18))[0] == {}
    def incomplete(path, params):
        return {} if path.endswith("/A") else get(path, params)
    assert peer_benchmark(incomplete, peers, "consolidated", date(2026,10,18))[0] == {}


def test_pdf_uses_saved_snapshot_escapes_company_and_withholds_not_rated_score(example):
    report = sample_report(example)
    report["company"]["name"] = "A & B <Research>"
    pdf = render_premium_pdf(report)
    reader = PdfReader(BytesIO(pdf))
    content = "\n".join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) >= 4
    assert "54.50 / 100" in content and "A & B <Research>" in content
    assert report["inputHash"] not in content.replace("\n", "")
    report["rating"] = score_company({}, "BANK")
    content = "\n".join(page.extract_text() for page in PdfReader(BytesIO(render_premium_pdf(report))).pages)
    assert "NOT RATED" in content and "54.50 / 100" not in content


def auth():
    token = jwt.encode({"sub": "admin@example.test", "role": "admin", "iat": int(time.time()), "exp": int(time.time()) + 120}, "test-only-jwt-secret-with-more-than-32-bytes", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def memory_report(monkeypatch, report, expires=None):
    monkeypatch.setattr(server, "_premium_jobs", {report["id"]: {"report": deepcopy(report), "expires": server.monotonic() + 1800 if expires is None else expires}})


def test_report_routes_require_admin_and_use_no_database(monkeypatch, example):
    class NoDatabase:
        def __getattr__(self, name): pytest.fail("On-demand reports must not access the database")
    monkeypatch.setattr(server, "db", NoDatabase())
    monkeypatch.setattr(server, "_premium_jobs", {})
    monkeypatch.setattr(server, "_resolve_finedge_stock", lambda query: {"symbol": "TEST", "name": "Test Ltd"})
    called = []
    async def task(*args): called.append(args)
    monkeypatch.setattr(server, "_generate_premium_report", task)
    for method, path, body in [("POST", "/api/premium-reports", {"query": "TEST"}), ("GET", "/api/premium-reports/" + "a"*32, None), ("GET", "/api/premium-reports/" + "a"*32 + "/pdf", None)]:
        assert asgi_request(server.app, method, path, body)[0] == 401
    # There is no history/list endpoint, including for authenticated administrators.
    assert asgi_request(server.app, "GET", "/api/premium-reports", headers=auth())[0] == 405
    code, data = asgi_request(server.app, "POST", "/api/premium-reports", {"query": "TEST"}, auth())
    assert code == 202 and data["state"] == "generating"
    assert server._premium_jobs[data["id"]]["report"] == data and called[0][0] == data["id"]
    assert asgi_request(server.app, "GET", "/api/premium-reports/invalid", headers=auth())[0] == 404
    assert asgi_request(server.app, "GET", "/api/premium-reports/" + data["id"], headers=auth())[0] == 200


def test_interrupted_report_and_pdf_readiness(monkeypatch):
    record = {"id": "a"*32, "state": "generating", "createdAt": "2020-01-01T00:00:00+00:00"}
    memory_report(monkeypatch, record)
    result = asyncio.run(server._current_premium_report("a"*32))
    assert result["state"] == "failed"
    assert asgi_request(server.app, "GET", "/api/premium-reports/"+"a"*32+"/pdf", headers=auth())[0] == 409


def test_temporary_reports_expire_and_unknown_old_links_are_not_loaded(monkeypatch, example):
    memory_report(monkeypatch, sample_report(example), expires=server.monotonic()-1)
    assert asgi_request(server.app, "GET", "/api/premium-reports/"+"a"*32, headers=auth())[0] == 404
    assert server._premium_jobs == {}
    assert asgi_request(server.app, "POST", "/api/premium-reports/"+"a"*32+"/download-link", headers=auth())[0] == 404


def test_generation_completes_in_memory_without_database(monkeypatch, example):
    from backend import premium_service
    report=sample_report(example)
    memory_report(monkeypatch, {**report,"state":"generating"})
    monkeypatch.setattr(premium_service,"generate_report",lambda *args:report)
    asyncio.run(server._generate_premium_report(report['id'],'TEST','Test','consolidated',report['createdAt']))
    assert server._premium_jobs[report['id']]['report']==report



def test_value_trap_cap_and_score_reconciliation(example):
    example.update(price=1, sales_q=[200 - i for i in range(14)], net_profit_q=[40 - i for i in range(14)], sales_y=[500,450,400,350,300,250], net_profit_y=[100,90,80,70,60,50])
    result = score_company(example, "MFG")
    assert result["valuationCapped"] and result["parts"]["valuation"] == 60
    assert sum(row["pointsEarned"] for row in result["metrics"]) - result["capPointsLost"] == pytest.approx(result["final"])
    assert sum(row["pointsLost"] for row in result["metrics"]) + result["capPointsLost"] == pytest.approx(100 - result["final"])


def test_successful_pdf_route_uses_current_calculation_without_provider_call(monkeypatch, example):
    memory_report(monkeypatch, sample_report(example))
    def forbidden(*args, **kwargs): pytest.fail("Download must not fetch or recalculate data")
    monkeypatch.setattr(server, "_finedge_get", forbidden)
    status, pdf = asgi_request(server.app, "GET", "/api/premium-reports/"+"a"*32+"/pdf", headers=auth())
    assert status == 200 and pdf.startswith(b"%PDF")


def test_adapter_excludes_ytd_quarter_and_prefers_latest_restatement():
    raw = {"profile": {"industry": "IT - Software"}, "quarterly": {"financials": [
        {"period_end": 20260331, "period_start": 20260101, "result_date": 20260501, "revenueFromOperations": 100_000_000},
        {"period_end": 20260331, "period_start": 20260101, "result_date": 20260401, "revenueFromOperations": 90_000_000},
        {"period_end": 20251231, "period_start": 20250401, "revenueFromOperations": 500_000_000},
        {"period_end": 20250930, "period_start": 20250701, "revenueFromOperations": 80_000_000},
    ]}}
    inputs, _, _, _, warnings, _ = adapt_inputs(raw, "TEST", date(2026,10,18), "consolidated")
    assert inputs["sales_q"] == [8, None, 10]
    assert any("non-comparable" in warning for warning in warnings)


def test_quote_share_count_conflict_never_overrides_dated_filing():
    raw = {"summary": {"summary": [{"header": "Jun 2026", "paidUpEquityShares": 13_300_000_000}]},
           "quote": {"TEST": {"current_price": 1210, "shares": 6_330_000_000, "market_cap": 1_637_437}}}
    inputs, _, _, meta, warnings, _ = adapt_inputs(raw, "TEST", date(2026,10,18), "consolidated")
    assert inputs["shares"] == 1330
    assert any("quote share count conflicts" in warning for warning in warnings)
    assert "ownership summary" in meta["provenance"]["shares"][0]
    raw["summary"] = {}
    assert adapt_inputs(raw, "TEST", date(2026,10,18), "consolidated")[0]["shares"] is None


def test_native_download_capability_is_admin_minted_bound_expiring_and_one_use(monkeypatch, example):
    monkeypatch.setattr(server, "_premium_pdf_tokens", {})
    memory_report(monkeypatch, sample_report(example))
    mint = "/api/premium-reports/" + "a"*32 + "/download-link"
    assert asgi_request(server.app, "POST", mint)[0] == 401
    status, link = asgi_request(server.app, "POST", mint, headers=auth())
    assert status == 200 and link["expiresIn"] == 120
    status, body = asgi_request(server.app, "GET", link["url"])
    assert status == 200 and body.startswith(b"%PDF")
    assert asgi_request(server.app, "GET", link["url"])[0] == 404
    _, link = asgi_request(server.app, "POST", mint, headers=auth())
    for capability in server._premium_pdf_tokens.values(): capability["expires"] = 0
    assert asgi_request(server.app, "GET", link["url"])[0] == 404
    assert asgi_request(server.app, "GET", "/api/premium-report-downloads/guess")[0] == 404


def test_temporary_generation_failure_is_reported_without_storage(monkeypatch, example):
    from backend import premium_service
    report=sample_report(example)
    memory_report(monkeypatch,{**report,'state':'generating'})
    def fail(*args):raise ValueError('provider unavailable')
    monkeypatch.setattr(premium_service,'generate_report',fail)
    asyncio.run(server._generate_premium_report(report['id'],'TEST','Test','consolidated',report['createdAt']))
    assert server._premium_jobs[report['id']]['report']['state']=='failed'


def test_completed_work_cannot_resurrect_an_expired_job(monkeypatch, example):
    from backend import premium_service
    report=sample_report(example)
    memory_report(monkeypatch,{**report,'state':'generating'})
    def finish_after_expiry(*args):
        server._premium_jobs.clear()
        return report
    monkeypatch.setattr(premium_service,'generate_report',finish_after_expiry)
    asyncio.run(server._generate_premium_report(report['id'],'TEST','Test','consolidated',report['createdAt']))
    assert server._premium_jobs=={}
