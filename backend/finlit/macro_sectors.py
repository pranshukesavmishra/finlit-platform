"""Macro backdrop per sector (owner's spec "From macro data to sector signals", 1 Nov 2026).

1. Each indicator becomes a signal from -1 to +1: the average of the parts that exist, each capped at +-1:
       level    = clip((reading - neutral) / band)        momentum = clip(change / typical change)
   A positive signal means the indicator is high or rising (for rates: pressure to hike; for the rupee: the rupee weakening).
2. Each sector reacts to each indicator by -2..+2 (the spec's matrix, page 3: ++ strong and direct, + moderate or indirect, a dot no meaningful link).
3. raw = sum(sensitivity x signal); score = 50 + 50 x tanh(raw / 3): 0 to 100, 50 = neutral.
   Labels: 70 or more strong tailwind, 58-69 tailwind, 43-57 neutral, 31-42 headwind, 30 or less strong headwind.
4. The two largest contributions (at least 0.3 in size) are the reasons ("Credit +" helps, "Rate hikes -" hurts); below that, "No strong driver today".

The sensitivities are the spec's starting estimates, not yet backtested (the spec asks for a 10-year backtest). It describes the macro backdrop of a sector, not a
company: a strong company can do well in a weak sector. Information only, not investment advice.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

DISCLAIMER = ("Describes the macro backdrop of the company's sector from official data (MoSPI, RBI); not a view on the company and not a recommendation. "
              "The sector sensitivities are starting estimates. Information only, not investment advice.")

# key, label shown in reasons, short words
INDICATORS: List[Tuple[str, str]] = [
    ("cpi", "CPI"), ("wpi_cpi", "WPI-CPI"), ("rates", "Rate hikes"), ("growth", "Growth"), ("credit", "Credit"),
    ("funding", "Funding"), ("rupee", "Rupee"), ("food", "Food CPI"), ("unemployment", "Unemployment"), ("crude", "Crude"),
]
KEYS = [k for k, _ in INDICATORS]
LABEL = dict(INDICATORS)

# The spec's matrix (page 3), columns in KEYS order.
SECTORS: List[Tuple[str, str, Tuple[int, ...]]] = [
    ("private_banks", "Private banks", (0, 0, 1, 1, 2, -1, 0, 0, -1, 0)),
    ("psu_banks", "PSU banks", (0, 0, 1, 1, 1, -1, 0, 0, -1, 0)),
    ("nbfc", "NBFCs & housing finance", (-1, 0, -2, 1, 1, -1, 0, 0, -1, 0)),
    ("it", "IT services", (0, 0, 0, 0, 0, 0, 2, 0, 0, 0)),
    ("pharma", "Pharma (export-led)", (0, -1, 0, 0, 0, 0, 1, 0, 0, -1)),
    ("fmcg", "FMCG", (-1, -2, 0, 1, 0, 0, -1, -2, -1, -1)),
    ("autos", "Autos", (-1, -1, -1, 2, 1, 0, -1, -1, -1, -1)),
    ("realty", "Real estate", (0, -1, -2, 1, 1, 0, 0, 0, -1, 0)),
    ("capital_goods", "Capital goods & infra", (0, -1, -1, 2, 1, 0, 0, 0, 0, 0)),
    ("cement", "Cement", (0, -1, -1, 1, 0, 0, 0, 0, 0, -1)),
    ("metals", "Metals & mining", (0, 2, 0, 1, 0, 0, 1, 0, 0, -1)),
    ("upstream", "Upstream oil & gas", (0, 1, 0, 0, 0, 0, 1, 0, 0, 2)),
    ("omc", "Oil marketing cos. (OMCs)", (0, 0, 0, 1, 0, 0, -1, 0, 0, -2)),
    ("chemicals", "Specialty chemicals", (0, 1, 0, 1, 0, 0, 1, 0, 0, -2)),
    ("paints", "Paints", (0, -2, 0, 1, 0, 0, -1, 0, 0, -2)),
    ("aviation", "Aviation", (0, 0, 0, 1, 0, 0, -2, 0, 0, -2)),
    ("hotels", "Hotels & QSR", (1, -1, 0, 1, 0, 0, 0, -1, -1, 0)),
    ("agri", "Agri inputs", (0, 0, 0, 0, 0, 0, -1, 1, 0, -1)),
]
SECTOR_NAME = {k: n for k, n, _ in SECTORS}
REASON_MIN = 0.3


def clip(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _avg(parts: Sequence[Optional[float]]) -> Optional[float]:
    have = [p for p in parts if p is not None]
    return sum(have) / len(have) if have else None


def label_of(score: float) -> str:
    return "Strong tailwind" if score >= 70 else "Tailwind" if score >= 58 else "Neutral" if score >= 43 else "Headwind" if score >= 31 else "Strong headwind"


# ----------------------------------------------------------------------------------------------------------- reading the macro page's payload
def _card(p: dict, key: str) -> dict:
    return next((c for c in p.get("cards") or [] if c.get("key") == key), {})


def _last_two(points: Any) -> Tuple[Optional[Tuple[str, float]], Optional[Tuple[str, float]]]:
    pts = [(str(d), float(v)) for d, v in (points or []) if _num(v) is not None]
    return (pts[-1] if pts else None), (pts[-2] if len(pts) > 1 else None)


def _series(p: dict, key: str):
    return _last_two(((p.get("series") or {}).get(key) or {}).get("points"))


def readings(p: dict, crude_pct_3m: Optional[float] = None) -> Dict[str, Dict[str, Any]]:
    """Every indicator's reading, change and signal, worked out from the macro page's payload. A part with no data is left out (never zero); an indicator
    with no part at all has signal None and a reason."""
    out: Dict[str, Dict[str, Any]] = {}

    def put(key, signal, reading, reason=None):
        out[key] = {"key": key, "label": LABEL[key], "signal": None if signal is None else round(signal, 4), "reading": reading,
                    "reason": reason if signal is None else None}

    cpi, wpi = _card(p, "cpi"), _card(p, "wpi")
    c, cc = _num(cpi.get("value")), _num(cpi.get("change"))
    put("cpi", _avg([None if c is None else clip((c - 4) / 2), None if cc is None else clip(cc / 0.5)]),
        None if c is None else f"{c:.2f}%" + ("" if cc is None else f", {cc:+.2f} pp"), "No CPI reading.")
    w, wc = _num(wpi.get("value")), _num(wpi.get("change"))
    gap = None if c is None or w is None else w - c
    dgap = None if wc is None or cc is None else wc - cc
    put("wpi_cpi", _avg([None if gap is None else clip(gap / 4), None if dgap is None else clip(dgap / 1)]),
        None if gap is None else f"{gap:.2f} pp gap", "No WPI or CPI reading.")
    repo, real = _card(p, "repo"), _card(p, "real_rate")
    rc, rr = _num(repo.get("change")), _num(real.get("value"))
    put("rates", _avg([None if rr is None else clip((1.5 - rr) / 1.5), None if rc is None else clip(rc / 0.25)]),
        None if rr is None and rc is None else ", ".join(x for x in [None if _num(repo.get("value")) is None else f"repo {repo['value']}%" + ("" if rc is None else f" ({rc:+.2f})"),
                                                                    None if rr is None else f"real repo {rr:+.2f} pp"] if x), "No repo reading.")
    g, gc, i, ic = _num(_card(p, "gdp").get("value")), _num(_card(p, "gdp").get("change")), _num(_card(p, "iip").get("value")), _num(_card(p, "iip").get("change"))
    lvl = _avg([None if g is None else clip((g - 6.5) / 1.5), None if i is None else clip((i - 4) / 3)])
    mom = _avg([None if gc is None else clip(gc / 1), None if ic is None else clip(ic / 1)])
    put("growth", _avg([lvl, mom]), None if g is None and i is None else ", ".join(x for x in [None if g is None else f"GDP {g:.2f}%", None if i is None else f"IIP {i:.2f}%"] if x),
        "No GDP or IIP reading.")
    cr = _series(p, "credit_yoy")[0] or ((_card(p, "credit_yoy").get("date"), _num(_card(p, "credit_yoy").get("value"))) if _num(_card(p, "credit_yoy").get("value")) is not None else None)
    dep = _series(p, "deposits_yoy")[0]
    put("credit", None if cr is None else clip((cr[1] - 12) / 4), None if cr is None else f"bank credit {cr[1]:+.1f}% y/y", "No bank credit reading.")
    put("funding", None if cr is None or dep is None else clip((cr[1] - dep[1]) / 3), None if cr is None or dep is None else f"credit {cr[1]:.1f}% vs deposits {dep[1]:.1f}%",
        "No bank deposit reading.")
    now, prev = _series(p, "usdinr")
    pct = None if now is None or prev is None or prev[1] == 0 else (now[1] / prev[1] - 1) * 100
    put("rupee", None if pct is None else clip(pct / 1), None if now is None else f"Rs {now[1]:.2f} per US$" + ("" if pct is None else f" ({pct:+.2f}% vs {prev[0][:7]})"),
        "No rupee history.")
    food = next((d for d in p.get("cpiDivisions") or [] if re.match(r"food", str(d.get("label", "")), re.I)), None)
    fn, fp = _last_two((food or {}).get("points"))
    put("food", _avg([None if fn is None else clip((fn[1] - 4) / 2), None if fn is None or fp is None else clip((fn[1] - fp[1]) / 0.5)]),
        None if fn is None else f"{fn[1]:.1f}%" + ("" if fp is None else f", from {fp[1]:.1f}%"), "No food inflation reading.")
    u, uc = _num(_card(p, "unemployment").get("value")), _num(_card(p, "unemployment").get("change"))
    put("unemployment", _avg([None if u is None else clip((u - 5) / 1), None if uc is None else clip(uc / 0.5)]), None if u is None else f"{u:.1f}%", "No unemployment reading.")
    put("crude", None if crude_pct_3m is None else clip(crude_pct_3m / 15), None if crude_pct_3m is None else f"Brent {crude_pct_3m:+.1f}% over 3 months",
        "No three months of Brent prices are stored yet, so crude oil is left out.")
    return out


def score_sectors(sig: Dict[str, Optional[float]]) -> List[Dict[str, Any]]:
    """Every sector's score, label and reasons from the indicator signals (a missing signal counts as 0, as the spec does for crude)."""
    rows = []
    for key, name, sens in SECTORS:
        contrib = {k: s * (sig.get(k) or 0.0) for k, s in zip(KEYS, sens)}
        raw = sum(contrib.values())
        score = 50 + 50 * math.tanh(raw / 3)
        top = sorted((kv for kv in contrib.items() if abs(kv[1]) >= REASON_MIN), key=lambda kv: -abs(kv[1]))[:2]
        rows.append({"key": key, "name": name, "score": round(score, 2), "label": label_of(round(score)), "raw": round(raw, 3),
                     "reasons": [f"{LABEL[k]} {'+' if v > 0 else '-'}" for k, v in top] or ["No strong driver today"]})
    return sorted(rows, key=lambda r: -r["score"])


