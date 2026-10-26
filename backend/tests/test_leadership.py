"""The Leader / In line / Laggard rules, one test per case of the developer spec (pure functions: no database)."""
from datetime import date, timedelta

import pytest

from finlit import leadership as L

END = date(2026, 10, 23)   # a Friday


def weekly(end=END, weeks=60, start=100.0, growth=0.0, lag_days=0):
    ds = [end - timedelta(days=7 * (weeks - 1 - i) + lag_days) for i in range(weeks)]
    return L.Prices(ds, [start * (1 + growth) ** i for i in range(weeks)])


def member(sym, growth, mcap=1e4, weeks=60, **kw):
    return L.Member(sym=sym, prices=weekly(weeks=weeks, growth=growth), mcap=mcap, **kw)


def group(n, flat_sector=True):
    # n stocks whose weekly growth falls with the index, against a flat sector index
    ms = [member(f"S{i:02d}", 0.004 - i * 0.0006, mcap=1e4 - i) for i in range(n)]
    return ms, weekly(weeks=60, growth=0.0)


@pytest.mark.parametrize("n,k", [(13, 4), (6, 2), (7, 3), (10, 3), (1, 1), (20, 6)])
def test_cut_off_size(n, k):
    assert L.top_count(n) == k


def test_leader_laggard_and_sign_rules():
    ms, idx = group(10)
    g = L.label_group(ms, END, idx, None)
    assert g.n == 10 and g.k == 3
    labels = {r.sym: r.label for r in g.rows}
    assert [r.rank for r in g.rows] == list(range(1, 11))
    assert labels["S00"] == "leader" and labels["S09"] == "laggard" and labels["S05"] == "in_line"


def test_whole_group_trailing_has_no_leader():
    ms = [member(f"S{i}", -0.002 - i * 0.0003) for i in range(8)]
    g = L.label_group(ms, END, weekly(growth=0.01), None)
    assert all(r.rel52 < 0 for r in g.rows)
    assert not any(r.label == "leader" for r in g.rows) and sum(r.label == "laggard" for r in g.rows) == g.k


def test_whole_group_ahead_has_no_laggard():
    ms = [member(f"S{i}", 0.01 + i * 0.0003) for i in range(8)]
    g = L.label_group(ms, END, weekly(growth=0.0), None)
    assert not any(r.label == "laggard" for r in g.rows) and any(r.label == "leader" for r in g.rows)


@pytest.mark.parametrize("move,expected", [(0.05, "gaining"), (0.049, None), (-0.05, "weakening"), (-0.049, None)])
def test_direction_thresholds(move, expected):
    # the stock's 13-week return minus the benchmark's equals `move` exactly
    ds = [END - timedelta(days=7 * (59 - i)) for i in range(60)]
    base = [100.0] * 60
    bench_closes = [100.0] * 60
    stock = list(base)
    stock[-1] = 100.0 * (1 + move)
    m = [L.Member("A", L.Prices(ds, stock))] + [L.Member(f"B{i}", L.Prices(ds, [100.0] * 60), mcap=1.0 - i / 10) for i in range(6)]
    g = L.label_group(m, END, L.Prices(ds, bench_closes), None)
    a = next(r for r in g.rows if r.sym == "A")
    assert a.direction == expected


def test_ties_break_on_six_month_return_then_market_cap():
    ds = [END - timedelta(days=7 * (59 - i)) for i in range(60)]
    def mk(sym, mid, cap):
        c = [100.0] * 60
        c[-27] = mid   # the 26-week anchor
        c[-1] = 120.0
        return L.Member(sym, L.Prices(ds, c), mcap=cap)
    ms = [mk("X", 100.0, 5.0), mk("Y", 90.0, 1.0), mk("Z", 100.0, 9.0)] + [L.Member(f"F{i}", L.Prices(ds, [100.0] * 60), mcap=i + 1) for i in range(4)]
    g = L.label_group(ms, END, L.Prices(ds, [100.0] * 60), None)
    order = [r.sym for r in g.rows[:3]]
    assert [r.rel52 for r in g.rows[:3]] == [pytest.approx(0.2)] * 3
    r26 = {r.sym: r.rel26 for r in g.rows}
    # all three tie on 12 months: X and Z (6-month anchor 100) beat Y (anchor 90) is false (a lower anchor means a higher 6-month return), so Y leads
    assert order == ["Y", "Z", "X"] and r26["Y"] > r26["Z"] == r26["X"]


