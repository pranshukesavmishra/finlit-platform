"""The 'Filter companies by growth' panel of the quarter-results page: thresholds on QoQ / YoY growth, AND / OR, missing figures, lenders, counts, plan gate."""

import itertools
from datetime import timedelta

import pytest

from finlit import results as R
from test_auth import app, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401
from test_results import D, FIG, _raises, _row, seeded  # noqa: F401


def co(sym, rev_q=None, rev_y=None, np_q=None, np_y=None, op_q=None, op_y=None, **kw):
    """A company whose growth figures are exactly the given ones (None = no figure). Revenue and net profit growth come from the screener metrics, operating profit from `opg`."""
    m = {**FIG, "q_sales_qoq": rev_q, "q_sales_yoy": rev_y, "q_profit_qoq": np_q, "q_profit_yoy": np_y}
    opg = {"opQoQ": op_q, "opYoY": op_y}
    r = R.build_row(sym, R.Decl(D(2026, 10, 14), True), {"name": sym, "sector": kw.get("sector", "IT"), "market_cap": 100.0}, m, D(2026, 9, 30), D(2026, 10, 20), kw.get("cap", "Large"), [], opg)
    return r


def spec(qoq=None, yoy=None, join="and", extra=()):
    """qoq / yoy are (metric, op, value) as the old two-filter form; `extra` adds more (metric, period, op, value) conditions."""
    conds = [R.GrowthCond(t[0], per, t[1], t[2]) for per, t in (("qoq", qoq), ("yoy", yoy)) if t is not None] + [R.GrowthCond(*t) for t in extra]
    return R.GrowthSpec(tuple(conds), join)


def gp(qs):
    """growth_params for a query string such as 'revQoQValue=5&join=or'."""
    from starlette.requests import Request
    return R.growth_params(Request({"type": "http", "query_string": qs.encode(), "headers": []}))


def syms(rows):
    return [r["symbol"] for r in rows]


ROWS = [co("A", np_q=5, np_y=20), co("B", np_q=5, np_y=-3), co("C", np_q=-2, np_y=20), co("D", np_q=-2, np_y=-3), co("E", np_q=None, np_y=20), co("F", np_q=5, np_y=None),
        _row("G", m={})]   # G has no figures at all


def test_operators_are_inclusive_or_exclusive_exactly_as_the_table_shows():
    rows = [co("A", np_q=1.0), co("B", np_q=1.1), co("C", np_q=0.9), co("D", np_q=-1.0)]
    q = lambda op, v: syms(R.growth_filter(rows, spec(qoq=("netProfit", op, v)))[0])   # noqa: E731
    assert q(">=", 1.0) == ["A", "B"] and q(">", 1.0) == ["B"] and q("<=", 1.0) == ["A", "C", "D"] and q("<", 1.0) == ["C", "D"]
    assert q(">=", -1.0) == ["A", "B", "C", "D"] and q("<", -1.0) == [] and q("<=", -1.0) == ["D"] and q(">", 0.0) == ["A", "B", "C"]


def test_each_metric_reads_its_own_columns_and_yoy_is_not_qoq():
    r = co("A", rev_q=1, rev_y=2, np_q=3, np_y=4, op_q=5, op_y=6)
    one = lambda s: bool(R.growth_filter([r], s)[0])   # noqa: E731
    for metric, (qv, yv) in {"revenue": (1, 2), "netProfit": (3, 4), "operatingProfit": (5, 6)}.items():
        assert one(spec(qoq=(metric, ">=", qv))) and not one(spec(qoq=(metric, ">", qv)))
        assert one(spec(yoy=(metric, ">=", yv))) and not one(spec(yoy=(metric, ">", yv)))
        assert not one(spec(qoq=(metric, ">=", yv))) or qv >= yv   # QoQ never reads the YoY column
    assert not one(spec(yoy=("netProfit", "<=", 3.9)))


def test_and_or_and_single_filter():
    Q, Y = ("netProfit", ">=", 1.0), ("netProfit", ">=", 10.0)
    assert syms(R.growth_filter(ROWS, spec(Q, Y, "and"))[0]) == ["A"]
    assert syms(R.growth_filter(ROWS, spec(Q, Y, "or"))[0]) == ["A", "B", "C", "E", "F"]
    assert syms(R.growth_filter(ROWS, spec(qoq=Q))[0]) == ["A", "B", "F"] == syms(R.growth_filter(ROWS, spec(qoq=Q, join="or"))[0])   # one filter alone: AND/OR make no difference
    assert syms(R.growth_filter(ROWS, spec(yoy=Y))[0]) == ["A", "C", "E"]
    rows, summ = R.growth_filter(ROWS, spec())
    assert rows is ROWS and summ is None                                             # no filter: nothing changes


