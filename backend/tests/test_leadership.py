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
    assert [L.size_bucket(x) for x in (107000, 106999.99, 32800, 32799.99, 500, 0, -5, None, float("nan"))] == ["large", "mid", "mid", "small", "small", "unknown", "unknown", "unknown", "unknown"]
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
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2) ON CONFLICT DO NOTHING", sym, 200000 - i * 100)
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
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2) ON CONFLICT DO NOTHING", sym, 190000 - i * 100)
            g = 0.004 - i * 0.0004
            ds = [END - timedelta(days=7 * (119 - k)) for k in range(120)]
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1, 'consolidated', 'price-MAX', $2, 'x', now())", sym,
                               _json.dumps({"series": {"t": [d.isoformat() for d in ds], "c": [100 * (1 + g) ** k for k in range(120)], "v": [1e6] * 120}}))
    for code in ("NIFPRIBAN", "NIFPSUBAN", "NIFBAN", "NIF50", "NIFMID150", "NIFSMA250"):
        await store.redis.set(f"idx:px:{code}", _json.dumps({"t": _time.time(), "v": _levels(0.002)}))
    await L.run(store, make_settings(), as_of=END)
    async with store.pool.acquire() as conn:
        got = {r["symbol"]: (r["group_name"], r["sector_code"], r["ranked"]) for r in await conn.fetch("SELECT symbol, group_name, sector_code, ranked FROM leadership")}
    # the indicator's researched groups: private banks and PSU banks, each against its own Nifty index
    assert got["HDFCBANK"] == ("private bank", "NIFPRIBAN", 6) and got["SBIN"] == ("PSU bank", "NIFPSUBAN", 6)
    # IDBI is on the indicator's "Major Banks" list (not on either researched group): ranked there, against the average of those peers while the Nifty Financial Services
    # levels are not cached in this test
    assert got["IDBI"][0] == "Major Banks" and got["IDBI"][1] == "peer_average" and got["IDBI"][2] == 11


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


# --------------------------------------------------------------------------------------------------- the indicator's peer lists (finlit_technicals v1.1)
import math as _math
import random as _random

PARITY = _json.loads((__import__("pathlib").Path(__file__).parent / "fixtures" / "leadership_parity.json").read_text())


def _gauss(rnd):
    return _math.sqrt(-2 * _math.log(1 - rnd.random())) * _math.cos(2 * _math.pi * rnd.random())


def _walk(rnd, weeks, drift, vol, p0):
    price, out = p0, []
    for _ in range(weeks):
        price *= _math.exp(drift + vol * (sum(rnd.random() for _ in range(12)) - 6))
        out.append(price)
    return out


def pure_world(n_peers, weeks, seed, thin, short, stale, midweek, sector, mcap):
    """Identical to pure_world() in docs/technicals/parity_leadership.py: weekly bars (date = the week's last trading day) of a stock STK, its peers, a sector index and a market index."""
    rnd = _random.Random(seed)
    fridays = [END - timedelta(days=7 * (weeks - 1 - i)) for i in range(weeks)]
    world = {}
    for k, sym in enumerate(["STK"] + [f"P{i}" for i in range(n_peers)]):
        drift = 0.0030 if sym == "STK" else 0.0012 + 0.0015 * _gauss(rnd)
        closes = _walk(rnd, weeks, drift, 0.03 + 0.01 * (k % 3), 100.0)
        vols = [_math.exp(13.5 + 0.4 * _gauss(rnd)) for _ in range(weeks)]
        dates = list(fridays)
        if k and (k - 1) in thin:
            vols = [v * 0.0005 for v in vols]
        if k and (k - 1) in short:
            dates, closes, vols = dates[-70:], closes[-70:], vols[-70:]
        if k and (k - 1) in stale:
            dates, closes, vols = dates[:-2], closes[:-2], vols[:-2]
        if k and (k - 1) in midweek:
            dates = dates[:-1] + [dates[-1] - timedelta(days=2)]
        world[sym] = (dates, closes, vols)
    world["SECTOR"] = (fridays, _walk(rnd, weeks, 0.0012, 0.015, 1000.0), [0.0] * weeks)
    world["MARKET"] = (fridays, _walk(rnd, weeks, 0.0010, 0.012, 20000.0), [0.0] * weeks)
    return world


