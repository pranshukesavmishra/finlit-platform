"""ETF vs index fund (finlit/etf_vs_index.py): index detection from benchmark and name text, the pure maths against hand-worked examples (alignment,
point returns, rolling windows, XIRR, SIP, tracking error, drawdown, downside deviation), the summary by category, and the API on small stored fixtures.

The series are made up for the test; every expected figure is worked by hand in the comment beside it."""

import json
import math
import os
import re
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finlit import etf, etf_vs_index as ev, mf
from finlit import mf_compare
from finlit.config import Settings
from finlit.store import MIGRATIONS, Store

D0 = date(2024, 1, 1).toordinal()


def consecutive(n, start=D0):
    return list(range(start, start + n))


# ---------------------------------------------------------------------------------------------- which index

@pytest.mark.parametrize("text,key", [
    ("Nifty 50 TRI", "nifty50"), ("NIFTY 50 Index (TRI)", "nifty50"), ("Nifty 50 Total Return Index", "nifty50"), ("NIFTY50", "nifty50"),
    ("UTI Nifty 50 Index Fund - Direct Plan - Growth Option", "nifty50"), ("Nippon India ETF Nifty 50 BeES", "nifty50"), ("SBI Nifty Index Fund", "nifty50"),
    ("Nippon India ETF Nifty BeES", "nifty50"), ("NIFTYBEES", "nifty50"),
    ("Nifty Next 50 Index TRI", "niftynext50"), ("Nippon India ETF Nifty Next 50 Junior BeES", "niftynext50"),
    ("S&P BSE Sensex TRI", "sensex"), ("BSE Sensex (TRI)", "sensex"), ("HDFC BSE Sensex Index Fund", "sensex"),
    ("Nifty Bank Index (TRI)", "niftybank"), ("Nifty 500 TRI", "nifty500"), ("Nifty Midcap 150 Index TRI", "midcap150"), ("NIFTY MIDCAP150", "midcap150"),
    ("Nifty Smallcap 250 TRI", "smallcap250"), ("Nifty 100 Index", "nifty100"), ("Nifty Private Bank Index", "pvtbank"), ("Nifty Financial Services TRI", "finserv"),
])
def test_names_and_benchmarks_that_mean_one_index(text, key):
    assert ev.detect(text) == key


@pytest.mark.parametrize("text", [
    "Nifty 50 Equal Weight Index", "Nifty 50 Value 20 TRI", "Nifty 50 Arbitrage Index", "Nifty 50 USD", "Nifty 500 Value 50", "Nifty 500 Multicap 50:25:25",
    "Nifty Midcap 150 Quality 50", "Nifty Midcap 150 Momentum 50 TRI", "Nifty 100 Low Volatility 30", "BSE Sensex Next 30", "Nifty Financial Services 25/50",
    "CRISIL IBX Gilt Index", "Nifty 50 and Nifty Next 50 blend", "", None, "Gold ETF",
])
def test_variants_and_unclear_text_are_not_the_plain_index(text):
    assert ev.detect(text) is None


def test_return_type_is_read_from_the_text_and_never_assumed():
    assert ev.return_type("Nifty 50 TRI") == "TRI" and ev.return_type("S&P BSE Sensex Total Return Index") == "TRI"
    assert ev.return_type("Nifty 50 Price Return Index") == "price"
    assert ev.return_type("Nifty 50") is None and ev.return_type(None) is None


def test_classify_prefers_the_stated_benchmark_and_drops_conflicts():
    assert ev.classify("Nifty 50 TRI", ["UTI Nifty 50 Index Fund"]) == {"key": "nifty50", "basis": "benchmark", "returnType": "TRI", "conflict": False}
    assert ev.classify(None, ["UTI Nifty 50 Index Fund"]) == {"key": "nifty50", "basis": "name", "returnType": None, "conflict": False}
    c = ev.classify("Nifty Next 50 TRI", ["Some Nifty 50 Index Fund"])
    assert c["key"] is None and c["conflict"] is True            # two different indices: left out, not guessed
    assert ev.classify("Some strategy index", ["Plain fund"])["key"] is None
    assert ev.classify(None, [None, "Nippon India ETF Nifty 50 BeES"])["key"] == "nifty50"


# ---------------------------------------------------------------------------------------------- alignment and returns

def test_align_keeps_only_the_days_every_series_has():
    days, vals = ev.align({"a": ([1, 2, 3, 5], [10, 20, 30, 50]), "b": ([2, 3, 4, 5], [1, 2, 3, 5])})
    assert days == [2, 3, 5] and vals == {"a": [20, 30, 50], "b": [1, 2, 5]}
    assert ev.align({}) == ([], {})
    assert ev.align({"a": ([1, 2], [1, 2]), "b": ([3, 4], [1, 2])})[0] == []


