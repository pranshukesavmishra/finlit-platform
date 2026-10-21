"""ETFs: classification, parsing, the price metrics (hand-checked numbers), the nightly refresh over recorded Upstox/AMFI answers, and the API.

Fixtures (tests/fixtures/etf) are REAL answers recorded on 21 Oct 2026: the NSE instrument list rows, AMFI NAVAll lines, Upstox quotes and
10 years of daily candles for 17 ETFs (a plain index ETF, gold, silver, liquid, a young ETF, one with an unadjusted split, one with
repeated dates, one with almost no history, ...). Needs Postgres and Redis; skipped when they are not reachable.
"""

import gzip
import json
import math
import os
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from finlit import etf
from finlit.api import create_app
from finlit.config import Settings
from finlit.store import MIGRATIONS, Store
from test_integration import TEST_DB, TEST_REDIS, make_settings

FX = Path(__file__).parent / "fixtures" / "etf"
NOW = datetime(2026, 10, 21, 17, 30, tzinfo=timezone.utc)          # 23:00 IST, well after the close
CANDLES = json.loads(gzip.open(FX / "candles.json.gz", "rt").read())
QUOTES = json.loads((FX / "quotes.json").read_text())
INSTRUMENTS = json.loads(gzip.decompress((FX / "instruments.json.gz").read_bytes()))
ETFS = [r for r in INSTRUMENTS if etf.is_etf(r)]
BY_SYMBOL = {r["trading_symbol"]: r for r in ETFS}
BY_KEY = {r["instrument_key"]: r["trading_symbol"] for r in ETFS}
D = date.fromisoformat


# ------------------------------------------------------------------------------------------------------------ categories
def cat(scheme, short, exch, sym):
    return etf.classify(scheme, short, exch, sym)


def test_registered_name_decides_and_unclear_names_stay_blank():
    assert cat("Nippon India ETF Gold BeES", None, "NIP IND ETF GOLD BEES", "GOLDBEES") == "gold"
    assert cat("Axis Nifty 50 ETF", "Axis Nifty AAA Bond Plus SDL Apr 2026 50:50 ETF", "AXISAMC-NIFTYAXIS", "NIFTYAXIS") == "nifty50"   # Upstox's short name was wrong
    assert cat(None, "DSP Nifty Bank ETF", "DSPAMC - DSPPSBKETF", "PSUBANKADD") is None      # short name says bank, symbol says PSU bank: do not guess
    assert cat(None, "ICICI Pru Nifty PSU Bank ETF", "ICICIPRAMC - ICICIBANKP", "PVTBANIETF") is None
    assert cat(None, None, "HDFCAMC - HDFCNIMEG", "HDFCNIMEG") is None
    assert cat(None, "Groww Nifty Cements ETF", "GROWWAMC - CEMNTGROWW", "CEMNTGROWW") is None


@pytest.mark.parametrize("name,key", [
    ("Mirae Asset Nifty 100 ESG Sector Leaders ETF", "factor"),                    # "ESG SECTOR" must not read as G-Sec
    ("Mirae Asset Nifty India New Age Consumption ETF", "consumption"),            # "new age" alone is not an EV fund
    ("ICICI Prudential Nifty EV & New Age Automotive ETF", "ev"),
    ("Mirae Asset Nifty200 Momentum 30 Plus 8-13 yr G-Sec 50:50 ETF", "hybrid"),
    ("Aditya Birla Sun Life CRISIL Liquid Overnight ETF", "liquid"),
    ("UTI Nifty 10 yr Benchmark G-Sec ETF", "gsec"),
    ("Bharat Bond ETF - April 2030", "bond"),
    ("ICICI Prudential Nifty Financial Services Ex-Bank ETF", "financial"),
    ("Nippon India ETF Nifty Bank BeES", "bank"),
    ("Mirae Asset Nifty PSU Bank ETF", "psu_bank"),
    ("HDFC NIFTY Private Bank ETF", "pvt_bank"),
    ("Nippon India Nifty Next 50 Junior BeES", "next50"),
    ("DSP BSE SENSEX Next 30 ETF", "sensex_next"),
    ("HDFC Nifty 50 Value 20 ETF", "factor"),                                      # a Nifty 50 strategy index, not plain Nifty 50
    ("Nifty 500 Healthcare", "health"),
    ("Mirae Asset Nifty Smallcap 250 Momentum Quality 100 ETF", "factor"),
    ("Motilal Oswal Nasdaq 100 ETF", "intl"),
    ("Mirae Asset S&P 500 Top 50 ETF", "intl"),
    ("Kotak Nifty IT ETF", "it"),
    ("SBI Nifty IT ETF", "it"),
    ("Nippon India Nifty 50 Shariah BeES", "factor"),
    ("Invesco India Nifty ETF", "nifty50"),
])
def test_category_words(name, key):
    assert etf.category_of(name) == key


def test_every_fixture_etf_gets_the_expected_category():
    want = {"NIFTYBEES": "nifty50", "GOLDBEES": "gold", "BANKBEES": "bank", "LIQUIDBEES": "liquid", "ITBEES": "it", "JUNIORBEES": "next50",
            "SILVERBEES": "silver", "MID150BEES": "midcap", "HDFCVALUE": "factor", "MON100": "intl", "GSEC10ABSL": "gsec", "PSUBANKADD": "psu_bank",
            "GROWWMOM50": "factor", "HDFCNIMEG": None, "SILVER001": "silver"}
    amfi = etf.parse_amfi((FX / "amfi.txt").read_text(), [r["isin"] for r in ETFS])
    for sym, key in want.items():
        r = BY_SYMBOL[sym]
        a = amfi.get(r["isin"])
        assert etf.classify(a["name"] if a else None, r.get("short_name"), r["name"], sym) == key, sym