@pytest.mark.parametrize("name", [k for k in PARITY if not k.startswith("_")])
def test_weekly_runs_equal_the_package_week_by_week(name):
    """Rank, leader slots, the 12-, 6- and 3-month relative returns, the market figure, this week's label and the published label (two runs in a row), on the
    same weekly closes as finlit_technicals v1.1 (peers.compute). The expected values were produced by the package."""
    spec = PARITY[name]
    p = spec["params"]
    world = pure_world(**p)
    members = [L.Member(sym=s, prices=L.Prices(d, c, v), liquid=L.liquid_enough(d, c, v)) for s, (d, c, v) in world.items() if s not in ("SECTOR", "MARKET")]
    sidx, midx = (L.Prices(*world["SECTOR"][:2]) if p["sector"] else None), L.Prices(*world["MARKET"][:2])
    weeks = [date.fromisoformat(r["week"]) for r in spec["runs"]]
    pub, last_raw, checked = None, None, 0
    # the stability rule needs the runs before the compared window too: walk every Friday from the first rankable one
    everything = sorted({d - timedelta(days=d.weekday()) for d, *_ in [(x,) for x in world["STK"][0]]})[1:]
    expected = {r["week"]: r for r in spec["runs"]}
    for ref in everything:
        t = ref + timedelta(days=4)
        g = L.label_group(members, t, sidx, midx)
        me = next((x for x in g.rows if x.sym == "STK"), None)
        if g.n < L.MIN_PEERS or me is None:
            continue
        pub, _ = L.settle(pub, last_raw, me.label)
        last_raw = me.label
        want = expected.get(ref.isoformat())
        if want is None or want["state"] != 0:
            continue
        checked += 1
        mret = L.ret(midx, t, L.RANK_WEEKS)
        assert (g.n, g.k, me.rank) == (want["ranked"], want["k"], want["rank"]), ref
        for key, got in (("rel52", me.rel52), ("rel26", me.rel26), ("rel13", me.rel13), ("rel52Market", me.ret52 - mret if mret is not None else None)):
            assert (got is None) == (want[key] is None) and (got is None or abs(got - want[key]) < 1e-8), (ref, key)
        assert me.label == want["raw"], ref
        assert pub == want["pub"], ref
    assert checked == sum(1 for r in spec["runs"] if r["state"] == 0) and checked > 10


def test_the_indicators_lists_are_the_files_and_the_precedence_is_the_indicators():
    groups, as_of = L.load_lists()
    assert as_of == "2026-10-27" and len(groups) == 95 and len({g.id for g in groups}) == 95
    by = {g.id: g for g in groups}
    assert [len(by[i].symbols) for i in ("pl-it", "pl-pharma", "pl-private-bank", "pl-psu-bank", "pl-auto-sector")] == [14, 16, 13, 12, 20]   # the spec's five researched groups
    assert by["pl-it"].index_code == "NIFIT" and by["pl-private-bank"].index_code == "NIFPRIBAN" and by["pl-psu-bank"].index_code == "NIFPSUBAN"
    assert by["pl-steel"].index_code == "NIFMET" and by["pl-steel"].index_name == "Nifty Metal" and by["pl-aluminum"].index_code == "NIFMET"
    assert by["pl-oil-refining-marketing"].index_code == "NIFENE" and by["pl-textiles"].index_code is None and by["pl-hospital-nursing-management"].index_code is None   # no index: the peers' average
    assert all(len(g.symbols) <= 35 or g.kind == "curated" for g in groups) and all(g.symbols for g in groups)
    first = lambda sym: [g.id for g in L.lists_for(sym, groups)]
    assert first("TCS") == ["pl-it", "pl-information-technology-services", "pl-technology-services-sector"]      # researched group first, then industry, then sector
    assert first("M&M")[0] == "pl-auto-sector" and first("m-m")[0] == "pl-auto-sector" and first("BAJAJ-AUTO")[0] == "pl-auto-sector"   # M&M = M-M = M_M; BAJAJ-AUTO = BAJAJ_AUTO
    assert first("SBIN")[0] == "pl-psu-bank" and first("HDFCBANK")[0] == "pl-private-bank" and first("NOSUCHCO") == []
    assert L.norm_symbol("m&m") == "M_M" == L.norm_symbol("M_M") and L.norm_symbol("bajaj-auto") == L.norm_symbol("BAJAJ_AUTO")


