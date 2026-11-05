"""The Emerging tech theme map (redesign pdf, "Emerging tech: defence and shipbuilding"). A company joins a sub-theme by its Sector label automatically; a short named list
adds companies whose label is a generic parent ("Capital Goods", "Financial Services", "Information Technology"), and a short exclusion list removes the odd one out.
The sub-theme is shown as a column on the screen, so the theme is tab data. The research team reviews the named lists every quarter. Pure: no database.
The universe of a sub-theme is the UNION of the two: every company whose Sector label is listed, plus the named additions (the companies the spec names are also written in by symbol, so a label spelled differently in the data cannot drop them).
The label is the company's own Sector label, never the broad macro sector ("Industrials", "Consumer Discretionary"): `Table.sector_label`.
Three sub-themes have no clean Sector label and run on named lists only until the Sector field carries basic industries for every company."""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .industry import key

THEME = "Emerging tech"

# sub-theme -> (Sector labels that join it, named additions, named exclusions)
SUBTHEMES: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]] = {
    "Defence, aerospace and shipbuilding": (("Aerospace & Defense", "Aerospace & Defence", "Ship Building & Allied Services", "Shipbuilding", "Explosives"), ("SWANDEF", "KRISHNADEF", "AVANTEL", "NIBE", "SIKA", "BEML", "HAL", "BEL", "SOLARINDS", "MAZDOCK", "GRSE", "DATAPATTNS", "MTARTECH", "ASTRAMICRO", "PARAS"), ()),
    "Electronics, EMS and semiconductors": (("Consumer Electronics", "Computers Hardware & Equipments", "Telecom - Equipment & Accessories"),
                                            ("KAYNES", "SYRMA", "CYIENTDLM", "AMBER", "AVALON", "MOSCHIP", "CGPOWER", "DIXON"), ("HAVELLS",)),
    "Software products, AI and data": (("Software Products", "Data Processing Services"), ("PERSISTENT", "KPITTECH", "COFORGE", "NEWGEN", "RATEGAIN", "HAPPSTMNDS", "LATENTVIEW", "AFFLE"), ()),
    "Digital platforms": (("E-Retail/ E-Commerce", "Internet & Catalogue Retail", "Digital Entertainment", "E-Learning", "Web based media and service"), ("TBOTEK", "IXIGO", "LENSKART", "BLACKBUCK", "ETERNAL", "NYKAA", "NAUKRI"), ()),
    "Fintech and market infrastructure": (("Financial Technology (Fintech)", "Exchange and Data Platform", "Depositories, Clearing Houses and Other Intermediaries"), ("MCX", "BSE", "CDSL", "CAMS", "KFINTECH", "IEX"), ()),
    "Data centres, cloud and telecom tech": ((), ("NETWEB", "RAILTEL", "E2E", "HFCL", "STLTECH"), ()),
    "EV and batteries": ((), ("OLECTRA", "SONACOMS", "HBLENGINE", "ARE&M", "ATHERENERG", "GREAVESCOT"), ()),
    "Clean-energy manufacturing": ((), ("WAAREEENER", "PREMIERENE", "SUZLON", "INOXWIND", "KPIGREEN"), ()),
}
# a company whose symbol changed: the old symbol still counts while only it is listed
ALIASES: Dict[str, Tuple[str, ...]] = {"ARE&M": ("AMARAJABAT",)}


def subthemes() -> List[str]:
    return list(SUBTHEMES)


def tags_for(symbols: Sequence[str], sectors: Sequence[Optional[str]]) -> Dict[str, List[str]]:
    """symbol -> sub-themes, from the Sector label and the named lists, in the map's order. A company in no sub-theme is absent."""
    present = set(symbols)
    out: Dict[str, List[str]] = {}
    for sub, (labels, add, drop) in SUBTHEMES.items():
        want = {key(x) for x in labels}
        named = set()
        for a in add:
            named.add(a if a in present else next((x for x in ALIASES.get(a, ()) if x in present), a))
        for sym, sec in zip(symbols, sectors):
            if sym in drop:
                continue
            if sym in named or (sec and key(sec) in want):
                out.setdefault(sym, []).append(sub)
    return out


def unmatched_labels(sectors: Sequence[Optional[str]]) -> List[str]:
    """Sector labels written in SUBTHEMES that no company carries today: a spelling that differs from the data (reported by the nightly job so it is seen at once)."""
    have = {key(x) for x in sectors if x}
    return sorted({lab for labels, _, _ in SUBTHEMES.values() for lab in labels if key(lab) not in have})
