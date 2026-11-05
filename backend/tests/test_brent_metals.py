"""Brent crude (U.S. EIA, daily) and copper, aluminium, natural gas (World Bank Pink Sheet, monthly) in the Macro Outlook, the India macro page and the Commodities page.
Fixtures only: no test reaches a network."""
import io
import json
from datetime import date, timedelta

import httpx
import openpyxl
import pytest

from finlit import commodities as cm
from finlit import macro
from finlit.macro_outlook import seed as SEED
from finlit.macro_outlook import store as ST
from finlit.macro_outlook import views as V
from test_integration import store  # noqa: F401
from test_macro import mstore  # noqa: F401
from test_macro_outlook import MO_TABLES, mo  # noqa: F401

D = date
TODAY = D(2026, 11, 5)
ADVICE = ("buy", "sell", "hold", "reduce", "avoid", "accumulate", "target", "best", "multibagger", "top pick", "recommend")


def daily(last: date, n: int, base=80.0):
    return {last - timedelta(days=i): round(base + (i % 7) * .4, 2) for i in range(n)}


def monthly(last_month_end: date, n: int, base: float):
    out, d = {}, last_month_end
    for i in range(n):
        out[d] = round(base + i * 3, 2)
        d = D(d.year, d.month, 1) - timedelta(days=1)
    return out


async def put(conn, series, pts):
    await macro.save_points(conn, series, pts)


async def sectors(mo_):
    async with mo_.pool.acquire() as conn:
        version = await conn.fetchval("SELECT model_version FROM macro_model_configuration WHERE active")
        return {s["sector"]["code"]: s for s in (await V.impact(conn, version))["sectors"]}, version


async def seed_all_but_commodities(mo_):
    from test_macro_outlook import load_macro
    await load_macro(mo_)


# ------------------------------------------------------------------------------------------------------------ the outlook reads the public series
@pytest.mark.integration
async def test_fresh_brent_removes_missing_critical_brent_for_oil_marketing(mo):
    await seed_all_but_commodities(mo)
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    before, _ = await sectors(mo)
    assert "BRENT" in before["oil_marketing"]["criticalMissing"] and before["oil_marketing"]["status"] != "ok"
    async with mo.pool.acquire() as conn:
        await put(conn, "brent_d", daily(D(2026, 10, 21), 400))
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    after, _ = await sectors(mo)
    assert after["oil_marketing"]["criticalMissing"] == [] and "BRENT" not in after["oil_marketing"]["missing"] and after["oil_marketing"]["status"] == "ok"
    async with mo.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM macro_indicators WHERE indicator_code = 'BRENT'")
    assert row["status"] == "Available" and row["source"] == "U.S. EIA" and row["observation_date"] == D(2026, 10, 21) and row["pub_date_basis"] == ST.ASSUMED
    assert "2 days since the observation date" in row["detail"]


@pytest.mark.integration
async def test_monthly_copper_aluminium_gas_complete_auto_ancillaries_and_fertilisers(mo):
    await seed_all_but_commodities(mo)
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    before, _ = await sectors(mo)
    assert {"COPPER", "ALUMINIUM"} <= set(before["auto_ancillaries"]["missing"]) or before["auto_ancillaries"]["status"] != "ok"
    async with mo.pool.acquire() as conn:
        await put(conn, "brent_d", daily(D(2026, 10, 21), 400))
        await put(conn, "copper_m", monthly(D(2026, 9, 30), 14, 9000))
        await put(conn, "aluminium_m", monthly(D(2026, 9, 30), 14, 2500))
        await put(conn, "natgas_m", monthly(D(2026, 9, 30), 14, 3))
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    after, _ = await sectors(mo)
    asc = after["auto_ancillaries"]
    assert "COPPER" not in asc["missing"] and "ALUMINIUM" not in asc["missing"] and asc["status"] == "ok" and asc["coverage"] >= 0.7
    assert after["fertilisers"]["criticalMissing"] == [] and "NATGAS" not in after["fertilisers"]["missing"]
    async with mo.pool.acquire() as conn:
        cur = {r["indicator_code"]: r for r in await conn.fetch("SELECT * FROM macro_indicators WHERE indicator_code IN ('COPPER', 'ALUMINIUM', 'NATGAS')")}
        sig = await conn.fetchval("SELECT final_signal FROM macro_indicator_signals WHERE indicator_code = 'COPPER' ORDER BY calculation_date DESC LIMIT 1")
    assert all(r["status"] == "Available" and r["source"].startswith("World Bank") and r["frequency"] == "Monthly" and r["observation_date"] == D(2026, 9, 30) for r in cur.values())
    assert sig is not None