def test_the_spec_research_is_shown_until_the_site_has_its_own():
    groups, _ = L.load_lists()
    by = {g.id: g for g in groups}
    tiers = {i: L.spec_reliability(by[i])["tier"] for i in ("pl-it", "pl-pharma", "pl-private-bank", "pl-psu-bank", "pl-auto-sector")}
    assert tiers == {"pl-it": "mixed", "pl-pharma": "consistent", "pl-private-bank": "mixed", "pl-psu-bank": "mixed", "pl-auto-sector": "not_reliable"}   # the package's own words for these groups
    assert L.spec_reliability(by["pl-steel"]) is None
    rel = L.spec_reliability(by["pl-pharma"])
    assert L.reliability_sentence("pharma", rel).startswith("In pharma, leaders have kept beating laggards: 64% of checks since 2005, and in every five-year period")
    assert L.tier_of(0.6, [{"hitRate6m": 0.6}], 119) == "insufficient" and L.tier_of(0.6, [{"hitRate6m": 0.6}], 120) == "consistent" and L.tier_of(0.49, [], 200) == "not_reliable"


def test_a_peer_with_no_bar_in_the_last_week_is_stale_even_when_its_last_close_is_recent():
    ms = [member(f"S{i:02d}", 0.004 - i * 0.0006) for i in range(8)]
    behind = L.Member(sym="LATE", prices=L.Prices([END - timedelta(days=7 * (59 - i) + 6) for i in range(60)], [100 * 1.001 ** i for i in range(60)]))   # last close the Saturday before: previous week
    g = L.label_group(ms + [behind], END, weekly(growth=0.0), None)
    assert g.excluded == {"LATE": "stale"} and g.n == 8
    mid = L.Member(sym="MID", prices=L.Prices([END - timedelta(days=7 * (59 - i) + 2) for i in range(60)], [100 * 1.001 ** i for i in range(60)]))      # last close on the Wednesday of the week: that week
    assert L.label_group(ms + [mid], END, weekly(growth=0.0), None).n == 9
    # all prices lagging the same way is a late refresh, not a stale peer
    lagging = [L.Member(sym=f"L{i}", prices=weekly(weeks=60, growth=0.001 * i, lag_days=3)) for i in range(7)]
    assert L.label_group(lagging, END, weekly(growth=0.0), None).n == 7


def test_liquidity_is_judged_as_of_each_date_when_volumes_are_known():
    ds = [END - timedelta(days=7 * (119 - i)) for i in range(120)]
    vol = [1e6] * 100 + [1.0] * 20                                 # thin for the last 20 weeks only
    p = L.Prices(ds, [100.0] * 120, vol)
    m = L.Member(sym="X", prices=p, liquid=False)
    assert L.exclusion(m, ds[99]) is None and L.exclusion(m, END) == "liquidity"
    assert L.Prices(ds, [100.0] * 120).thin_on(END) is False       # no volumes: unknown is not thin
    assert L.exclusion(L.Member(sym="Y", prices=L.Prices(ds, [100.0] * 120), liquid=False), END) == "liquidity"      # a series without volumes keeps the verdict it was given


def test_this_week_line_names_the_rule_without_advice_words():
    assert L.pending_line("laggard", "in_line") == "This week the ranking says Laggard. It becomes the label if the next weekly run says the same."
    assert L.pending_line("leader", "leader") is None and L.pending_line(None, "leader") is None and L.pending_line("leader", None) is None
    import re
    banned = re.compile(r"\b(buy|sell|hold|holds|holding|accumulate|target|entry|stop|avoid|reduce)\w*\b", re.I)
    for text in [*L.UNRANKED_TEXT.values(), *L.REASON_TEXT.values(), L.pending_line("laggard", "in_line")]:
        assert not banned.search(text), text


def test_market_cap_cut_offs_are_the_prism_technical_views():
    """One company, one size class: the rupee cut-offs here are the ones the Prism technical view uses for its relative-strength benchmark."""
    from pathlib import Path
    src = (Path(L.__file__).parents[2] / "site-api" / "backend" / "technical_series.py").read_text()
    assert f">= {int(L.MARKET_CAP_CUTS[0])}" in src and f">= {int(L.MARKET_CAP_CUTS[1])}" in src