def test_short_history_is_excluded():
    ms, idx = group(8)
    ms.append(member("NEW", 0.01, weeks=40))
    g = L.label_group(ms, END, idx, None)
    assert "NEW" in g.excluded and g.excluded["NEW"] == "history" and all(r.sym != "NEW" for r in g.rows)


def test_small_industry_widens_to_sector_then_gives_up():
    ind = [member(f"I{i}", 0.003) for i in range(4)]
    sector = ind + [member(f"O{i}", 0.001 * i) for i in range(5)]
    kind, chosen, _ = L.choose_group(ind, sector, END)
    assert kind == "sector" and len(chosen) == 9
    kind2, _, _ = L.choose_group(ind, ind, END)
    assert kind2 is None


def test_no_sector_index_uses_peer_average():
    ms, _ = group(9)
    g = L.label_group(ms, END, None, None)
    assert g.kind == "peer_average"
    assert abs(sum(r.rel52 for r in g.rows)) < 1e-9


def test_thin_trading_and_stale_price():
    ms, idx = group(8)
    ms.append(member("THIN", 0.01, liquid=False))
    stale = L.Member("OLD", weekly(lag_days=9), mcap=1.0)
    ms.append(stale)
    g = L.label_group(ms, END, idx, None)
    assert g.excluded["THIN"] == "liquidity" and g.excluded["OLD"] == "stale"


def test_liquidity_estimate():
    closes, vols = [100.0] * 13, [50000.0] * 13        # Rs 10 lakh a day
    assert not L.liquid_enough([], closes, vols)
    assert L.liquid_enough([], closes, [5e6] * 13)     # Rs 1 crore a day
    assert L.liquid_enough([], closes, [])             # unknown is not thin


def test_stability_rule():
    assert L.settle(None, None, "leader") == ("leader", True)          # first label at once
    assert L.settle("in_line", "in_line", "leader") == ("in_line", False)   # one week is not enough
    assert L.settle("in_line", "leader", "leader") == ("leader", True)  # two in a row
    assert L.settle("leader", "in_line", "leader") == ("leader", False)


def test_data_break_on_corporate_action():
    ds = [END - timedelta(days=7 * (59 - i)) for i in range(60)]
    c = [100.0] * 60
    for i in range(30, 60):
        c[i] = 70.0
    p = L.Prices(ds, c)
    on = ds[30]
    assert L.find_breaks(p, END, [on])
    assert not L.find_breaks(p, END, [])                 # a −30% week with no corporate action is a real move
    assert not L.find_breaks(p, END, [ds[10]])


def test_fundamental_check():
    ms, idx = group(10)
    for i, m in enumerate(ms):
        m.fund = 10.0 + i * 5    # S00 (the price leader) has the lowest fundamentals
    g = L.label_group(ms, END, idx, None)
    by = {r.sym: r for r in g.rows}
    assert by["S00"].fundamental == "below_peers" and by["S09"].fundamental == "stronger_than_price"
    assert by["S05"].fundamental is None


def test_display_strings():
    assert L.ordinal(1) == "1st" and L.ordinal(2) == "2nd" and L.ordinal(3) == "3rd" and L.ordinal(11) == "11th" and L.ordinal(12) == "12th" and L.ordinal(22) == "22nd"
    assert L.pts(-0.072) == "−7.2" and L.pts(0.012) == "+1.2" and L.pts(0) == "0.0" and L.pts(None) == "—"
    d = L.display(label="laggard", rank=11, ranked=13, group_short="IT", sector_name="Nifty IT", market_name="Nifty 50", rel52=-0.072,
                  rel52_market=-0.101, direction="weakening", fundamental="stronger_than_price", fund_rank=3, fund_n=13)
    assert d["chip"] == "Laggard"
    assert d["line"] == "11th of 13 IT peers · −7.2 pts vs Nifty IT · −10.1 pts vs Nifty 50 (12 months) · weakening over 3 months"
    assert d["note"] == "Fundamentals rank 3rd of 13, stronger than the price"
    blob = " ".join(str(v) for v in d.values()).lower()
    assert not any(w in blob for w in ("buy", "sell", "avoid"))
    e = L.display(label=None, rank=None, ranked=None, group_short="", sector_name="", market_name=None, rel52=None, rel52_market=None, direction=None,
                  fundamental=None, fund_rank=None, fund_n=None, reason="group")
    assert e["chip"] is None and e["line"] == "Too few comparable companies to rank"


