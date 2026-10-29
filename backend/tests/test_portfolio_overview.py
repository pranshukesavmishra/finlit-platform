"""POST /api/portfolio/overview: the My portfolio page's bulk read. Shape, plan gating (Silver: FinLit score and no Prism field; Gold: Prism and no FinLit
score block; Basic and visitors refused), ratios and financials equal to what the stock page shows (Reliance fixture), the preparing and unknown
statuses, the blank-figure reasons, and the 500 limit."""

import pytest

from finlit import portfolio_overview as po
from finlit.api import create_app
from test_auth import new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401  (fixtures)
from test_screener_prism import put

pytestmark = pytest.mark.integration


@pytest.fixture
async def app(ingested):  # noqa: F811
    from finlit.screener import data as screener_data
    app = create_app(make_settings(), store=ingested)
    async with app.router.lifespan_context(app):
        await ingested.pool.execute("DELETE FROM prism_reports")
        await ingested.pool.execute("DELETE FROM ingest_queue")
        yield app
    screener_data.reset()


async def ask(client, symbols):
    return await client.post("/api/portfolio/overview", json={"symbols": symbols})


async def test_silver_gets_the_finlit_score_and_no_prism_field(app):
    await put(app.state.store, "RELIANCE", final=71.2)
    silver = await signed_in(app, "s@example.com", plan="silver")
    r = await ask(silver, ["reliance"])
    assert r.status_code == 200 and r.headers["cache-control"].startswith("private") and "Cookie" in r.headers["vary"]
    body = r.json()
    assert body["model"] == "finlit" and body["plan"] == "silver" and body["count"] == 1
    h = body["holdings"][0]
    assert h["symbol"] == "RELIANCE" and h["status"] == "ready" and h["name"] and h["price"] and h["marketCapCr"] and h["sector"]
    assert h["finlit"]["overall"] is not None and h["finlit"]["word"] and set(h["finlit"]["pillars"]) == set(po.PILLARS)
    assert not any("prism" in k.lower() for k in h) and "prism" not in r.text.lower().replace("finlit prism", "")
    assert set(h["ratios"]) == {"pe", "pb", "roe", "dividend_yield", "debt_to_equity"} and set(h["financials"]) == {"year", "quarter"}


async def test_gold_gets_prism_only(app):
    await put(app.state.store, "RELIANCE", final=71.2)
    gold = await signed_in(app, "g@example.com", plan="gold")
    body = (await ask(gold, ["RELIANCE"])).json()
    assert body["model"] == "prism" and body["plan"] == "gold"
    h = body["holdings"][0]
    assert "finlit" not in h
    p = h["prism"]
    assert p["state"] == "rated" and p["final"] == 71.2 and p["label"] == "HEALTHY" and p["status"] == "RATED"
    assert p["parts"] == {"fundamental": 70.1, "valuation": 40.2, "quality": 80.3, "risk": 65.4}
    # the site's descriptive words, never the model's own
    assert p["shortTerm"] == {"score": 22.5, "word": "Positive"} and p["longTerm"] == {"score": -30.0, "word": "Strongly negative"}
    assert not {"buy", "sell", "hold"} & {str(v).lower() for v in (p["shortTerm"]["word"], p["longTerm"]["word"])}


async def test_gold_without_a_stored_rating_and_with_a_not_rated_one(app):
    store = app.state.store
    gold = await signed_in(app, "g@example.com", plan="gold")
    none = (await ask(gold, ["RELIANCE"])).json()["holdings"][0]["prism"]
    assert none["state"] == "none" and none["final"] is None and none["parts"] is None
    await put(store, "RELIANCE", final=None, label="NOT RATED", status="NOT RATED", parts=False)
    await store.pool.execute("""UPDATE prism_reports SET report = jsonb_set(report, '{rating,notRatedReasons}', '[{"code": "insufficient_history", "text": "Only 3 years of reported history."}]')""")
    await store.redis.flushdb()
    nr = (await ask(gold, ["RELIANCE"])).json()["holdings"][0]["prism"]
    assert nr["state"] == "not_rated" and nr["final"] is None and nr["parts"] is None and nr["reason"] == "Only 3 years of reported history."


async def test_plan_gates_and_the_symbol_limit(app):
    anon = new_client(app)
    assert (await ask(anon, ["RELIANCE"])).status_code == 401
    basic = await signed_in(app, "b@example.com")
    r = await ask(basic, ["RELIANCE"])
    assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_required"
    silver = await signed_in(app, "s@example.com", plan="silver")
    assert (await ask(silver, [f"S{i}" for i in range(500)])).status_code == 200
    r = await ask(silver, [f"S{i}" for i in range(501)])
    assert r.status_code == 400 and r.json()["detail"]["status"] == "too_many"
    assert (await ask(silver, ["bad symbol!"])).status_code == 400
    assert (await ask(silver, [])).json()["holdings"] == []