def build(payload: dict, crude_pct_3m: Optional[float] = None) -> Dict[str, Any]:
    r = readings(payload, crude_pct_3m)
    sectors = score_sectors({k: v["signal"] for k, v in r.items()})
    return {"asOf": payload.get("today"), "signals": [r[k] for k in KEYS], "sectors": sectors, "disclaimer": DISCLAIMER,
            "method": "signal = average of level and momentum, each capped at plus or minus 1; score = 50 + 50 x tanh(sum of sensitivity x signal / 3)."}


# ----------------------------------------------------------------------------------------------------------- a company's sector
_RULES: List[Tuple[str, str]] = [
    ("paints", r"paint"), ("aviation", r"airline|aviation"), ("hotels", r"hotel|restaurant|resort|tourism|quick service"),
    ("agri", r"fertili[sz]er|pesticide|agro ?chemical|seeds"), ("chemicals", r"speciality chemical|specialty chemical|chemical|dyes|pigment"),
    ("cement", r"cement"), ("metals", r"steel|iron|metal|mining|alumin|copper|zinc|ferrous|ferro"),
    ("upstream", r"exploration|crude oil|oil & gas production|gas production"), ("omc", r"refiner|petroleum product|oil marketing"),
    ("realty", r"realty|real estate|residential|commercial projects"), ("autos", r"automobile|passenger car|2/3 wheeler|two wheeler|commercial vehicle|auto component|tractor|tyre"),
    ("it", r"software|computers|it enabled|it services|information technology"), ("pharma", r"pharma"),
    ("fmcg", r"fmcg|personal product|packaged food|household|food product|beverage|tobacco|edible oil|consumer food"),
    ("nbfc", r"non banking|non-banking|nbfc|housing finance|finance$|financial services|consumer finance"),
    ("capital_goods", r"capital goods|industrial machinery|construction|engineering|electrical equipment|heavy electrical|infrastructure|defence|ship ?building|aerospace"),
]
_PSU = re.compile(r"\b(state bank|bank of baroda|bank of india|bank of maharashtra|punjab national|punjab & sind|canara|union bank|indian bank|indian overseas|central bank|uco)\b", re.I)