# ------------------------------------------------------------------------------------------------------------ source parsing
def test_instrument_stream_reads_gzip_in_tiny_pieces_and_keeps_only_etfs():
    blob = (FX / "instruments.json.gz").read_bytes()
    pieces = [blob[i:i + 7] for i in range(0, len(blob), 7)]              # objects are split across pieces
    rows = list(etf.iter_json_array(pieces))
    assert len(rows) == len(INSTRUMENTS) == 20
    keep = [r["trading_symbol"] for r in rows if etf.is_etf(r)]
    assert "RELIANCE" not in keep and "BSEFUND" not in keep and "GSBOND" not in keep      # shares, BSE rows and non-EQ rows are not ETFs
    assert len(keep) == 17 and "NIFTYBEES" in keep
    plain = json.dumps([{"a": 1}, {"b": [1, 2, {"c": "]"}]}]).encode()                    # an uncompressed array works too, brackets inside strings are fine
    assert list(etf.iter_json_array([plain[:9], plain[9:]])) == [{"a": 1}, {"b": [1, 2, {"c": "]"}]}]


def test_truncated_gzip_is_an_error_not_a_short_list():
    blob = (FX / "instruments.json.gz").read_bytes()
    with pytest.raises(Exception):
        list(etf.iter_json_array([blob[:len(blob) // 2]]))


def test_amfi_parse():
    text = (FX / "amfi.txt").read_text()
    out = etf.parse_amfi(text, [r["isin"] for r in ETFS])
    nb = out[BY_SYMBOL["NIFTYBEES"]["isin"]]
    assert nb["nav"] == pytest.approx(261.1221) and nb["date"] == D("2026-10-19")
    assert nb["house"] == "Nippon India" and nb["name"].startswith("Nippon India ETF Nifty 50")
    assert "INF000000009" not in out                                         # a wanted-looking row with NAV "N.A." and an unknown ISIN
    only = etf.parse_amfi("Some Mutual Fund\r\n\r\n1;INFX;-;A ETF;;;N.A.;19-Oct-2026\r\n2;INFY;INFX;B ETF;;;10.5;19-Oct-2026\r\n3;-;INFY;B ETF;;;10.7;20-Oct-2026\r\n", ["INFX", "INFY"])
    assert set(only) == {"INFX", "INFY"} and only["INFX"]["nav"] == 10.5 and only["INFY"]["nav"] == 10.7 and only["INFY"]["date"] == D("2026-10-20")


def test_names():
    assert etf.tidy_scheme("Mirae Asset Nifty 1D Rate Liquid ETF-IDCW") == "Mirae Asset Nifty 1D Rate Liquid ETF"
    assert etf.tidy_scheme("Mirae Asset Nifty 1D Rate Liquid ETF - Growth") == "Mirae Asset Nifty 1D Rate Liquid ETF"
    assert etf.display_name("DSP NIFTY 10 YR BENCHMARK G-SEC ETF", "DSP Nifty 10 yr G-Sec ETF", "DSPAMC - GSEC10ADD") == "DSP Nifty 10 yr G-Sec ETF"   # all capitals: prefer the short name
    assert etf.display_name("Axis Gold ETF", "Axis Gold", "X") == "Axis Gold ETF"
    assert etf.display_name(None, None, "QUANT_AMC - SILVER001") == "SILVER001"


# ------------------------------------------------------------------------------------------------------------ candles and metrics
def test_candles_are_cleaned():
    rows = [["2026-10-19T00:00:00+05:30", 10, 11, 9, 10.5, 100, 0], ["2026-10-16T00:00:00+05:30", 10, 9, 10.2, 10.1, 5, 0],     # high below the close: widened
            ["2026-10-15T00:00:00+05:30", 10, 11, 9, 0, 5, 0], ["bad"], ["2026-10-14T00:00:00+05:30", 10, 11, 9, 10, None, 0],     # no close, junk, no volume
            ["2026-10-14T00:00:00+05:30", 10, 11, 9, 10.4, 7, 0]]                                                                     # repeated date
    out, dup = etf.parse_candles(rows)
    assert [c[0] for c in out] == [D("2026-10-14"), D("2026-10-16"), D("2026-10-19")] and dup == D("2026-10-14")
    assert tuple(out[1][2:5]) == (10.1, 10.0, 10.1)         # high 9 / low 10.2 contradict the open and close: widened to contain them


def test_month_back_and_lookback():
    assert etf.month_back(D("2026-10-21"), 12) == D("2025-10-21")
    assert etf.month_back(D("2026-03-31"), 1) == D("2026-02-28")
    assert etf.month_back(D("2024-02-29"), 12) == D("2023-02-28")
    dates = [D("2026-10-01"), D("2026-10-05"), D("2026-10-20")]
    assert etf._lookback(dates, 0, D("2026-10-06")) == (1, None)
    assert etf._lookback(dates, 0, D("2026-09-30")) == (None, "listed")
    assert etf._lookback(dates, 0, D("2026-10-19"))[1] == "sparse"             # nothing for 14 days before the target
    assert etf._lookback(dates, 2, D("2026-10-06"))[1] == "break"


def test_drawdown_by_hand():
    d = [D("2026-01-0%d" % i) for i in range(1, 8)]
    dd, peak, trough = etf.drawdown([100, 110, 99, 105, 120, 90, 100], d)
    assert dd == pytest.approx(90 / 120 - 1) and peak == D("2026-01-05") and trough == D("2026-01-06")      # 120 down to 90 is -25%, not 110 to 99
    assert etf.drawdown([1, 2, 3], d[:3])[0] == 0.0


def daily(start, n, f):
    ds = [start + timedelta(days=i) for i in range(n)]
    return ds, [f(i) for i in range(n)]


def test_metrics_on_a_series_with_a_known_answer():
    # a price rising 0.05% every calendar day for 1,600 days: every figure follows from the growth rate by hand
    r = 0.0005
    ds, cs = daily(D("2022-05-01"), 1600, lambda i: 100 * (1 + r) ** i)
    L = ds[-1]
    m = etf.build_metrics(ds, cs, as_of=L)
    days = (L - etf.month_back(L, 12)).days
    assert m["ret_1y"] == pytest.approx(((1 + r) ** days - 1) * 100)
    assert m["ret_1m"] == pytest.approx(((1 + r) ** (L - etf.month_back(L, 1)).days - 1) * 100)
    d3 = (L - etf.month_back(L, 36)).days
    assert m["ret_3y"] == pytest.approx(((1 + r) ** d3 - 1) * 100)
    assert m["cagr_3y"] == pytest.approx(((1 + r) ** 365.25 - 1) * 100)         # a steady 0.05% a day compounds to the same yearly rate whatever the window
    assert m["vol_1y"] == pytest.approx(0, abs=1e-9)                             # identical daily returns have no spread
    assert m["mdd_1y"] == 0 and m["mdd_3y"] == 0
    assert m["ret_5y"] is None and m["cagr_5y"] is None and m["reasons"]["ret_5y"] == "Listed less than 5 years" and m["reasons"]["mdd_5y"] == "Listed less than 5 years"
    assert m["high52"] == pytest.approx(cs[-1]) and m["low52"] == pytest.approx(cs[-366]) and m["range_from"] == L - timedelta(days=365)


def test_volatility_is_sample_stdev_times_root_252():
    ds, cs = daily(D("2025-01-01"), 600, lambda i: 100 + (i % 2) * 2)          # 100, 102, 100, 102 ...: daily moves of +2% and -1.96...%
    m = etf.build_metrics(ds, cs, as_of=ds[-1])
    base = etf.bisect_right(ds, etf.month_back(ds[-1], 12)) - 1
    rets = [cs[j] / cs[j - 1] - 1 for j in range(base + 1, len(cs))]
    mean = sum(rets) / len(rets)
    expect = math.sqrt(sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)) * math.sqrt(252) * 100
    assert m["vol_1y"] == pytest.approx(expect) and expect > 20


def test_split_in_the_series_withholds_what_needs_earlier_prices():
    ds, cs = daily(D("2023-01-01"), 1500, lambda i: (1000 if i < 700 else 100) * (1 + 0.0002 * (i % 7)))
    m = etf.build_metrics(ds, cs, as_of=ds[-1])
    assert m["break_date"] == ds[700]
    assert m["ret_1y"] is not None and m["ret_3y"] is None and m["ret_5y"] is None                   # 3 years back reaches before the break
    assert "break on" in m["reasons"]["ret_3y"] and "Listed less" in m["reasons"]["ret_5y"] or "break on" in m["reasons"]["ret_5y"]
    assert m["cagr_3y"] is None and m["mdd_3y"] is None
    assert m["high52"] < 200                                                                           # never the pre-split 1,000s
    assert etf.find_break(ds, cs) == ds[700]
    assert etf.find_break(ds[:600], cs[:600]) is None
    assert etf.find_break(ds[:600], cs[:600], D("2023-03-01")) == D("2023-03-01")                     # a repeated date counts as a break too


def test_sparse_trading_gives_no_volatility_and_no_made_up_return():
    ds = [D("2026-10-20") - timedelta(days=25 * i) for i in range(40)][::-1]                           # one trade every 25 days
    m = etf.build_metrics(ds, [100 + i for i in range(40)], as_of=ds[-1])
    assert m["vol_1y"] is None and m["reasons"]["vol_1y"].startswith("Traded on only")
    assert m["ret_1m"] is None and m["reasons"]["ret_1m"] == "Too few trades around the start of this period"


def test_stale_price_is_said_so():
    ds, cs = daily(D("2025-01-01"), 400, lambda i: 100 + i)
    m = etf.build_metrics(ds, cs, as_of=ds[-1] + timedelta(days=12))
    assert m["reasons"]["price"].startswith("Last traded on")


def test_nifty_bees_figures_checked_by_hand_against_the_recorded_candles():
    """Prices read off the raw Upstox candles by hand (close of the last trading day on or before each look-back date)."""
    rows, _ = etf.parse_candles(CANDLES["NIFTYBEES"])
    qc = etf.quote_candle(next(q for q in QUOTES.values() if q["symbol"] == "NIFTYBEES"), rows[-1][0], NOW)
    assert qc[0] == D("2026-10-21") and qc[4] == 259.57                                    # today's candle: the market has closed, the quote is the close
    rows.append(qc)
    ds, cs, hs, ls, _vs = etf.merge_series(None, rows)
    m = etf.build_metrics(ds, cs, hs, ls, None, D("2026-10-21"))
    last = 259.57
    assert last / 267.76 - 1 == pytest.approx(m["ret_1m"] / 100)       # 21 Sep 2026
    assert last / 277.63 - 1 == pytest.approx(m["ret_6m"] / 100)       # 21 Apr 2026
    assert last / 291.87 - 1 == pytest.approx(m["ret_1y"] / 100)       # 21 Oct 2025
    assert last / 215.30 - 1 == pytest.approx(m["ret_3y"] / 100)       # 21 Oct 2023 was a Saturday: the 20th
    assert last / 196.08 - 1 == pytest.approx(m["ret_5y"] / 100)       # 21 Oct 2021
    assert [round(m[k], 2) for k in ("ret_1m", "ret_6m", "ret_1y", "ret_3y", "ret_5y")] == [-3.06, -6.51, -11.07, 20.56, 32.38]
    assert round(m["cagr_3y"], 2) == 6.42 and round(m["cagr_5y"], 2) == 5.77
    assert round(m["vol_1y"], 2) == 13.02 and [round(m[k], 2) for k in ("mdd_1y", "mdd_3y", "mdd_5y")] == [-14.82, -15.23, -15.73]
    assert (m["high52"], m["low52"]) == (302.25, 251.7)               # highest high / lowest low of the last 365 days, from the raw candles
    assert m["break_date"] is None and m["first_date"] == D("2016-10-24")


def test_premium_uses_the_etfs_own_close_on_the_nav_day_only():
    ds = [D("2026-10-16"), D("2026-10-19"), D("2026-10-21")]
    cs = [100.0, 101.0, 103.0]
    assert etf.premium_of(ds, cs, 100.0, D("2026-10-19")) == (pytest.approx(1.0), None)
    assert etf.premium_of(ds, cs, 100.0, D("2026-10-20")) == (None, "The ETF did not trade on the NAV date (20 Oct 2026)")     # a holiday NAV: no premium
    assert etf.premium_of(ds, cs, None, None) == (None, None)
    assert etf.premium_of(ds, cs, 0.1, D("2026-10-19"))[0] is None                                                          # wildly different: wrong unit, not a premium


def test_weekly_series_and_rebase():
    ds, cs = daily(D("2026-01-01"), 21, lambda i: 100 + i)
    wd, wv = etf.weekly(ds, cs)
    assert wd[0] == ds[0] and wd[-1] == ds[-1] and len(wd) < len(ds) and all(v == 100 + (d - ds[0]).days for d, v in zip(wd, wv))
    out = etf.rebase({"A": (ds, cs), "B": (ds, [2 * c for c in cs])}, D("2026-01-06"))
    assert out["A"][0] == ["2026-01-06", 100.0] and out["B"][0] == ["2026-01-06", 100.0]
    assert out["A"][-1][1] == pytest.approx(120 / 105 * 100, abs=1e-3) and out["B"][-1][1] == out["A"][-1][1]


def test_quote_candle_only_after_the_close_and_for_a_new_day():
    q = {"last_trade_time": str(int(datetime(2026, 10, 21, 15, 29, tzinfo=etf.IST).timestamp() * 1000)), "last_price": 10.5, "volume": 100,
         "ohlc": {"open": 10, "high": 11, "low": 9.5, "close": 10.5}}
    assert etf.quote_candle(q, D("2026-10-19"), NOW)[4] == 10.5
    assert etf.quote_candle(q, D("2026-10-21"), NOW) is None                                      # history already has the day
    assert etf.quote_candle(q, D("2026-10-19"), datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)) is None     # 13:30 IST: still trading
    assert etf.quote_candle({**q, "last_price": 0}, D("2026-10-19"), NOW) is None
    assert etf.quote_candle({**q, "last_trade_time": "0"}, D("2026-10-19"), NOW) is None


def test_merge_keeps_old_days_and_new_ones_win():
    old = {"dates": [D("2026-10-14"), D("2026-10-15")], "closes": [10.0, 11.0], "highs": [10.5, 11.5], "lows": [9.5, 10.5]}
    ds, cs, hs, ls, vs = etf.merge_series(old, [(D("2026-10-15"), 11, 12, 10, 11.4, 5), (D("2026-10-16"), 11, 13, 11, 12, 6)])
    assert ds == [D("2026-10-14"), D("2026-10-15"), D("2026-10-16")] and cs == [10.0, 11.4, 12] and hs == [10.5, 12, 13] and ls == [9.5, 10, 11] and vs == [0.0, 5, 6]


def test_search_scoring():
    def s(q, text):
        w = etf._words(text)
        return etf.search_score(q, w, "".join(w))
    assert s("nifty bees", "Nippon India ETF Nifty 50 BeES NIFTYBEES") > 0
    assert s("niftybees", "Nippon India ETF Nifty 50 BeES NIFTYBEES") > 0
    assert s("nifti bees", "Nippon India ETF Nifty 50 BeES NIFTYBEES") > 0          # a typo
    assert s("gold", "Nippon India ETF Gold BeES GOLDBEES") >= 90
    assert s("goldbes", "Nippon India ETF Gold BeES GOLDBEES") > 0
    assert s("silver", "Nippon India ETF Gold BeES GOLDBEES") == 0
    assert s("bank psu", "Mirae Asset Nifty PSU Bank ETF") > 0                       # word order is free
    assert s("", "anything") == 1


# ------------------------------------------------------------------------------------------------------------ the nightly refresh over recorded answers
class Provider:
    """The recorded answers as an httpx transport: the instrument list, AMFI, Upstox quotes and daily candles (cut to the requested dates)."""

    def __init__(self, *, instruments=None, quotes_status=200, candles_status=200, empty_candles=False, token=True, amfi_status=200, candle_cut=None):
        self.calls, self.instruments, self.quotes_status, self.candles_status = [], instruments, quotes_status, candles_status
        self.empty, self.token, self.amfi_status, self.cut = empty_candles, token, amfi_status, candle_cut

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(str(req.url))
        if req.url.host == "assets.upstox.com":
            body = (FX / "instruments.json.gz").read_bytes() if self.instruments is None else gzip.compress(json.dumps(self.instruments).encode())
            return httpx.Response(200, content=body, headers={"content-type": "application/gzip"})
        if req.url.host == "portal.amfiindia.com":
            return httpx.Response(self.amfi_status, content=(FX / "amfi.txt").read_bytes() if self.amfi_status == 200 else b"")
        assert req.url.host == "api.upstox.com"
        if not self.token:
            return httpx.Response(401, json={"status": "error"})
        if req.url.path == "/v2/market-quote/quotes":
            if self.quotes_status != 200:
                return httpx.Response(self.quotes_status, json={"status": "error"})
            keys = set(req.url.params["instrument_key"].split(","))
            return httpx.Response(200, json={"status": "success", "data": {k: v for k, v in QUOTES.items() if v["instrument_token"] in keys}})
        if req.url.path.startswith("/v3/historical-candle/"):
            if self.candles_status != 200:
                return httpx.Response(self.candles_status, json={"status": "error"})
            _, _, _, key, _, _, to, frm = urllib.parse.unquote(req.url.path).split("/")
            rows = [] if self.empty else [c for c in CANDLES.get(BY_KEY.get(key, ""), []) if frm <= c[0][:10] <= to]
            if self.cut and rows:
                rows = rows[:self.cut]
            return httpx.Response(200, json={"status": "success", "data": {"candles": rows}})
        return httpx.Response(404)


@pytest.fixture
async def store(monkeypatch):
    monkeypatch.setattr(etf, "MIN_INSTRUMENTS", 10)        # the fixtures hold 17 ETFs; the real floor is 100 (tested below)
    s = Settings(database_url=TEST_DB, redis_url=TEST_REDIS)
    try:
        st = await Store.connect(s)
        await st.redis.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    async with st.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS etf_history, etf_runs, etf_funds CASCADE")
        await conn.execute("DROP TABLE IF EXISTS etf_hot CASCADE")
        await conn.execute((MIGRATIONS / "034_etf.sql").read_text())
        await conn.execute((MIGRATIONS / "038_etf_hot.sql").read_text())
    async for k in st.redis.scan_iter("etf:*"):
        await st.redis.delete(k)
    yield st
    await st.close()


def S(token="placeholder"):
    return Settings(upstox_access_token=token, database_url=TEST_DB, redis_url=TEST_REDIS)


async def snapshot(store):
    async with store.pool.acquire() as conn:
        funds = [dict(r) for r in await conn.fetch("SELECT * FROM etf_funds ORDER BY symbol")]
        hist = [dict(r) for r in await conn.fetch("SELECT symbol, dates, closes, highs, lows FROM etf_history ORDER BY symbol")]
    for f in funds:
        f.pop("updated_at")
    return funds, hist


async def fund(store, sym):
    async with store.pool.acquire() as conn:
        r = dict(await conn.fetchrow("SELECT * FROM etf_funds WHERE symbol = $1", sym))
    r["reasons"], r["extra"] = json.loads(r["reasons"]), json.loads(r["extra"])
    return r


async def test_refresh_without_a_token_does_nothing(store):
    prov = Provider()
    assert (await etf.refresh(store, S(""), transport=httpx.MockTransport(prov), now=NOW))["status"] == "skipped"
    assert prov.calls == []


async def test_first_refresh_stores_everything(store):
    prov = Provider()
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(prov), now=NOW)
    assert r["status"] == "ok", r
    assert r["instruments"] == 17 and r["quotes"] == 17 and r["amfi_matched"] == 15 and r["full"] == 17 and r["updated"] == 17 and not r["quote_disagree"]
    assert sum("/v2/market-quote/quotes" in c for c in prov.calls) == 1                     # one batch for all 17
    assert not any("Bearer" in c for c in prov.calls)
    nb = await fund(store, "NIFTYBEES")
    assert nb["category"] == "nifty50" and nb["asset_class"] == "equity" and nb["fund_house"] == "Nippon India" and nb["display_name"].startswith("Nippon India ETF Nifty 50")
    assert (nb["price"], nb["prev_close"], nb["price_date"]) == (259.57, 261.2, D("2026-10-21"))
    assert round(nb["change_pct"], 2) == -0.62 and round(nb["ret_1y"], 2) == -11.07 and round(nb["vol_1y"], 2) == 13.02
    assert nb["nav"] == pytest.approx(261.1221) and nb["nav_date"] == D("2026-10-19")
    assert round(nb["nav_premium"], 2) == 0.03                                               # close 261.20 on 19 Oct against NAV 261.1221 the same day
    assert nb["volume"] == 9576959 and nb["avg_turnover"] > 1e9
    async with store.pool.acquire() as conn:
        h = await conn.fetchrow("SELECT dates, closes, highs, lows FROM etf_history WHERE symbol = 'NIFTYBEES'")
        assert h["dates"][-1] == D("2026-10-21") and h["closes"][-1] == 259.57 and len(h["highs"]) == etf.TAIL == len(h["lows"])
        assert await conn.fetchval("SELECT status FROM etf_runs ORDER BY id DESC LIMIT 1") == "ok"
    # broken or special series
    hv = await fund(store, "HDFCVALUE")
    assert hv["break_date"] == D("2022-09-29") and hv["ret_5y"] is None and "break on 29 Sep 2022" in hv["reasons"]["ret_5y"] and hv["ret_3y"] is not None
    ms = await fund(store, "MIDSELIETF")
    assert ms["break_date"] == D("2017-03-14") and ms["ret_5y"] is not None                  # repeated dates / jumps only until March 2017: five years are fine
    young = await fund(store, "GROWWMOM50")
    assert young["ret_1y"] is not None and young["ret_3y"] is None and young["reasons"]["ret_3y"] == "Listed less than 3 years"
    far = await fund(store, "FARBEES")
    assert far["ret_1y"] is None and far["points"] <= 4
    mon = await fund(store, "MON100")
    assert mon["nav_premium"] > 10 and etf.row_view(mon)["premiumWide"] is True              # overseas ETFs really trade at large premiums: shown, with a note
    liq = await fund(store, "LIQUIDBEES")
    assert liq["category"] == "liquid" and liq["nav_premium"] is None and "did not trade on the NAV date" in liq["reasons"]["nav_premium"]   # NAV dated on a market holiday
    unk = await fund(store, "HDFCNIMEG")
    assert unk["category"] is None and unk["nav"] is None and unk["scheme_name"] is None and unk["display_name"] == "HDFCNIMEG"
    assert (await fund(store, "PSUBANKADD"))["category"] == "psu_bank"                       # AMFI settles what the Upstox names could not


async def test_a_second_night_only_adds_the_last_weeks_and_changes_nothing_else(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    before = await snapshot(store)
    prov = Provider()
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(prov), now=NOW + timedelta(hours=1))
    assert r["status"] == "ok" and r["incremental"] == 16 and r["full"] == 1 and r["adjusted"] == 0       # the one ETF with no traded value is cold: it keeps no stored history, so it is taken in full
    assert await snapshot(store) == before
    # the candle call asked only for the last ~40 days before the stored end, not 10 years
    candle_calls = [c for c in prov.calls if "historical-candle" in c]
    assert len(candle_calls) == 17 and all(c.rsplit("/", 1)[1] >= "2026-08-01" or "INF" in c for c in candle_calls)      # from ~40 days before the stored end, not 10 years back


async def test_a_new_trading_day_is_appended(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    # next evening: Upstox history now carries 21 Oct for real and the quote is for the 22nd
    day = datetime(2026, 10, 22, 15, 29, tzinfo=etf.IST)
    ms = int(day.timestamp() * 1000)
    quotes = {k: {**v, "last_trade_time": str(ms), "last_price": round(v["last_price"] * 1.01, 2), "ohlc": {**v["ohlc"], "close": round(v["last_price"] * 1.01, 2), "high": round(v["last_price"] * 1.02, 2)}} for k, v in QUOTES.items()}
    prov = Provider()
    real = prov.__call__

    def handler(req):
        if req.url.path == "/v2/market-quote/quotes":
            keys = set(req.url.params["instrument_key"].split(","))
            return httpx.Response(200, json={"status": "success", "data": {k: v for k, v in quotes.items() if v["instrument_token"] in keys}})
        if req.url.path.startswith("/v3/historical-candle/"):   # the real 21 Oct candle arrives, equal to the stored provisional one
            r = real(req)
            body = r.json()
            key = urllib.parse.unquote(req.url.path).split("/")[3]
            q = next(v for v in QUOTES.values() if v["instrument_token"] == key)
            body["data"]["candles"].insert(0, ["2026-10-21T00:00:00+05:30", q["ohlc"]["open"], q["ohlc"]["high"], q["ohlc"]["low"], q["last_price"], q["volume"], 0])
            return httpx.Response(200, json=body)
        return real(req)
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(handler), now=datetime(2026, 10, 22, 17, 30, tzinfo=timezone.utc))
    assert r["status"] == "ok" and r["adjusted"] == 0, r
    nb = await fund(store, "NIFTYBEES")
    assert nb["price_date"] == D("2026-10-22") and nb["prev_close"] == 259.57 and nb["price"] == round(259.57 * 1.01, 2)
    assert round(nb["change_pct"], 2) == 1.0


async def test_a_provider_adjustment_of_old_prices_triggers_a_full_refetch(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    real = Provider()

    def handler(req):
        r = real(req)
        if req.url.path.startswith("/v3/historical-candle/"):
            body = r.json()
            body["data"]["candles"] = [[c[0], c[1] / 2, c[2] / 2, c[3] / 2, c[4] / 2, c[5], 0] for c in body["data"]["candles"]]      # a 2:1 split, history restated
            return httpx.Response(200, json=body)
        return r
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(handler), now=NOW + timedelta(hours=1))
    assert r["adjusted"] >= 10 and r["full"] == r["adjusted"] + 1  # +1: the cold ETF has no stored history to compare, so it is always taken in full;                               # every ETF whose stored days no longer matched was taken again in full


async def test_short_or_empty_answers_never_overwrite_good_rows(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    before = await snapshot(store)
    later = NOW + timedelta(days=8)                                                           # past the weekly full re-fetch
    for prov in (Provider(empty_candles=True), Provider(candle_cut=40), Provider(candles_status=500)):
        r = await etf.refresh(store, S(), transport=httpx.MockTransport(prov), now=later)
        assert r["status"] == "partial" and len(r["kept"]) >= 10, r
        funds, hist = await snapshot(store)
        assert [(f["symbol"], f["price"], f["ret_1y"], f["points"]) for f in funds] == [(f["symbol"], f["price"], f["ret_1y"], f["points"]) for f in before[0]]
        assert [h["closes"] for h in hist] == [h["closes"] for h in before[1]]


async def test_expired_token_keeps_everything_and_says_so(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    before = await snapshot(store)
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider(token=False)), now=NOW + timedelta(days=1))
    assert r["status"] == "token_expired" and "expired" in r["reason"]
    assert await snapshot(store) == before


async def test_a_shrunken_instrument_list_is_refused(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    before = await snapshot(store)
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider(instruments=ETFS[:4])), now=NOW + timedelta(days=1))
    assert r["status"] == "refused" and "nothing was changed" in r["reason"]
    assert await snapshot(store) == before
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM etf_funds WHERE active") == 17