async def _seed_names(store, names, industry="IT - Services", skip_prices=(), mcap=200000, growth=0.006, step=0.0005):
    async with store.pool.acquire() as conn:
        for t in ("leadership", "leadership_history", "leadership_excluded", "leadership_unranked", "sector_reliability"):
            await conn.execute(f"DELETE FROM {t}")  # nosec B608 - fixed table names
        await conn.execute("UPDATE feature_flags SET enabled = true WHERE name = 'leadership'")
        await conn.execute("DELETE FROM price_history_long")
        for i, sym in enumerate(names):
            await conn.execute("INSERT INTO companies (symbol, name, sector, industry) VALUES ($1, $2, 'Information Technology', $3) ON CONFLICT DO NOTHING", sym, f"{sym} Ltd", industry)
            await conn.execute("INSERT INTO scores (symbol, statement, model, overall, pillar_quality, pillar_growth, pillar_profitability, pillar_balance, sector, industry, macro_sector) "
                               "VALUES ($1, 'consolidated', 'v1', 50, 50, 50, 50, 50, 'Information Technology', $2, 'Information Technology') ON CONFLICT DO NOTHING", sym, industry)
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2) ON CONFLICT (symbol) DO UPDATE SET market_cap = EXCLUDED.market_cap", sym, mcap - i * 10)
            if sym in skip_prices:
                continue
            g = growth - i * step
            ds = [END - timedelta(days=7 * (119 - k)) for k in range(120)]
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1, 'consolidated', 'price-MAX', $2, 'x', now()) ON CONFLICT DO NOTHING", sym,
                               _json.dumps({"series": {"t": [d.isoformat() for d in ds], "c": [100 * (1 + g) ** k for k in range(120)], "v": [1e6] * 120}}))
    for code, g in (("NIFIT", 0.002), ("NIF50", 0.0015), ("NIFMID150", 0.001), ("NIFSMA250", 0.001), ("NIF500", 0.001)):
        await store.redis.set(f"idx:px:{code}", _json.dumps({"t": _time.time(), "v": _levels(g)}))


@pytest.mark.integration
async def test_a_stock_on_the_indicators_it_list_is_ranked_there_with_its_not_ranked_peers_named(store):  # noqa: F811
    groups, _ = L.load_lists()
    it = next(g for g in groups if g.id == "pl-it")
    names = [s for s in it.symbols if s not in ("BSOFT", "HEXT")]                        # 12 of the 14 listed names are in this database ...
    await _seed_names(store, names, skip_prices=("OFSS",))                               # ... one of them has no stored prices, and BSOFT/HEXT are not covered at all
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO companies (symbol, name, sector, industry) VALUES ('ODD', 'Odd Ltd', 'Information Technology', 'IT - Services')")    # a provider-industry peer on no list
        await conn.execute("INSERT INTO scores (symbol, statement, model, overall, pillar_quality, pillar_growth, pillar_profitability, pillar_balance, sector, industry, macro_sector) "
                           "VALUES ('ODD', 'consolidated', 'v1', 50, 50, 50, 50, 50, 'Information Technology', 'IT - Services', 'Information Technology')")
    settings = make_settings()
    app = create_app(settings, store=store)
    async with app.router.lifespan_context(app):
        leadership_api._flag["at"] = 0.0
        out = await L.run(store, settings, as_of=END)
        assert out["labelled"] == 11 and out["onIndicatorLists"] == 11 and out["lists"]["pl-it"] == {"listed": 14, "withPrices": 11, "ranked": 11, "homes": 11}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            top = (await c.get("/api/stocks/TCS/leadership")).json()
            assert top["available"] and top["label"] == "leader" and top["rank"] == 1
            g = top["peerGroup"]
            assert (g["source"], g["name"], g["short"], g["ranked"], g["listed"], g["listAsOf"], g["leaderSlots"]) == ("list", "IT", "IT", 11, 14, "2026-10-27", 4)
            assert top["benchmarks"]["sector"]["code"] == "NIFIT" and top["benchmarks"]["market"]["code"] == "NIF50"
            assert top["display"]["line"].startswith("1st of 11 IT peers · +") and top["display"]["pending"] is None
            assert [p["symbol"] for p in top["peers"]][:2] == ["TCS", "INFY"] and all("rawLabel" in p for p in top["peers"])
            gone = {n["symbol"]: (n["reason"], n["text"]) for n in top["notRanked"]}
            assert gone == {"OFSS": ("no_prices", "No price history stored here yet"), "BSOFT": ("not_covered", "Not covered here"), "HEXT": ("not_covered", "Not covered here")}
            assert top["sectorReliability"]["source"] == "spec" and top["sectorReliability"]["tier"] == "mixed" and top["sectorReliability"]["checks"] == 269
            assert top["sectorReliability"]["sentence"].startswith("In IT, leadership has held in some periods and not others: 60% of checks since 2005")
            assert top["runs52"] == {"leader": 1, "in_line": 0, "laggard": 0, "total": 1}
            odd = (await c.get("/api/stocks/ODD/leadership")).json()                      # on no list: the data provider's industry, as before
            assert odd["available"] is False or odd["peerGroup"]["source"] == "industry"
            hist = (await c.get("/api/stocks/TCS/leadership-history")).json()
            assert hist["rows"][-1]["rawLabel"] == "leader" and hist["rows"][-1]["rel13"] is not None
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT group_source, group_listed, list_as_of, group_id FROM leadership WHERE symbol = 'INFY'")
        assert (row["group_source"], row["group_listed"], str(row["list_as_of"]), row["group_id"]) == ("list", 14, "2026-10-27", "pl-it")
        await conn.execute("UPDATE leadership SET group_source = NULL, group_listed = NULL, list_as_of = NULL WHERE symbol = 'INFY'")   # a row written before the lists existed
        await conn.execute("UPDATE feature_flags SET enabled = true WHERE name = 'leadership'")
        old = leadership_api.shape(dict(await conn.fetchrow("SELECT * FROM leadership WHERE symbol = 'INFY'")), None, [])
        assert old["peerGroup"]["source"] == "industry" and old["peerGroup"]["listed"] is None and old["notRanked"] == [] and old["runs52"] is None


