"""The initial model: indicator catalogue, sector master, sensitivity matrix, label map. INITIAL ASSUMPTIONS, NOT VALIDATED (the PRD says so too).
Written to the database once (ensure_seed, idempotent); from then on the database is the source of truth and the admin console edits it."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from .engine import DEFAULT_BANDS

MODEL_NOTE = "Initial assumptions, not validated: sensitivities, thresholds, K and signal scale are starting values to be calibrated and backtested."

GROUPS = [("inflation", "Inflation"), ("monetary", "Monetary Policy"), ("credit", "Credit & Banking"), ("growth", "Economic Growth"), ("currency", "Currency"), ("commodities", "Commodities")]

MOSPI, RBI, FBIL = ("MoSPI", "https://esankhyiki.mospi.gov.in"), ("RBI", "https://www.rbi.org.in"), ("RBI / FBIL", "https://www.fbil.org.in")
COMM = ("Commodity price snapshots (metals.dev / MetalpriceAPI via the commodity worker)", "https://www.finlitventures.com/commodities")


def thr(neutral: float, scale: float) -> Dict[str, Any]:
    return {"method": "threshold", "neutral": neutral, "scale": scale}


def mom(lookback: int, scale: float, method: str = "change") -> Dict[str, Any]:
    return {"method": method, "lookback_days": lookback, "scale": scale}


# code, name, group, unit, frequency, (source, url), stale_after_days, valid_min, valid_max, norm, note
INDICATORS: List[Tuple] = [
    ("CPI", "CPI inflation", "inflation", "%", "Monthly", MOSPI, 100, -5, 30, {"level": thr(4.0, 2.0), "momentum": mom(91, 1.0)}, "Reference 4% (the RBI's inflation reference), band 2-6%."),
    ("FOOD_CPI", "Food CPI inflation", "inflation", "%", "Monthly", MOSPI, 100, -30, 60, {"level": thr(4.0, 3.0), "momentum": mom(91, 2.0)}, "CPI food and beverages division."),
    ("WPI", "WPI inflation", "inflation", "%", "Monthly", MOSPI, 100, -20, 40, {"level": thr(2.5, 3.0), "momentum": mom(91, 1.5)}, "Wholesale prices, year on year."),
    ("REPO_RATE", "Repo rate", "monetary", "%", "On announcement", RBI, 120, 1, 15, {"level": thr(6.0, 1.5), "momentum": mom(182, 0.5)}, "Level against an assumed 6% reference; not an official neutral rate."),
    ("REPO_ACTION", "Policy rate change, 12 months", "monetary", "bp", "On announcement", RBI, 120, -600, 600, {"level": thr(0.0, 50.0), "momentum": {"method": "none"}},
     "Net change of the repo rate over the last 12 months: tightening is positive. Distinct from the repo-rate level."),
    ("BANK_CREDIT", "Bank credit growth", "credit", "%", "Fortnightly", RBI, 45, -20, 50, {"level": {"method": "hump", "neutral": 12.0, "scale": 4.0, "peak": 18.0, "fall": 6.0}, "momentum": mom(14, 2.0)},
     "Healthy up to about 18%; faster growth is read as overheating."),
    ("DEPOSIT_GROWTH", "Bank deposit growth", "credit", "%", "Fortnightly", RBI, 45, -20, 50, {"level": thr(10.0, 4.0), "momentum": mom(14, 2.0)}, "Funding availability for banks."),
    ("GDP", "GDP growth", "growth", "%", "Quarterly", ("NSO / MoSPI", MOSPI[1]), 200, -30, 30, {"level": thr(6.5, 1.5), "momentum": mom(91, 1.0)}, "Real GDP, year on year."),
    ("IIP", "Industrial production", "growth", "%", "Monthly", MOSPI, 100, -70, 100, {"level": thr(4.0, 3.0), "momentum": mom(91, 2.0)}, "IIP general index growth."),
    ("IIP_CAPITAL", "IIP: capital goods", "growth", "%", "Monthly", MOSPI, 100, -70, 100, {"level": thr(4.0, 6.0), "momentum": mom(91, 4.0)}, "Use-based group."),
    ("IIP_INFRA", "IIP: infrastructure goods", "growth", "%", "Monthly", MOSPI, 100, -70, 100, {"level": thr(4.0, 5.0), "momentum": mom(91, 3.0)}, "Infrastructure and construction goods."),
    ("IIP_DURABLES", "IIP: consumer durables", "growth", "%", "Monthly", MOSPI, 100, -70, 100, {"level": thr(4.0, 6.0), "momentum": mom(91, 4.0)}, "Use-based group."),
    ("IIP_NONDURABLES", "IIP: consumer non-durables", "growth", "%", "Monthly", MOSPI, 100, -70, 100, {"level": thr(3.0, 4.0), "momentum": mom(91, 3.0)}, "Use-based group."),
    ("UNEMPLOYMENT", "Unemployment rate", "growth", "%", "Monthly", ("PLFS / MoSPI", MOSPI[1]), 100, 0, 40, {"level": thr(5.0, 1.0), "momentum": mom(91, 0.5)}, "Persons 15+, current weekly status."),
    ("USDINR", "USD/INR", "currency", "₹", "Daily", FBIL, 10, 20, 250, {"level": {"method": "pct_vs_mean", "window_days": 365, "scale_pct": 3.0, "min_points": 3}, "momentum": mom(91, 3.0, "pct_change")},
     "A high reading is a weaker rupee."),
    ("BRENT", "Brent crude", "commodities", "$/bbl", "Daily", COMM, 10, 10, 250, {"level": {"method": "pct_vs_mean", "window_days": 365, "scale_pct": 15.0, "min_points": 20}, "momentum": mom(91, 15.0, "pct_change")}, "Needs a commodity-price key on the server."),
    ("COPPER", "Copper", "commodities", "$/t", "Daily", COMM, 10, 1000, 30000, {"level": {"method": "pct_vs_mean", "window_days": 365, "scale_pct": 12.0, "min_points": 20}, "momentum": mom(91, 12.0, "pct_change")}, "Needs a commodity-price key."),
    ("ALUMINIUM", "Aluminium", "commodities", "$/t", "Daily", COMM, 10, 500, 10000, {"level": {"method": "pct_vs_mean", "window_days": 365, "scale_pct": 12.0, "min_points": 20}, "momentum": mom(91, 12.0, "pct_change")}, "Needs a commodity-price key."),
    ("NATGAS", "Natural gas", "commodities", "$/mmBtu", "Daily", COMM, 10, 0.5, 40, {"level": {"method": "pct_vs_mean", "window_days": 365, "scale_pct": 25.0, "min_points": 20}, "momentum": mom(91, 25.0, "pct_change")}, "Needs a commodity-price key."),
]

# code, name, description
SECTORS: List[Tuple[str, str, str]] = [
    ("private_banks", "Private banks", "Private-sector banks"), ("psu_banks", "PSU banks", "Public-sector banks"), ("nbfc", "NBFCs", "Non-banking finance companies"),
    ("housing_finance", "Housing finance", "Housing finance companies"), ("insurance", "Insurance", "Life and general insurers"), ("real_estate", "Real estate", "Developers and realty"),
    ("autos", "Automobiles", "Vehicle makers"), ("auto_ancillaries", "Auto ancillaries", "Auto components and tyres"), ("fmcg", "FMCG", "Packaged consumer goods, food and beverages"),
    ("consumer_durables", "Consumer durables", "Appliances, electronics, furniture"), ("cement", "Cement", "Cement and building materials"), ("capital_goods", "Capital goods", "Machinery and electrical equipment"),
    ("infrastructure", "Infrastructure", "Construction and engineering"), ("metals_mining", "Metals & mining", "Steel, non-ferrous metals, mining"),
    ("specialty_chemicals", "Specialty chemicals", "Chemicals"), ("paints", "Paints", "Paints and coatings"), ("pharma", "Pharma", "Pharmaceuticals"), ("hospitals", "Hospitals", "Hospitals and diagnostics"),
    ("it_services", "IT services", "Software and IT services"), ("telecom", "Telecom", "Telecom services and equipment"), ("aviation", "Aviation", "Airlines and airports"),
    ("hotels_qsr", "Hotels & QSR", "Hotels, restaurants, leisure"), ("oil_marketing", "Oil marketing", "Refining and fuel marketing"), ("upstream_oil_gas", "Upstream oil & gas", "Exploration and production"),
    ("power_generation", "Power generation", "Thermal and hydro generation, utilities"), ("power_transmission", "Power transmission", "Transmission and distribution"),
    ("renewable_energy", "Renewable energy", "Solar, wind and green power"), ("agri_inputs", "Agri inputs", "Agrochemicals and seeds"), ("textiles", "Textiles", "Textiles and apparel"),
    ("logistics", "Logistics", "Transport, shipping and logistics"), ("media_entertainment", "Media & entertainment", "Media and entertainment"), ("paper", "Paper", "Paper and packaging"),
    ("sugar", "Sugar", "Sugar and ethanol"), ("fertilisers", "Fertilisers", "Fertiliser makers"), ("diversified", "Diversified", "Conglomerates with no single dominant business"),
]

# sector -> {indicator: (coefficient, weight, critical)}. Positive coefficient: the sector gains when the indicator is high or rising.
_M = {
    "private_banks": {"BANK_CREDIT": (.75, 2, 1), "DEPOSIT_GROWTH": (.5, 1.5, 0), "REPO_RATE": (-.25, 1, 0), "REPO_ACTION": (-.25, 1, 0), "GDP": (.5, 1, 0), "UNEMPLOYMENT": (-.25, .5, 0), "IIP": (.25, .5, 0)},
    "psu_banks": {"BANK_CREDIT": (.75, 2, 1), "DEPOSIT_GROWTH": (.5, 1.5, 0), "REPO_RATE": (-.25, 1, 0), "REPO_ACTION": (-.25, 1, 0), "GDP": (.5, 1, 0), "IIP_CAPITAL": (.25, .5, 0)},
    "nbfc": {"BANK_CREDIT": (.75, 2, 1), "REPO_RATE": (-.75, 2, 1), "REPO_ACTION": (-.5, 1.5, 0), "DEPOSIT_GROWTH": (.25, 1, 0), "GDP": (.5, 1, 0), "UNEMPLOYMENT": (-.25, .5, 0), "CPI": (-.25, .5, 0)},
    "housing_finance": {"BANK_CREDIT": (.75, 2, 1), "REPO_RATE": (-.75, 2, 1), "REPO_ACTION": (-.5, 1.5, 0), "GDP": (.25, 1, 0), "IIP_INFRA": (.25, .5, 0), "UNEMPLOYMENT": (-.25, .5, 0), "CPI": (-.25, .5, 0)},
    "insurance": {"GDP": (.5, 1.5, 1), "REPO_RATE": (.25, 1, 0), "CPI": (-.25, .5, 0), "UNEMPLOYMENT": (-.25, .5, 0), "DEPOSIT_GROWTH": (.25, .5, 0)},
    "real_estate": {"REPO_RATE": (-1, 2, 1), "REPO_ACTION": (-.75, 1.5, 0), "BANK_CREDIT": (.5, 1, 0), "WPI": (-.5, 1.5, 0), "IIP_INFRA": (.5, 1, 0), "GDP": (.5, 1, 0), "UNEMPLOYMENT": (-.25, .5, 0), "CPI": (-.25, .5, 0)},
    "autos": {"REPO_RATE": (-.5, 1.5, 0), "REPO_ACTION": (-.25, 1, 0), "BANK_CREDIT": (.5, 1.5, 1), "IIP_DURABLES": (.5, 1, 0), "GDP": (.75, 1.5, 1), "CPI": (-.5, 1, 0), "BRENT": (-.25, 1, 0), "UNEMPLOYMENT": (-.5, 1, 0), "ALUMINIUM": (-.25, .5, 0), "COPPER": (-.25, .5, 0)},
    "auto_ancillaries": {"IIP": (.5, 1.5, 0), "GDP": (.5, 1, 0), "BANK_CREDIT": (.25, .5, 0), "REPO_RATE": (-.25, .5, 0), "ALUMINIUM": (-.25, 1, 0), "COPPER": (-.25, 1, 0), "WPI": (-.5, 1, 0)},
    "fmcg": {"FOOD_CPI": (-.75, 2, 1), "WPI": (-.5, 1.5, 0), "CPI": (-.5, 1, 0), "IIP_NONDURABLES": (.5, 1.5, 1), "GDP": (.5, 1, 0), "UNEMPLOYMENT": (-.5, 1, 0), "BRENT": (-.25, .5, 0), "USDINR": (-.25, .5, 0)},
    "consumer_durables": {"BANK_CREDIT": (.5, 1, 0), "REPO_RATE": (-.5, 1, 0), "IIP_DURABLES": (.75, 1.5, 1), "GDP": (.5, 1, 0), "CPI": (-.5, 1, 0), "COPPER": (-.5, 1, 0), "ALUMINIUM": (-.5, 1, 0), "USDINR": (-.25, .5, 0), "UNEMPLOYMENT": (-.5, 1, 0)},
    "cement": {"IIP_INFRA": (.75, 2, 1), "GDP": (.5, 1, 0), "BRENT": (-.5, 1.5, 0), "REPO_RATE": (-.5, 1, 0), "BANK_CREDIT": (.25, .5, 0), "WPI": (-.25, 1, 0), "REPO_ACTION": (-.25, .5, 0)},
    "capital_goods": {"IIP_CAPITAL": (.75, 2, 1), "IIP": (.5, 1, 0), "BANK_CREDIT": (.5, 1, 0), "REPO_RATE": (-.5, 1, 0), "GDP": (.5, 1, 0), "COPPER": (-.25, .5, 0), "ALUMINIUM": (-.25, .5, 0)},
    "infrastructure": {"IIP_INFRA": (.75, 2, 1), "GDP": (.5, 1, 0), "REPO_RATE": (-.5, 1.5, 0), "BANK_CREDIT": (.5, 1, 0), "REPO_ACTION": (-.25, .5, 0), "WPI": (-.5, 1, 0)},
    "metals_mining": {"IIP": (.5, 1, 0), "IIP_INFRA": (.5, 1.5, 1), "COPPER": (.75, 2, 0), "ALUMINIUM": (.5, 1.5, 0), "GDP": (.5, 1, 0), "BRENT": (-.25, .5, 0), "USDINR": (.25, .5, 0), "REPO_RATE": (-.25, .5, 0)},
    "specialty_chemicals": {"IIP": (.5, 1, 0), "GDP": (.5, 1, 0), "BRENT": (-.5, 1.5, 0), "NATGAS": (-.25, .5, 0), "USDINR": (.25, 1, 0), "WPI": (-.25, 1, 0)},
    "paints": {"BRENT": (-.75, 2, 1), "WPI": (-.5, 1.5, 0), "GDP": (.5, 1, 0), "BANK_CREDIT": (.25, .5, 0), "REPO_RATE": (-.25, .5, 0), "USDINR": (-.25, .5, 0), "IIP_DURABLES": (.25, .5, 0)},
    "pharma": {"USDINR": (.5, 1.5, 0), "GDP": (.25, 1, 0), "WPI": (-.25, 1, 0), "BRENT": (-.25, .5, 0), "IIP": (.25, .5, 0), "CPI": (-.25, .5, 0)},
    "hospitals": {"GDP": (.5, 1.5, 0), "UNEMPLOYMENT": (-.25, .5, 0), "CPI": (-.25, 1, 0), "REPO_RATE": (-.25, .5, 0), "FOOD_CPI": (-.25, .5, 0)},
    "it_services": {"USDINR": (.75, 2, 1), "GDP": (.25, 1, 0), "CPI": (-.25, .5, 0), "UNEMPLOYMENT": (-.25, .5, 0)},
    "telecom": {"GDP": (.5, 1, 0), "CPI": (-.25, .5, 0), "UNEMPLOYMENT": (-.25, .5, 0), "USDINR": (-.25, .5, 0), "REPO_RATE": (-.25, .5, 0)},
    "aviation": {"BRENT": (-1, 2, 1), "USDINR": (-.75, 2, 1), "GDP": (.5, 1.5, 0), "CPI": (-.25, .5, 0), "UNEMPLOYMENT": (-.25, .5, 0), "REPO_RATE": (-.25, .5, 0)},
    "hotels_qsr": {"GDP": (.75, 1.5, 0), "FOOD_CPI": (-.5, 1.5, 0), "UNEMPLOYMENT": (-.5, 1, 0), "CPI": (-.25, .5, 0), "BANK_CREDIT": (.25, .5, 0), "IIP_NONDURABLES": (.25, .5, 0)},
    "oil_marketing": {"BRENT": (-.5, 2, 1), "USDINR": (-.5, 1, 0), "GDP": (.5, 1, 0), "IIP": (.25, .5, 0)},
    "upstream_oil_gas": {"BRENT": (1, 2, 1), "NATGAS": (.5, 1, 0), "USDINR": (.5, 1, 0), "GDP": (.25, .5, 0)},
    "power_generation": {"IIP": (.5, 1.5, 0), "GDP": (.5, 1, 0), "NATGAS": (-.25, .5, 0), "REPO_RATE": (-.5, 1, 0), "REPO_ACTION": (-.25, .5, 0), "BANK_CREDIT": (.25, .5, 0)},
    "power_transmission": {"REPO_RATE": (-.5, 1, 0), "GDP": (.5, 1, 0), "IIP_CAPITAL": (.5, 1, 0), "IIP_INFRA": (.5, 1, 0), "REPO_ACTION": (-.25, .5, 0), "COPPER": (-.25, .5, 0)},
    "renewable_energy": {"REPO_RATE": (-.75, 2, 1), "REPO_ACTION": (-.5, 1.5, 0), "BRENT": (.25, .5, 0), "GDP": (.5, 1, 0), "ALUMINIUM": (-.25, .5, 0), "COPPER": (-.25, .5, 0), "BANK_CREDIT": (.25, .5, 0)},
    "agri_inputs": {"FOOD_CPI": (.5, 1.5, 0), "GDP": (.5, 1, 0), "NATGAS": (-.5, 1, 0), "BRENT": (-.25, .5, 0), "USDINR": (-.25, .5, 0), "WPI": (-.25, .5, 0)},
    "textiles": {"USDINR": (.5, 1.5, 0), "BRENT": (-.25, 1, 0), "GDP": (.5, 1, 0), "WPI": (-.25, 1, 0), "IIP_NONDURABLES": (.5, 1, 0), "UNEMPLOYMENT": (-.25, .5, 0)},
    "logistics": {"BRENT": (-.5, 1.5, 0), "IIP": (.75, 2, 1), "GDP": (.5, 1, 0), "REPO_RATE": (-.25, .5, 0), "IIP_INFRA": (.25, .5, 0), "USDINR": (-.25, .5, 0)},
    "media_entertainment": {"GDP": (.5, 1, 0), "CPI": (-.5, 1, 0), "UNEMPLOYMENT": (-.5, 1, 0), "FOOD_CPI": (-.25, .5, 0), "IIP_NONDURABLES": (.25, .5, 0), "USDINR": (-.25, .5, 0)},
    "paper": {"WPI": (-.5, 1, 0), "BRENT": (-.25, .5, 0), "NATGAS": (-.25, .5, 0), "IIP": (.5, 1, 0), "GDP": (.5, 1, 0), "USDINR": (-.25, .5, 0)},
    "sugar": {"FOOD_CPI": (.5, 1, 0), "BRENT": (.5, 1.5, 0), "WPI": (.25, .5, 0), "GDP": (.25, .5, 0), "REPO_RATE": (-.25, .5, 0)},
    "fertilisers": {"NATGAS": (-.75, 2, 1), "FOOD_CPI": (.25, .5, 0), "USDINR": (-.5, 1, 0), "BRENT": (-.25, .5, 0), "GDP": (.25, .5, 0), "REPO_RATE": (-.25, .5, 0), "WPI": (-.25, .5, 0)},
    "diversified": {"GDP": (.5, 2, 0), "IIP": (.5, 1, 0), "CPI": (-.25, 1, 0), "REPO_RATE": (-.25, 1, 0), "BANK_CREDIT": (.25, .5, 0), "USDINR": (0.25, .5, 0)},
}


def sensitivity_rows() -> List[Tuple[str, str, float, float, bool]]:
    return [(s, i, c, w, bool(k)) for s, d in _M.items() for i, (c, w, k) in d.items()]


# Label map rules: (kind, match, pattern, sector, priority, note). Patterns are compared in lower case with "&" read as "and" and punctuation removed (presets.industry.key).
def _exact(kind: str, sector: str, *labels: str, p: int = 10) -> List[Tuple]:
    return [(kind, "exact", l, sector, p, "NSE/exchange label") for l in labels]


def _has(kind: str, sector: str, *words: str, p: int = 60) -> List[Tuple]:
    return [(kind, "contains", w, sector, p, "wording rule") for w in words]


LABEL_RULES: List[Tuple] = [
    # named symbols: the public-sector banks share the generic "Banks" label with private ones
    *[("symbol", "exact", s, "psu_banks", 1, "public-sector bank") for s in
      ("SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK", "INDIANB", "BANKINDIA", "MAHABANK", "IOB", "CENTRALBK", "UCOBANK", "PSB")],
    *_exact("sector", "private_banks", "private sector bank", "banks", p=20), *_exact("sector", "psu_banks", "public sector bank"),
    *_exact("sector", "nbfc", "non banking financial company nbfc", "financial services", "other financial services", "investment company", "financial institution", "microfinance", "finance", p=40),
    *_exact("sector", "housing_finance", "housing finance company"),
    *_exact("sector", "insurance", "life insurance", "general insurance", "insurance", "other insurance companies"),
    *_exact("sector", "real_estate", "residential commercial projects", "real estate", "realty", "real estate related services", "property"),
    *_exact("sector", "autos", "passenger cars and utility vehicles", "2 3 wheelers", "commercial vehicles", "tractors", "automobiles", "automobile", "automobiles two and three wheelers", "automobiles passenger cars"),
    *_exact("sector", "auto_ancillaries", "auto components and equipments", "tyres and rubber products", "auto ancillary", "auto ancillaries", "auto components", "castings and forgings", "bearings", "batteries"),
    *_exact("sector", "fmcg", "fmcg", "personal care", "packaged foods", "edible oil", "tea and coffee", "breweries and distilleries", "cigarettes tobacco products", "household products", "dairy products",
            "other food products", "other beverages", "consumer food", "sugar and confectionery", "spirits", "stationary", "diversified fmcg", "agricultural food and other products", "tobacco products"),
    *_exact("sector", "consumer_durables", "consumer electronics", "household appliances", "air conditioners", "electronics", "cables electricals", "furniture home furnishing", "plastic products consumer",
            "jewellery", "watches and accessories", "footwear", "leather", "consumer durables", "diversified consumer durables"),
    *_exact("sector", "cement", "cement and cement products", "cement", "cement major", "cement mini", "ceramics", "tiles", "building products", "building materials"),
    *_exact("sector", "capital_goods", "industrial products", "heavy electrical equipment", "other electrical equipment", "compressors pumps and diesel engines", "industrial machinery", "capital goods", "industrial gases and fuels",
            "defence", "aerospace and defense", "ship building and allied services", "abrasives and bearings", "electrical equipment", "other industrial products", "railway wagons", "engineering", "castings"),
    *_exact("sector", "infrastructure", "civil construction", "construction", "infrastructure", "infrastructure developers and operators", "infrastructure support services", "ports", "roads and highways", "airport services", "engineering and construction"),
    *_exact("sector", "metals_mining", "iron and steel", "pig iron", "sponge iron", "iron and steel products", "aluminium", "aluminium and aluminium products", "copper", "zinc", "other non ferrous metals", "ferro and silica manganese",
            "industrial minerals", "diversified metals", "coal", "minerals and mining", "metals and mining", "steel", "mining", "mining and minerals", "other metals and minerals"),
    *_exact("sector", "specialty_chemicals", "specialty chemicals", "commodity chemicals", "dyes and pigments", "carbon black", "chemicals", "other chemical products", "petrochemicals", "explosives", "industrial chemicals", "chemicals and petrochemicals"),
    *_exact("sector", "paints", "paints"),
    *_exact("sector", "pharma", "pharmaceuticals", "pharmaceuticals and drugs", "biotechnology", "drug and drug intermediaries", "pharma", "healthcare", "bulk drugs"),
    *_exact("sector", "hospitals", "hospital", "hospitals", "healthcare services", "diagnostics", "healthcare facilities", "medical equipment and supplies"),
    *_exact("sector", "it_services", "computers software and consulting", "it enabled services", "software products", "it services and consulting", "information technology", "it software", "it consulting and software", "computers hardware and equipments",
            "business process outsourcing", "data processing services", "software"),
    *_exact("sector", "telecom", "telecom services", "telecom equipment and accessories", "telecom infrastructure", "telecommunications", "telecom cellular and fixed line services", "telecom", "cable and satellite"),
    *_exact("sector", "aviation", "airline", "airlines", "aviation", "air transport"),
    *_exact("sector", "hotels_qsr", "hotels and resorts", "restaurants", "leisure services", "tour travel related services", "hotels", "hotels and restaurants", "tourism", "quick service restaurants", "amusement parks"),
    *_exact("sector", "oil_marketing", "refineries and marketing", "petroleum products", "oil marketing and distribution", "refineries", "oil and gas marketing", "lubricants"),
    *_exact("sector", "upstream_oil_gas", "oil exploration and production", "oil and gas exploration", "exploration and production", "oil drilling and exploration", "oil and gas equipment", "oil equipment and services", "oil"),
    *_exact("sector", "power_generation", "power generation", "electric utilities", "power generation and distribution", "power", "thermal power", "independent power producers", "power generation and supply", "utilities", "coal based power"),
    *_exact("sector", "power_transmission", "transmission", "power transmission", "power distribution", "power trading", "transmission and distribution", "transmission line towers", "gas distribution", "gas transmission marketing", "gas utilities"),
    *_exact("sector", "renewable_energy", "renewable energy", "solar power", "wind power", "renewable energy equipment and services", "power renewable", "green energy"),
    *_exact("sector", "agri_inputs", "pesticides and agrochemicals", "agrochemicals", "seeds", "agricultural inputs", "plant protection", "agriculture", "other agricultural products", "plantation and plantation products", "floriculture"),
    *_exact("sector", "textiles", "textiles", "garments and apparels", "other textile products", "cotton and blended yarn", "readymade garments apparel", "textile spinning", "textile weaving", "home textiles", "fabrics and garments", "synthetic fibres", "textile products", "diversified textiles"),
    *_exact("sector", "logistics", "logistics solution provider", "transport services", "shipping", "transport related services", "courier services", "logistics", "road transport", "railways", "port and port services", "marine port and services", "cargo handling", "container"),
    *_exact("sector", "media_entertainment", "media and entertainment", "broadcasting and cable tv", "film production distribution and entertainment", "print media", "digital entertainment", "media", "publishing", "radio", "advertising and media agencies", "tv broadcasting"),
    *_exact("sector", "paper", "paper and paper products", "paper", "paper forest and jute products", "packaging", "printing and stationery", "forest products", "paper packaging", "printing and publishing"),
    *_exact("sector", "sugar", "sugar", "sugar and ethanol"),
    *_exact("sector", "fertilisers", "fertilizers", "fertilisers", "fertilizers and agrochemicals", "fertilizers and pesticides", "nitrogenous fertilizers", "phosphatic fertilizers", "other fertilizers"),
    *_exact("sector", "diversified", "diversified", "trading and distributors", "diversified commercial services", "conglomerates", "trading", "commercial services and supplies", "trading and distribution", "multi sector"),
    # wording rules on either label, used when no exact rule matched
    *_has("sector", "psu_banks", "public sector bank"), *_has("sector", "private_banks", "bank"),
    *_has("sector", "housing_finance", "housing finance"), *_has("sector", "nbfc", "nbfc", "non banking", "finance"), *_has("sector", "insurance", "insurance"),
    *_has("sector", "real_estate", "realty", "real estate"), *_has("sector", "autos", "automobile", "vehicle"), *_has("sector", "pharma", "pharma"),
    *_has("sector", "cement", "cement"), *_has("sector", "metals_mining", "steel", "alumin", "mining"), *_has("sector", "specialty_chemicals", "chemical"),
    *_has("sector", "it_services", "software", "it services"), *_has("sector", "textiles", "textile", "apparel", "garment"), *_has("sector", "hospitals", "hospital"),
    *_has("sector", "fertilisers", "fertili"), *_has("sector", "power_generation", "power"), *_has("sector", "hotels_qsr", "hotel", "restaurant"),
    *_has("sector", "agri_inputs", "agro", "pesticide", "seed"), *_has("sector", "media_entertainment", "media", "entertainment", "broadcast"), *_has("sector", "logistics", "logistic", "shipping", "transport"),
    *_has("sector", "paper", "paper"), *_has("sector", "sugar", "sugar"), *_has("sector", "telecom", "telecom"), *_has("sector", "aviation", "airline", "aviation"),
    *_has("sector", "renewable_energy", "solar", "wind energy", "renewable"), *_has("sector", "capital_goods", "capital goods", "machinery", "electrical equipment"),
    *_has("sector", "infrastructure", "construction", "infrastructure"), *_has("sector", "consumer_durables", "consumer durable", "appliance"),
    *_has("sector", "fmcg", "fmcg", "food", "beverage"), *_has("sector", "upstream_oil_gas", "exploration"), *_has("sector", "oil_marketing", "refiner", "petroleum"),
    # revenue segments of diversified companies (only these reliably name a covered sector; others stay unmapped and are left out of the weights)
    *[("segment", "contains", p, s, 50, "segment wording") for p, s in (
        ("oil to chemicals", "oil_marketing"), ("refining", "oil_marketing"), ("petroleum", "oil_marketing"), ("oil and gas", "upstream_oil_gas"), ("exploration", "upstream_oil_gas"),
        ("digital services", "telecom"), ("telecom", "telecom"), ("cement", "cement"), ("steel", "metals_mining"), ("aluminium", "metals_mining"), ("copper", "metals_mining"),
        ("pharma", "pharma"), ("hospital", "hospitals"), ("insurance", "insurance"), ("real estate", "real_estate"), ("realty", "real_estate"), ("automotive", "autos"), ("vehicles", "autos"),
        ("fmcg", "fmcg"), ("hotels", "hotels_qsr"), ("paints", "paints"), ("fertili", "fertilisers"), ("sugar", "sugar"), ("power", "power_generation"), ("software", "it_services"),
        ("it services", "it_services"), ("media", "media_entertainment"), ("textile", "textiles"), ("logistics", "logistics"), ("paper", "paper"), ("renewable", "renewable_energy"),
        ("chemical", "specialty_chemicals"), ("banking", "private_banks"), ("airline", "aviation"), ("aviation", "aviation"), ("agri", "agri_inputs"))],
]


def default_config() -> Dict[str, Any]:
    return {"k": 3, "signal_scale": 5, "min_coverage": 0.70, "stale_after_hours": 48, "bands": [{"min": m, "label": l} for m, l in DEFAULT_BANDS]}


def indicator_settings() -> Dict[str, Any]:
    """The per-indicator model settings frozen into each model version."""
    return {code: {"norm": norm, "stale_after_days": stale, "priority": 10 + i * 5, "active": True, "valid_min": lo, "valid_max": hi}
            for i, (code, _n, _g, _u, _f, _s, stale, lo, hi, norm, _note) in enumerate(INDICATORS)}


async def ensure_seed(conn) -> bool:
    """Write the initial model when the database has none. Idempotent; returns True when it wrote anything. Never touches an existing model."""
    wrote = False
    for i, (code, name, grp, unit, freq, (src, url), stale, lo, hi, norm, note) in enumerate(INDICATORS):
        r = await conn.execute(
            "INSERT INTO macro_indicator_defs (indicator_code, name, group_code, unit, frequency, source_name, source_url, sort_order, priority, stale_after_days, valid_min, valid_max, norm, reading_note) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14) ON CONFLICT (indicator_code) DO NOTHING",
            code, name, grp, unit, freq, src, url, (i + 1) * 10, 10 + i * 5, stale, lo, hi, json.dumps(norm), note)
        wrote = wrote or r.endswith(" 1")
    for i, (code, name, desc) in enumerate(SECTORS):
        r = await conn.execute("INSERT INTO sector_master (sector_code, name, description, sort_order) VALUES ($1,$2,$3,$4) ON CONFLICT (sector_code) DO NOTHING", code, name, desc, (i + 1) * 10)
        wrote = wrote or r.endswith(" 1")
    for kind, match, pattern, sector, prio, note in LABEL_RULES:
        await conn.execute("INSERT INTO macro_label_map (label_kind, match_type, pattern, sector_code, priority, note) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING", kind, match, pattern, sector, prio, note)
    if await conn.fetchval("SELECT count(*) FROM macro_model_configuration") == 0:
        c = default_config()
        async with conn.transaction():
            await conn.execute("INSERT INTO macro_model_configuration (model_version, k, signal_scale, min_coverage, stale_after_hours, bands, indicators, active, change_note, created_by) "
                               "VALUES (1,$1,$2,$3,$4,$5::jsonb,$6::jsonb,true,$7,'system')", c["k"], c["signal_scale"], c["min_coverage"], c["stale_after_hours"], json.dumps(c["bands"]),
                               json.dumps(indicator_settings()), "Initial model. " + MODEL_NOTE)
            ids = {r["sector_code"]: r["id"] for r in await conn.fetch("SELECT id, sector_code FROM sector_master")}
            methods = {t[0]: (t[9].get("level") or {}).get("method", "") for t in INDICATORS}
            await conn.executemany("INSERT INTO sector_sensitivity (model_version, sector_id, indicator_code, coefficient, weight, critical, normalisation_method) VALUES (1,$1,$2,$3,$4,$5,$6)",
                                   [(ids[s], i, c_, w, k, methods.get(i, "")) for s, i, c_, w, k in sensitivity_rows()])
            await conn.execute("INSERT INTO macro_audit_log (actor, action, entity, entity_key, new_value, model_version, note) VALUES ('system','seed','model','1',$1::jsonb,1,$2)",
                               json.dumps(default_config()), MODEL_NOTE)
        wrote = True
    return wrote
