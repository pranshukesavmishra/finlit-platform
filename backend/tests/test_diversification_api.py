"""POST /api/diversification end to end: 422s for anything but share names, the sample list through the real endpoint, caching, plan lock on the style tilt."""

import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from finlit.diversification import api as div_api
from finlit.indices import IST
from finlit.store import stock_key
from test_auth import app, new_client, signed_in  # noqa: F401  (fixtures + helpers)
from test_integration import ingested, make_settings, store  # noqa: F401
from test_diversification_calc import PRICES_MAX, PRISM, SAMPLE, ref

pytestmark = pytest.mark.integration
URL = "/api/diversification"
EXPECTED = json.loads((Path(__file__).parent / "fixtures" / "diversification" / "expected_output.json").read_text())
LABELS = {"Oil & gas": "Oil Gas & Consumable Fuels", "Financial services": "Banks", "Information technology": "Information Technology", "FMCG": "Fast Moving Consumer Goods",
          "Construction": "Construction", "Telecom": "Telecommunication", "Metals & mining": "Metals & Mining", "Healthcare": "Healthcare"}


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(div_api, "now_ist", lambda: datetime(2026, 11, 4, 12, 0, tzinfo=IST))     # a Wednesday in ISO week 2026-W45

    async def universe(_app):
        return [dict(zip(PRISM["cols"], r)) | {"prism_status": r[1]} for r in PRISM["rows"]]
    monkeypatch.setattr(div_api, "_prism_universe", universe)


async def seed(app, symbols=SAMPLE):
    st = app.state.store
    async with st.pool.acquire() as conn:
        for i, s in enumerate(symbols):
            await conn.execute("INSERT INTO companies (symbol, name, sector) VALUES ($1, $2, $3) ON CONFLICT (symbol) DO UPDATE SET sector = EXCLUDED.sector, name = EXCLUDED.name",
                               s, s.title(), LABELS[ref.SAMPLE_SECTORS[s]])
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2) ON CONFLICT (symbol) DO UPDATE SET market_cap = EXCLUDED.market_cap", s, ref.SAMPLE_MCAP_CR[s])
        await conn.execute("INSERT INTO companies (symbol, name, sector) VALUES ('NEWCO', 'New Co', 'Healthcare') ON CONFLICT (symbol) DO NOTHING")
    for s in symbols:
        series = {"t": PRICES_MAX[s]["t"], "c": PRICES_MAX[s]["c"]}
        await st.redis.hset(stock_key(s, "consolidated"), mapping={"price-MAX": json.dumps({"series": series}), "price-MAX:etag": "x"})
    t = PRICES_MAX["TCS"]
    await st.redis.hset(stock_key("NEWCO", "consolidated"), mapping={"price-MAX": json.dumps({"series": {"t": t["t"][-20:], "c": t["c"][-20:]}}), "price-MAX:etag": "x"})
    rows = [{"quote_date": r["d"], "close_price": r["c"]} for r in PRICES_MAX["__NIFTY"]["rows"]]
    await st.redis.set("idx:px:NIF50", json.dumps({"t": time.time(), "v": {"rows": rows}}))


async def test_only_share_names_are_accepted(app):  # noqa: F811
    async with new_client(app) as c:
        base = {"symbols": ["TCS", "INFY", "HCLTECH"]}
        for extra in ({"quantity": [10, 5, 1]}, {"amount": 5000}, {"price": 3500.5}, {"date": "2026-01-01"}, {"qty": 1}, {"weights": [1, 1, 1]}):
            r = await c.post(URL, json={**base, **extra})
            assert r.status_code == 422, extra
            assert "Cache-Control" in r.headers
        assert (await c.post(URL, json={**base, "horizon": "daily"})).status_code == 422
        assert (await c.post(URL, json={**base, "horizon": "Weekly"})).status_code == 422
        assert (await c.post(URL, json={**base, "benchmark": "NIFBAN"})).status_code == 422
        assert (await c.post(URL, json={"symbols": []})).status_code == 422
        assert (await c.post(URL, json={"symbols": ["bad symbol!"]})).status_code == 422
        assert (await c.post(URL, json={"symbols": [f"S{i}" for i in range(101)]})).status_code == 422
        assert (await c.post(URL, json={"symbols": [{"symbol": "TCS", "qty": 3}]})).status_code == 422