async def test_amfi_down_keeps_names_and_nav(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    before = await fund(store, "NIFTYBEES")
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider(amfi_status=503)), now=NOW + timedelta(hours=1))
    after = await fund(store, "NIFTYBEES")
    assert "amfi" in r and (after["nav"], after["nav_date"], after["scheme_name"], after["display_name"], after["category"]) == \
        (before["nav"], before["nav_date"], before["scheme_name"], before["display_name"], before["category"])


async def test_quotes_failing_still_stores_history_without_todays_candle(store):
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider(quotes_status=500)), now=NOW)
    assert r["status"] == "partial" and r["quotes"] == 0 and r["updated"] == 17
    assert (await fund(store, "NIFTYBEES"))["price_date"] == D("2026-10-19")


async def test_etfs_that_left_the_list_are_marked_not_deleted(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    keep = [r for r in ETFS if r["trading_symbol"] != "FARBEES"]                              # 16 of 17 is above the 80% line
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider(instruments=keep)), now=NOW + timedelta(hours=1))
    assert r["status"] in ("ok", "partial")
    f = await fund(store, "FARBEES")
    assert f["active"] is False and f["price"] is not None


async def test_the_absolute_floor_on_the_instrument_list(store, monkeypatch):
    monkeypatch.setattr(etf, "MIN_INSTRUMENTS", 100)
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)       # 17 ETFs on a fresh database: not believable as the whole list
    assert r["status"] == "refused"
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM etf_funds") == 0


