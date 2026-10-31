"""The 'Rules for writing a query' guide on the query builder page (frontend/src/content/queryRules.json) is checked against the real parser:
every example parses and runs, every syntax row parses, every 'do' is accepted and every 'don't' fails with the documented code, and every error
code in the guide is one the parser can produce."""

import json
import re
from pathlib import Path

import pytest

from finlit.screener import ql
from finlit.screener.catalog import CATALOG
from finlit.screener.data import Table
from finlit.screener.qeval import run
from tests.test_ql import row

RULES = json.loads((Path(__file__).resolve().parents[2] / "frontend" / "src" / "content" / "queryRules.json").read_text(encoding="utf-8"))


def codes(q, plan="gold"):
    return [p.code for p in ql.analyze(q, plan).problems]


def errors(q, plan="gold"):
    return [p.code for p in ql.analyze(q, plan).problems if p.severity == "error"]


def table(extra=()):
    return Table([
        row("A", market_cap=1000, pe=10, pb=1.5, roe=20, roce=25, net_profit=100, debt_to_equity=0.2, div_paying=1.0, dividend_yield=3, q_period_end=20260930),
        row("B", market_cap=600, pe=14, roe=12, roce=22, net_profit=0, debt_to_equity=0.0, div_paying=0.0, q_period_end=20260930),
        row("C", market_cap=300, pe=30, roe=25, roce=10, net_profit=50, debt_to_equity=1.5, q_period_end=20260630),
        row("D", market_cap=5000, roe=15, roce=15.04, net_profit=200, debt_to_equity=0.5),
        *extra,
    ], {}, {})


EX = [(e["id"], e["query"]) for e in RULES["examples"]]


def test_there_are_ten_examples_and_each_is_open_to_every_plan():
    assert len(EX) == 10 and len({i for i, _ in EX}) == 10
    for _id, q in EX:
        a = ql.analyze(q, "basic")
        assert a.ok and not a.problems, (_id, [p.message for p in a.problems])


@pytest.mark.parametrize("ex", EX, ids=[i for i, _ in EX])
def test_every_example_runs(ex):
    a = ql.analyze(ex[1], "basic")
    run(table(), a.root)          # does not raise


def test_syntax_rows_parse():
    for r in RULES["syntax"]:
        a = ql.analyze(r["example"], "gold")
        assert a.ok, (r["op"], r["example"], [p.message for p in a.problems])
        assert not [p for p in a.problems if p.severity == "error"]


def test_dos_are_accepted_and_donts_give_the_documented_code():
    for d in RULES["dos"]:
        assert ql.analyze(d["do"], "gold").ok and not codes(d["do"]), d
        assert d["code"] in codes(d["dont"]), (d, codes(d["dont"]))


def test_error_rules_bad_fails_with_that_code_and_good_passes():
    for code, e in RULES["errors"].items():
        assert e["rule"] and e["fix"], code
        if "bad" in e:
            assert code in codes(e["bad"]), (code, e["bad"], codes(e["bad"]))
            assert ql.analyze(e["good"], "gold").ok and not codes(e["good"]), (code, e["good"])


def test_specials_match_what_the_parser_reports():
    for k, s in RULES["specials"].items():
        probs = ql.analyze(s["bad"], "basic").problems
        unknown = [p.to_dict(s["bad"])["text"] for p in probs if p.code == "unknown_metric"]
        assert any(re.search(s["match"], t, re.I) for t in unknown), (k, unknown)
        assert not re.search(s["match"], "ROE", re.I)


def test_codes_without_a_sample_are_checked_here():
    assert errors("") == ["empty"]
    assert "too_long" in errors("x" * 2001)
    many = "\n".join(["ROE > 15"] * 31)
    assert "too_many_conditions" in errors(many)
    assert not errors("\n".join(["ROE > 15"] * 30))
    locked = next(m for m in CATALOG if m.tier == "gold")
    assert "plan_locked" in errors(f"{locked.label} > 1", "basic") and "plan_locked" not in errors(f"{locked.label} > 1", "gold")
    assert "crore_units" in codes("Market cap > 5000000000") and ql.analyze("Market cap > 5000000000", "basic").ok       # a warning: it still runs
    assert "contradiction" in codes("ROE > 50 AND ROE < 10") and ql.analyze("ROE > 50 AND ROE < 10", "basic").ok


