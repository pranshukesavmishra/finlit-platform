"""Coal India was NOT RATED because its FinEdge label ("Coal" / "Energy") matched no classification rule. Every label we can know about must
resolve to a model group, except the ones listed here as intentionally unrated (with the reason the report gives)."""
import json
import re
from pathlib import Path

import pytest

from backend.premium_classification import CLASSIFICATION_VERSION, resolve_group, unmapped_reason, unrated_kind
from backend.premium_data import adapt_inputs
from backend.premium_engine import score_company
from backend.tests.test_premium_not_rated_reasons import AS_OF, adapt, example

ROOT = Path(__file__).resolve().parents[3]

# FinEdge-style and Indian-market labels by business. Value: the model group chosen from the business economics (docs/prism/CLASSIFICATION.md).
LABELS = {
    "Coal": "HEAVY", "Energy": "HEAVY", "Mining & Minerals": "HEAVY", "Minerals & Mining": "HEAVY", "Lignite": "HEAVY",
    "Oil & Gas Exploration": "HEAVY", "Oil Exploration & Production": "HEAVY", "Refineries": "HEAVY", "Petrochemicals": "MFG", "Petrochemicals": "MFG",
    "Aluminium": "HEAVY", "Copper": "HEAVY", "Zinc": "HEAVY", "Ferro Alloys": "HEAVY", "Iron & Steel": "HEAVY", "Forgings & Castings": "HEAVY",
    "Power Generation": "UTILITY", "Power Transmission": "UTILITY", "Renewable Energy": "UTILITY", "Solar Power": "UTILITY", "Wind Energy": "UTILITY",
    "Ports": "UTILITY", "Airports": "UTILITY", "Roads & Highways": "UTILITY", "Railway Infrastructure": "UTILITY", "Water Supply": "UTILITY",
    "Fertilisers": "MFG", "Chemicals": "MFG", "Specialty Chemicals": "MFG", "Agrochemicals": "MFG", "Textiles": "MFG", "Auto Ancillaries": "MFG",
    "Capital Goods": "MFG", "Defence": "MFG", "Shipping": "MFG", "Airlines": "MFG", "Logistics": "MFG", "Paper": "MFG", "Sugar": "MFG",
    "Tobacco": "MFG", "Alcoholic Beverages": "MFG", "Breweries & Distilleries": "MFG", "Packaging": "MFG", "Jewellery": "MFG",
    "Diversified": "MFG", "Conglomerates": "MFG", "Healthcare": "MFG", "Hospitals": "MFG", "Diagnostics": "MFG", "Medical Equipment": "MFG",
    "Building Products": "MFG", "Home Furnishings": "MFG", "Aerospace": "MFG", "Dyes & Pigments": "MFG",
    "Media": "LIGHT", "Education": "LIGHT", "Trading": "LIGHT", "Travel & Tourism": "LIGHT", "Broadcasting": "LIGHT", "Consumer Staples": "LIGHT",
    "Household & Personal Care": "LIGHT", "Courier Services": "LIGHT", "Gaming": "LIGHT",
    "Banks": "BANK", "Insurance": "INSURANCE", "Housing Finance": "NBFC", "Real Estate": "REALTY",
}
# Intentionally not rated: label -> the kind of reason the report gives.
UNRATED = {
    "REIT": "trust", "InvIT": "trust", "Real Estate Investment Trust": "trust", "Infrastructure Investment Trust": "trust", "Investment Trusts/Mutual Funds": "trust",
    "ETF": "fund", "Exchange Traded Fund": "fund", "SPAC": "fund", "Special Purpose Acquisition Company": "fund", "Mutual Fund": "fund",
}


def repo_labels():
    """Every label found in the repository's recorded lists (screener demo, search index, peer groups)."""
    found = set()
    screener = ROOT / "frontend/public/demo/screener.json"
    if screener.exists():
        found |= {r["sector"] for r in json.loads(screener.read_text())["rows"] if r.get("sector")}
    index = ROOT / "frontend/public/demo/search-index.json"
    if index.exists():
        found |= set(json.loads(index.read_text())["sectors"])
    groups = ROOT / "backend/finlit/data/leadership_groups.json"
    if groups.exists():
        found |= {g["name"] for g in json.loads(groups.read_text())["groups"] if g.get("kind") in ("industry", "sector")}
    return sorted(found)


@pytest.mark.parametrize("label,group", sorted(LABELS.items()))
def test_every_business_label_has_a_group(label, group):
    assert resolve_group({"industry": label}) == (group, False)


@pytest.mark.parametrize("label,kind", sorted(UNRATED.items()))
def test_trusts_and_funds_stay_unrated_with_an_honest_reason(label, kind):
    assert resolve_group({"industry": label})[1] is True and unrated_kind({"industry": label}) == kind
    reason = unmapped_reason({"industry": label})
    assert "not rated by this model" in reason and label in reason and "yet" not in reason


def test_no_recorded_label_is_unmapped_unless_listed_as_unrated():
    labels = repo_labels()
    assert len(labels) > 50 or not labels
    unmapped = [label for label in labels if resolve_group({"industry": label})[1] and label not in UNRATED]
    assert unmapped == []


def test_asset_managers_are_not_mistaken_for_funds():
    for label in ("Asset Management", "Mutual Fund Management", "Fund Houses", "Investment Managers"):
        assert resolve_group({"industry": label})[1] is False


def test_labels_that_already_had_a_group_keep_it():
    cases = {"Finance": "NBFC", "Automobiles": "MFG", "Cement": "HEAVY", "Steel": "HEAVY", "Pharmaceuticals": "LIGHT", "Power": "UTILITY", "Software": "LIGHT",
             "Medical/Nursing Services": "LIGHT", "Hospital/Nursing Management": "MFG", "Banks": "BANK"}
    for label, group in cases.items():
        assert resolve_group({"industry": label}) == (group, False)
    # the precedence: a financial label is never pulled into HEAVY / UTILITY by words such as energy, power or infrastructure
    assert resolve_group({"industry": "Power Finance", "macro_sector": "Energy"})[0] == "NBFC"
    assert resolve_group({"industry": "Infrastructure Finance"})[0] == "NBFC"
    assert resolve_group({"industry": "Automobiles", "macro_sector": "Energy"})[0] == "MFG"


def test_coal_india_is_rated_not_blocked():
    """The founder's report: industry Coal, sector Energy, macro Energy; a debt-free PSU with large cash and heavy dividends."""
    profile = {"industry": "Coal", "sector": "Energy", "sub_industry": "Coal", "macro_sector": "Energy"}
    d, group, _, meta, _, _ = adapt(profile)
    assert group == "HEAVY" and not meta["groupDefaulted"] and not d["rating_blockers"]
    assert meta["classificationVersion"] == CLASSIFICATION_VERSION == 3
    result = score_company(example(), "HEAVY")
    assert result["status"] != "NOT RATED" and result["final"] is not None


def test_a_trust_gets_its_own_blocker_text_in_the_report():
    d, *_ = adapt({"industry": "Infrastructure Investment Trust", "macro_sector": "Financial Services"})
    assert len(d["rating_blockers"]) == 1 and "Trusts (REITs, InvITs) are not rated by this model" in d["rating_blockers"][0]
    assert "model group" in d["rating_blockers"][0]       # the stale re-rating and audit key on these words


def test_python_and_backend_classification_versions_match():
    text = (ROOT / "backend/finlit/prism.py").read_text()
    assert int(re.search(r"^CLASSIFICATION_VERSION = (\d+)", text, re.M).group(1)) == CLASSIFICATION_VERSION