# ------------------------------------------------------------------------------------------------------------ the API
@pytest.fixture
async def api(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def test_list_counts_are_honest_and_carry_the_required_notes(api):
    r = await api.get("/api/etf")
    b = r.json()
    assert r.status_code == 200 and b["total"] == 17 and b["universe"] == 17 and len(b["items"]) == 17 and b["asOf"] == "2026-10-21"
    assert b["disclaimer"] == "Information only. Not investment advice. Past returns do not guarantee future returns."
    assert "Upstox" in b["source"] and "AMFI" in b["source"] and b["updatedAt"]
    assert r.headers["cache-control"].startswith("public")
    assert b["items"][0]["symbol"] == "LIQUIDBEES" and b["items"][1]["symbol"] == "SILVERBEES"      # most rupees traded a day first (20-session average)
    have = [i["avgTurnover"] for i in b["items"] if i["avgTurnover"] is not None]
    assert have == sorted(have, reverse=True) and b["items"][-1]["avgTurnover"] is None or len(have) == 17
    lim = (await api.get("/api/etf?limit=5&offset=3")).json()
    assert lim["total"] == 17 and len(lim["items"]) == 5 and lim["offset"] == 3
    assert len((await api.get("/api/etf?limit=100000")).json()["items"]) == 17 and (await api.get("/api/etf?limit=100000")).json()["limit"] == 100
    assert {c["key"] for c in b["categories"]} >= {"nifty50", "gold", "none"} and sum(c["count"] for c in b["categories"]) == 17
    nb = next(i for i in b["items"] if i["symbol"] == "NIFTYBEES")
    assert nb["price"] == 259.57 and nb["changePct"] == -0.62 and nb["ret1y"] == -11.07 and nb["cagr3y"] == 6.42 and nb["premium"] == 0.03 and nb["navDate"] == "2026-10-19"


async def test_search_filters_and_sort(api):
    async def syms(qs):
        return [i["symbol"] for i in (await api.get("/api/etf?" + qs)).json()["items"]]
    assert "NIFTYBEES" in (await syms("q=nifty%20bees"))[:2]
    assert (await syms("q=niftybees"))[0] == "NIFTYBEES"
    assert "NIFTYBEES" in (await syms("q=nifti%20bees"))                                         # a typo
    assert set(await syms("q=silver")) == {"SILVERBEES", "SILVER001"}
    assert (await syms("q=INF204KB14I2")) == ["NIFTYBEES"]                                        # by ISIN
    assert (await api.get("/api/etf?q=zzzzqqq")).json()["total"] == 0
    assert set(await syms("category=gold,silver")) == {"GOLDBEES", "SILVERBEES", "SILVER001"}
    assert set(await syms("asset=debt")) == {"LIQUIDBEES", "GSEC10ABSL", "FARBEES"}
    assert set(await syms("category=none")) == {"HDFCNIMEG"}
    assert (await syms("category=bogus,gold")) == ["GOLDBEES"]                                    # unknown values are ignored, never an error
    hi = (await api.get("/api/etf?ret1yMin=10")).json()
    assert {i["symbol"] for i in hi["items"]} >= {"GOLDBEES", "SILVERBEES"} and all(i["ret1y"] >= 10 for i in hi["items"])
    assert hi["excluded"] == 3 and hi["universe"] == 17                                           # ETFs with no 1-year figure are counted as left out, never hidden silently
    assert (await api.get("/api/etf?ret1yMin=abc&ret1yMax=nan")).json()["total"] == 17           # unusable bounds are ignored
    asc = (await api.get("/api/etf?sort=ret1y&order=asc")).json()["items"]
    vals = [i["ret1y"] for i in asc]
    nn = [v for v in vals if v is not None]
    assert nn == sorted(nn) and vals[len(nn):] == [None] * (len(vals) - len(nn))                  # blanks always last
    assert (await syms("sort=name&order=asc"))[0] == min((await api.get("/api/etf")).json()["items"], key=lambda i: i["name"].lower())["symbol"]
    assert (await api.get("/api/etf?sort=hack;drop")).status_code == 200


async def test_detail(api):
    r = await api.get("/api/etf/niftybees?range=1Y")
    b = r.json()
    assert r.status_code == 200 and b["symbol"] == "NIFTYBEES" and b["isin"] == "INF204KB14I2" and b["category"] == "nifty50"
    assert [x["key"] for x in b["returns"]] == ["1m", "6m", "1y", "3y", "5y"] and b["returns"][2]["price"] == -11.07
    assert b["returns"][3]["annualised"] == 6.42 and b["returns"][0]["annualised"] is None
    assert b["risk"]["vol1y"]["value"] == 13.02 and b["risk"]["drawdowns"][0]["value"] == -14.82 and b["risk"]["drawdowns"][0]["peak"] and b["risk"]["range52"]["high"] == 302.25
    assert b["nav"]["value"] == 261.1221 and b["nav"]["date"] == "2026-10-19" and b["nav"]["premium"] == 0.03 and b["nav"]["source"] == "AMFI"
    assert "Expense ratio" in b["unavailable"] and "Tracking error" in b["unavailable"] and b["unavailableWhy"] == "Not published in our price data source"
    s = b["series"]
    assert s["available"] and s["range"] == "1Y" and s["grain"] == "daily" and s["points"][0][0] == "2025-10-21" and s["points"][0][1] == 291.87 and s["points"][-1] == ["2026-10-21", 259.57]
    assert {k for k, v in b["ranges"].items() if v["available"]} == {"1M", "6M", "1Y", "3Y", "5Y", "MAX"}
    assert b["disclaimer"].startswith("Information only") and b["asOf"] == "2026-10-21"
    five = (await api.get("/api/etf/NIFTYBEES?range=5Y")).json()["series"]
    assert five["grain"] == "weekly" and five["points"][0] == ["2021-10-21", 196.08] and five["points"][-1] == ["2026-10-21", 259.57] and len(five["points"]) < 300
    mx = (await api.get("/api/etf/NIFTYBEES?range=max")).json()["series"]
    assert mx["points"][0][0] == "2016-10-24"


async def test_detail_of_a_young_split_and_blank_etfs_explains_itself(api):
    young = (await api.get("/api/etf/GROWWMOM50?range=3Y")).json()
    assert young["series"]["available"] is False and young["series"]["why"] == "Listed less than 3 years" and young["ranges"]["3Y"]["available"] is False
    assert young["returns"][3]["price"] is None and young["returns"][3]["why"] == "Listed less than 3 years"
    hv = (await api.get("/api/etf/HDFCVALUE?range=5Y")).json()
    assert hv["breakNote"].startswith("Prices before 29 Sep 2022") and hv["series"]["available"] is False and "break" in hv["series"]["why"]
    mx = (await api.get("/api/etf/HDFCVALUE?range=MAX")).json()["series"]
    assert mx["points"][0][0] == "2022-09-29" and min(p[1] for p in mx["points"]) > 50          # nothing from before the split: no 1,189 -> 84 cliff
    assert (await api.get("/api/etf/FARBEES")).json()["returns"][2]["price"] is None
    liq = (await api.get("/api/etf/LIQUIDBEES")).json()
    assert liq["nav"]["premium"] is None and "did not trade" in liq["nav"]["premiumWhy"]


async def test_detail_errors(api):
    assert (await api.get("/api/etf/NOSUCHETF")).status_code == 404
    assert (await api.get("/api/etf/..%2Fetc")).status_code in (404, 400)
    assert (await api.get("/api/etf/NIFTYBEES?range=7Y")).status_code == 400
    assert (await api.get("/api/etf/ni'ftybees")).status_code == 404


async def test_compare(api):
    r = await api.get("/api/etf/compare?symbols=NIFTYBEES,GOLDBEES&range=1Y")
    b = r.json()
    assert r.status_code == 200 and b["symbols"] == ["NIFTYBEES", "GOLDBEES"] and b["start"] == "2025-10-21"
    assert [i["symbol"] for i in b["items"]] == ["NIFTYBEES", "GOLDBEES"] and b["items"][1]["ret1y"] is not None
    assert b["series"]["NIFTYBEES"][0] == ["2025-10-21", 100.0] and b["series"]["GOLDBEES"][0][1] == 100.0
    assert b["series"]["NIFTYBEES"][-1][1] == pytest.approx(259.57 / 291.87 * 100, abs=0.01)
    assert b["disclaimer"].startswith("Information only") and "Upstox" in b["source"]
    young = (await api.get("/api/etf/compare?symbols=NIFTYBEES,GROWWMOM50,HDFCVALUE,SILVERBEES&range=MAX")).json()
    assert young["start"] == max(young["series"][s][0][0] for s in young["series"])               # starts where the newest of them begins
    assert any("chart starts on" in n and "GROWWMOM50" in n for n in young["notes"]) and any("29 Sep 2022" in n for n in young["notes"])
    assert all(v[0][1] == 100.0 for v in young["series"].values())
    assert (await api.get("/api/etf/compare?symbols=NIFTYBEES")).status_code == 400
    assert (await api.get("/api/etf/compare?symbols=A,B,C,D,E")).status_code == 400
    assert (await api.get("/api/etf/compare?symbols=NIFTYBEES,NOSUCH")).status_code == 404
    assert (await api.get("/api/etf/compare?symbols=NIFTYBEES,GOLDBEES&range=2Y")).status_code == 400
    assert (await api.get("/api/etf/compare?symbols=NIFTYBEES,niftybees")).status_code == 400    # the same ETF twice is one ETF


async def test_price_against_amfi_nav_cross_check(api):
    """The exchange close and AMFI's NAV of the same day agree closely for plain ETFs; overseas ETFs are the known exception."""
    items = {i["symbol"]: i for i in (await api.get("/api/etf")).json()["items"]}
    checked = 0
    for sym in ("NIFTYBEES", "GOLDBEES", "BANKBEES", "JUNIORBEES", "SILVERBEES", "MID150BEES", "ITBEES", "HDFCVALUE", "GSEC10ABSL"):
        i = items[sym]
        assert i["premium"] is not None and abs(i["premium"]) < 3, (sym, i["premium"], i["navDate"])
        checked += 1
    assert checked == 9


async def test_no_secret_in_any_response_or_stored_row(api, store):
    for path in ("/api/etf", "/api/etf/NIFTYBEES", "/api/etf/compare?symbols=NIFTYBEES,GOLDBEES"):
        assert "placeholder" not in (await api.get(path)).text
    async with store.pool.acquire() as conn:
        dump = json.dumps([dict(r) for r in await conn.fetch("SELECT detail FROM etf_runs")], default=str)
    assert "placeholder" not in dump and "Bearer" not in dump


def test_migration_numbering():
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    assert "034_etf.sql" in names
    assert len({n[:3] for n in names}) == len(names)                                              # no two migrations share a number