def test_every_documented_code_exists_in_the_parser_source():
    src = (Path(ql.__file__)).read_text(encoding="utf-8")
    for code in RULES["errors"]:
        if code != "recent_unavailable":
            assert f'"{code}"' in src, code
    # and every code the parser can raise has a rule in the guide
    raised = set(re.findall(r'(?:err|add)\(\s*"([a-z_]+)"', src)) | set(re.findall(r'Problem\(\s*"([a-z_]+)"', src))
    assert raised <= set(RULES["errors"]), raised - set(RULES["errors"])


def test_golden_rules_are_true():
    # 1 + 2: lines are joined with AND, at the lowest precedence
    assert ql.canonical(ql.analyze("ROE > 15 OR P/E < 10\nROCE > 5").root) == "Return on equity > 15 OR P/E Ratio < 10\nReturn on capital employed > 5"
    a = ql.analyze("ROE > 15 OR P/E < 10\nROCE > 5")
    assert a.root.kind == "and" and a.root.lines and a.root.items[0].kind == "or"
    # 3: AND before OR, && and ||, a line starting with AND / OR continues the one above
    assert ql.analyze("ROE > 1 OR ROE > 2 AND ROE > 3").root.kind == "or"
    assert ql.analyze("ROE > 15 && PE < 5 || ROCE > 1").root.kind == "or"
    cont = ql.analyze("ROE > 15\nOR PE < 10").root
    assert cont.kind == "or" and not getattr(cont, "lines", False)
    # 4: case, spacing and everyday names are one name
    assert ql.canonical(ql.analyze("  roe   >15 and P/E<20 ").root) == ql.canonical(ql.analyze("Return on equity > 15 AND pe < 20").root)
    assert ql.canonical(ql.analyze("mcap > 5").root) == ql.canonical(ql.analyze("Market cap > 5").root)
    # 5: a bare number and the same number with the ratio's unit are the same
    assert ql.analyze("ROE > 15%").ok and ql.analyze("ROE > 15").ok
    assert [r.value for r in [ql.analyze("Market cap > 1 lakh crore").root.r]] == [100000.0]
    assert ql.analyze("Market cap > 5,00,000 Cr").root.r.value == 500000.0
    # 6: yes / no
    assert ql.analyze("Pays a dividend = yes").ok and ql.analyze("Pays a dividend = no").ok
    # 8: limits
    assert ql.MAX_CHARS == 2000 and ql.MAX_CONDITIONS == 30


def test_missing_values_negative_values_and_recent():
    t = table([row(f"S{i}", market_cap=1, q_period_end=20260930) for i in range(30)])     # the latest quarter needs enough companies that reported it

    def got(q, recent=False):
        r = run(t, ql.analyze(q, "gold").root, recent)
        return [t.symbols[i] for i in r.index]
    assert got("P/E < 100") == ["A", "B", "C"]                       # D has no P/E: not matched
    assert got("P/E != 10") == ["B", "C"]                            # != on a missing figure is not a match either
    assert got("P/E < 15 OR ROE > 14") == ["A", "B", "C", "D"]       # true OR unknown is true
    assert got("ROE > -5") == ["A", "B", "C", "D"]                   # a negative number compares as a number
    assert got("Market cap > 100", recent=True) == ["A", "B"]        # only companies that reported the latest quarter
    assert got("ROCE = 15") == ["D"]                                 # equal as shown (15.04 shows as 15.0)
    assert got("ROE between 12 and 20") == ["A", "B", "D"]           # both ends included
    r = run(t, ql.analyze("P/E < 100", "gold").root)
    assert {m["key"]: m["leftOut"] for m in r.per_metric}["pe"] == 31
