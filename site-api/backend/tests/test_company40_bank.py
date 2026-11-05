"""The founder's 40 company questions: they are in the bank in the same structure, the matcher recognises each typed with a company symbol, and the assistant gets an answer plan
that says what the data tools cannot answer instead of guessing."""
import json
import pathlib
import re

import pytest

from backend import question_matcher as qm

ROOT = pathlib.Path(__file__).resolve().parents[3]
BANK = qm.bank()
SET = [q for q in BANK.q if q.get("set") == "company40"]
BY_ID = {q["id"]: q for q in BANK.q}

# The list exactly as the founder wrote it (ABC = the company, XYZ = the second company in question 39), in order.
FOUNDER = [
    'Which sector, industry and sub-industry does ABC belong to, and which cap bucket is it in?',
    'Where does ABC rank in its sector by market cap, revenue and profit?',
    "What was ABC's revenue over the last 5 years and the last 8 quarters?",
    "What are ABC's 3-year, 5-year and 10-year revenue CAGRs?",
    "Is ABC's revenue growing faster or slower than the sector median?",
    "How have ABC's operating profit (EBITDA) and operating margin trended over the last 5 years?",
    "What are ABC's 3-year and 5-year profit CAGRs?",
    "How did ABC's latest quarter compare with the same quarter last year and with the previous quarter?",
    "What share of ABC's PBT comes from other income, and did exceptional items affect its profit?",
    "How have ABC's total borrowings and debt-to-equity ratio changed over the last 5 years?",
    "How has ABC's net worth grown, and has its share count changed through dilution or buybacks?",
    'Is ABC net debt or net cash, and what is its debt-to-EBITDA ratio?',
    "What are ABC's receivable, inventory and payable days, and how has its cash conversion cycle changed?",
    "Are ABC's assets growing faster than its revenue?",
    "How has ABC's operating cash flow trended, and what is its CFO-to-PAT ratio each year?",
    'How much has ABC spent on capex each year, and what is that as a percentage of sales?',
    "What is ABC's free cash flow trend and FCF yield, and in how many of the last 10 years was FCF positive?",
    "What are ABC's ROE, ROCE and ROA over the last 5 years, and how do they compare with the sector median?",
    "What are ABC's interest coverage and current ratio, and are they improving?",
    "How does ABC's ROE break down into margin, asset turnover and leverage (DuPont)?",
    "For banks and NBFCs only: what are ABC's NIM, GNPA, NNPA and CASA ratio?",
    "What are ABC's current PE, PB, P/S and EV/EBITDA?",
    "How does ABC's PE compare with its own 3-year, 5-year and 10-year average, and in what percentile of its history is it?",
    'Is ABC cheaper or more expensive than the sector median on PE and PB?',
    "What are ABC's dividend yield and payout ratio, and for how many consecutive years has it paid a dividend?",
    "How has ABC's market cap changed over 1, 3 and 5 years?",
    'How has promoter holding in ABC changed over the last 8 quarters?',
    "What percentage of ABC's promoter shares is pledged?",
    'How have FII, DII and mutual fund holdings in ABC changed over the last 4 quarters?',
    'How many shareholders does ABC have, and who are its top holders?',
    "How far is ABC's current price from its 52-week high, 52-week low and all-time high?",
    "What are ABC's returns over 1 month, 3 months, 1 year, 3 years and 5 years versus its index and sector?",
    'Is ABC trading above or below its 50, 100 and 200 day moving averages, and what is its MACD signal?',
    "What is ABC's RSI, and is it overbought or oversold?",
    "What are ABC's volatility, beta and maximum drawdown?",
    "What is ABC's overall fundamental score and rating, and how do its component scores compare?",
    "How has ABC's score changed versus last quarter, and which factors drove the change?",
    "What is ABC's dividend, split, bonus and buyback history, and when is its next result date?",
    'How does ABC compare with XYZ on growth, margins, returns and valuation?',
    'Does ABC show any red flags, such as rising debt with falling margins, high promoter pledge, rising receivable days, CFO below PAT, or declining ROCE for 3+ years?',
]
GROUP_COUNTS = [2, 7, 5, 3, 4, 5, 4, 5, 2, 1, 1, 1]
NOT_AVAILABLE_IDS = ["C.1.Q2", "C.2.Q5", "C.5.Q21", "C.6.Q23", "C.6.Q24", "C.7.Q28", "C.9.Q37", "C.10.Q38", "C.3.Q11", "C.8.Q33", "C.8.Q35"]