def test_reliability_tiers():
    def checks(rates, per=40):
        out = []
        for (y, r) in rates:
            for i in range(per):
                out.append(L.Check(on=date(y, 1 + i % 12, 1 + (i // 12)), hit=i < per * r, gap=0.01, n=8))
        return out
    few = L.summarise_checks(checks([(2020, 0.8)]))
    assert few["tier"] == "insufficient" and L.reliability_sentence("IT", few) == "Not enough history to judge"
    good = L.summarise_checks(checks([(2006, 0.6), (2012, 0.6), (2017, 0.6), (2022, 0.6)]))
    assert good["tier"] == "consistent" and good["checks"] == 160
    mixed = L.summarise_checks(checks([(2006, 0.7), (2012, 0.7), (2017, 0.6), (2022, 0.3)]))
    assert mixed["tier"] == "mixed"
    bad = L.summarise_checks(checks([(2006, 0.4), (2012, 0.4), (2017, 0.4), (2022, 0.4)]))
    assert bad["tier"] == "not_reliable"
    for r in (good, mixed, bad):
        s = L.reliability_sentence("IT", r)
        assert "IT" in s and "%" in s


def test_backtest_checks_uses_only_information_at_the_time():
    ms = [member(f"S{i:02d}", 0.004 - i * 0.0006, mcap=1e4 - i, weeks=120) for i in range(8)]
    idx = weekly(weeks=120, growth=0.0)
    dates = [END - timedelta(days=7 * w) for w in (40, 30)]
    cs = L.backtest_checks(ms, idx, dates)
    assert cs and all(c.hit for c in cs)    # in this synthetic group, past leaders keep leading


def test_run_dates_and_helpers():
    assert L.run_dates(END) == [END]
    d = L.run_dates(END, date(2026, 6, 1))
    assert d[-1] == END and all(b - a == timedelta(days=28) for a, b in zip(d, d[1:]))
    assert L.last_friday(date(2026, 10, 24)) == END and L.last_friday(END) == END
    assert L.size_bucket(100) == "large" and L.size_bucket(101) == "mid" and L.size_bucket(251) == "small" and L.size_bucket(None) == "small"
    assert L.norm_industry("IT - Software & Services") == L.norm_industry("it software and services")


# --------------------------------------------------------------------------------------------------- the job and the API, on the real tables
import json as _json
import time as _time

import httpx

from finlit import leadership_api
from finlit.api import create_app
from test_integration import make_settings, store  # noqa: F401


def _levels(growth, weeks=140):
    ds = [END - timedelta(days=7 * (weeks - 1 - i)) for i in range(weeks)]
    return {"rows": [{"quote_date": d.isoformat(), "close_price": 100.0 * (1 + growth) ** i} for i, d in enumerate(ds)]}


async def _seed(store, n=14, industry="IT - Software"):
    async with store.pool.acquire() as conn:
        for t in ("leadership", "leadership_history", "leadership_excluded", "sector_reliability"):
            await conn.execute(f"DELETE FROM {t}")  # nosec B608 - fixed table names
        await conn.execute("UPDATE feature_flags SET enabled = false WHERE name = 'leadership'")
        await conn.execute("DELETE FROM price_history_long")
        for i in range(n):
            sym = f"T{i:02d}"
            await conn.execute("INSERT INTO companies (symbol, name, sector, industry) VALUES ($1, $2, 'Information Technology', $3) ON CONFLICT DO NOTHING", sym, f"Tee {i}", industry)
            await conn.execute("INSERT INTO scores (symbol, statement, model, overall, pillar_quality, pillar_growth, pillar_profitability, pillar_balance, sector, industry, macro_sector) "
                               "VALUES ($1, 'consolidated', 'v1', 50, $2, $2, $2, $2, 'Information Technology', $3, 'Information Technology')", sym, 90 - i * 5, industry)
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2) ON CONFLICT DO NOTHING", sym, 50000 - i * 100)
            g = 0.006 - i * 0.0008
            ds = [END - timedelta(days=7 * (119 - k)) for k in range(120)]
            body = _json.dumps({"series": {"t": [d.isoformat() for d in ds], "c": [100 * (1 + g) ** k for k in range(120)], "v": [1e6] * 120}})
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1, 'consolidated', 'price-MAX', $2, 'x', now())", sym, body)
    for code, g in (("NIFIT", 0.002), ("NIF50", 0.0015), ("NIFMID150", 0.001), ("NIFSMA250", 0.001)):
        await store.redis.set(f"idx:px:{code}", _json.dumps({"t": _time.time(), "v": _levels(g)}))


@pytest.mark.integration
async def test_weekly_run_then_api(store):  # noqa: F811
    await _seed(store)
    settings = make_settings()
    app = create_app(settings, store=store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            before = (await c.get("/api/stocks/T00/leadership")).json()
            assert before == {"available": False, "reason": "hidden"}                      # the switch is off: nobody but an administrator sees it
            async with store.pool.acquire() as conn:
                await conn.execute("UPDATE feature_flags SET enabled = true WHERE name = 'leadership'")
            leadership_api._flag["at"] = 0.0
            assert (await c.get("/api/stocks/T00/leadership")).json() == {"available": False, "reason": "pending"}   # on, but the first weekly run has not happened
            res = await L.run(store, settings, as_of=END)
            assert res["labelled"] == 14 and res["history"] == 14
            assert "public" in (await c.get("/api/stocks/T00/leadership")).headers["cache-control"]
            top = (await c.get("/api/stocks/T00/leadership")).json()
            bottom = (await c.get("/api/stocks/T13/leadership")).json()
            mid = (await c.get("/api/stocks/T07/leadership")).json()
            assert top["available"] and top["label"] == "leader" and top["rank"] == 1 and top["peerGroup"]["ranked"] == 14
            assert top["benchmarks"]["sector"]["code"] == "NIFIT" and top["benchmarks"]["market"]["code"] == "NIF50"
            assert top["display"]["chip"] == "Leader" and top["display"]["line"].startswith("1st of 14 IT software peers · +")
            assert bottom["label"] == "laggard" and mid["label"] == "in_line" and len(top["peers"]) == 14
            assert top["sectorReliability"]["tier"] == "insufficient" and top["sectorReliability"]["sentence"] == "Not enough history to judge"
            assert top["fundamentalNote"] == "below_peers" or top["fundamentalNote"] is None   # the price leader has the strongest fundamentals here
            assert bottom["fundamentalNote"] == "stronger_than_price" or bottom["fundamentalNote"] is None
            hist = (await c.get("/api/stocks/T00/leadership-history")).json()
            assert hist["available"] and hist["rows"][-1]["rank"] == 1 and hist["series"]["sector"] and len(hist["series"]["dates"]) == 120
            gone = (await c.get("/api/stocks/NOPE/leadership")).json()
            assert gone == {"available": False, "reason": "history", "display": gone["display"]} and gone["display"]["line"].startswith("Not enough price history")

    # the second weekly run publishes nothing new unless the raw label held for two runs; a re-run of the same Friday is idempotent
    again = await L.run(store, settings, as_of=END)
    assert again["churn"] == 0
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM leadership_history") == 14


@pytest.mark.integration
async def test_small_industry_widens_and_tiny_one_is_unranked(store):  # noqa: F811
    await _seed(store, n=4, industry="IT - Hardware")
    settings = make_settings()
    res = await L.run(store, settings, as_of=END)
    assert res["labelled"] == 0
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT reason FROM leadership_excluded WHERE symbol = 'T00'") == "group"


@pytest.mark.integration
async def test_banks_are_split_into_private_and_public_sector_groups(store):  # noqa: F811
    await _seed(store, n=0)
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE feature_flags SET enabled = true WHERE name = 'leadership'")
    names = [("HDFCBANK", "private"), ("ICICIBANK", "private"), ("KOTAKBANK", "private"), ("AXISBANK", "private"), ("INDUSINDBK", "private"), ("FEDERALBNK", "private"),
             ("SBIN", "psu"), ("PNB", "psu"), ("UNIONBANK", "psu"), ("BANKBARODA", "psu"), ("INDIANB", "psu"), ("CANBK", "psu"), ("IDBI", "other")]
    async with store.pool.acquire() as conn:
        for i, (sym, _) in enumerate(names):
            await conn.execute("INSERT INTO companies (symbol, name, sector, industry) VALUES ($1, $1, 'Financial Services', 'Banks')", sym)
            await conn.execute("INSERT INTO scores (symbol, statement, model, overall, pillar_quality, pillar_growth, pillar_profitability, pillar_balance, sector, industry, macro_sector) "
                               "VALUES ($1, 'consolidated', 'v1', 50, 50, 50, 50, 50, 'Financial Services', 'Banks', 'Financial Services')", sym)
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2) ON CONFLICT DO NOTHING", sym, 90000 - i * 100)
            g = 0.004 - i * 0.0004
            ds = [END - timedelta(days=7 * (119 - k)) for k in range(120)]
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1, 'consolidated', 'price-MAX', $2, 'x', now())", sym,
                               _json.dumps({"series": {"t": [d.isoformat() for d in ds], "c": [100 * (1 + g) ** k for k in range(120)], "v": [1e6] * 120}}))
    for code in ("NIFPRIBAN", "NIFPSUBAN", "NIFBAN", "NIF50", "NIFMID150", "NIFSMA250"):
        await store.redis.set(f"idx:px:{code}", _json.dumps({"t": _time.time(), "v": _levels(0.002)}))
    await L.run(store, make_settings(), as_of=END)
    async with store.pool.acquire() as conn:
        got = {r["symbol"]: (r["group_name"], r["sector_code"], r["ranked"]) for r in await conn.fetch("SELECT symbol, group_name, sector_code, ranked FROM leadership")}
    assert got["HDFCBANK"] == ("private banks", "NIFPRIBAN", 6) and got["SBIN"] == ("public sector banks", "NIFPSUBAN", 6)
    assert got["IDBI"][0] == "Financial Services" and got["IDBI"][1] == "peer_average"   # a lone bank outside both lists is ranked with the whole sector, against its peers' average


