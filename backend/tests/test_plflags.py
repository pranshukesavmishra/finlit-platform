"""The Python P&L flag rules against the same shared cases the front end runs (frontend/src/lib/fixtures/plFlags.cases.json)."""

import json
from pathlib import Path

import pytest

from finlit import plflags as pf

CASES = json.loads((Path(__file__).parents[2] / "frontend/src/lib/fixtures/plFlags.cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_cases(case):
    assert sorted(f["key"] for f in pf.pl_flags(case.get("annual"), case.get("quarterly"))) == case["expect"]


def test_all_eight_cases_are_covered_by_the_shared_cases():
    assert {k.split(":")[0] for c in CASES for k in c["expect"]} == {str(n) for n in range(1, 9)}


def annual(rev, np, op=None):
    rows = {"revenue": rev, "net_profit": np, **({"operating_profit": op} if op else {})}
    return {"periods": ["FY25", "FY26"], "periodEnds": ["2025-03-31", "2026-03-31"], "rows": rows}


def test_text_and_figures_match_the_front_end():
    [f] = pf.pl_flags(annual([100, 110], [10, 9]), None)
    assert f["text"] == "Revenue grew 10.0% while net profit fell 10.0%. Compared with FY25."
    assert (f["revenueGrowth"], f["profitGrowth"], f["severity"], f["rows"], f["periods"]) == (10, -10, "caution", ["revenue", "net_profit"], ["FY26", "FY25"])


def test_loss_to_profit_is_described_in_words_without_a_percentage():
    [f] = pf.pl_flags(annual([100, 101], [-5, 4]), None)
    assert f["case"] == 5 and f["profitGrowth"] is None
    assert "turned from a loss of ₹5 crore to a profit of ₹4 crore" in f["text"]


def test_garbage_input_never_raises_or_flags():
    assert pf.pl_flags(None, None) == []
    assert pf.pl_flags({}, {}) == []
    assert pf.pl_flags(annual([100, float("nan")], [10, 15]), None) == []
    assert pf.pl_flags(annual(["x", 110], [10, 15]), None) == []
    assert pf.pl_flags({"periods": ["FY26"], "periodEnds": ["bad"], "rows": {"revenue": [1]}}, None) == []
    assert pf.pl_flags({"periods": ["FY25", "FY26"], "periodEnds": ["2025-03-31", "nope"], "rows": {"revenue": [1, 2], "net_profit": [1, 2]}}, None) == []
