"""The price-position half of the results-calendar filter card: distance below the 52-week high and below the all-time high, bands, stale highs, AND / OR."""

import datetime

import pytest

from finlit import results as R
from test_auth import app, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401
from test_results import _raises, seeded  # noqa: F401
from test_results_growth import co, gp, spec, syms


def at(sym, below52=None, below_ath=None, **kw):
    """A company whose two distances are exactly the given ones."""
    return {**co(sym, np_q=5, np_y=20, **kw), "below52": below52, "belowAth": below_ath}


def pp(qs):
    from starlette.requests import Request
    return R.price_params(Request({"type": "http", "query_string": qs.encode(), "headers": []}))


def band(i, key="w52"):
    return R.PriceCond(key, R.BANDS[i][0], R.BANDS[i][1], i)


def test_distance_is_high_minus_price_over_high_rounded_like_the_table():
    r = R.price_position(87.6, 100.0, 60.0, 120.0, datetime.date(2026, 1, 12))
    assert r["below52"] == 12.4 and r["belowAth"] == 27.0 and r["above52Low"] == 46.0 and r["athDate"] == "2026-01-12" and not r["stale52"] and not r["staleAth"]
    assert R.price_position(100.0, 100.0, None, None, None)["below52"] == 0.0


def test_a_price_above_a_stale_high_counts_as_zero_and_is_marked():
    r = R.price_position(105.0, 100.0, 50.0, 102.0, None)
    assert r["below52"] == 0.0 and r["stale52"] is True and r["belowAth"] == 0.0 and r["staleAth"] is True


def test_missing_prices_and_highs_give_no_figure_and_never_match():
    for args in ((None, 100.0, None, 100.0), (50.0, None, None, None), (50.0, 0.0, None, 0.0), (0.0, 100.0, None, 100.0), (-1.0, 100.0, None, None)):
        r = R.price_position(*args, None)
        assert (r["below52"] is None or args[1] and args[0]) and (r["belowAth"] is None or args[3] and args[0])
    r = R.price_position(50.0, None, None, 80.0, None)
    assert r["below52"] is None and r["belowAth"] == 37.5
    rows = [at("A", None, None), at("B", 3.0, 3.0)]
    assert syms(R.price_filter(rows, R.PriceSpec((band(0),)))[0]) == ["B"]
    out, s = R.price_filter(rows, R.PriceSpec((band(0), band(0, "ath"))))
    assert s["conditions"][0]["missing"] == 1 and s["companies"] == 2


def test_band_boundaries_are_half_open_and_every_company_is_in_exactly_one_band():
    edges = [0.0, 4.9, 5.0, 9.9, 10.0, 14.9, 15.0, 19.9, 20.0, 29.9, 30.0, 39.9, 40.0, 49.9, 50.0, 73.2, 100.0]
    want = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 7]
    rows = [at(f"E{i}", v) for i, v in enumerate(edges)]
    for b in range(8):
        got = syms(R.price_filter(rows, R.PriceSpec((band(b),)))[0])
        assert got == [f"E{i}" for i, w in enumerate(want) if w == b], b
    assert sum(len(R.price_filter(rows, R.PriceSpec((band(b),)))[0]) for b in range(8)) == len(rows)


def test_and_or_inside_the_card_and_with_the_growth_card():
    rows = [at("A", 3, 3), at("B", 3, 45), at("C", 12, 3), at("D", 12, 45), at("E", None, 3)]
    both = (band(0), band(6, "ath"))
    assert syms(R.price_filter(rows, R.PriceSpec(both, "and"))[0]) == ["B"]
    assert syms(R.price_filter(rows, R.PriceSpec(both, "or"))[0]) == ["A", "B", "D"]
    out, s = R.price_filter(rows, R.PriceSpec(both, "or"))
    assert s["matching"] == 3 and s["conditions"][0]["met"] == 2 and s["conditions"][0]["missing"] == 1
    assert R.price_filter(rows, R.PriceSpec()) == (rows, None)
    grown = [at("A", 3, 3, ), at("B", 3, 3)]
    grown[1]["profitQoQ"] = -5.0
    g, _ = R.growth_filter(grown, spec(qoq=("netProfit", ">=", 0)))
    p, _ = R.price_filter(grown, R.PriceSpec((band(0),)))
    assert syms(g) == ["A"] and syms(p) == ["A", "B"]