def test_missing_figure_never_matches_even_for_less_than_or_negative_limits():
    rows = [co("A", np_q=None, np_y=None), _row("NOFIG", m={})]
    for op, v in ((">=", -1000), ("<", 1000), ("<=", 0), (">", -1e9)):
        assert R.growth_filter(rows, spec(qoq=("netProfit", op, v)))[0] == []
        assert R.growth_filter(rows, spec(yoy=("netProfit", op, v), qoq=("revenue", op, v), join="or"))[0] == []
    # a row that lost its figures (hasNumbers False) is out even if a stale growth value were left on it
    stale = dict(co("S", np_q=50), hasNumbers=False)
    assert R.growth_filter([stale], spec(qoq=("netProfit", ">=", 0)))[0] == []


def test_lenders_never_match_an_operating_profit_filter():
    bank = co("BANK", np_q=5, np_y=5)                                                # no operating profit growth, as the table shows for a lender
    bank = R.build_row("BANK", R.Decl(D(2026, 10, 14), True), {"name": "Bank", "sector": "Banks", "market_cap": 1.0}, {**FIG, "q_operating_profit": None}, D(2026, 9, 30), D(2026, 10, 20), "Large", [])
    assert bank["opYoY"] is None and bank["opQoQ"] is None and bank["opYoYWhy"]
    other = co("IT1", op_q=10, op_y=10)
    for op, v in ((">=", -100), ("<", 100), ("<=", 100)):
        assert syms(R.growth_filter([bank, other], spec(qoq=("operatingProfit", op, v)))[0]) == ["IT1"]
        assert syms(R.growth_filter([bank, other], spec(yoy=("operatingProfit", op, v)))[0]) == ["IT1"]
    # but a lender still matches a net profit filter
    assert "BANK" in syms(R.growth_filter([bank], spec(qoq=("netProfit", ">=", 0)))[0])


def test_counts_add_up_to_companies_with_figures():
    Q, Y = ("netProfit", ">=", 1.0), ("netProfit", ">=", 10.0)
    _, s = R.growth_filter(ROWS, spec(Q, Y))
    assert (s["metAll"], s["metSome"], s["metNone"]) == (1, 4, 1) and s["withFigures"] == 6 and s["k"] == 2     # G has no figures: not counted
    assert [(c["period"], c["met"], c["missing"]) for c in s["conditions"]] == [("qoq", 3, 1), ("yoy", 3, 1)] and s["matching"] == 1
    _, o = R.growth_filter(ROWS, spec(Q, Y, "or"))
    assert o["matching"] == o["metAll"] + o["metSome"] == 5 and o["metNone"] == 1
    _, one = R.growth_filter(ROWS, spec(qoq=Q))
    assert one["k"] == 1 and one["metSome"] == 0 and one["metAll"] == 3 and one["metNone"] == 3 and one["matching"] == 3


def test_six_cells_all_combinations_of_filled_cells():
    r = co("A", rev_q=5, rev_y=5, np_q=5, np_y=-5, op_q=5, op_y=5)
    cells = [("revenue", "qoq"), ("revenue", "yoy"), ("operatingProfit", "qoq"), ("operatingProfit", "yoy"), ("netProfit", "qoq"), ("netProfit", "yoy")]
    for n in range(1, 7):
        for pick in itertools.combinations(cells, n):
            conds = tuple(R.GrowthCond(m, p, ">=", 0.0) for m, p in pick)
            expect_and = all(not (m == "netProfit" and p == "yoy") for m, p in pick)
            assert bool(R.growth_filter([r], R.GrowthSpec(conds, "and"))[0]) == expect_and, pick
            assert bool(R.growth_filter([r], R.GrowthSpec(conds, "or"))[0]) == (len(pick) > 1 or expect_and), pick
    # revenue AND profit, each on both horizons (the founder's example)
    rows = [co("OK", rev_q=1, rev_y=2, np_q=3, np_y=4), co("NOQ", rev_q=-1, rev_y=2, np_q=3, np_y=4), co("NOPY", rev_q=1, rev_y=2, np_q=3, np_y=None)]
    four = tuple(R.GrowthCond(m, p, ">=", 0.0) for m in ("revenue", "netProfit") for p in ("qoq", "yoy"))
    out, s = R.growth_filter(rows, R.GrowthSpec(four, "and"))
    assert syms(out) == ["OK"] and s["conditions"][3]["missing"] == 1 and s["conditions"][0]["met"] == 2