@pytest.mark.integration
async def test_a_list_too_thin_to_rank_falls_back_to_the_next_list_then_the_industry(store):  # noqa: F811
    groups, _ = L.load_lists()
    it = next(g for g in groups if g.id == "pl-it")
    await _seed_names(store, it.symbols[:5])                                                 # only 5 of the researched IT names have prices: below the 6 a ranking needs
    settings = make_settings()
    out = await L.run(store, settings, as_of=END)
    assert out["labelled"] == 0 and out["onIndicatorLists"] == 0
    async with store.pool.acquire() as conn:
        assert {r["symbol"]: r["reason"] for r in await conn.fetch("SELECT symbol, reason FROM leadership_excluded")} == {s: "group" for s in it.symbols[:5]}
    await _seed_names(store, it.symbols[:5] + [f"Z{i}" for i in range(4)])                   # four more in the same industry on no list: the provider's industry group has 9
    out = await L.run(store, settings, as_of=END)
    assert out["labelled"] == 9 and out["onIndicatorLists"] == 0 and out["onProviderIndustry"] == 9
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT group_source FROM leadership WHERE symbol = 'TCS'") == "industry"


@pytest.mark.integration
async def test_market_index_follows_the_rupee_cut_offs_and_unknown_uses_the_nifty_500(store):  # noqa: F811
    groups, _ = L.load_lists()
    it = next(g for g in groups if g.id == "pl-it")
    names = it.symbols[:8]
    await _seed_names(store, names, mcap=40000)
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE listing_quotes SET market_cap = 200000 WHERE symbol = $1", names[0])      # large
        await conn.execute("UPDATE listing_quotes SET market_cap = 20000 WHERE symbol = $1", names[1])       # small
        await conn.execute("DELETE FROM listing_quotes WHERE symbol = $1", names[2])                         # unknown
    await L.run(store, make_settings(), as_of=END)
    async with store.pool.acquire() as conn:
        got = {r["symbol"]: r["market_code"] for r in await conn.fetch("SELECT symbol, market_code FROM leadership")}
    assert (got[names[0]], got[names[1]], got[names[2]], got[names[3]]) == ("NIF50", "NIFSMA250", "NIF500", "NIFMID150")
