"""The query language: tokenizer, parser, aliases, units, plan locks and evaluation against hand-computed rows."""

import json
import time

import pytest

from finlit.screener import ql
from finlit.screener.catalog import BY_KEY, CATALOG
from finlit.screener.data import Table
from finlit.screener.qaliases import ALIAS, CURATED, DROPPED, display_names, norm
from finlit.screener.qapi import EXAMPLES
from finlit.screener.qeval import data_warnings, run


def codes(q, plan="gold", sev=None):
    return [p.code for p in ql.analyze(q, plan).problems if sev is None or p.severity == sev]


def canon(q):
    a = ql.analyze(q)
    assert a.ok, [p.message for p in a.problems]
    return ql.canonical(a.root)


# ---------------------------------------------------------------------------------------------------------------- tokenizer
def test_tokenizer_kinds_and_positions():
    toks, errs = ql.tokenize("ROE >= 1,00,000.5 AND (PE<15)\n&& x")
    assert not errs
    assert [(t.kind, t.text) for t in toks][:8] == [("WORD", "ROE"), ("CMP", ">="), ("NUM", "1,00,000.5"), ("WORD", "AND"), ("LP", "("), ("WORD", "PE"), ("CMP", "<"), ("NUM", "15")]
    assert toks[2].start == 7 and toks[2].end == 17
    assert any(t.kind == "NL" for t in toks) and any(t.kind == "KW" and t.text == "and" for t in toks)
    assert [t.text for t in ql.tokenize("a ≥ 1 ≠ 2 <> 3 == 4")[0] if t.kind == "CMP"] == [">=", "!=", "!=", "="]


def test_tokenizer_bad_characters_and_numbers():
    toks, errs = ql.tokenize("ROE > 1.2.3 ; PE")
    assert [e.code for e in errs] == ["bad_number", "bad_character"]
    assert (errs[0].start, errs[0].end) == (6, 11) and (errs[1].start, errs[1].end) == (12, 13)


# ---------------------------------------------------------------------------------------------------------------- grammar
def test_and_binds_tighter_than_or():
    a = ql.analyze("PE < 10 OR ROE > 20 AND D/E < 1")
    root = a.root
    assert root.kind == "or" and root.items[0].op == "<" and root.items[1].kind == "and"


def test_parentheses_change_grouping():
    root = ql.analyze("(PE < 10 OR ROE > 20) AND D/E < 1").root
    assert root.kind == "and" and root.items[0].kind == "or"


def test_newline_means_and_at_lowest_precedence_and_continues_before_and_or():
    root = ql.analyze("PE < 10 OR ROE > 20\nD/E < 1").root
    assert root.kind == "and" and root.lines and root.items[0].kind == "or"        # (A OR B) AND C
    root = ql.analyze("PE < 10\nAND ROE > 20\nOR D/E < 1").root
    assert root.kind == "or"                                                       # a line starting with AND / OR continues the one above
    assert ql.analyze("(PE < 10\n OR ROE > 20)\nD/E < 1").ok


def test_any_case_and_symbol_connectors():
    for q in ("pe < 10 and roe > 5", "PE < 10 And ROE > 5", "PE < 10 && ROE > 5"):
        assert ql.analyze(q).root.kind == "and"
    assert ql.analyze("PE < 10 || ROE > 5").root.kind == "or"


def test_arithmetic_precedence_and_canonical_roundtrip():
    root = ql.analyze("ROE + ROCE * 2 > 10").root
    assert root.l.op == "+" and root.l.r.op == "*"
    root = ql.analyze("(ROE + ROCE) * 2 > 10").root
    assert root.l.op == "*" and root.l.l.op == "+"
    for q in ("(ROE + ROCE) / 2 > 10 AND (PE < 5 OR PB < 1)", "Market cap > 500 Cr\nP/E < 15\nROE > ROCE", "-ROE < -5", "ROE - (ROCE - 3) > 1", "ROE between 10 and 20"):
        c = canon(q)
        assert canon(c) == c


