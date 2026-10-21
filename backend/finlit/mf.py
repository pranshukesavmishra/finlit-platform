"""Mutual funds: list, detail and compare, from AMFI's official NAV files. (Owned by the mutual fund build.)"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/mf")


async def refresh(store, settings) -> dict:
    """Nightly refresh, called by `python -m finlit.worker refresh-mf`."""
    return {"status": "not built"}