def sector_for(name: Optional[str], sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    """The spec's sector for a company, from its industry (then sector) words; None when none of the 18 fits."""
    words = " ".join(x for x in (industry, sector) if x).lower()
    if not words:
        return None
    if re.search(r"non[ -]?banking|nbfc|housing finance", words):           # "Non Banking Financial Company" holds the word bank: decide it first
        return "nbfc"
    if "bank" in words and "investment bank" not in words:
        return "psu_banks" if "public sector" in words or (name and _PSU.search(name)) else "private_banks"
    for key, pat in _RULES:
        if re.search(pat, words):
            return key
    return None


# ----------------------------------------------------------------------------------------------------------- serving: GET /api/macro/sectors[?symbol=]
import time  # noqa: E402

from fastapi import APIRouter, Query, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

router = APIRouter()
FLAG = "macro_sectors"
_flag = {"on": False, "at": 0.0}
NO_STORE = {"Cache-Control": "private, no-store", "Vary": "Cookie"}
_SYMBOL = re.compile(r"^[A-Z0-9&._-]{1,24}$")


async def switched_on(store) -> bool:
    if time.monotonic() - _flag["at"] > 20:
        async with store.pool.acquire() as conn:
            _flag["on"] = bool(await conn.fetchval("SELECT enabled FROM feature_flags WHERE name = $1", FLAG))
        _flag["at"] = time.monotonic()
    return bool(_flag["on"])


async def crude_3m(conn) -> Optional[float]:
    """Brent's percentage change over about three months (latest against the last day at least 91 days before it), or None. The commodity vendor's stored daily
    snapshots are read first; when there are none the U.S. EIA daily Brent series loaded by the macro job (macro series brent_d) is used."""
    import datetime as _dt
    for sql_last, sql_then in (
            ("SELECT day AS d, value AS v FROM commodity_snapshots WHERE symbol = 'brent' AND kind = 'intl_usd' AND value > 0 ORDER BY day DESC LIMIT 1",
             "SELECT day AS d, value AS v FROM commodity_snapshots WHERE symbol = 'brent' AND kind = 'intl_usd' AND value > 0 AND day <= $1 ORDER BY day DESC LIMIT 1"),
            ("SELECT d, v FROM macro_points WHERE series = 'brent_d' AND v > 0 ORDER BY d DESC LIMIT 1",
             "SELECT d, v FROM macro_points WHERE series = 'brent_d' AND v > 0 AND d <= $1 ORDER BY d DESC LIMIT 1")):
        last = await conn.fetchrow(sql_last)
        if last is None:
            continue
        then = await conn.fetchrow(sql_then, last["d"] - _dt.timedelta(days=91))
        if then is None or (last["d"] - then["d"]).days > 120:
            continue
        return (float(last["v"]) / float(then["v"]) - 1) * 100
    return None


@router.get("/api/macro/sectors")
async def sectors(request: Request, symbol: str = Query("", max_length=40)) -> JSONResponse:
    """The macro backdrop of all 18 sectors, and of one company's sector when `symbol` is given. Gold, and only once switched on (administrators always)."""
    from .auth.entitlements import has
    from .auth.service import current
    from .macro import get_meta
    ctx = await current(request)
    store = request.app.state.store
    admin = ctx.role == "admin"
    if not admin and not await switched_on(store):
        return JSONResponse({"status": "off", "detail": "The macro backdrop is not switched on yet."}, status_code=404, headers=NO_STORE)
    if not admin and not (ctx.authed and has(ctx.plan, "gold")):
        return JSONResponse({"status": "plan_required", "plan": "gold", "detail": "The macro backdrop is part of the Gold plan."}, status_code=403, headers=NO_STORE)
    sym = symbol.strip().upper()
    if sym and not _SYMBOL.match(sym):
        return JSONResponse({"status": "bad_request", "detail": "That is not a company symbol."}, status_code=422, headers=NO_STORE)
    async with store.pool.acquire() as conn:
        payload = await get_meta(conn, "payload")
        crude = await crude_3m(conn)
        co = await conn.fetchrow("SELECT name, sector, industry FROM companies WHERE symbol = $1", sym) if sym else None
    if not payload:
        return JSONResponse({"status": "loading", "detail": "Macro data has not been loaded yet. It loads nightly."}, status_code=503, headers=NO_STORE)
    body = build(payload, crude)
    if sym:
        key = sector_for(co["name"], co["sector"], co["industry"]) if co else None
        row = next((r for r in body["sectors"] if r["key"] == key), None)
        body["company"] = {"symbol": sym, "sectorKey": key, "sector": row, "industry": co["industry"] if co else None,
                           "reason": None if row else ("This company is not in our list." if co is None else
                                                       f"This company's industry ({co['industry'] or co['sector'] or 'not stated'}) is not one of the 18 sectors the macro model covers.")}
    body["switchedOn"] = await switched_on(store)
    return JSONResponse(body, headers=NO_STORE)