def test_between_expands_to_two_conditions():
    root = ql.analyze("ROE between 10 and 20").root
    assert root.kind == "and" and [c.op for c in root.items] == [">=", "<="]
    assert codes("ROE between 10") != []


# ---------------------------------------------------------------------------------------------------------------- aliases
def test_aliases_are_unambiguous_and_case_punctuation_blind():
    assert len(ALIAS) > 1000
    assert all(k in BY_KEY for k in ALIAS.values()) and set(CURATED) <= set(BY_KEY)
    for m in CATALOG:      # every metric answers to its key and label, and the label comes back from its own name
        assert ALIAS[norm(m.label)] == m.key and ALIAS[norm(m.key)] == m.key
        assert ALIAS[norm(display_names(m.key)[0])] == m.key
    for q, key in (("P/E", "pe"), ("pe", "pe"), ("Price to earning", "pe"), ("market cap", "market_cap"), ("MCAP", "market_cap"), ("m-cap", "market_cap"), ("ROCE", "roce"),
                   ("ROE", "roe"), ("D/E", "debt_to_equity"), ("debt to equity", "debt_to_equity"), ("Dividend  Yield", "dividend_yield"),
                   ("sales growth 3 years", "sales_cagr_3y"), ("5Y profit CAGR", "profit_cagr_5y"), ("52 week high", "high_52w"), ("RSI (14 days)", "rsi14"),
                   ("F&O", "fno"), ("P / E", "pe"), ("Price / Sales", "ps")):
        root = ql.analyze(f"{q} > 1").root
        assert isinstance(root.l, ql.Met) and root.l.key == key, q


def test_longest_name_wins_and_names_do_not_bleed_into_arithmetic():
    assert ql.analyze("ROE 3 year average > 5").root.l.key == "roe_3y"
    root = ql.analyze("ROE / ROCE > 1").root
    assert isinstance(root.l, ql.Bin) and root.l.l.key == "roe" and root.l.r.key == "roce"
    root = ql.analyze("PE - 5 < 3").root
    assert root.l.op == "-" and root.l.l.key == "pe"


# ---------------------------------------------------------------------------------------------------------------- errors, with positions
def one(q, code, plan="gold"):
    probs = [p for p in ql.analyze(q, plan).problems if p.code == code]
    assert probs, (q, [(p.code, p.message) for p in ql.analyze(q, plan).problems])
    return probs[0]


def test_unknown_metric_has_position_suggestions_and_see_all():
    q = "Market cap > 500 AND Piotroski score > 5"
    p = one(q, "unknown_metric")
    assert q[p.start:p.end] == "Piotroski score" and p.extra["seeAll"] and "We don't have a ratio called 'Piotroski score'" in p.message
    d = p.to_dict(q)
    assert d["line"] == 1 and d["col"] == 22 and d["text"] == "Piotroski score"
    p = one("Return on eqity > 5", "unknown_metric")
    assert p.extra["suggestions"][0]["label"] == "Return on equity" and p.fixes[0]["text"] == "Return on equity"
    assert len(p.extra["suggestions"]) <= 3
    assert one("ROE growth > 5", "unknown_metric").extra["suggestions"][0]["key"] == "roe"


def test_every_problem_is_returned_at_once_with_line_and_column():
    q = "Foo > 1\nROE >\nBar < 2 AND"
    a = ql.analyze(q)
    got = [(p.code, p.to_dict(q)["line"]) for p in a.problems]
    assert ("unknown_metric", 1) in got and ("missing_value", 2) in got and ("unknown_metric", 3) in got and ("dangling_connector", 3) in got


