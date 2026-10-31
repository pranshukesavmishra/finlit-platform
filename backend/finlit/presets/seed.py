"""The research team's seed list for the "Emerging tech" screen (spec p8-9): sub-theme -> symbols. The single source: migration 078 carries a copy
(tests compare the two), and the nightly job tops the table up from here once a missing listing has been mapped into `companies`."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

THEME = "Emerging tech"

SEED: Dict[str, List[str]] = {
    "EMS and electronics": ["DIXON", "KAYNES", "SYRMA", "AMBER", "AVALON", "CYIENTDLM", "CENTUM", "PGEL", "ELIN", "OPTIEMUS"],
    "Semiconductors": ["MOSCHIP", "CGPOWER"],
    "Defence tech and drones": ["BEL", "DATAPATTNS", "ASTRAMICRO", "ZENTEC", "PARAS", "IDEAFORGE", "MTARTECH"],
    "Data centres and cloud": ["NETWEB", "E2E", "ANANTRAJ", "RAILTEL", "TATACOMM"],
    "AI, data and software products": ["TATAELXSI", "KPITTECH", "PERSISTENT", "COFORGE", "LATENTVIEW", "HAPPSTMNDS", "AFFLE", "TANLA", "NEWGEN", "INTELLECT",
                                       "RATEGAIN", "ZAGGLE", "ROUTE"],
    "Digital platforms": ["ETERNAL", "SWIGGY", "NYKAA", "NAUKRI", "INDIAMART", "JUSTDIAL", "CARTRADE", "FIRSTCRY", "MEESHO", "LENSKART", "URBANCO", "IXIGO",
                          "EASEMYTRIP", "NAZARA", "TBOTEK", "DELHIVERY", "BLACKBUCK"],
    "Fintech and market infrastructure": ["PAYTM", "POLICYBZR", "BSE", "MCX", "CDSL", "CAMS", "KFINTECH", "ANGELONE", "GODIGIT"],
    "EV and batteries": ["ATHERENERG", "OLAELEC", "OLECTRA", "JBMA", "GREAVESCOT", "SONACOMS", "EXIDEIND", "ARE&M", "HBLENGINE"],
    "Solar and clean-energy manufacturing": ["WAAREEENER", "PREMIERENE", "WEBELSOLAR", "INOXWIND", "SUZLON", "KPIGREEN"],
    "Telecom tech (5G, fibre)": ["STLTECH", "HFCL", "TEJASNET", "ITI", "VINDHYATEL"],
}

# Named on spec p9 as missing from the data ("add once their listings are mapped"). Loaded the night they appear in `companies`.
PENDING: Dict[str, List[str]] = {
    "Data centres and cloud": ["SIFY"],
    "Semiconductors": ["SPEL"],
    "EMS and electronics": ["ASMTEC"],
    "Digital platforms": ["CEINFO"],       # MapmyIndia
}
# Amara Raja's old symbol: used only while `companies` still lists it and not the current one.
ALIASES: Dict[str, List[str]] = {"ARE&M": ["AMARAJABAT"]}


def pairs(include_pending: bool = True) -> List[Tuple[str, str]]:
    """(symbol, sub_theme) for every seed company, in a stable order."""
    out = [(s, sub) for sub, syms in SEED.items() for s in syms]
    if include_pending:
        out += [(s, sub) for sub, syms in PENDING.items() for s in syms]
    return out


def slug(sub_theme: str) -> str:
    """The chip id of a sub-theme (the spec's `&sub=ems` is the frontend's short form of it)."""
    return re.sub(r"[^a-z0-9]+", "-", sub_theme.lower()).strip("-")