def test_a_missing_day_in_one_product_removes_it_for_all_and_returns_span_the_gap():
    d = consecutive(10)
    a = [100.0 + k for k in range(10)]
    b_days = [x for x in d if x != d[4]]                      # b has no price on day 4
    b = [200.0 + (x - D0) for x in b_days]
    days, v = ev.align({"a": (d, a), "b": (b_days, b)})
    assert len(days) == 9 and D0 + 4 not in days
    assert ev.daily_returns(v["a"])[3] == pytest.approx(105.0 / 103.0 - 1)      # day 5 (105) against day 3 (103): the return across the gap


def test_period_return_worked_by_hand():
    days = consecutive(365, date(2025, 1, 1).toordinal())     # 1 Jan to 31 Dec 2025
    vals = [100.0 + k for k in range(365)]                    # +1 a day: 31 Dec is 464
    one_m = ev.period_return(days, vals, 1)                   # target 30 Nov (index 333, value 433): 464 / 433 - 1
    assert one_m["value"] == pytest.approx(round((464 / 433 - 1) * 100, 2)) and one_m["from"] == "2025-11-30" and one_m["cagr"] is None and one_m["why"] is None
    six = ev.period_return(days, vals, 6)                     # target 30 Jun (index 180, value 280)
    assert six["value"] == pytest.approx(round((464 / 280 - 1) * 100, 2))
    one_y = ev.period_return(days, vals, 12, "1 year")        # 31 Dec 2024 is before the first day: no return, with the reason
    assert one_y["value"] is None and "starts on 1 Jan 2025" in one_y["why"] and "31 Dec 2024" in one_y["why"]
    since = ev.period_return(days, vals, None)
    assert since["value"] == pytest.approx(364.0) and since["cagr"] is None       # 364 days: under a year, so no yearly rate


def test_cagr_over_two_years_is_the_yearly_rate():
    days = consecutive(732, date(2023, 1, 1).toordinal())     # 1 Jan 2023 to 1 Jan 2025: 731 days apart
    vals = [100 * 1.1 ** ((d - days[0]) / 365) for d in days]
    r = ev.period_return(days, vals, 24, "2 years")
    assert r["cagr"] == pytest.approx(10.0, abs=0.01) and r["value"] == pytest.approx((1.1 ** (731 / 365) - 1) * 100, abs=0.01) and r["from"] == "2023-01-01"


def test_look_back_price_must_be_within_ten_days():
    days = [d for d in consecutive(400) if not D0 + 20 <= d - 0 <= D0 + 330]       # a hole from day 20 to day 330
    vals = [100.0] * len(days)
    r = ev.period_return(days, vals, 12)
    assert r["value"] is None or r["from"] is not None
    last = days[-1]
    assert ev.at_or_before(days, last - 200) is None                  # nearest earlier price is 170+ days before the target


def test_rolling_windows_counted_by_hand():
    days = consecutive(800)                                   # 1 Jan 2024 + 799 days; 2024 is a leap year, so 1 Jan 2025 is day 366
    vals = [100.0 + k for k in range(800)]
    ed, rv = ev.rolling_returns(days, vals, 12)
    assert len(ed) == 800 - 366 and ed[0] == D0 + 366
    assert rv[0] == pytest.approx((466.0 / 100.0 - 1) * 100)  # day 366 (value 466) against day 0 (value 100)
    s = ev.roll_stats(rv)
    assert s["count"] == 434 and s["best"] == pytest.approx(rv[0], abs=0.01) and s["worst"] == pytest.approx(min(rv), abs=0.01) and s["positive"] == 100.0
    assert s["median"] == pytest.approx(sorted(rv)[216] / 2 + sorted(rv)[217] / 2, abs=0.01)
    few = ev.roll_stats(rv[:10])
    assert few["why"] and "not enough history" in few["why"]


def test_head_to_head_counts_ahead_level_and_behind():
    a = [1.0, 2.0, 3.0, 4.0]
    b = [1.0, 1.0, 5.0, 4.001]                               # level, ahead, behind, level (4.001 rounds to 4.00)
    h = ev.head_to_head(a, b)
    assert h == {"ahead": 25.0, "level": 50.0, "behind": 25.0, "windows": 4}


# ---------------------------------------------------------------------------------------------- XIRR, SIP, lump sum