@pytest.mark.parametrize("q,code", [
    ("", "empty"), ("   \n ", "empty"),
    ("ROE >", "missing_value"), ("> 5", "missing_metric"), ("ROE 15", "missing_operator"), ("ROE", "incomplete_condition"),
    ("ROE > 15 AND", "dangling_connector"), ("AND ROE > 15", "starts_with_connector"), ("ROE > 15 AND OR PE < 5", "double_connector"),
    ("(ROE > 15", "missing_paren"), ("ROE > 15)", "extra_paren"), ("ROE > 15 PE < 5", "missing_connector"), ("5 > 3", "no_metric"),
    ("ROE < 5 < 10", "chained_comparison"), ("ROE > 15xyz", "bad_unit"), ("ROE > 1.2.3", "bad_number"), ("ROE > 5 ; PE < 2", "bad_character"),
    ("ROE / 0 > 1", "divide_by_zero"), ("ROE > ()", "empty_paren"),
])
def test_syntax_errors(q, code):
    assert code in codes(q), (q, codes(q))
    assert not ql.analyze(q).ok


def test_syntax_error_positions_and_fixes():
    p = one("ROE > 15 AND", "dangling_connector")
    assert (p.start, p.end) == (9, 12) and p.fixes[0]["text"] == "" and (p.fixes[0]["start"], p.fixes[0]["end"]) == (9, 12)
    p = one("PE 15", "missing_operator")
    assert {f["text"] for f in p.fixes} >= {" > 15", " < 15"}
    p = one("PE < 15 ROE > 10", "missing_connector")
    assert p.start == 8 and {f["text"] for f in p.fixes} == {"AND ", "OR "}
    p = one("(PE < 5", "missing_paren")
    assert (p.start, p.end) == (0, 1)


def test_size_limits():
    assert "too_long" in codes("PE < 5 AND " * 200)
    q = " AND ".join(f"ROE > {i}" for i in range(ql.MAX_CONDITIONS + 1))
    assert "too_many_conditions" in codes(q)
    assert ql.analyze(" AND ".join(f"ROE > {i}" for i in range(ql.MAX_CONDITIONS))).ok


# ---------------------------------------------------------------------------------------------------------------- units
def test_amounts_and_percents_accepted():
    for q in ("Market cap > 500", "Market cap > 500 Cr", "Market cap > 1,000", "Market cap > 1,00,000 crore", "Market cap > 2 lakh crore", "Market cap > 50000 lakh",
              "ROE > 22%", "ROE > 22 %", "PE < 15x", "PE < 15 times", "Promoter holding change > 2%", "Inventory days < 30 days", "Share price < 100"):
        assert ql.analyze(q).ok, (q, [p.message for p in ql.analyze(q).problems])
    assert ql.analyze("Market cap > 2 lakh crore").root.r.value == 200000
    assert ql.analyze("Market cap > 50000 lakh").root.r.value == 500
    assert ql.analyze("Market cap > 1,00,000").root.r.value == 100000


def test_unit_mismatches():
    p = one("Market cap > 5%", "unit_mismatch")
    assert "₹ crore" in p.message and p.fixes[0]["text"] == "5"
    assert "unit_mismatch" in codes("PE < 15 Cr")
    assert "unit_mismatch" in codes("ROE > Market cap")
    assert "unit_mismatch" in codes("ROE + Market cap > 5")
    assert "unit_mismatch" in codes("Market cap > ₹500")
    assert "unit_mismatch" in codes("RSI (14 days) < 30%")          # points are not a percentage
    assert "unit_mismatch" not in codes("ROE > ROCE") and "unit_mismatch" not in codes("Market cap / Net profit > 20")


def test_likely_mistake_warnings_do_not_block():
    a = ql.analyze("Market cap > 500000")
    assert a.ok and [p.code for p in a.problems] == ["crore_units"] and "crore" in a.problems[0].message
    assert a.problems[0].severity == "warning"
    a = ql.analyze("ROE > 0.15")
    assert a.ok and a.problems[0].code == "looks_like_fraction"
    a = ql.analyze("PB > 3 AND PB < 1")
    assert "contradiction" in [p.code for p in a.problems]
    assert not any(p.code == "contradiction" for p in ql.analyze("PB > 3 OR PB < 1").problems)