async def test_switch_endpoints_need_an_administrator(store):  # noqa: F811
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.get("/api/admin/features")).status_code in (401, 403)
            assert (await c.put("/api/admin/features/leadership", json={"enabled": True})).status_code in (401, 403)


# --------------------------------------------------------------------------------------------------- longer history
from finlit import history as H


def test_older_closes_are_scaled_to_meet_the_report_and_nothing_overlaps():
    recent = [date(2024, 1, 5) + timedelta(days=7 * i) for i in range(5)]
    old = [date(2023, 11, 24) + timedelta(days=7 * i) for i in range(8)]       # runs to 2024-01-12: overlaps the report by two weeks
    d, c = H.splice(recent, [200.0] * 5, old, [100.0 + i for i in range(8)])
    assert d == sorted(set(d)) and d[0] == old[0] and d[-5:] == recent
    k = 200.0 / 106.0   # the old close on the join date (2024-01-05) is 106, so older closes are multiplied by 200 / 106
    assert [round(x, 4) for x in c[:2]] == [round(100.0 * k, 4), round(101.0 * k, 4)]
    assert H.splice(recent, [1.0] * 5, [date(2010, 1, 1)], [5.0]) == (recent, [1.0] * 5)    # no overlap near the join: nothing is added
    assert H.splice([], [], old, [1.0] * 8) == ([], [])


