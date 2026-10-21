"""ETFs: list, detail and compare for exchange-traded funds, from Upstox prices and candles. (Owned by the ETF build.)"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/etf")


async def refresh(store, settings) -> dict:
    """Nightly refresh, called by `python -m finlit.worker refresh-etf`."""
    return {"status": "not built"}