def test_xirr_of_known_flows():
    assert ev.xirr([(0, -1000.0), (365, 1100.0)]) == pytest.approx(0.10, abs=1e-9)
    # 100 in at day 0 and day 365, 231 out at day 730: 100 x 1.1^2 + 100 x 1.1 = 231, so exactly 10%
    assert ev.xirr([(0, -100.0), (365, -100.0), (730, 231.0)]) == pytest.approx(0.10, abs=1e-9)
    assert ev.xirr([(0, -100.0), (365, 50.0)]) == pytest.approx(-0.5, abs=1e-9)
    assert ev.xirr([(0, -100.0), (10, -100.0)]) is None          # no money back: no rate
    assert ev.xirr([]) is None


def test_sip_days_move_to_the_next_common_day_and_clamp_short_months():
    days = [d for d in consecutive(200, date(2024, 1, 1).toordinal()) if date.fromordinal(d).weekday() < 5]
    got = [date.fromordinal(d) for d in ev.sip_days(days, date(2024, 1, 31).toordinal())]
    # 31 Jan (Wed), 29 Feb (Thu: February has 29 days in 2024), 31 Mar is a Sunday -> Mon 1 Apr, 30 Apr (Tue; April has 30 days), 31 May, 30 Jun is Sunday -> Mon 1 Jul
    assert got[:6] == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 4, 1), date(2024, 4, 30), date(2024, 5, 31), date(2024, 7, 1)]
    assert len(set(got)) == len(got)


def test_sip_on_a_steady_12_percent_series_has_a_12_percent_xirr():
    days = consecutive(3 * 365 + 40, date(2022, 1, 1).toordinal())
    vals = [100 * 1.12 ** ((d - days[0]) / 365) for d in days]
    r = ev.sip_result(days, vals, days[0], 10000.0)
    assert r["xirr"] == pytest.approx(12.0, abs=0.01) and r["installments"] == 38 and r["invested"] == 380000.0
    units = sum(10000.0 / vals[days.index(d)] for d in [date.fromisoformat(r["first"]).toordinal()])    # first instalment: 10000 / 100
    assert units == pytest.approx(100.0)
    assert r["value"] == pytest.approx(r["units"] * vals[-1], abs=0.01) and r["gain"] == pytest.approx(r["value"] - 380000.0, abs=0.01)


def test_sip_shorter_than_a_year_gives_no_yearly_rate():
    days = consecutive(200)
    r = ev.sip_result(days, [100.0 + k for k in range(200)], days[0], 1000.0)
    assert r["xirr"] is None and "less than a year" in r["xirrWhy"] and r["installments"] == 7


def test_lump_sum_by_hand():
    days = consecutive(731, date(2023, 1, 1).toordinal())
    vals = [100.0] * 730 + [121.0]
    r = ev.lump_result(days, vals, days[0], 50000.0)
    assert r["units"] == 500.0 and r["value"] == 60500.0 and r["gain"] == 10500.0 and r["gainPct"] == 21.0 and r["cagr"] == pytest.approx((1.21 ** (365 / 730) - 1) * 100, abs=0.01)
    assert ev.lump_result(days, vals, days[-1], 1000.0)["why"]


# ---------------------------------------------------------------------------------------------- tracking and risk

def _path(returns, start=100.0, places=None):
    out = [start]
    for r in returns:
        out.append(out[-1] * (1 + r))
    return [round(x, places) for x in out] if places else out


def test_tracking_error_is_zero_for_identical_series_and_follows_the_formula():
    rs = [0.001 * ((-1) ** i) + 0.0005 for i in range(300)]
    iv = _path(rs)
    t, n, why = ev.tracking_error(list(iv), list(iv))
    assert t == 0.0 and n == 300 and why is None
    d = 0.0004
    diffs = [d * (1 if i % 2 == 0 else -1) for i in range(300)]
    pv = _path([r + x for r, x in zip(rs, diffs)])
    t, n, _ = ev.tracking_error(pv, iv)
    assert t == pytest.approx(round(d * math.sqrt(300 / 299) * math.sqrt(252) * 100, 3), abs=0.002)     # sample st. dev. of +-d, annualised
    short, n2, why2 = ev.tracking_error(pv[:100], iv[:100])
    assert short is None and n2 == 99 and "not enough history" in why2


def test_volatility_and_downside_deviation_by_hand():
    rs = [0.01, -0.01] * 100
    v, why = ev.volatility(_path(rs))
    assert why is None and v == pytest.approx(0.01 * math.sqrt(200 / 199) * math.sqrt(252) * 100, abs=0.01)
    rs2 = [-0.01, 0.02] * 50
    dd, _ = ev.downside_deviation(_path(rs2))       # sqrt(mean(min(r,0)^2)) = sqrt(0.5 x 0.0001) = 0.0070711; x sqrt(252) x 100
    assert dd == pytest.approx(math.sqrt(0.5e-4) * math.sqrt(252) * 100, abs=0.01)
    assert ev.volatility([100.0, 101.0])[0] is None