def test_params_bands_typed_ranges_and_errors():
    s = pp("p52=0&pAth=7&pJoin=or&zzz=1&join=or")
    assert s.conds == (band(0), band(7, "ath")) and s.join == "or"
    assert pp("").active is False and pp("p52=&pAth=").active is False
    t = pp("p52min=12.5&p52max=20").conds[0]
    assert (t.lo, t.hi, t.band) == (12.5, 20.0, None)
    assert [c.key for c in pp("pAthMax=10").conds] == ["ath"] and pp("pAthMax=10").conds[0].lo == 0.0
    assert R._in_band(20.0, t) and R._in_band(12.5, t) and not R._in_band(20.1, t)   # a typed range includes both ends
    for qs in ("p52=8", "p52=-1", "p52=x", "p52=1.5", "pJoin=xor", "p52min=-1", "p52max=101", "p52min=abc", "p52min=30&p52max=10", "p52=2&p52min=5", "pAth=99"):
        e = _raises(lambda q=qs: pp(q))
        assert e.status_code == 400 and e.detail["detail"], qs
    assert gp("p52=2&pAth=3&pJoin=or").active is False   # the growth reader ignores the price parameters


def test_no_filter_by_default_and_price_sorts_put_missing_last():
    rows = [at("A", 9.0), at("B", None), at("C", 1.0)]
    assert syms(R.select(rows, sort="below52", desc=False)) == ["C", "A", "B"] and syms(R.select(rows, sort="below52", desc=True)) == ["A", "C", "B"]
    assert "below52" in R.NUMERIC_SORTS and "belowAth" in R.SORTS
    out = R.strip_figures(at("A", 3, 4))
    assert all(out[k] is None for k in R.PRICE_FIELDS)


@pytest.mark.integration
async def test_endpoint_combines_with_growth_gates_by_plan_and_exports(app, seeded):  # noqa: F811
    q = seeded["quarter"]
    silver = await signed_in(app, "res-price@example.com", plan="silver")
    base = (await silver.get(f"/api/results/quarter?quarter={q}&limit=100")).json()
    assert base["price"] is None and all(k in base["rows"][0] for k in R.PRICE_FIELDS) and base["priceStrip"]["companies"] == base["total"]
    allb = (await silver.get(f"/api/results/quarter?quarter={q}&p52min=0&p52max=100&limit=100")).json()
    assert allb["price"]["conditions"][0]["key"] == "w52" and allb["total"] == allb["price"]["matching"]
    assert allb["price"]["companies"] == base["total"] and allb["total"] + allb["price"]["conditions"][0]["missing"] == base["total"]
    both = (await silver.get(f"/api/results/quarter?quarter={q}&p52min=0&p52max=100&qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue=-100000&limit=100")).json()
    assert both["total"] == both["price"]["combined"] == both["growth"]["combined"] <= min(allb["total"], both["growth"]["matching"])
    exp = (await silver.get(f"/api/results/quarter/export?quarter={q}&p52min=0&p52max=100")).json()
    assert len(exp["rows"]) == allb["total"] and all(r["below52"] is not None for r in exp["rows"])
    assert (await silver.get(f"/api/results/quarter?quarter={q}&p52=9")).status_code == 400
    assert (await silver.get(f"/api/results/quarter/export?quarter={q}&pAth=x")).status_code == 400
    assert (await silver.get(f"/api/results/quarter?quarter={q}&sort=below52&dir=asc")).status_code == 200
    async with new_client(app) as anon:
        r = await anon.get(f"/api/results/quarter?quarter={q}&p52=1")
        assert r.status_code == 403 and r.json()["detail"]["plan"] == "silver"
        assert (await anon.get(f"/api/results/quarter?quarter={q}&sort=below52")).status_code == 403
        plain = (await anon.get(f"/api/results/quarter?quarter={q}")).json()
        assert plain["price"] is None and plain["priceStrip"] is None and all(x[k] is None for x in plain["rows"] for k in R.PRICE_FIELDS)


def test_strip_counts_near_and_missing():
    rows = [at("A", 0.0, 4.9), at("B", 5.0, None), at("C", None, 60.0)]
    assert R.price_strip(rows) == {"companies": 3, "have52": 2, "near52": 1, "haveAth": 2, "nearAth": 1}