def typed(q, name="Infosys", other="TCS"):
    return q["text"].replace("{company_2}", other).replace("{company}", name)


def test_the_forty_questions_are_in_the_bank_word_for_word():
    assert len(SET) == 40 and [q["n"] for q in SET] == list(range(1, 41))
    for q, want in zip(SET, FOUNDER):
        assert q["text"].replace("{company_2}", "XYZ").replace("{company}", "ABC") == want
        assert "{company}" in q["text"] and q["group"] == "Company"
    assert [q["text"].count("{company_2}") for q in SET if q["n"] != 39] == [0] * 39 and "{company_2}" in SET[38]["text"]


def test_ids_are_unique_follow_the_scheme_and_never_meet_an_older_id():
    ids = [q["id"] for q in BANK.q]
    assert len(ids) == len(set(ids)) == 497
    for q in SET:
        assert q["id"] == f"C.{q['section']}.Q{q['n']}" and re.fullmatch(r"C\.\d+\.Q\d+", q["id"])
    assert not {q["id"] for q in SET} & {q["id"] for q in BANK.q if q.get("set") != "company40"}


def test_group_counts_and_headings():
    counts = [sum(1 for q in SET if q["section"] == s) for s in range(1, 13)]
    assert counts == GROUP_COUNTS
    sug = json.loads((ROOT / "frontend/src/content/questionSuggestions.json").read_text(encoding="utf-8"))
    assert [g["title"] for g in sug["groups"]] == ["Business Snapshot", "Profit & Loss", "Balance Sheet", "Cash Flow", "Ratios", "Valuation", "Shareholding", "Price & Technicals", "Model Scores", "Corporate Actions", "Compare", "Red Flags"]
    assert [len(g["items"]) for g in sug["groups"]] == GROUP_COUNTS
    assert [i["id"] for g in sug["groups"] for i in g["items"]] == [q["id"] for q in SET]
    assert [i["text"] for g in sug["groups"] for i in g["items"]] == [q["text"] for q in SET]
    assert [i["id"] for g in sug["groups"] for i in g["items"] if i.get("lendersOnly")] == ["C.5.Q21"]
    assert [i["id"] for g in sug["groups"] for i in g["items"] if i.get("needsSecondCompany")] == ["C.11.Q39"]
    assert len(sug["company"]) == 8      # the five quick chips (and spare) are untouched


def test_every_question_names_real_tools_a_plan_and_the_older_questions_it_covers():
    src = (ROOT / "backend/finlit/mcp/tools.py").read_text(encoding="utf-8")
    real = set(re.findall(r'Tool\("([a-z_]+)"', src))
    for q in SET:
        assert q["plan"].strip() and q["tools"] and set(q["tools"]) <= real, q["id"]
        assert q["status"] in ("available", "partly", "not_available")
        assert all(c in BY_ID and BY_ID[c].get("set") != "company40" for c in q["covers"]), q["id"]
        assert q["status"] == "available" or q["limits"], q["id"]


@pytest.mark.parametrize("q", SET, ids=lambda q: q["id"])
def test_each_question_typed_with_a_symbol_finds_itself_with_high_confidence(q):
    for name in ("Infosys", "RELIANCE", "Tata Motors"):
        r = BANK.match(typed(q, name))
        assert r.confidence == "high" and r.best.id == q["id"], (name, r.best.id if r.best else None, r.confidence)