@pytest.mark.integration
async def test_no_key_and_failed_download_reasons_stay_honest(mo):
    await seed_all_but_commodities(mo)
    async with mo.pool.acquire() as conn:
        await macro.set_meta(conn, "run:eia_brent", {"status": "nokey", "reason": macro.EIA_NO_KEY})
        await macro.set_meta(conn, "run:worldbank", {"status": "failed", "reason": "World Bank answered 503"})
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    async with mo.pool.acquire() as conn:
        rows = {r["indicator_code"]: r for r in await conn.fetch("SELECT * FROM macro_indicators WHERE indicator_code IN ('BRENT', 'COPPER')")}
    assert rows["BRENT"]["status"] == "Missing" and "Brent: source key not set" in rows["BRENT"]["detail"]
    assert rows["COPPER"]["status"] == "Missing" and "download from the World Bank failed" in rows["COPPER"]["detail"]
    got, _ = await sectors(mo)
    assert "BRENT" in got["oil_marketing"]["criticalMissing"]


@pytest.mark.integration
async def test_stale_public_series_are_flagged_and_excluded(mo):
    await seed_all_but_commodities(mo)
    async with mo.pool.acquire() as conn:
        await put(conn, "brent_d", daily(D(2026, 9, 1), 400))                    # 52 days old against a 10 day limit
        await put(conn, "copper_m", monthly(D(2026, 5, 31), 14, 9000))            # 145 days old against a 75 day limit
        await put(conn, "aluminium_m", monthly(D(2026, 9, 30), 14, 2500))         # 23 days old: fine for a monthly series
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    async with mo.pool.acquire() as conn:
        rows = {r["indicator_code"]: r for r in await conn.fetch("SELECT indicator_code, status FROM macro_indicators WHERE indicator_code IN ('BRENT', 'COPPER', 'ALUMINIUM')")}
    assert rows["BRENT"]["status"] == "Stale" and rows["COPPER"]["status"] == "Stale" and rows["ALUMINIUM"]["status"] == "Available"
    got, _ = await sectors(mo)
    assert "BRENT" in got["oil_marketing"]["criticalMissing"]                      # stale is never guessed into a score


@pytest.mark.integration
async def test_a_connected_vendor_feed_wins_only_while_enough_and_at_least_as_recent(mo):
    await seed_all_but_commodities(mo)
    async with mo.pool.acquire() as conn:
        await put(conn, "brent_d", daily(D(2026, 10, 20), 300))
        await conn.executemany("INSERT INTO commodity_snapshots (day, symbol, kind, value) VALUES ($1, 'brent', 'intl_usd', $2) ON CONFLICT DO NOTHING",
                               [(d, v) for d, v in daily(D(2026, 10, 22), 60, 90).items()])
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    async with mo.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT value, source FROM macro_indicators WHERE indicator_code = 'BRENT'")
        await conn.execute("DELETE FROM commodity_snapshots WHERE day > '2026-10-10'")
    assert r["source"] == "commodity price vendor feed" and float(r["value"]) >= 90
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)          # the vendor is now older than the EIA series: the EIA series is used
    async with mo.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT source FROM macro_indicators WHERE indicator_code = 'BRENT'")
    assert r["source"] == "U.S. EIA"


@pytest.mark.integration
async def test_an_old_model_is_upgraded_to_a_new_version_for_the_monthly_series(mo):
    async with mo.pool.acquire() as conn:
        await SEED.ensure_seed(conn)
        row = await conn.fetchrow("SELECT indicators FROM macro_model_configuration WHERE model_version = 1")
        ind = json.loads(row["indicators"]) if isinstance(row["indicators"], str) else dict(row["indicators"])
        for c in SEED.UPGRADED:
            ind[c]["norm"]["level"]["min_points"], ind[c]["stale_after_days"] = 20, 10          # the shape an already-deployed model has
        await conn.execute("UPDATE macro_model_configuration SET indicators = $1::jsonb WHERE model_version = 1", json.dumps(ind))
        assert await SEED.upgrade_model(conn) == 2
        assert await SEED.upgrade_model(conn) is None                                       # idempotent
        new = await conn.fetchrow("SELECT indicators, active, parent_version FROM macro_model_configuration WHERE model_version = 2")
        n1 = await conn.fetchval("SELECT count(*) FROM sector_sensitivity WHERE model_version = 1")
        n2 = await conn.fetchval("SELECT count(*) FROM sector_sensitivity WHERE model_version = 2")
    new_ind = json.loads(new["indicators"]) if isinstance(new["indicators"], str) else new["indicators"]
    assert new["active"] and new["parent_version"] == 1 and n1 == n2 and new_ind["COPPER"]["stale_after_days"] == 75 and new_ind["COPPER"]["norm"]["level"]["min_points"] == 6


