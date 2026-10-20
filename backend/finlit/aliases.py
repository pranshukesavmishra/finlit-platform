"""Retired trading symbols and where their data lives now. Tata Motors demerged in October 2025: the passenger-vehicle business kept the old
share history as TMPV (the provider already answers TATAMOTORS with TMPV's data), and the commercial-vehicle business listed as TMCV."""

SYMBOL_ALIASES = {"TATAMOTORS": "TMPV"}


def canonical(symbol: str) -> str:
    s = symbol.strip().upper()
    return SYMBOL_ALIASES.get(s, s)
