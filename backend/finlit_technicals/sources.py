"""Where the daily prices come from. The calculations need only pandas DataFrames, so any vendor works.

A source answers two questions:
    daily(symbol)   NSE stock symbol (as in data/peer_groups.json, e.g. "SAMBHV", "M&M", "BAJAJ_AUTO")
    index(code)     index code, TradingView style: "NSE:CNX500", "NSE:CNXSMALLCAP", "NSE:CNXMETAL" ... (INDICES)
Each returns a DataFrame indexed by trading date with columns open, high, low, close, volume (oldest first,
adjusted for splits and bonuses), or None when there is no data.

Included: CsvFolder (one CSV per symbol), MemorySource (DataFrames you already hold), Cached (wraps any source
so a batch run loads each file once), and NseHistory in nse.py (NSE's own daily files: every stock and index). For a database or a vendor API, write a class with the same two methods.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Protocol

import pandas as pd

from .peers import norm_symbol

# Index codes used by the indicators -> display name and NSE's official index name (map these to your vendor)
INDICES: Dict[str, Dict[str, str]] = {
    "NSE:CNX500": {"name": "Nifty 500", "nse": "NIFTY 500"},
    "NSE:NIFTY": {"name": "Nifty 50", "nse": "NIFTY 50"},
    "NSE:CNXMIDCAP": {"name": "Nifty Midcap 100", "nse": "NIFTY MIDCAP 100"},
    "NSE:CNXSMALLCAP": {"name": "Nifty Smallcap 100", "nse": "NIFTY SMALLCAP 100"},
    "NSE:NIFTYMIDCAP150": {"name": "Nifty Midcap 150", "nse": "NIFTY MIDCAP 150"},
    "NSE:NIFTYSMLCAP250": {"name": "Nifty Smallcap 250", "nse": "NIFTY SMALLCAP 250"},
    "NSE:CNXIT": {"name": "Nifty IT", "nse": "NIFTY IT"},
    "NSE:CNXPHARMA": {"name": "Nifty Pharma", "nse": "NIFTY PHARMA"},
    "NSE:NIFTYPVTBANK": {"name": "Nifty Pvt Bank", "nse": "NIFTY PRIVATE BANK"},
    "NSE:CNXPSUBANK": {"name": "Nifty PSU Bank", "nse": "NIFTY PSU BANK"},
    "NSE:CNXAUTO": {"name": "Nifty Auto", "nse": "NIFTY AUTO"},
    "NSE:CNXENERGY": {"name": "Nifty Energy", "nse": "NIFTY ENERGY"},
    "NSE:CNXMETAL": {"name": "Nifty Metal", "nse": "NIFTY METAL"},
    "NSE:CNXREALTY": {"name": "Nifty Realty", "nse": "NIFTY REALTY"},
    "NSE:CNXFMCG": {"name": "Nifty FMCG", "nse": "NIFTY FMCG"},
    "NSE:CNXFINANCE": {"name": "Nifty Fin Service", "nse": "NIFTY FINANCIAL SERVICES"},
    "NSE:CNXMEDIA": {"name": "Nifty Media", "nse": "NIFTY MEDIA"},
    "NSE:CNXINFRA": {"name": "Nifty Infra", "nse": "NIFTY INFRASTRUCTURE"},
}
COLUMNS = ["open", "high", "low", "close", "volume"]


class PriceSource(Protocol):
    def daily(self, symbol: str) -> Optional[pd.DataFrame]: ...

    def index(self, code: str) -> Optional[pd.DataFrame]: ...


def read_csv(path: Path) -> Optional[pd.DataFrame]:
    """date,open,high,low,close,volume (any column order, extra columns ignored, header names any case)."""
    if not path.exists():
        return None
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    date_col = cols.get("date") or cols.get("timestamp") or df.columns[0]
    out = pd.DataFrame({k: pd.to_numeric(df[cols[k]], errors="coerce") for k in COLUMNS if k in cols})
    if "close" not in out:
        raise ValueError(f"{path}: no close column")
    when = pd.to_datetime(df[date_col])
    if when.dt.tz is not None:
        when = when.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    out.index = pd.DatetimeIndex(when).normalize()
    out.index.name = "date"
    return out.sort_index()


class CsvFolder:
    """root/stocks/<SYMBOL>.csv and root/indices/<CODE>.csv (CODE = the index code without "NSE:", e.g. CNX500.csv).
    Stock files may also be named the normalised way (M_M.csv for M&M, BAJAJ_AUTO.csv)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def daily(self, symbol: str) -> Optional[pd.DataFrame]:
        d = self.root / "stocks"
        s = symbol.strip().upper()
        for name in dict.fromkeys([s, norm_symbol(s), s.replace("&", "_")]):
            df = read_csv(d / f"{name}.csv")
            if df is not None:
                return df
        return None

    def index(self, code: str) -> Optional[pd.DataFrame]:
        return read_csv(self.root / "indices" / f"{code.split(':')[-1]}.csv")

    def symbols(self) -> List[str]:
        return sorted(p.stem for p in (self.root / "stocks").glob("*.csv"))


class MemorySource:
    """{symbol: DataFrame} for stocks and {index code: DataFrame} for indices, already in memory."""

    def __init__(self, stocks: Dict[str, pd.DataFrame], indices: Optional[Dict[str, pd.DataFrame]] = None):
        self.stocks = {norm_symbol(k): v for k, v in stocks.items()}
        self.indices = indices or {}

    def daily(self, symbol: str) -> Optional[pd.DataFrame]:
        return self.stocks.get(norm_symbol(symbol))

    def index(self, code: str) -> Optional[pd.DataFrame]:
        return self.indices.get(code)

    def symbols(self) -> List[str]:
        return list(self.stocks)


class Cached:
    """Loads each symbol once (wrap the source for a batch run over many stocks)."""

    def __init__(self, source: PriceSource):
        self.source = source
        self._d: Dict[str, Optional[pd.DataFrame]] = {}
        self._i: Dict[str, Optional[pd.DataFrame]] = {}

    def daily(self, symbol: str) -> Optional[pd.DataFrame]:
        k = norm_symbol(symbol)
        if k not in self._d:
            self._d[k] = self.source.daily(symbol)
        return self._d[k]

    def index(self, code: str) -> Optional[pd.DataFrame]:
        if code not in self._i:
            self._i[code] = self.source.index(code)
        return self._i[code]

    def symbols(self) -> List[str]:
        return self.source.symbols() if hasattr(self.source, "symbols") else []

    def __getattr__(self, name):          # panel, key, names ... of an NseHistory underneath
        return getattr(self.source, name)