@pytest.mark.parametrize("join", ["and", "or"])
def test_identity_holds_for_every_operator_combination(join):
    vals = [None, -5.0, -0.1, 0.0, 0.1, 5.0]
    rows = [co(f"X{i}", np_q=a, np_y=b) for i, (a, b) in enumerate(itertools.product(vals, vals))] + [_row("NF", m={})]
    for oq, oy in itertools.product(R.GROWTH_OPS.values(), repeat=2):
        for t in (-0.1, 0.0, 2.5):
            out, s = R.growth_filter(rows, spec(("netProfit", oq, t), ("netProfit", oy, -t), join))
            assert s["metAll"] + s["metSome"] + s["metNone"] == s["withFigures"] == len(vals) ** 2
            assert len(out) == s["matching"] == (s["metAll"] if join == "and" else s["metAll"] + s["metSome"])


def test_distribution_counts_sectors_and_caps():
    rows = [co(f"S{i}", sector=f"Sec{i % 9}", cap=["Large", "Mid", "Small", None][i % 4]) for i in range(40)] + [co("N", sector=None)]
    d = R.distribution(rows)
    assert d["total"] == 41 and sum(x["n"] for x in d["sectors"]) == 41 and sum(x["n"] for x in d["caps"]) == 41
    assert len(d["sectors"]) == R.TOP_SECTORS + 1 and d["sectors"][-1]["name"] == "Others"
    assert [x["name"] for x in d["caps"]] == ["Large", "Mid", "Small", "Not classified"]
    assert R.distribution([]) == {"total": 0, "sectors": [], "caps": []}


def test_validation_is_strict_with_plain_messages():
    ok = gp("qoqMetric=netProfit&qoqOp=>=&qoqValue=1&yoyMetric=revenue&yoyOp=<&yoyValue=-2.5&join=or")
    assert ok.conds == (R.GrowthCond("revenue", "yoy", "<", -2.5), R.GrowthCond("netProfit", "qoq", ">=", 1.0)) and ok.join == "or"
    assert gp("").active is False and gp("qoqMetric=netProfit&qoqOp=>=&qoqValue=").active is False and gp("revQoQOp=>=&revQoQValue=").active is False   # empty value = off
    assert gp("yoyMetric=revenue&yoyOp=gt&yoyValue=.5").conds == (R.GrowthCond("revenue", "yoy", ">", 0.5),) and gp("qoqMetric=revenue&qoqOp=>=&qoqValue=%2B3").conds[0].value == 3.0
    for qs in ("qoqMetric=sales&qoqOp=>=&qoqValue=1", "qoqMetric=netProfit&qoqOp==>&qoqValue=1", "qoqMetric=netProfit&qoqOp=>=&qoqValue=abc", "qoqMetric=netProfit&qoqOp=>=&qoqValue=nan",
               "qoqMetric=netProfit&qoqOp=>=&qoqValue=inf", "qoqMetric=netProfit&qoqOp=>=&qoqValue=1e999", "qoqMetric=netProfit&qoqOp=>=&qoqValue=1e3", "qoqMetric=netProfit&qoqOp=>=&qoqValue=9999999",
               "qoqMetric=netProfit&qoqOp=>=&qoqValue=1,5", "qoqMetric=netProfit&qoqOp=>=&qoqValue=--1", "qoqOp=>=&qoqValue=1", "qoqMetric=netProfit&qoqValue=1", "yoyMetric=bogus", "yoyOp=!",
               "qoqMetric=netProfit&qoqOp=>=&qoqValue=1&join=xor", "npYoYOp=!&npYoYValue=1", "revQoQValue=abc", "opYoYOp=>=&opYoYValue=1e3"):
        e = _raises(lambda q=qs: gp(q))
        assert e.status_code == 400 and e.detail["detail"], qs


def test_grid_cells_and_old_links_agree():
    new = gp("revQoQOp=>=&revQoQValue=5&npYoYOp=<&npYoYValue=-1&opQoQValue=2&join=or")
    assert new.conds == (R.GrowthCond("revenue", "qoq", ">=", 5.0), R.GrowthCond("operatingProfit", "qoq", ">=", 2.0), R.GrowthCond("netProfit", "yoy", "<", -1.0)) and new.join == "or"
    old = gp("qoqMetric=revenue&qoqOp=>=&qoqValue=5&yoyMetric=netProfit&yoyOp=<&yoyValue=-1")
    assert old.conds == (R.GrowthCond("revenue", "qoq", ">=", 5.0), R.GrowthCond("netProfit", "yoy", "<", -1.0))
    both = gp("qoqMetric=revenue&qoqOp=>=&qoqValue=5&revQoQOp=>&revQoQValue=7")   # same cell twice: the grid cell wins, never counted twice
    assert both.conds == (R.GrowthCond("revenue", "qoq", ">", 7.0),)