def test_weekly_closes_take_the_last_day_of_each_week_and_drop_bad_ticks():
    rows = [{"quote_date": f"2024-01-{d:02d}", "close_price": c} for d, c in [(1, 100), (2, 101), (3, 0), (5, 103), (8, 104), (12, 110)]]
    ds, cs = H.weekly_closes({"price": rows})
    assert ds == [date(2024, 1, 5), date(2024, 1, 12)] and cs == [103.0, 110.0]


@pytest.mark.integration
async def test_backfill_stores_older_weeks_and_tries_each_company_once(store):  # noqa: F811
    await _seed(store, n=3)

    class Fake:
        calls = []
        async def get(self, path, params=None, timeout=10, retries=3):
            self.calls.append(path)
            if path.endswith("/T01"):
                raise RuntimeError("provider down")
            return {"price": [{"quote_date": (date(2004, 1, 5) + timedelta(days=7 * i)).isoformat(), "close_price": 10 + i} for i in range(1100)]}

    f = Fake()
    out = await H.backfill(f, store, limit=10)
    assert out["stored"] == 2 and out["failed"] == 1 and out["oldest"] == "2004-01-05"
    again = await H.backfill(f, store, limit=10)     # tried within 90 days: left alone, apart from the one that failed
    assert again["stored"] == 0 and again["failed"] == 1
    async with store.pool.acquire() as conn:
        n, first = await conn.fetchrow("SELECT count(*), min(first_date) FROM price_history_long")
        assert n == 2 and first == date(2004, 1, 5)
    prices = await L._load_prices(store, await L._load_universe(store), long_history=True)
    assert prices["T00"][0].dates[0] <= date(2004, 1, 9) and len(prices["T00"][0]) > 600