# ------------------------------------------------------------------------------------------------------------ the World Bank step
def pink_sheet(copper="Copper", unit="($/mt)", rows=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Prices"
    ws.append(["World Bank Commodity Price Data (The Pink Sheet)"])
    ws.append(["monthly prices in nominal US dollars"])
    ws.append(["(monthly series are averages of the daily prices)"])
    ws.append(["Updated on November 03, 2026"])
    ws.append([None, "Crude oil, Brent", "Natural gas, US", "Aluminum", copper])
    ws.append([None, "($/bbl)", "($/mmbtu)", "($/mt)", unit])
    for r in rows or [("2026M08", 80, 3.1, 2600.5, 9800.1), ("2026M09", 81, 3.2, "..", 9900.2), ("2026M10", 82, 3.3, 2650.0, 10100.0), ("1960M01", 1.6, 0.1, 500, 500)]:
        ws.append(list(r))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_pink_sheet_parser_reads_month_ends_skips_placeholders_and_refuses_a_changed_column():
    got, updated = macro.parse_pink_sheet(pink_sheet())
    assert updated == "Updated on November 03, 2026"
    assert got["copper_m"] == {D(2026, 8, 31): 9800.1, D(2026, 9, 30): 9900.2, D(2026, 10, 31): 10100.0}
    assert got["aluminium_m"] == {D(2026, 8, 31): 2600.5, D(2026, 10, 31): 2650.0} and got["natgas_m"][D(2026, 10, 31)] == 3.3
    with pytest.raises(RuntimeError, match="not as expected"):
        macro.parse_pink_sheet(pink_sheet(unit="(cents/lb)"))


def wb_site(content=None, status=200):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "www.worldbank.org":
            return httpx.Response(200, text='<a href="https://thedocs.worldbank.org/en/doc/abc-0050012026/related/CMO-Historical-Data-Monthly.xlsx">x</a>')
        if req.url.host == "thedocs.worldbank.org":
            assert "abc-0050012026" in str(req.url)                       # the link found on the page is the one downloaded
            return httpx.Response(status, content=content or b"")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.mark.integration
async def test_worldbank_step_stores_months_shows_them_with_licence_and_keeps_old_data_on_failure(mstore):
    res = await macro.refresh(mstore, transport=wb_site(pink_sheet()), today=TODAY, only=["worldbank"])
    assert res["steps"]["worldbank"]["status"] == "ok" and res["steps"]["worldbank"]["points"] == 8
    async with mstore.pool.acquire() as conn:
        p = await macro.get_meta(conn, "payload")
    cards = {c["key"]: c for c in p["cards"]}
    assert cards["copper_m"]["value"] == 10100.0 and cards["copper_m"]["date"] == "2026-10-31" and cards["copper_m"]["source"] == "World Bank" and "monthly" in cards["copper_m"]["lag"].lower()
    assert "CC BY 4.0" in p["series"]["copper_m"]["note"] and p["series"]["aluminium_m"]["freq"] == "M" and p["metals"] == {}
    res = await macro.refresh(mstore, transport=wb_site(status=503), today=TODAY, only=["worldbank"])
    assert res["steps"]["worldbank"]["status"] == "failed"
    async with mstore.pool.acquire() as conn:
        p = await macro.get_meta(conn, "payload")
    assert {c["key"]: c for c in p["cards"]}["copper_m"]["value"] == 10100.0


@pytest.mark.integration
async def test_macro_page_says_why_copper_and_brent_have_no_card_and_shows_brent_when_loaded(mstore, monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    await macro.refresh(mstore, transport=httpx.MockTransport(lambda r: httpx.Response(503)), today=TODAY, only=["eia_brent", "worldbank"])
    async with mstore.pool.acquire() as conn:
        p = await macro.get_meta(conn, "payload")
    assert p["brent"]["reason"] == "Brent: source key not set" and "brent_d" not in {c["key"] for c in p["cards"]}
    assert "failed" in p["metals"]["copper_m"]["reason"] and set(p["metals"]) == {"copper_m", "aluminium_m", "natgas_m"}
    async with mstore.pool.acquire() as conn:
        await put(conn, "brent_d", {D(2026, 11, 2): 100.5, D(2026, 11, 3): 102.0})
    p = await macro.build(mstore, TODAY)
    b = {c["key"]: c for c in p["cards"]}["brent_d"]
    assert b["value"] == 102.0 and b["date"] == "2026-11-03" and b["change"] == 1.5 and b["source"] == "U.S. EIA" and "1-2 business days" in b["lag"]


# ------------------------------------------------------------------------------------------------------------ the Commodities page
def test_commodities_brent_card_uses_eia_with_inr_conversion_and_both_dates():
    eia = {"brent": [(D(2026, 11, 2), 100.0), (D(2026, 11, 3), 102.5)], "usdinr": (D(2026, 11, 4), 88.1234), "reason": None}
    b = cm.eia_brent_item(eia, TODAY)["eia"]
    assert b["state"] == "ok" and b["usd"] == "102.50" and b["date"] == "2026-11-03" and b["changePct"] == "2.50" and b["lag"] == "U.S. EIA, daily, 1-2 business day lag"
    assert b["inr"]["value"] == "9033" and b["inr"]["usdinrDate"] == "2026-11-04" and b["inr"]["priceDate"] == "2026-11-03" and "not a quote" in b["inr"]["label"]
    assert cm.eia_brent_item({**eia, "usdinr": (D(2026, 10, 1), 88.0)}, TODAY)["eia"]["inr"] is None        # an old rate: no rupee figure
    assert cm.eia_brent_item({**eia, "usdinr": None}, TODAY)["eia"]["inr"] is None
    old = cm.eia_brent_item({"brent": [(D(2026, 10, 1), 90.0)], "usdinr": None}, TODAY)["eia"]
    assert old["state"] == "stale" and "35 days old" in old["note"] and old["changePct"] is None
    none = cm.eia_brent_item({"brent": [], "usdinr": None, "reason": "Brent: source key not set"}, TODAY)["eia"]
    assert none["state"] == "none" and none["usd"] is None and none["note"] == "Brent: source key not set"


def test_commodities_page_lists_the_eia_card_beside_crude_only_when_the_vendor_has_no_brent():
    from test_commodities import CFG, NOW, TS, intl_blob, mcx_blob, settings
    eia = {"brent": [(D(2026, 11, 3), 102.0)], "usdinr": None, "reason": None}
    codes = [i["code"] for i in cm.build(settings(metals_dev_api_key="", metalprice_api_key=""), NOW, mcx_blob(), None, CFG, TS - 2, eia)["items"]]
    assert codes[codes.index("crude") + 1] == "brent"
    assert "brent" not in [i["code"] for i in cm.build(settings(metals_dev_api_key="", metalprice_api_key=""), NOW, mcx_blob(), None, CFG, TS - 2)["items"]]
    withv = cm.build(settings(), NOW, mcx_blob(), intl_blob(), CFG, TS - 2, eia)
    crude = next(i for i in withv["items"] if i["code"] == "crude")
    vendor_has_brent = any(x["key"] == "brent" and x["usd"] is not None for x in crude["intl"])
    assert ("brent" in [i["code"] for i in withv["items"]]) is (not vendor_has_brent)
    brent = next(i for i in cm.build(settings(metals_dev_api_key="", metalprice_api_key=""), NOW, mcx_blob(), None, CFG, TS - 2, eia)["items"] if i["code"] == "brent")
    assert brent["mcx"] is None and brent["intl"] == [] and brent["group"] == "energy" and "dhan" not in json.dumps(brent).lower()


# ------------------------------------------------------------------------------------------------------------ wording
def test_new_wording_describes_and_never_advises():
    import re
    texts = [macro.WB_LICENCE, cm.EIA_LAG] + [d[-1] for d in SEED.INDICATORS if d[0] in ("BRENT", "COPPER", "ALUMINIUM", "NATGAS")] + \
            [SERIES["what"] for k, SERIES in ((k, v) for k, v in macro.SERIES.items() if k in ("brent_d", "copper_m", "aluminium_m", "natgas_m"))]
    texts += [cm.eia_brent_item({"brent": [(D(2026, 11, 3), 1.0 + 100)], "usdinr": (D(2026, 11, 4), 88.0), "reason": None}, TODAY)["eia"]["inr"]["label"]]
    for t in texts:
        for w in ADVICE:
            assert not re.search(r"\b" + w + r"\b", t, re.I), (w, t)