# ---------------------------------------------------------------- the endpoint, against Postgres

@pytest.mark.integration
async def test_endpoint_filters_on_the_server_and_counts_everything(app, seeded):  # noqa: F811
    q = seeded["quarter"]
    silver = await signed_in(app, "res-growth@example.com", plan="silver")
    base = (await silver.get(f"/api/results/quarter?quarter={q}&limit=100")).json()
    assert base["growth"] is None and base["distribution"]["total"] == base["total"]
    with_fig = [x for x in base["rows"] if x["hasNumbers"]]
    assert with_fig
    rel = next(x for x in base["rows"] if x["symbol"] == "RELIANCE")
    url = f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue=-100000&yoyMetric=revenue&yoyOp=%3C%3D&yoyValue=100000&join=and&limit=1"
    body = (await silver.get(url)).json()                                                          # paging does not change counts
    g = body["growth"]
    assert g["withFigures"] == len(with_fig) and g["metAll"] + g["metSome"] + g["metNone"] == g["withFigures"]
    exp_match = [x for x in with_fig if x["profitQoQ"] is not None and x["revenueYoY"] is not None]
    assert body["total"] == g["matching"] == g["metAll"] == len(exp_match) and len(body["rows"]) == min(1, len(exp_match))
    if rel["profitQoQ"] is not None:
        thr = rel["profitQoQ"]                                                                     # exactly the figure the table shows: >= matches, > does not
        ge = (await silver.get(f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue={thr}&limit=100")).json()
        gt = (await silver.get(f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3E&qoqValue={thr}&limit=100")).json()
        assert "RELIANCE" in {x["symbol"] for x in ge["rows"]} and "RELIANCE" not in {x["symbol"] for x in gt["rows"]}
        assert all(x["profitQoQ"] is not None and x["profitQoQ"] >= thr for x in ge["rows"])
    cells = (await silver.get(f"/api/results/quarter?quarter={q}&revQoQValue=-100000&npYoYOp=%3C&npYoYValue=100000&join=or&limit=100")).json()["growth"]   # the grid form
    assert cells["k"] == 2 and [c["period"] for c in cells["conditions"]] == ["qoq", "yoy"]
    exp = (await silver.get(url.replace("&limit=1", "") .replace("/quarter?", "/quarter/export?"))).json()   # the CSV follows the same filter
    assert len(exp["rows"]) == body["total"]
    # applied on top of the other filters
    other = (await silver.get(f"/api/results/quarter?quarter={q}&q=reliance&qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue=-100000")).json()
    assert {x["symbol"] for x in other["rows"]} <= {"RELIANCE"}
    # a company awaiting its report (LATEX) is never counted as having figures, never matches
    lt = (await silver.get(f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3C&qoqValue=100000&limit=100")).json()
    assert "LATEX" not in {x["symbol"] for x in lt["rows"]} and "NOSCORE" not in {x["symbol"] for x in lt["rows"]}


@pytest.mark.integration
async def test_endpoint_validation_and_plan_gate(app, seeded):  # noqa: F811
    q = seeded["quarter"]
    silver = await signed_in(app, "res-growth2@example.com", plan="silver")
    for bad in ("qoqMetric=sales&qoqOp=%3E%3D&qoqValue=1", "qoqMetric=netProfit&qoqOp=!&qoqValue=1", "qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue=nan", "yoyMetric=netProfit&yoyOp=%3E%3D&yoyValue=inf",
                "qoqMetric=netProfit&qoqValue=1", "qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue=1&join=xor"):
        r = await silver.get(f"/api/results/quarter?quarter={q}&{bad}")
        assert r.status_code == 400 and r.json()["detail"]["detail"], bad
        assert (await silver.get(f"/api/results/quarter/export?quarter={q}&{bad}")).status_code == 400
    ok = await silver.get(f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue=&join=or")           # empty value: filter off
    assert ok.status_code == 200 and ok.json()["growth"] is None
    async with new_client(app) as anon:                                                                                      # Basic: panel shows, no numbers, upgrade behaviour
        r = await anon.get(f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue=1")
        assert r.status_code == 403 and r.json()["detail"]["plan"] == "silver"
        plain = (await anon.get(f"/api/results/quarter?quarter={q}")).json()
        assert plain["growth"] is None and plain["distribution"]["total"] == plain["total"] and all(x[k] is None for x in plain["rows"] for k in R.FIGURES)
