"""The basic FinLit score must not depend on the industry or on a company having debt (Coal India: debt-free, huge figures, large dividends).
A pillar with no score says exactly which inputs the provider did not report."""
import copy

import pytest

from conftest import load, BUNDLE_FILES
from finlit.snapshot import build


def bundle():
    b = {key: load(name) for key, name in BUNDLE_FILES.items()}
    b.update(symbol="COALINDIA", statement="consolidated")
    return b


def zero(b, section, test):
    for row in b[section]["financials"]:
        for key, value in list(row.items()):
            if test(key.lower()) and isinstance(value, (int, float)):
                row[key] = 0


def debt_free(b):
    zero(b, "bs_annual", lambda k: "borrow" in k or "debt" in k or "lease" in k)
    zero(b, "pl_annual", lambda k: "financecost" in k or "interest" in k)
    zero(b, "pl_quarterly", lambda k: "financecost" in k)


def negative_equity(b):
    for row in b["bs_annual"]["financials"]:
        for key, value in list(row.items()):
            if "equity" in key.lower() and isinstance(value, (int, float)):
                row[key] = -abs(value)


def huge(b):
    for section in ("bs_annual", "pl_annual", "cf_annual", "pl_quarterly"):
        for row in b[section]["financials"]:
            for key, value in list(row.items()):
                if isinstance(value, (int, float)) and not key.lower().startswith(("eps", "shares", "dilut")):
                    row[key] = value * 1000


def no_dividends(b):
    b["dividends"] = [] if isinstance(b["dividends"], list) else {}


@pytest.mark.parametrize("change", [debt_free, negative_equity, huge, no_dividends, lambda b: (debt_free(b), huge(b))], ids=["debt-free", "negative-equity", "huge", "no-dividends", "debt-free-huge"])
def test_extreme_companies_are_still_scored(change):
    b = bundle()
    change(b)
    score = build(copy.deepcopy(b))["summary"]["score"]
    assert score["overall"] is not None and score["band"]["key"] != "insufficient"
    assert all(p["score"] is not None for p in score["pillars"])


def test_a_pillar_without_inputs_names_them():
    b = bundle()
    for key in ("cf_annual",):
        b[key] = {"financials": []}
    for key in ("ratios_pr", "ratios_le", "ratios_li", "ratios_ef", "growth", "basic"):
        b[key] = None
    quality = next(p for p in build(b)["summary"]["score"]["pillars"] if p["key"] == "quality")
    assert quality["score"] is None
    assert "ROE" in quality["reason"] and "ROCE" in quality["reason"] and "CFO / PAT" in quality["reason"]