async def test_ratios_and_financials_equal_the_stock_page(app):
    gold = await signed_in(app, "g@example.com", plan="gold")
    h = (await ask(gold, ["RELIANCE"])).json()["holdings"][0]
    page = (await gold.get("/api/stocks/RELIANCE/ratios")).json()
    for key in ("pe", "pb", "roe", "dividend_yield", "debt_to_equity"):
        shown = page["latest"][key]
        assert h["ratios"][key]["value"] == shown["value"] and h["ratios"][key]["period"] == shown["period"], key
    fin = (await gold.get("/api/stocks/RELIANCE/financials")).json()
    pl = fin["yearly"]["pl"]
    y = h["financials"]["year"]
    assert y["period"] == pl["periods"][-1] and y["periodEnd"] == pl["periodEnds"][-1]
    for field in ("revenue", "other_income", "operating_profit", "finance_costs", "net_profit", "eps"):
        assert y[field]["value"] == pl["rows"][field][-1], field
    assert y["tax_ratio"]["value"] == pytest.approx(pl["rows"]["tax"][-1] / pl["rows"]["profit_before_tax"][-1] * 100, abs=0.01)
    q = fin["quarterly"]["pl"]
    assert h["financials"]["quarter"]["period"] == q["periods"][-1] and h["financials"]["quarter"]["net_profit"]["value"] == q["rows"]["net_profit"][-1]
    summary = (await gold.get("/api/stocks/RELIANCE")).json()
    assert h["price"] == summary["quote"]["price"] and h["changePct"] == summary["quote"]["changePct"] and h["marketCapCr"] == summary["profile"]["marketCapCr"]
    assert h["basis"] in ("consolidated", "standalone")
    silver = await signed_in(app, "s@example.com", plan="silver")
    s = (await ask(silver, ["RELIANCE"])).json()["holdings"][0]
    assert s["finlit"]["overall"] == summary["score"]["overall"]
    assert s["finlit"]["pillars"] == {p["key"]: p["score"] for p in summary["score"]["pillars"]}


async def test_preparing_and_unknown_companies(app):
    silver = await signed_in(app, "s@example.com", plan="silver")
    r = (await ask(silver, ["RELIANCE", "TCS", "ZZNOSUCH", "TCS"])).json()
    assert [h["symbol"] for h in r["holdings"]] == ["RELIANCE", "TCS", "ZZNOSUCH"]
    tcs, nosuch = r["holdings"][1], r["holdings"][2]
    assert tcs["status"] == "preparing" and tcs["reason"] and "finlit" not in tcs and "ratios" not in tcs
    assert nosuch["status"] == "unknown" and nosuch["reason"]
    queued = [x["symbol"] for x in await app.state.store.pool.fetch("SELECT symbol FROM ingest_queue")]
    assert queued == ["TCS"]                                  # built the way opening its page builds it; the unknown one is never queued


def holding_from(parts, gold=False, prism=None):
    return po.holding("X", parts, prism, gold)


def test_blank_figures_carry_their_reason():
    summary = {"isBank": True, "profile": {"name": "Some Bank", "marketCapCr": 5000}, "quote": {"price": 10, "changePct": 1}}
    ratios = {"latest": {"pb": {"value": 1.5, "period": "As of 1 Oct"}}, "blanks": {"pe": "FinEdge sent no P/E and it cannot be worked out."}}
    fin = {"yearly": {"periods": ["FY26"], "ends": ["2026-03-31"], "rows": {"revenue": [100.0], "net_profit": [-5.0], "profit_before_tax": [-2.0], "tax": [3.0],
                                                                         "operating_profit": [9.0], "eps": [None]}, "equity": [50.0]}, "quarterly": {}}
    h = holding_from({"summary": summary, "ratios": ratios, "financials": fin})
    assert h["ratios"]["debt_to_equity"]["why"].startswith("Not applicable to banks")
    assert h["ratios"]["pe"]["why"].startswith("Loss-making")
    assert h["ratios"]["pb"]["value"] == 1.5
    assert h["ratios"]["roe"]["why"] and h["ratios"]["dividend_yield"]["why"]
    y = h["financials"]["year"]
    assert y["operating_profit"]["value"] is None and "banks" in y["operating_profit"]["why"]
    assert y["tax_ratio"]["value"] is None and y["tax_ratio"]["why"]
    assert y["eps"]["value"] is None and "FY26" in y["eps"]["why"]
    assert h["financials"]["quarter"]["available"] is False and h["financials"]["quarter"]["why"]
    ratios["blanks"] = {}
    neg = holding_from({"summary": {**summary, "isBank": False}, "ratios": ratios, "financials": {**fin, "yearly": {**fin["yearly"], "equity": [-1.0]}}})
    assert "equity is zero or negative" in neg["ratios"]["roe"]["why"] and "equity" in neg["ratios"]["debt_to_equity"]["why"]


def test_symbol_cleaning():
    assert po.clean_symbols(["tcs", " TCS ", "m&m"]) == ["TCS", "M&M"]
    with pytest.raises(Exception):
        po.clean_symbols(["a b"])
