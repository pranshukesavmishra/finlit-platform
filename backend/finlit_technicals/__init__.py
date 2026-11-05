"""FinLit technicals: the TradingView indicators "ST/LT Score Breakdown & Peers v1.2", "Leader & Laggard vs
Peers v1.0" and "Sector & Leaders v2.0" in Python, for the website. Needs numpy, pandas and openpyxl.

    from finlit_technicals import score, peer_label, CsvFolder
    src = CsvFolder("prices")                       # or your own source with daily() and index()
    score("SAMBHV", src, cap="small")               # -> dict, ready for json.dumps
    peer_label("SAMBHV", src, cap="small")          # -> dict
    nse = NseHistory("nse")                         # NSE's own daily files (python -m finlit_technicals fetch-nse --dir nse)
    eng = SectorEngine(nse)                         # sector breadth by NSE industry: eng.board(), eng.industry("Ferrous Metals"), eng.stock("SAMBHV")
    stress.run(stress.company_from_pack(pack), stress.PRESETS["2022"])   # Stress Lab: macro shock -> revenue, EBITDA, EPS
    ownership.analyse(ownership.pack_from_site(own_json, premium_json))  # ownership insights for any stock
    rotation.Rotation(eng).view()                   # sector rotation: corners, ranking and rank changes by NSE group
"""
from .api import canonical, jsonable, peer_dict, peer_label, score, score_dict
from .industries import load_industries
from .nse import NseHistory
from .sectors import SectorEngine, SectorParams, industry_view, sector_board, stock_sector
from .universe import UniverseRules
from .sources import INDICES, Cached, CsvFolder, MemorySource, PriceSource
from .stlt import StltParams
from . import company_brief, ownership, rotation, stress

__version__ = "2.4.1"
__all__ = ["score", "peer_label", "score_dict", "peer_dict", "canonical", "jsonable", "CsvFolder", "MemorySource",
           "Cached", "PriceSource", "INDICES", "StltParams", "SectorEngine", "SectorParams", "sector_board",
           "industry_view", "stock_sector", "NseHistory", "UniverseRules", "load_industries", "stress", "ownership", "rotation", "__version__"]