def test_max_drawdown_of_a_known_path_with_dates():
    days = consecutive(6)
    r = ev.max_drawdown(days, [100.0, 120.0, 90.0, 95.0, 130.0, 65.0])      # 120 -> 90 is -25%; 130 -> 65 is -50%
    assert r == {"value": -50.0, "peak": date.fromordinal(D0 + 4).isoformat(), "trough": date.fromordinal(D0 + 5).isoformat()}
    up = ev.max_drawdown(days, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert up == {"value": 0.0, "peak": None, "trough": None}


def test_best_and_worst_day():
    days = consecutive(4)
    r = ev.best_worst_day(days, [100.0, 110.0, 99.0, 99.99])         # +10%, -10%, +1%
    assert r["best"] == {"value": 10.0, "date": date.fromordinal(D0 + 1).isoformat()} and r["worst"] == {"value": -10.0, "date": date.fromordinal(D0 + 2).isoformat()}


# ---------------------------------------------------------------------------------------------- the summary by category

def test_level_inside_the_tolerance_and_a_clear_gap():
    r = ev._lead({"a": 0.05, "b": 0.06}, False, ev.TOL_COST)
    assert r["level"] is True and sorted(r["leaders"]) == ["a", "b"]
    r = ev._lead({"a": 0.05, "b": 0.20}, False, ev.TOL_COST)
    assert r["leaders"] == ["a"] and r["level"] is False and r["gap"] == 0.15
    r = ev._lead({"a": 12.0, "b": 11.0, "c": None}, True, ev.TOL_RETURN)
    assert r["leaders"] == ["a"] and r["gap"] == 1.0
    assert ev._lead({"a": 1.0, "b": None}, True, 0.1)["leaders"] == []         # one value is not a comparison


def test_summary_rows_use_neutral_words_and_say_when_there_is_no_answer():
    names = {"a": "Sample ETF", "b": "Sample Fund"}
    rets = {"a": {"3Y": {"value": 40.0, "cagr": 11.9}}, "b": {"3Y": {"value": 39.0, "cagr": 11.5}}}
    risk = {"a": {"maxDrawdown": {"value": -12.0}, "volatility": 12.5}, "b": {"maxDrawdown": {"value": -12.2}, "volatility": 13.5}}
    rows = ev.summary_rows(names, rets, {"a": 0.05, "b": 0.20}, {"a": None, "b": None}, risk, "3Y", "3Y")
    text = {r["measure"]: r["text"] for r in rows}
    assert text["Higher return over 3 years"] == "Higher return over 3 years: level (within 0.25 percentage points)" or "Sample ETF" in text["Higher return over 3 years"]
    assert text["Lower expense ratio"] == "Lower expense ratio: Sample ETF"
    assert text["Smaller tracking error"] == "Smaller tracking error: not enough data to say"
    assert text["Smaller maximum fall"] == "Smaller maximum fall: level (within 0.5 percentage points)"
    assert text["Smaller volatility"] == "Smaller volatility: Sample ETF"
    sentence = ev.summary_sentence(names, rows, "2026-10-19", "3Y")
    assert sentence.endswith("Differences of this size can reverse in other periods. Information only, not investment advice.")
    assert "19 Oct 2026" in sentence and "Sample ETF 0.05" in sentence


def test_no_advice_words_in_the_module_text():
    src = Path(ev.__file__).read_text()
    shown = " ".join(re.findall(r'f?"([^"\n]{12,})"', src))
    for bad in (r"\bbuy\b", r"\bsell\b", r"\bhold\b", r"best[- ]to", r"\bwinner", r"\brecommend", r"\boutperform"):
        assert not re.search(bad, shown, re.I), bad


# ---------------------------------------------------------------------------------------------- compute() on two products and an index

def _series_pair():
    days = [d for d in consecutive(1500, date(2022, 1, 3).toordinal()) if date.fromordinal(d).weekday() < 5]
    rs = [0.0004 + 0.008 * math.sin(i / 7.0) for i in range(len(days) - 1)]
    idx = _path(rs, 1000.0)
    etfv = _path([r - 0.0000005 for r in rs], 50.0)             # an ETF that costs a hair less
    fund = _path([r - 0.0000020 for r in rs], 20.0)
    return days, idx, etfv, fund


def test_compute_runs_all_six_blocks_on_common_dates():
    days, idx, etfv, fund = _series_pair()
    prods = [{"id": "SAMPLEETF", "label": "SAMPLEETF"}, {"id": "1", "label": "Sample Index Fund"}]
    series = {"SAMPLEETF": (days, etfv), "1": (days[5:], fund[5:])}        # the fund starts five days later
    out = ev.compute(prods, series, (days, idx), None, 10000.0, 100000.0, None)
    assert out["common"]["days"] == len(days) - 5 and out["common"]["from"] == date.fromordinal(days[5]).isoformat()
    r = out["returns"]["SAMPLEETF"]
    assert r["1Y"]["value"] is not None and r["5Y"]["value"] is None and "5 years" in r["5Y"]["why"]
    assert r["since"]["value"] is not None
    assert out["rolling"]["stats"]["SAMPLEETF"]["count"] > 400 and out["rolling"]["headToHead"]["1"]["windows"] == out["rolling"]["windows"]
    tr = out["tracking"]["SAMPLEETF"]
    assert tr["te"]["value"] is not None and tr["te"]["value"] < tr["te"]["value"] + 1 and tr["td"]["1Y"]["value"] is not None and tr["td"]["5Y"]["value"] is None
    assert out["tracking"]["1"]["gap"]["1Y"]["value"] is not None and "gap" in out["tracking"]["1"] and out["tracking"]["SAMPLEETF"]["gap"] == {}
    # the ETF costs less in this made-up path, so it tracks the index at least as closely and is ahead since the common start
    assert out["tracking"]["SAMPLEETF"]["te"]["value"] <= out["tracking"]["1"]["te"]["value"]
    assert out["returns"]["SAMPLEETF"]["since"]["value"] > out["returns"]["1"]["since"]["value"]
    assert set(out["sip"]) == {"SAMPLEETF", "1"} and out["sip"]["1"]["diffVsRef"]["rupees"] == pytest.approx(out["sip"]["1"]["value"] - out["sip"]["SAMPLEETF"]["value"], abs=0.01)
    assert out["lump"]["SAMPLEETF"]["diffVsRef"] is None
    assert out["risk"]["all"]["products"]["1"]["maxDrawdown"]["value"] <= 0 and out["risk"]["5Y"]["why"]
    ch = out["chart"]
    assert len(ch["t"]) <= ev.CHART_CAP and ch["index"] is not None and len(ch["index"]) == len(ch["t"]) and set(ch["v"]) == {"SAMPLEETF", "1"}


def test_compute_without_index_levels_says_why_and_still_compares_the_products():
    days, idx, etfv, fund = _series_pair()
    prods = [{"id": "E", "label": "E"}, {"id": "F", "label": "F"}]
    out = ev.compute(prods, {"E": (days, etfv), "F": (days, fund)}, None, "The index levels are not available right now.", 10000.0, 100000.0, None)
    assert out["tracking"]["E"]["te"]["value"] is None and out["tracking"]["E"]["te"]["why"] == "The index levels are not available right now."
    assert out["tracking"]["E"]["td"]["1Y"]["why"] == "The index levels are not available right now."
    assert out["chart"]["index"] is None and out["chart"]["indexWhy"]
    assert out["returns"]["E"]["1Y"]["value"] is not None


def test_compute_with_too_few_common_dates():
    out = ev.compute([{"id": "E", "label": "E"}, {"id": "F", "label": "F"}], {"E": ([1, 2, 3], [1.0, 2.0, 3.0]), "F": ([2, 3, 4], [1.0, 2.0, 3.0])}, None, None, 1000.0, 1000.0, None)
    assert out["common"]["days"] == 2 and "not enough" in out["common"]["why"] and "returns" not in out


def test_index_that_starts_after_the_common_start_gives_no_index_line():
    days, idx, etfv, fund = _series_pair()
    late = (days[600:], idx[600:])
    out = ev.compute([{"id": "E", "label": "E"}, {"id": "F", "label": "F"}], {"E": (days, etfv), "F": (days, fund)}, late, None, 10000.0, 100000.0, None)
    assert out["chart"]["index"] is None and "after the first common date" in out["chart"]["indexWhy"]
    assert out["tracking"]["E"]["te"]["value"] is not None            # the overlap with the index is long enough for the tracking error
    assert out["tracking"]["E"]["td"]["5Y"]["value"] is None


# ---------------------------------------------------------------------------------------------- database + API

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test_c")
TEST_REDIS = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/14")
ALL = [d for d in consecutive(2700, date(2016, 1, 4).toordinal()) if date.fromordinal(d).weekday() < 5]
END = ALL[-1]
RS = [0.0004 + 0.008 * math.sin(i / 9.0) for i in range(len(ALL) - 1)]
INDEX_PATH = _path(RS, 1000.0)
SPECS = {  # code -> (name, plan, path)
    910001: ("Sample Nifty 50 Index Fund - Direct Plan - Growth", "Direct", _path([r - 0.0000008 for r in RS], 10.0, 4)),
    910002: ("Sample Nifty 50 Index Fund - Regular Plan - Growth", "Regular", _path([r - 0.0000040 for r in RS], 10.0, 4)),
    910003: ("Other Nifty Next 50 Index Fund - Direct Plan - Growth", "Direct", _path([r - 0.0000008 for r in RS], 10.0, 4)),
    910004: ("Equal Weight Nifty 50 Index Fund - Direct Plan - Growth", "Direct", _path([r - 0.0000008 for r in RS], 10.0, 4)),
}
ETF_PATH = _path([r - 0.0000003 for r in RS], 200.0)


def levels_payload(days, vals):
    return {"rows": [{"quote_date": date.fromordinal(d).isoformat(), "close_price": v} for d, v in zip(days, vals)]}


class Mirror:
    def __init__(self):
        self.calls = {}

    def client(self):
        async def handler(request):
            code = int(request.url.path.rsplit("/", 1)[1])
            self.calls[code] = self.calls.get(code, 0) + 1
            name, plan, path = SPECS[code]
            return httpx.Response(200, json={"meta": {"scheme_code": code}, "status": "SUCCESS",
                                             "data": [{"date": date.fromordinal(d).strftime("%d-%m-%Y"), "nav": f"{v:.4f}"} for d, v in reversed(list(zip(ALL, path)))]})
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
async def store():
    s = Settings(finedge_api_key="test", finedge_mode="fixtures", database_url=TEST_DB, redis_url=TEST_REDIS)
    try:
        st = await Store.connect(s, migrate=True)
        await st.redis.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    async with st.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS etf_history, etf_runs, etf_funds, etf_hot CASCADE")
        for f in ("034_etf.sql", "038_etf_hot.sql", "039_etf_fetched.sql"):
            await conn.execute((MIGRATIONS / f).read_text())
        await conn.execute("TRUNCATE mf_cat_avg, mf_history, mf_backfill, mf_meta, mf_facts, mf_schemes CASCADE")
        for code, (name, plan, path) in SPECS.items():
            await conn.execute("""INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, option_label, family, nav, nav_date, prev_nav, prev_date, active, isin)
                                  VALUES ($1, $2, 'Sample Mutual Fund', 'Open Ended', 'Other Scheme - Index Funds', $3, 'Growth', 'Growth', $4, $5, $6, $7, $8, true, $9)""",
                               code, name, plan, "fam" + name.split(" - ")[0], path[-1], date.fromordinal(ALL[-1]), path[-2], date.fromordinal(ALL[-2]), f"INF00000{code}")
        await conn.execute("""INSERT INTO etf_funds (symbol, isin, instrument_key, exchange_name, scheme_name, fund_house, display_name, category, asset_class, active, price, price_date, first_date, points)
                              VALUES ('SAMPLEETF', 'INF000000ETF', 'NSE_EQ|INF000000ETF', 'SAMPLE ETF NIFTY 50', 'Sample ETF Nifty 50', 'Sample', 'Sample ETF Nifty 50', 'nifty50', 'equity', true, $1, $2, $3, $4)""",
                           ETF_PATH[-1], date.fromordinal(ALL[-1]), date.fromordinal(ALL[0]), len(ALL))
        await conn.execute("""INSERT INTO etf_funds (symbol, isin, instrument_key, exchange_name, scheme_name, fund_house, display_name, category, asset_class, active, price, price_date, first_date, points)
                              VALUES ('NEXTETF', 'INF000001ETF', 'NSE_EQ|INF000001ETF', 'SAMPLE NEXT 50', 'Sample ETF Nifty Next 50', 'Sample', 'Sample ETF Nifty Next 50', 'next50', 'equity', true, $1, $2, $3, $4)""",
                           ETF_PATH[-1], date.fromordinal(ALL[-1]), date.fromordinal(ALL[0]), len(ALL))
        await conn.execute("INSERT INTO etf_history (symbol, dates, closes) VALUES ('SAMPLEETF', $1, $2), ('NEXTETF', $1, $2)", [date.fromordinal(d) for d in ALL], ETF_PATH)
    async for k in st.redis.scan_iter("etf:*"):
        await st.redis.delete(k)
    async for k in st.redis.scan_iter("mf:*"):
        await st.redis.delete(k)
    yield st
    async with st.pool.acquire() as conn:   # leave no rows behind for the tests that run after this one
        await conn.execute("TRUNCATE mf_cat_avg, mf_history, mf_backfill, mf_meta, mf_facts, mf_schemes CASCADE")
        await conn.execute("TRUNCATE etf_funds CASCADE")
    await st.close()


@pytest.fixture
async def api(store, monkeypatch):
    from finlit import indices
    calls = {"n": 0}

    async def fake_cached(app, key, fresh, fetch, wait=True):
        calls["n"] += 1
        if key == "idx:px:NIF50":
            return levels_payload(ALL[-1250:], INDEX_PATH[-1250:])
        return None

    async def fake_facts(pool, key):
        ter = {"value": "0.05% a year", "asOf": "2026-10-01", "source": "AMFI, TER of mutual fund schemes"} if str(key).startswith("INF") else {"value": "0.20% a year", "asOf": "2026-10-01", "source": "AMFI, TER of mutual fund schemes"}
        bm = {"value": "Nifty 50 TRI", "asOf": "2026-09-30", "source": "Fund-house portfolio file"}
        return {"ter": ter, "terDirect": ter, "terRegular": {"value": "0.60% a year", "asOf": "2026-10-01", "source": "AMFI"}, "benchmark": bm, "exitLoad": {"unavailable": "not loaded"},
                "minInvestment": {"value": "1 unit, bought on the stock exchange", "source": "NSE trading rules"} if str(key).startswith("INF") else {"unavailable": "x"}, "aum": {"unavailable": "x"}}

    monkeypatch.setattr(indices, "_cached", fake_cached)
    monkeypatch.setattr(ev, "facts_of", fake_facts)
    from finlit.api import create_app
    from test_integration import make_settings
    app = create_app(make_settings(), store=store)
    app.state.mirror = Mirror()
    app.state.mf_client = app.state.mirror.client()
    async with app.router.lifespan_context(app):
        app.state.mf_client = app.state.mirror.client()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            c.app = app
            c.calls = calls
            yield c


@pytest.mark.integration
async def test_options_group_products_by_index_and_leave_variants_out(api):
    d = (await api.get("/api/etf-vs-index/options")).json()
    by = {i["key"]: i for i in d["indices"]}
    assert by["nifty50"]["etfCount"] == 1 and by["nifty50"]["fundCount"] == 1 and by["nifty50"]["ready"] is True       # the Regular plan and the equal-weight fund are not offered
    assert by["niftynext50"]["etfCount"] == 1 and by["niftynext50"]["fundCount"] == 1
    assert [f["code"] for f in d["funds"]] == [910003, 910001] or sorted(f["code"] for f in d["funds"]) == [910001, 910003]
    assert all(f["plan"] == "Direct" for f in d["funds"]) and d["unmatchedFunds"] == 1 and d["plan"] == "Direct"
    assert d["disclaimer"].startswith("Information only")
    allp = (await api.get("/api/etf-vs-index/options?plan=All")).json()
    assert {f["code"] for f in allp["funds"]} == {910001, 910002, 910003} and {i["key"]: i for i in allp["indices"]}["nifty50"]["fundCount"] == 2
    assert (await api.get("/api/etf-vs-index/options?plan=Both")).status_code == 422


@pytest.mark.integration
async def test_compare_end_to_end(api):
    r = await api.get("/api/etf-vs-index/compare", params={"index": "nifty50", "etf": "SAMPLEETF", "fund": "910001", "sip": 5000, "lump": 200000})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["index"]["key"] == "nifty50" and "price index" in d["index"]["levels"] and [p["id"] for p in d["products"]] == ["SAMPLEETF", "910001"]
    etf_p, fund_p = d["products"]
    assert etf_p["basis"] == "price" and etf_p["source"] == "NSE closing price" and fund_p["basis"] == "nav" and fund_p["returnType"] == "TRI" and fund_p["indexBasis"] == "benchmark"
    assert d["asOf"] == date.fromordinal(END).isoformat() and d["common"]["days"] == len(ALL)
    # the ETF's one-year return in the payload is the pure function's on the same prices
    want = ev.period_return(ALL, ETF_PATH, 12)
    assert d["returns"]["SAMPLEETF"]["1Y"]["value"] == want["value"]
    assert d["returns"]["SAMPLEETF"]["10Y" if False else "5Y"]["cagr"] is not None
    # costs: expense ratios from the facts, drag = ratio x Rs 10 lakh
    assert d["costs"]["SAMPLEETF"]["terPct"] == 0.05 and d["costs"]["SAMPLEETF"]["dragPerYear"] == 500
    assert d["costs"]["910001"]["terPct"] == 0.20 and d["costs"]["910001"]["dragPerYear"] == 2000
    assert d["costs"]["910001"]["minimum"]["value"] is None and "documents" in d["costs"]["910001"]["minimum"]["why"]
    # the index covers about five years: 5Y tracking difference exists, the tracking error needs a year
    td = d["tracking"]["SAMPLEETF"]
    assert td["te"]["value"] is not None and td["td"]["1Y"]["value"] is not None
    assert d["chart"]["index"] is None or len(d["chart"]["index"]) == len(d["chart"]["t"])
    s = d["summary"]
    assert any(row["text"] == "Lower expense ratio: SAMPLEETF" for row in s["rows"]) and s["sentence"].endswith("Information only, not investment advice.")
    assert d["inputs"] == {"sip": 5000.0, "lump": 200000.0, "dragBase": 1000000}
    assert d["sip"]["SAMPLEETF"]["invested"] == 5000.0 * d["sip"]["SAMPLEETF"]["installments"]
    assert any("closing price" in n for n in d["notes"])
    # the fund's 10 years came from the mirror once; a second request is served from the saved answer
    again = await api.get("/api/etf-vs-index/compare", params={"index": "nifty50", "etf": "SAMPLEETF", "fund": "910001", "sip": 5000, "lump": 200000})
    assert again.status_code == 200 and again.json() == d and api.app.state.mirror.calls.get(910001, 0) == 1


@pytest.mark.integration
async def test_compare_refuses_what_it_should(api):
    g = api.get
    base = {"index": "nifty50", "etf": "SAMPLEETF", "fund": "910001"}
    assert (await g("/api/etf-vs-index/compare", params={**base, "index": "niftynext50"})).json()["detail"]["status"] == "index_mismatch"     # the ETF follows the Nifty 50
    assert (await g("/api/etf-vs-index/compare", params={**base, "fund": "910002"})).json()["detail"]["status"] == "regular_plan"           # Regular plan, Direct asked
    assert (await g("/api/etf-vs-index/compare", params={**base, "fund": "910002", "plan": "All"})).status_code == 200
    assert (await g("/api/etf-vs-index/compare", params={**base, "fund": "910004"})).json()["detail"]["status"] == "index_mismatch"           # equal-weight variant
    assert (await g("/api/etf-vs-index/compare", params={"index": "nifty50", "etf": "SAMPLEETF"})).status_code == 400                       # needs a fund too
    assert (await g("/api/etf-vs-index/compare", params={"index": "nifty50", "fund": "910001"})).status_code == 400
    assert (await g("/api/etf-vs-index/compare", params={**base, "etf": "SAMPLEETF,NEXTETF", "fund": "910001,910003,910002", "plan": "All"})).status_code == 400   # five products
    assert (await g("/api/etf-vs-index/compare", params={**base, "index": "nope"})).status_code == 400
    assert (await g("/api/etf-vs-index/compare", params={**base, "etf": "NOSUCH"})).status_code == 404
    assert (await g("/api/etf-vs-index/compare", params={**base, "fund": "abc"})).status_code == 400
    assert (await g("/api/etf-vs-index/compare", params={**base, "sip": 5})).status_code == 422
    assert (await g("/api/etf-vs-index/compare", params={**base, "start": "1990-01-01"})).status_code == 400


@pytest.mark.integration
async def test_compare_without_index_levels_keeps_the_products_comparison(api, monkeypatch):
    from finlit import indices

    async def none_cached(app, key, fresh, fetch, wait=True):
        return None
    monkeypatch.setattr(indices, "_cached", none_cached)
    d = (await api.get("/api/etf-vs-index/compare", params={"index": "nifty50", "etf": "SAMPLEETF", "fund": "910001"})).json()
    assert d["index"]["why"] == "The index levels are not available right now."
    assert d["tracking"]["SAMPLEETF"]["te"]["value"] is None and d["tracking"]["SAMPLEETF"]["te"]["why"] == d["index"]["why"]
    assert d["returns"]["SAMPLEETF"]["1Y"]["value"] is not None and d["chart"]["index"] is None


def test_a_variant_named_in_either_place_is_a_conflict():
    assert ev.classify("Nifty 50 Equal Weight TRI", ["Some Nifty 50 Index Fund"])["conflict"] is True
    assert ev.classify("Nifty 50 TRI", ["Some Nifty 50 Equal Weight Index Fund"])["conflict"] is True