def test_yes_no_ratios():
    assert ql.analyze("Pays a dividend = yes").ok and ql.analyze("Is bank = no").ok and ql.analyze("Pays a dividend != 1").ok
    for q, code in (("Pays a dividend", "incomplete_condition"), ("Pays a dividend > 1", "flag_operator"), ("Pays a dividend = 5", "flag_value"), ("ROE = yes", "yes_no_misuse")):
        assert code in codes(q), q


def test_plan_locks_name_the_plan_and_are_not_dropped():
    q = "ROE > 10 AND P/B < 2 AND FinLit score > 60"
    probs = [p for p in ql.analyze(q, "basic").problems if p.code == "plan_locked"]
    assert [(q[p.start:p.end], p.extra["plan"]) for p in probs] == [("P/B", "silver"), ("FinLit score", "gold")]
    assert "Silver plan" in probs[0].message and "Gold plan" in probs[1].message
    assert [p.code for p in ql.analyze(q, "silver").problems] == ["plan_locked"]
    assert ql.analyze(q, "gold").ok


def test_examples_are_valid_against_the_real_catalogue():
    for ex in EXAMPLES:
        a = ql.analyze(ex["query"], "gold")
        assert a.ok and not a.problems, (ex["id"], [p.message for p in a.problems])
        assert canon(ql.canonical(a.root)) == ql.canonical(a.root)


# ---------------------------------------------------------------------------------------------------------------- evaluation
def row(sym, sector="IT", **m):
    return {"symbol": sym, "name": sym.title(), "sector": sector, "industry": None, "band": "mixed", "metrics": json.dumps(m)}


def table():
    rows = [
        row("A", market_cap=1000, pe=10, roe=20, roce=18, net_profit=100, debt_to_equity=0.2, div_paying=1.0, q_period_end=20260930),
        row("B", market_cap=600, pe=14, roe=12, roce=22, net_profit=0, debt_to_equity=0.0, div_paying=0.0, q_period_end=20260930),
        row("C", market_cap=300, pe=30, roe=25, roce=10, net_profit=50, debt_to_equity=1.5, q_period_end=20260630),
        row("D", market_cap=5000, roe=15, roce=15.04, net_profit=200, debt_to_equity=0.5),                   # no P/E (loss-maker: stored as unknown)
        row("E", market_cap=800, pe=-5, roe=30, roce=30, net_profit=10, debt_to_equity=0.1, div_paying=1.0),    # negative P/E is not a P/E
    ]
    return Table(rows, {}, {})


def match(q, recent=False, plan="gold"):
    t = table()
    a = ql.analyze(q, plan)
    assert a.ok, [p.message for p in a.problems]
    res = run(t, a.root, recent)
    return [t.symbols[i] for i in res.index], res, t


def test_evaluation_matches_hand_computed_rows():
    assert match("Market cap > 500")[0] == ["A", "B", "D", "E"]
    assert match("Market cap >= 600 AND ROE > 12")[0] == ["A", "D", "E"]
    assert match("PE < 15 AND ROE > 15")[0] == ["A"]
    assert match("PE < 15 OR ROE > 24")[0] == ["A", "B", "C", "E"]               # D has no P/E but E, C pass ROE; D fails ROE
    assert match("(PE < 15 OR ROE > 24) AND Market cap > 700")[0] == ["A", "E"]
    assert match("ROE > ROCE")[0] == ["A", "C"]
    assert match("ROE - ROCE >= 2")[0] == ["A", "C"] and match("ROE - ROCE > 2")[0] == ["C"]
    assert match("(ROE + ROCE) / 2 >= 19")[0] == ["A", "E"]
    assert match("Net profit * 10 > Market cap")[0] == ["C"]           # A: 1000 > 1000 is false
    assert match("Net profit * 10 >= Market cap")[0] == ["A", "C"]
    assert match("5 < ROE and ROE < 13")[0] == ["B"]                              # constant on the left
    assert match("ROE between 12 and 20")[0] == ["A", "B", "D"]


