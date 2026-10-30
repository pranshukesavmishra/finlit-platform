"""Peer values for the sector inputs, from the screener table (one row per company with its stored growth figures). Pure over the table's arrays."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .model import MIN_PEERS, SECTOR_COLUMNS


def peer_values(kind: str, symbol: str, symbols: List[str], sector: List[Optional[str]], industry: List[Optional[str]], cols: Dict[str, List[float]]
                ) -> Tuple[Optional[Dict[str, List[float]]], Dict[str, str], Optional[str]]:
    """For each sector parameter: the peers' values (the company left out), taken from its industry when at least MIN_PEERS peers have the figure,
    else from its sector. Returns (values by parameter key or None, group name by parameter key, why none)."""
    try:
        me = symbols.index(symbol)
    except ValueError:
        return None, {}, "This company is not in the screener table yet, so its peers' growth is not available."
    ind, sec = industry[me], sector[me]
    if not ind and not sec:
        return None, {}, "No sector or industry is stored for this company."
    values: Dict[str, List[float]] = {}
    groups: Dict[str, str] = {}
    for key, col in SECTOR_COLUMNS[kind].items():
        xs = cols.get(col)
        if xs is None:
            continue
        pick = lambda match: [xs[i] for i in range(len(xs)) if i != me and match(i) and isinstance(xs[i], (int, float)) and math.isfinite(xs[i])]  # noqa: E731
        by_ind = pick(lambda i: bool(ind) and industry[i] == ind)
        by_sec = pick(lambda i: bool(sec) and sector[i] == sec)
        if len(by_ind) >= MIN_PEERS:
            values[key], groups[key] = by_ind, f"{ind} (industry)"
        else:
            values[key], groups[key] = by_sec, f"{sec} (sector)" if sec else f"{ind} (industry)"
    return values, groups, None
