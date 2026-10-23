"""International prices and USD/INR for the commodity page: two vendor adapters, one common answer.

DECISION PENDING (no plan or key yet): the spec recommends metals.dev (about US$19.99 a month, 60-second updates) for metals, base metals and
USD/INR, and MetalpriceAPI for crude oil and natural gas. Both adapters read their key from the environment (METALS_DEV_API_KEY,
METALPRICEAPI_KEY); with neither, nothing is called and the page says the international price is not connected.

The response shapes below follow the vendors' documentation as saved by the research agent (MetalpriceAPI: success/base/timestamp/rates with
USDXAU style keys) and metals.dev's public description (status/currency/unit/metals/currencies/timestamps). They have NOT been checked against
a live answer: no key exists. Every number is parsed as an exact Decimal, never a float, and anything unreadable is dropped, not guessed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx

from .commodity_calc import dec

log = logging.getLogger("finlit.commodities")
METALS_DEV_URL = "https://api.metals.dev/v1/latest"
METALPRICE_URL = "https://api.metalpriceapi.com/v1/latest"

# Our commodity code -> the vendor's code. Units: precious metals USD per troy ounce, base metals USD per metric tonne (metals.dev),
# crude oil USD per barrel, natural gas USD per mmBtu (MetalpriceAPI).
METALS_DEV = {"gold": "gold", "silver": "silver", "platinum": "platinum", "copper": "copper", "aluminium": "aluminum"}
METALPRICE_METALS = {"gold": "XAU", "silver": "XAG", "platinum": "XPT"}
METALPRICE_ENERGY = {"wti": "WTI", "brent": "BRENT", "natgas": "NATURALGAS"}
USDINR_RANGE = (Decimal(20), Decimal(500))     # a rate outside this is a misread (e.g. the inverse), never shown


class FeedError(RuntimeError):
    """Any failure talking to a price vendor. The text never holds a URL or a key."""


@dataclass
class Quote:
    usd: Decimal
    ts: float        # the vendor's own time (UNIX seconds, UTC)


@dataclass
class Snapshot:
    vendor: str
    quotes: Dict[str, Quote] = field(default_factory=dict)
    usdinr: Optional[Quote] = None


def _epoch(v: Any) -> Optional[float]:
    """A UNIX time (seconds) or an ISO-8601 text to UNIX seconds."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()


def _positive(v: Any) -> Optional[Decimal]:
    x = dec(v)
    return x if x is not None and x > 0 else None


def _inr(x: Optional[Decimal]) -> Optional[Decimal]:
    """Rupees per dollar from whichever way the vendor states it: 95 (rupees per dollar) or 0.0105 (dollars per rupee)."""
    if x is None or x <= 0:
        return None
    r = x if x >= 1 else 1 / x
    return r if USDINR_RANGE[0] <= r <= USDINR_RANGE[1] else None


def parse_metals_dev(body: Any) -> Snapshot:
    """metals.dev /v1/latest?currency=USD&unit=toz: {"status": "success", "metals": {"gold": ..., "copper": ...}, "currencies": {"INR": ...},
    "timestamps": {"metal": "...Z", "currency": "...Z"}}."""
    if not isinstance(body, dict):
        raise FeedError("metals.dev: unreadable answer")
    if body.get("status") != "success":
        raise FeedError("metals.dev: " + str(body.get("error_code") or body.get("status") or "unreadable answer")[:60])
    ts = body.get("timestamps") if isinstance(body.get("timestamps"), dict) else {}
    t_metal, t_cur = _epoch(ts.get("metal")), _epoch(ts.get("currency"))
    snap = Snapshot("metals.dev")
    metals = body.get("metals") if isinstance(body.get("metals"), dict) else {}
    for code, key in METALS_DEV.items():
        x = _positive(metals.get(key))
        if x is not None and t_metal is not None:
            snap.quotes[code] = Quote(x, t_metal)
    inr = _inr(_positive((body.get("currencies") or {}).get("INR") if isinstance(body.get("currencies"), dict) else None))
    if inr is not None and t_cur is not None:
        snap.usdinr = Quote(inr, t_cur)
    return snap


def parse_metalprice(body: Any, metals: bool = True) -> Snapshot:
    """MetalpriceAPI /v1/latest?base=USD: {"success": true, "timestamp": ..., "rates": {"USDXAU": 1856.9, "USDINR": 95.0, ...}}.
    The USD-prefixed keys are dollars per unit (ounce, barrel, mmBtu); the bare keys are the inverse and are used only when the prefixed one is absent."""
    if not isinstance(body, dict) or body.get("success") is not True:
        err = (body or {}).get("error") if isinstance(body, dict) else None
        raise FeedError("MetalpriceAPI: " + (str(err.get("code")) if isinstance(err, dict) else "unreadable answer"))
    t = _epoch(body.get("timestamp"))
    rates = body.get("rates") if isinstance(body.get("rates"), dict) else {}
    snap = Snapshot("MetalpriceAPI")
    if t is None:
        return snap

    def usd_per(code: str) -> Optional[Decimal]:
        x = _positive(rates.get("USD" + code))
        if x is None:
            inv = _positive(rates.get(code))
            x = 1 / inv if inv is not None else None
        return x

    wanted = {**(METALPRICE_METALS if metals else {}), **METALPRICE_ENERGY}
    for code, vendor in wanted.items():
        x = usd_per(vendor)
        if x is not None:
            snap.quotes[code] = Quote(x, t)
    inr = _inr(_positive(rates.get("USDINR")) or (1 / _positive(rates.get("INR")) if _positive(rates.get("INR")) else None))
    if inr is not None:
        snap.usdinr = Quote(inr, t)
    return snap


async def _get(http: httpx.AsyncClient, vendor: str, url: str, **kw: Any) -> Any:
    try:
        r = await http.get(url, **kw)
    except httpx.HTTPError as e:
        raise FeedError(f"{vendor}: {type(e).__name__}") from None
    if r.status_code != 200:
        raise FeedError(f"{vendor}: HTTP {r.status_code}")     # 429 or 403 = quota used up or plan lapsed
    try:
        return json.loads(r.text, parse_float=Decimal)
    except ValueError:
        raise FeedError(f"{vendor}: unreadable answer") from None


async def fetch_metals_dev(http: httpx.AsyncClient, key: str) -> Snapshot:
    return parse_metals_dev(await _get(http, "metals.dev", METALS_DEV_URL, params={"api_key": key, "currency": "USD", "unit": "toz"}))


async def fetch_metalprice(http: httpx.AsyncClient, key: str, metals: bool = True) -> Snapshot:
    codes = ",".join([*(METALPRICE_METALS.values() if metals else ()), *METALPRICE_ENERGY.values(), "INR"])
    body = await _get(http, "MetalpriceAPI", METALPRICE_URL, params={"base": "USD", "currencies": codes}, headers={"X-API-KEY": key})
    return parse_metalprice(body, metals)