def test_missing_data_never_matches_and_is_counted():
    got, res, t = match("PE < 100")
    assert got == ["A", "B", "C"]                  # D (missing) and E (negative P/E) never match
    assert res.unknown == [t.pos["D"], t.pos["E"]]
    pm = {m["key"]: m for m in res.per_metric}
    assert pm["pe"]["missing"] == 2 and pm["pe"]["leftOut"] == 2 and pm["pe"]["known"] == 3
    got, res, _ = match("PE != 10")
    assert got == ["B", "C"]                       # != on an unknown is unknown, not true
    assert match("PE < 15 OR ROE > 14")[0] == ["A", "B", "C", "D", "E"]           # true OR unknown is true
    got, res, t = match("PE < 5 AND ROE > 100")
    assert got == [] and res.unknown == [t.pos["D"], t.pos["E"]][:0] + res.unknown and "D" not in got
    assert match("PE > 5 AND ROE > 14")[0] == ["A", "C"]


def test_division_by_zero_excludes_the_company():
    got, res, t = match("Net profit / Debt to equity > 100")
    assert t.pos["B"] in res.unknown and res.divzero == 1 and "B" not in got      # B: debt to equity 0 -> unknown, never a match
    # exact values: A 100/0.2=500, C 50/1.5=33.3, D 200/0.5=400, E 10/0.1=100
    assert match("Net profit / Debt to equity > 100")[0] == ["A", "D"]
    assert match("Net profit / Debt to equity >= 100")[0] == ["A", "D", "E"]


def test_equals_is_equal_as_shown():
    assert match("ROCE = 15")[0] == ["D"]                                         # 15.04 shows as 15.0
    assert match("ROCE != 15")[0] == ["A", "B", "C", "E"]
    assert match("Pays a dividend = yes")[0] == ["A", "E"]
    assert match("Pays a dividend = no")[0] == ["B"]                              # C and D unknown: not "no"


def test_recent_results_only():
    with pytest.raises(ValueError):                                               # fewer than 25 companies report a quarter: no latest quarter to compare with
        match("Market cap > 100", recent=True)
    t = Table([row(f"S{i}", market_cap=100 + i, q_period_end=20260930) for i in range(30)] + [row("OLD", market_cap=999, q_period_end=20260630), row("NODATE", market_cap=999)], {}, {})
    assert t.latest_quarter() == 20260930
    a = ql.analyze("Market cap > 100")
    res = run(t, a.root, True)
    assert len(res.index) == 29 and res.recent["dropped"] == 2 and res.recent["reported"] == 30
    assert t.symbols[res.index[0]].startswith("S")


def test_no_company_warning_uses_real_ranges():
    t = table()
    a = ql.analyze("Market cap > 90000")
    assert [p.code for p in data_warnings(t, a.root)] == ["no_company_in_range"]
    assert data_warnings(t, ql.analyze("Market cap > 100").root) == []


def test_speed_on_a_full_sized_table():
    rows = [row(f"S{i}", market_cap=i * 3.7, pe=5 + (i % 40), roe=(i % 50), roce=(i % 37), debt_to_equity=(i % 9) / 4, net_profit=i % 300) for i in range(5800)]
    t = Table(rows, {}, {})
    q = " AND ".join(["PE < 30 OR ROE > 5", "ROCE > 10", "Debt to equity < 1.5", "Net profit / Debt to equity > 20", "(ROE + ROCE) / 2 > 12"] * 4)
    a = ql.analyze(q)
    assert a.ok
    t0 = time.perf_counter()
    run(t, a.root)
    assert time.perf_counter() - t0 < 0.15
