"""Every FinEdge label must resolve to a model group, with defaulted=False for known businesses.

Root cause of the Bajaj Finserv 'Not rated' report: the classification text
('Finance' / 'Financial Services' / holding-company style labels) matched no rule, so the
group defaulted to MFG and the report was blocked as 'group could not be verified'.
"""
import pytest
from backend.premium_classification import resolve_group


def P(industry="", sector="", sub="", macro=""):
    return {"industry": industry, "sector": sector, "sub_industry": sub or sector, "macro_sector": macro}


FIN = "Financial Services"
CASES = [
    # the reported case and sibling financial labels
    (P("Finance", "Holding Companies", macro=FIN), "NBFC", False),
    (P("Finance", "Finance - Holding", macro=FIN), "NBFC", False),
    (P("Finance", "Financial Services", macro=FIN), "NBFC", False),
    (P("Financial Services"), "NBFC", False),
    (P("Finance"), "NBFC", False),
    (P("Diversified Financials", macro=FIN), "NBFC", False),
    (P("Finance", "Investment Companies", macro=FIN), "NBFC", False),
    (P("Finance", "Specialized Finance", macro=FIN), "NBFC", False),
    (P("Finance", "Consumer Finance", macro=FIN), "NBFC", False),
    (P("Finance", "Microfinance Institutions", macro=FIN), "NBFC", False),
    (P("Finance", "Housing Finance Company", macro=FIN), "NBFC", False),
    (P("Finance", "Infrastructure Finance", macro=FIN), "NBFC", False),
    (P("Finance", "Financial Institution", macro=FIN), "NBFC", False),
    (P("Finance", "Non Banking Financial Company (NBFC)", macro=FIN), "NBFC", False),
    (P("Finance", "Non-Banking Financial Company (NBFC)", macro=FIN), "NBFC", False),
    (P("Finance", "Gold Loan Finance", macro=FIN), "NBFC", False),
    # insurance first
    (P("Insurance", "Life Insurance", macro=FIN), "INSURANCE", False),
    (P("Insurance", "General Insurance", macro=FIN), "INSURANCE", False),
    (P("Finance", "Insurance Brokers", macro=FIN), "INSURANCE", False),
    # banks
    (P("Banks", "Private Sector Bank", macro=FIN), "BANK", False),
    (P("Banks", "Public Sector Bank", macro=FIN), "BANK", False),
    (P("Banks", "Small Finance Bank", macro=FIN), "BANK", False),
    (P("Banks", "Payments Bank", macro=FIN), "BANK", False),
    (P("Financial Services", "Banking", macro=FIN), "BANK", False),
    # asset-light financial services stay LIGHT
    (P("Finance", "Asset Management Company", macro=FIN), "LIGHT", False),
    (P("Finance", "Capital Markets", macro=FIN), "LIGHT", False),
    (P("Finance", "Stock Exchanges & Depositories", macro=FIN), "LIGHT", False),
    (P("Finance", "Stock Broking", macro=FIN), "LIGHT", False),
    (P("Finance", "Financial Technology (Fintech)", macro=FIN), "LIGHT", False),
    (P("Finance", "Rating Agency", macro=FIN), "LIGHT", False),
    # unchanged non-financial groups
    (P("Realty", "Real Estate"), "REALTY", False),
    (P("Power", "Power Generation"), "UTILITY", False),
    (P("Cement"), "HEAVY", False),
    (P("Metals & Mining", "Steel"), "HEAVY", False),
    (P("IT - Software", "Computers - Software & Consulting"), "LIGHT", False),
    (P("FMCG"), "LIGHT", False),
    (P("Automobiles", "Passenger Cars & Utility Vehicles"), "MFG", False),
    (P("Petroleum Products", "Refineries & Marketing", macro="Energy"), "HEAVY", False),
    # labels that used to fall through and be flagged
    (P("Trading", "Trading & Distributors"), "LIGHT", False),
    (P("Services", "Business Support Services"), "LIGHT", False),
    (P("Education", "Education Services"), "LIGHT", False),
    (P("Wholesale Trading"), "LIGHT", False),
    (P("Agriculture", "Agro Products"), "MFG", False),
    (P("Paper", "Paper & Paper Products"), "MFG", False),
    (P("Printing & Publication"), "MFG", False),
    (P("Plastic Products"), "MFG", False),
    (P("Packaging"), "MFG", False),
    (P("Shipping"), "MFG", False),
    (P("Airlines"), "MFG", False),
    (P("Sugar"), "MFG", False),
    (P("Tea & Coffee"), "MFG", False),
    (P("Fertilizers"), "MFG", False),
    (P("Fertilisers & Agrochemicals"), "MFG", False),
    (P("Gems & Jewellery"), "MFG", False),
    # genuinely unknown stays flagged
    (P("Zzyzx Widgets"), "MFG", True),
    (P(), "MFG", True),
]


@pytest.mark.parametrize("profile,group,defaulted", CASES, ids=lambda v: v if isinstance(v, str) else None)
def test_label_resolves(profile, group, defaulted):
    assert resolve_group(profile) == (group, defaulted)