NEAR = [
    ("C.2.Q3", "show me TCS sales for the past five years and the last eight quarters"),
    ("C.2.Q4", "what is Asian Paints revenue CAGR over 3, 5 and 10 years"),
    ("C.3.Q12", "is Zomato carrying net debt or net cash, and what is its debt to EBITDA"),
    ("C.4.Q15", "Nestle operating cash flow trend and CFO to PAT ratio each year"),
    ("C.6.Q22", "what are the current PE, PB, price to sales and EV/EBITDA of Titan"),
    ("C.6.Q23", "how does the PE of ITC compare with its 3 year, 5 year and 10 year average PE and what percentile is it in"),
    ("C.7.Q27", "how has the promoter stake in Reliance changed over the last 8 quarters"),
    ("C.8.Q33", "is Infosys above or below its 50 100 and 200 day moving average and what is the MACD signal"),
    ("C.9.Q36", "what is Wipro's overall fundamental score and rating and how do the component scores compare"),
    ("C.12.Q40", "does HDFC Bank show any red flags like rising debt with falling margins, high promoter pledge, rising receivable days, CFO below PAT or declining ROCE"),
]


@pytest.mark.parametrize("qid,msg", NEAR)
def test_a_paraphrase_still_finds_the_question(qid, msg):
    r = BANK.match(msg)
    assert r.best and (r.best.id == qid or BANK.same_ground(r.best.id, qid)), (r.best.id if r.best else None, r.confidence)
    assert r.confidence in ("high", "related")


@pytest.mark.parametrize("msg", ["hello", "tell me a joke", "who will win the world cup", "what is the weather in Mumbai today", "write me a python function to sort a list", "how do I cook biryani"])
def test_unrelated_messages_do_not_match_the_set(msg):
    r = BANK.match(msg)
    assert r.confidence == "none" or r.best.id not in BY_ID or BY_ID[r.best.id].get("set") != "company40" or r.confidence == "related" and r.best.score < 0.34


def test_the_older_narrow_questions_are_still_answered_as_themselves():
    r = BANK.match("does Zomato have net debt or net cash")
    assert r.best.id in ("C.3.5.1", "C.3.Q12") and r.confidence == "high"
    assert BANK.match("what is the market cap of Reliance, is it large cap or mid cap").best.id in ("C.1.1.2", "C.1.Q1")


def directive_for(q):
    return qm.directive(BANK.match(typed(q)))


@pytest.mark.parametrize("q", SET, ids=lambda q: q["id"])
def test_the_directive_carries_the_plan_and_the_rule_for_what_is_not_available(q):
    d = directive_for(q)
    assert q["id"] in d and "Answer plan:" in d and q["plan"][:60] in d and "cover every part" in d
    if q["limits"]:
        assert "DATA LIMITS (strict)" in d and "Never estimate" in d and "do not provide it" in d
        for lim in q["limits"]:
            assert lim in d
    assert "Give no advice and no instruction to act" in d


@pytest.mark.parametrize("qid", NOT_AVAILABLE_IDS)
def test_the_data_limited_questions_say_exactly_what_is_not_available(qid):
    q = BY_ID[qid]
    assert q["status"] in ("partly", "not_available") and q["limits"]
    assert re.search(r"\b(not (?:available|stored)|do(?:es)? not|cannot|is not)\b", " ".join(q["limits"]), re.I)


def test_specific_limits_are_stated_for_ten_year_average_pe_casa_pledge_and_sector_median():
    assert "not available" in " ".join(BY_ID["C.6.Q23"]["limits"]) and "10-year" in " ".join(BY_ID["C.6.Q23"]["limits"])
    assert "CASA" in " ".join(BY_ID["C.5.Q21"]["limits"]) and "not available" in " ".join(BY_ID["C.5.Q21"]["limits"])
    assert "pledged is not stored" in " ".join(BY_ID["C.7.Q28"]["limits"])
    assert "sector median" in " ".join(BY_ID["C.2.Q5"]["limits"])
    assert BY_ID["C.5.Q21"]["status"] == "not_available" and BY_ID["C.5.Q21"].get("lendersOnly")


def test_plans_and_limits_never_advise():
    bad = re.compile(r"\b(buy|sell|hold|reduce|avoid|accumulate|multibagger|top pick|best|target price)\b", re.I)
    for q in SET:
        text = q["plan"] + " " + " ".join(q["limits"])
        assert not bad.search(text), (q["id"], bad.search(text).group(0))
    d = qm.DESCRIBE_RULE
    assert "Give no advice" in d and "overbought, oversold" in d and not bad.search(d)
