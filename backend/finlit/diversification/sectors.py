"""Macro-sector mapping and business-group tag for the Diversification card. Both are data files (finlit/diversification/data/*.json) that the owner
can edit without a code change. A label with no rule goes to the named bucket 'Not classified' and is reported, never dropped."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DATA = Path(__file__).parent / "data"


def key(name: Optional[str]) -> str:
    """Comparison key: lower case, '&' read as 'and', punctuation and extra spaces gone (same rule as finlit.presets.industry.key)."""
    s = (name or "").lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


@lru_cache(maxsize=1)
def _map() -> dict:
    return json.loads((DATA / "macro_sector_map.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _exact() -> Dict[str, str]:
    return {key(label): sector for sector, labels in _map()["exact"].items() for label in labels}


@lru_cache(maxsize=1)
def _groups() -> Dict[str, str]:
    raw = json.loads((DATA / "business_groups.json").read_text(encoding="utf-8"))["groups"]
    return {sym: g for g, syms in raw.items() for sym in syms}


UNMAPPED = _map()["unmapped"]


def macro_sector(label: Optional[str], symbol: Optional[str] = None) -> str:
    """The macro sector of a company from its Sector label. Order: symbol override, exact label, wording rule; otherwise the 'Not classified' bucket."""
    m = _map()
    if symbol and symbol in m["symbolOverrides"]:
        return m["symbolOverrides"][symbol]
    k = key(label)
    if not k:
        return UNMAPPED
    if k in _exact():
        return _exact()[k]
    padded = k + " "
    for sector, words in m["contains"]:
        if any(w in padded if w.endswith(" ") else w in k for w in words):
            return sector
    return UNMAPPED


def business_group(symbol: str) -> Optional[str]:
    return _groups().get(symbol)


def macro_sector_names() -> List[str]:
    return list(_map()["exact"].keys())
