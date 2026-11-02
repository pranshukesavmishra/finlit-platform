"""NSE's industry classification and the groups the sector engine reads.

NSE classifies every listed company on four levels: Macro-economic Sector > Sector > Industry > Basic Industry
(for example Commodities > Metals & Mining > Ferrous Metals > Iron & Steel). The sector engine uses the Industry
level. An industry with fewer than 10 stocks in the universe today is read together with the other small industries
of its NSE Sector (for example Oil + Gas + Consumable Fuels as "Oil Gas & Consumable Fuels").

data/nse_industries.json holds the classification of every stock listed on 29 Oct 2026 and of the stocks traded
since 2016 that have since been delisted (pre-2023 labels mapped to the current names). New listings come from
<nse folder>/ref/industries_extra.json, which `fetch-nse --industries` fills when NSE's site answers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

DATA = Path(__file__).resolve().parent / "data" / "nse_industries.json"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_industries(extra: Optional[str | Path] = None) -> Dict[str, Tuple[str, str]]:
    """symbol -> (industry, sector)."""
    d = json.loads(DATA.read_text())
    out = {k: (v[0], v[1]) for k, v in d["stocks"].items()}
    if extra and Path(extra).exists():
        try:
            for k, v in json.loads(Path(extra).read_text()).get("stocks", {}).items():
                out[k] = (v[0], v[1])
        except (ValueError, KeyError, IndexError):
            pass
    return out


def build_groups(keys, members_now, cls: Dict[str, Tuple[str, str]], min_members: int = 10):
    """Groups over every classified stock (history included): {name: [column, ...]} and
    {name: {"kind": "industry"|"sector", "industries": [...], "sector": ...}}.
    `members_now` is a boolean per key: in the universe on the latest day."""
    count: Dict[str, int] = {}
    for k, m in zip(keys, members_now):
        if m and k in cls:
            count[cls[k][0]] = count.get(cls[k][0], 0) + 1
    big = {i for i, n in count.items() if n >= min_members}
    groups: Dict[str, list] = {}
    meta: Dict[str, dict] = {}
    for j, k in enumerate(keys):
        if k not in cls:
            continue
        ind, sec = cls[k]
        name, kind = (ind, "industry") if ind in big else (sec, "sector")
        if name in big and kind == "sector":           # a sector named like a big industry
            name = sec + " (other)"
        groups.setdefault(name, []).append(j)
        m = meta.setdefault(name, {"kind": kind, "industries": set(), "sector": sec})
        m["industries"].add(ind)
    return groups, {g: {"kind": m["kind"], "industries": sorted(m["industries"]), "sector": m["sector"]}
                    for g, m in meta.items()}