async def test_sample_list_through_the_endpoint(app):  # noqa: F811
    await seed(app)
    async with new_client(app) as c:
        r = await c.post(URL, json={"symbols": [s.lower() for s in SAMPLE], "benchmark": "NIF50"})
        assert r.status_code == 200, r.text
        j = r.json()
        # one score on the site: the card shows the My portfolio engine's score (104 weeks, plain correlations); calc's own 156-week figure is in expected_output.json
        assert j["score"] == {**EXPECTED["score"], "value": 68, "unrounded": 68.0, "coMovement": 66, "effectiveSectors": 4.4} and j["scoreVersion"] == "1" and j["horizon"] == "weekly"
        assert j["headline"] == {**EXPECTED["headline"], "effectiveStocks": 5.9, "effectiveStocksRounded": 6} and j["clusters"] == EXPECTED["clusters"]
        assert j["asOf"]["fromWeek"] == "2023-W45" and j["asOf"]["toWeek"] == "2026-W44" and j["asOf"]["label"] == "Nov 2023 – Oct 2026"
        assert j["spread"]["sectors"][0] == {"name": "Financial services", "count": 6} and j["spread"]["size"] == {"Large": 15, "Mid": 0, "Small": 0}
        assert j["spread"]["groups"] == [{"name": "Tata", "symbols": ["TCS", "TATASTEEL"]}]      # Bajaj and Reliance have one stock each: not a concentration
        assert j["market"]["betaEqual"] == 0.96 and j["recentVsLongRun"]["recent"]["effectiveStocks"] == 6.78
        assert j["excluded"] == [] and "Vary" in r.headers and r.headers["cache-control"] == "private, no-store"


async def test_monthly_yearly_and_score_unchanged(app):  # noqa: F811
    await seed(app)
    async with new_client(app) as c:
        body = {"symbols": SAMPLE}
        w = (await c.post(URL, json=body)).json()
        m = (await c.post(URL, json={**body, "horizon": "monthly"})).json()
        y = (await c.post(URL, json={**body, "horizon": "yearly"})).json()
        assert m["score"] == w["score"] == y["score"]
        assert m["headline"]["avgCorrelation"] == 0.28 and m["headline"]["effectiveStocks"] == 6.4 and m["market"]["betaEqual"] == 0.91 and m["market"]["benchmarkReturns"] == 59
        assert len(m["clusters"]) == 3
        assert y["indicative"] is True and y["headline"]["effectiveStocks"] == 4.09 and y["headline"]["avgCorrelation"] == 0.49 and "clusters" not in y
        assert y["asOf"]["effectiveObservations"] == 6.8


async def test_short_list_and_short_history(app):  # noqa: F811
    await seed(app)
    async with new_client(app) as c:
        two = (await c.post(URL, json={"symbols": ["TCS", "INFY"]})).json()
        assert "score" not in two and two["needsThree"] is True and two["spread"]["sectors"] == [{"name": "Information technology", "count": 2}]
        assert "styleTilt" not in two
        j = (await c.post(URL, json={"symbols": SAMPLE + ["NEWCO"]})).json()
        assert j["excluded"][0]["symbol"] == "NEWCO" and j["excluded"][0]["reason"] == "history" and j["included"] == 15
        assert {"name": "Healthcare", "count": 2} in j["spread"]["sectors"]
        u = (await c.post(URL, json={"symbols": SAMPLE + ["ZZUNKNOWN"]})).json()
        assert {"symbol": "ZZUNKNOWN", "reason": "unknown", "weeks": 0} in u["excluded"] and u["score"]["value"] == 68


async def test_style_tilt_is_gold_only(app):  # noqa: F811
    await seed(app)
    async with new_client(app) as anon:
        j = (await anon.post(URL, json={"symbols": SAMPLE})).json()
        assert j["styleTilt"]["locked"] == "gold" and "Gold" in j["styleTilt"]["reason"] and "parts" not in j["styleTilt"]
    gold = await signed_in(app, "gdiv@example.com", plan="gold")
    t = (await gold.post(URL, json={"symbols": SAMPLE})).json()["styleTilt"]
    assert [p["avgPercentile"] for p in t["parts"]] == [53, 61, 65, 82, 72, 48] and t["universe"] == 650 and t["notRated"] == []
    assert t["sentence"].startswith("This list leans towards lower-risk and higher-quality companies")


async def test_second_call_is_served_from_the_cache(app, monkeypatch):  # noqa: F811
    await seed(app)
    async with new_client(app) as c:
        await c.post(URL, json={"symbols": SAMPLE})
        monkeypatch.setattr(div_api, "_build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recomputed")))
        r = await c.post(URL, json={"symbols": list(reversed(SAMPLE))})           # same names in another order: same cache entry
        assert r.status_code == 200 and r.json()["score"]["value"] == 68
