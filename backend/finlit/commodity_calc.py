"""Exact arithmetic for the commodity page: unit conversions, import parity, purity, premium and day change. Pure functions, no I/O.

Everything is a `Decimal` (28 digits, ROUND_HALF_UP), never a float. Rounding happens only when a figure is turned into text for display
(`q`); every secondary number (22K, 10 g, per kg, GST) is derived from the UNROUNDED base. Prices reach the browser as text already rounded
to the digits shown, so the page never computes or rounds a price itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, Context, InvalidOperation
from typing import Any, Optional, Tuple

CTX = Context(prec=28, rounding=ROUND_HALF_UP)
D = Decimal

# The international grain (1959 agreement): 0.06479891 g exactly. A troy ounce is 480 grains, a tola 180 grains.
GRAIN_G = D("0.06479891")
TROY_OZ_G = GRAIN_G * 480        # 31.1034768
TOLA_G = GRAIN_G * 180           # 11.6638038 (some Indian sources round it to 11.664)

# DECISION PENDING (22K): "22/24" (the convention of the founder's screenshot and Goodreturns) or "916" (BIS hallmark / IBJA: 0.916).
# The difference is about Rs 9.50 a gram at today's price. The page says which one is used.
K22_CONVENTION = "22/24"
# DECISION PENDING (purity basis): MCX GOLD delivers 995 bars; the international price is per ounce of fine (999) gold. The premium line
# compares like with like by scaling the MCX figure from 995 to 999. The smaller MCX gold contracts are reported inconsistently (995 or 999),
# so the card is built on GOLD only.
MCX_GOLD_FINENESS = D(995)
FINE_FINENESS = D(999)


def dec(v: Any) -> Optional[Decimal]:
    """Text or number to Decimal (numbers go through str, so 0.1 stays 0.1); None, junk, NaN and infinity give None."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = D(str(v).strip())
    except (InvalidOperation, ValueError):
        return None
    return x if x.is_finite() else None


def q(x: Optional[Decimal], dp: int) -> Optional[str]:
    """Round half up to `dp` decimal places and write as text ('14163.33'); None stays None. Negative zero is written as zero."""
    if x is None:
        return None
    r = x.quantize(D(1).scaleb(-dp), rounding=ROUND_HALF_UP, context=CTX)
    if r == 0:
        r = abs(r)
    return format(r, "f")


# ------------------------------------------------------------------------------------------------------------------ units

def usd_oz_to_inr_gram(usd_per_oz: Decimal, usdinr: Decimal) -> Decimal:
    return usd_per_oz / TROY_OZ_G * usdinr


def usd_per_tonne_to_inr_per_kg(usd_per_tonne: Decimal, usdinr: Decimal) -> Decimal:
    """1 tonne = 1,000 kg: $10,000 a tonne at 95 rupees a dollar is Rs 950 a kg."""
    return usd_per_tonne * usdinr / 1000


# ------------------------------------------------------------------------------------------------------------------ import parity

@dataclass(frozen=True)
class Parity:
    base: Decimal       # rupees per gram at the exchange rate, before any duty
    duty_paid: Decimal  # with customs duty (BCD + AIDC), ex-GST: the figure comparable to MCX and IBJA quotes
    with_gst: Decimal   # with GST on top


def parity(usd_per_oz: Decimal, usdinr: Decimal, bcd: Decimal, aidc: Decimal, gst: Decimal) -> Parity:
    """Indicative landed price per gram. Rates are fractions (0.10 = 10%). The simple formula on market value; customs actually charge
    duty on a government tariff value, so the real landed cost can differ a little."""
    base = usd_oz_to_inr_gram(usd_per_oz, usdinr)
    duty_paid = base * (1 + bcd + aidc)
    return Parity(base, duty_paid, duty_paid * (1 + gst))


def mcx_to_fine(mcx_per_g: Decimal, fineness: Decimal = MCX_GOLD_FINENESS) -> Decimal:
    """MCX gold (995 bars) as the price of 999 gold: x 999 / 995."""
    return mcx_per_g * FINE_FINENESS / fineness


def premium_pct(mcx_per_g: Decimal, parity_per_g: Decimal) -> Optional[Decimal]:
    """(MCX / parity - 1) x 100; None when parity is not a positive price."""
    if parity_per_g <= 0:
        return None
    return (mcx_per_g / parity_per_g - 1) * 100


# ------------------------------------------------------------------------------------------------------------------ purity for gold

def k22(per_g_24k: Decimal, convention: str = K22_CONVENTION) -> Decimal:
    return per_g_24k * D("0.916") if convention == "916" else per_g_24k * 22 / 24


def k18(per_g_24k: Decimal) -> Decimal:
    return per_g_24k * D("0.75")


# ------------------------------------------------------------------------------------------------------------------ change

def day_change(last: Optional[Decimal], prev: Optional[Decimal]) -> Optional[Tuple[Decimal, Decimal]]:
    """(absolute change, percent) against the previous close; None when there is no previous close above zero (a percentage of zero or of a
    negative price means nothing). Zero change is (0, 0)."""
    if last is None or prev is None or prev <= 0:
        return None
    return last - prev, (last - prev) / prev * 100

