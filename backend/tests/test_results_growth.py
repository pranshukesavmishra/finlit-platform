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


def spec(qoq=None, yoy=None, join="and"):
    c = lambda t: None if t is None else R.GrowthCond(*t)   # noqa: E731
    return R.GrowthSpec(c(qoq), c(yoy), join)


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


def test_four_way_counts_add_up_to_companies_with_figures():
    Q, Y = ("netProfit", ">=", 1.0), ("netProfit", ">=", 10.0)
    _, s = R.growth_filter(ROWS, spec(Q, Y))
    assert (s["both"], s["onlyQoQ"], s["onlyYoY"], s["neither"]) == (1, 2, 2, 1) and s["withFigures"] == 6                 # G has no figures: not counted
    assert s["both"] + s["onlyQoQ"] + s["onlyYoY"] + s["neither"] == s["withFigures"]
    assert (s["qoqMissing"], s["yoyMissing"]) == (1, 1) and s["matching"] == 1
    _, o = R.growth_filter(ROWS, spec(Q, Y, "or"))
    assert o["matching"] == o["both"] + o["onlyQoQ"] + o["onlyYoY"] == 5 and o["neither"] == 1
    _, one = R.growth_filter(ROWS, spec(qoq=Q))
    assert one["both"] == 0 and one["onlyYoY"] == 0 and one["onlyQoQ"] == 3 and one["neither"] == 3 and one["yoy"] is False and one["matching"] == 3


@pytest.mark.parametrize("join", ["and", "or"])
def test_identity_holds_for_every_operator_combination(join):
    vals = [None, -5.0, -0.1, 0.0, 0.1, 5.0]
    rows = [co(f"X{i}", np_q=a, np_y=b) for i, (a, b) in enumerate(itertools.product(vals, vals))] + [_row("NF", m={})]
    for oq, oy in itertools.product(R.GROWTH_OPS.values(), repeat=2):
        for t in (-0.1, 0.0, 2.5):
            out, s = R.growth_filter(rows, spec(("netProfit", oq, t), ("netProfit", oy, -t), join))
            assert s["both"] + s["onlyQoQ"] + s["onlyYoY"] + s["neither"] == s["withFigures"] == len(vals) ** 2
            assert len(out) == s["matching"] == (s["both"] if join == "and" else s["both"] + s["onlyQoQ"] + s["onlyYoY"])


def test_distribution_counts_sectors_and_caps():
    rows = [co(f"S{i}", sector=f"Sec{i % 9}", cap=["Large", "Mid", "Small", None][i % 4]) for i in range(40)] + [co("N", sector=None)]
    d = R.distribution(rows)
    assert d["total"] == 41 and sum(x["n"] for x in d["sectors"]) == 41 and sum(x["n"] for x in d["caps"]) == 41
    assert len(d["sectors"]) == R.TOP_SECTORS + 1 and d["sectors"][-1]["name"] == "Others"
    assert [x["name"] for x in d["caps"]] == ["Large", "Mid", "Small", "Not classified"]
    assert R.distribution([]) == {"total": 0, "sectors": [], "caps": []}


def test_validation_is_strict_with_plain_messages():
    ok = R.growth_params("netProfit", ">=", "1", "revenue", "<", "-2.5", "or")
    assert ok.qoq == R.GrowthCond("netProfit", ">=", 1.0) and ok.yoy == R.GrowthCond("revenue", "<", -2.5) and ok.join == "or"
    assert R.growth_params("", "", "", "", "", "", "").active is False and R.growth_params("netProfit", ">=", "", "", "", "", "").active is False   # empty value = off
    assert R.growth_params("", "", "", "revenue", "gt", ".5", "").yoy == R.GrowthCond("revenue", ">", 0.5) and R.growth_params("revenue", ">=", "+3", "", "", "", "").qoq.value == 3.0
    for args in (("sales", ">=", "1", "", "", "", ""), ("netProfit", "=>", "1", "", "", "", ""), ("netProfit", ">=", "abc", "", "", "", ""), ("netProfit", ">=", "nan", "", "", "", ""),
                 ("netProfit", ">=", "inf", "", "", "", ""), ("netProfit", ">=", "1e999", "", "", "", ""), ("netProfit", ">=", "1e3", "", "", "", ""), ("netProfit", ">=", "9999999", "", "", "", ""),
                 ("netProfit", ">=", "1,5", "", "", "", ""), ("netProfit", ">=", "--1", "", "", "", ""), ("", ">=", "1", "", "", "", ""), ("netProfit", "", "1", "", "", "", ""),
                 ("", "", "", "bogus", "", "", ""), ("", "", "", "", "!", "", ""), ("netProfit", ">=", "1", "", "", "", "xor")):
        e = _raises(lambda a=args: R.growth_params(*a))
        assert e.status_code == 400 and e.detail["detail"], args


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
    assert g["withFigures"] == len(with_fig) and g["both"] + g["onlyQoQ"] + g["onlyYoY"] + g["neither"] == g["withFigures"]
    exp_match = [x for x in with_fig if x["profitQoQ"] is not None and x["revenueYoY"] is not None]
    assert body["total"] == g["matching"] == g["both"] == len(exp_match) and len(body["rows"]) == min(1, len(exp_match))
    if rel["profitQoQ"] is not None:
        thr = rel["profitQoQ"]                                                                     # exactly the figure the table shows: >= matches, > does not
        ge = (await silver.get(f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3E%3D&qoqValue={thr}&limit=100")).json()
        gt = (await silver.get(f"/api/results/quarter?quarter={q}&qoqMetric=netProfit&qoqOp=%3E&qoqValue={thr}&limit=100")).json()
        assert "RELIANCE" in {x["symbol"] for x in ge["rows"]} and "RELIANCE" not in {x["symbol"] for x in gt["rows"]}
        assert all(x["profitQoQ"] is not None and x["profitQoQ"] >= thr for x in ge["rows"])
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
