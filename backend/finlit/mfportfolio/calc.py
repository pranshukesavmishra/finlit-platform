"""Valuing the holdings. Pure code: money is Decimal and rounded half-up to the paisa, units to 4 places; ratios are rounded for display only at the end.

For one holding (its lots and its scheme's latest figures):
  invested   sum of the lots' money paid. A lot with no cost makes the holding's cost UNKNOWN (None with the reason), never 0.
  current    units x latest NAV, with the NAV's own date shown; a scheme with no NAV has no current value (reason given).
  gain       current - invested, and gain / invested in percent; only when the cost is known and above zero.
  xirr       the yearly rate that sets the dated cash flows to zero (finlit.mf.xirr: the spreadsheet's XIRR): every lot's money out on its purchase date,
             the current value in on the NAV date. Needs every lot dated and costed, no date after the NAV date, and the earliest purchase at least a year
             before the NAV date (an annualised rate over a few weeks says nothing). With one lot it is the compound annual growth rate (CAGR).
Every figure that is missing carries its reason in a sibling `...Why` field so the page never shows a bare blank.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..mf import xirr as mf_xirr
from .parse import q_money

MIN_XIRR_DAYS = 365
NAV_STALE_DAYS = 7

NO_RETURNS = {
    "stopped": "This scheme has stopped publishing NAVs, so it has no recent returns.",
    "idcw": "IDCW options are not given trailing returns here; see the Growth option of the same fund.",
    "unstated": "The scheme's option is not stated, so no returns are shown.",
    "no_history": "No NAV history is stored for this scheme yet.",
    "short": "The scheme is too young for a 1, 3 or 5 year return.",
}


def dec(v: Any) -> Optional[Decimal]:
    return None if v is None else Decimal(str(v))


def num(d: Optional[Decimal], dp: int = 2) -> Optional[float]:
    return None if d is None else float(d.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP))


def pct(numer: Decimal, denom: Decimal, dp: int = 2) -> Optional[float]:
    return None if denom <= 0 else num(numer / denom * 100, dp)


def xirr_of(lots: Sequence[Tuple[Decimal, Optional[Decimal], Optional[date]]], current: Optional[Decimal], nav_date: Optional[date]) -> Tuple[Optional[float], Optional[str], str]:
    """(rate in percent a year, why not, kind 'cagr' | 'xirr')."""
    kind = "cagr" if len(lots) == 1 else "xirr"
    if current is None or nav_date is None:
        return None, "There is no current value yet, so no annual return can be worked out.", kind
    if any(l[2] is None for l in lots):
        return None, "Add the purchase date of every purchase to see the XIRR." if len(lots) > 1 else "Add the purchase date to see the XIRR.", kind
    if any(l[1] is None for l in lots):
        return None, "The amount paid is not known for every purchase, so no XIRR can be worked out.", kind
    if any(l[2] > nav_date for l in lots):
        return None, "A purchase date is after the latest NAV date, so no XIRR can be worked out yet.", kind
    first = min(l[2] for l in lots)
    if (nav_date - first).days < MIN_XIRR_DAYS:
        return None, "Held for under a year: an annualised rate over a short time says little, so only the gain is shown.", kind
    paid = sum((l[1] for l in lots), Decimal(0))
    if paid <= 0:
        return None, "Nothing was paid for these units, so no XIRR can be worked out.", kind
    flows = [(l[2].toordinal(), -float(l[1])) for l in lots if l[1] > 0] + [(nav_date.toordinal(), float(current))]
    r = mf_xirr(flows)
    if r is None or r <= -1:
        return None, "No annual rate fits these cash flows (for example the current value is nil).", kind
    return round(r * 100, 2), None, kind


def value_holding(h: Dict[str, Any], s: Optional[Dict[str, Any]], data_date: Optional[date]) -> Dict[str, Any]:
    """One holding's row for the page. `h` = {id, code, folio, lots: [{id, units, invested, bought_on}]}, `s` = the scheme's row (None if it vanished)."""
    lots = [(l["units"], l["invested"], l["bought_on"]) for l in h["lots"]]
    units = sum((l[0] for l in lots), Decimal(0))
    cost_known = all(l[1] is not None for l in lots)
    invested = q_money(sum((l[1] for l in lots), Decimal(0))) if cost_known else None
    nav = dec(s["nav"]) if s and s["nav"] is not None else None
    nav_date: Optional[date] = s["nav_date"] if s else None
    current = q_money(units * nav) if nav is not None and nav > 0 else None
    out: Dict[str, Any] = {
        "id": h["id"], "code": h["code"], "folio": h["folio"], "units": num(units, 4),
        "lots": [{"id": l["id"], "units": num(l["units"], 4), "invested": num(l["invested"]), "boughtOn": l["bought_on"].isoformat() if l["bought_on"] else None} for l in h["lots"]],
        "invested": num(invested), "investedWhy": None if cost_known else "The amount paid is not known" + (" for every purchase." if len(lots) > 1 else ". Add it to see the gain."),
        "current": num(current), "currentWhy": None if current is not None else ("The scheme is no longer in the fund list." if s is None else "This scheme has no NAV yet, so it cannot be valued."),
        "nav": num(nav, 4) if nav is not None else None, "navDate": nav_date.isoformat() if nav_date else None,
    }
    stale = bool(s) and nav_date is not None and (not s["active"] or (data_date is not None and (data_date - nav_date).days > NAV_STALE_DAYS))
    out["navStale"] = stale
    out["navNote"] = (("This scheme has stopped publishing NAVs; the value uses its last NAV, from " if s and not s["active"] else "This NAV is older than the other funds' (from ")
                      + nav_date.strftime("%d %b %Y") + (")." if not (s and not s["active"]) else ".")) if stale and nav_date else None
    if current is not None and invested is not None and invested > 0:
        gain = current - invested
        out.update(gain=num(gain), gainPct=pct(gain, invested), gainWhy=None)
    else:
        out.update(gain=None, gainPct=None, gainWhy=(out["currentWhy"] if current is None else out["investedWhy"] if not cost_known else "Nothing was paid for these units, so a percentage gain is not meaningful."))
    x, why, kind = xirr_of(lots, current, nav_date)
    out.update(xirr=x, xirrWhy=why, xirrKind=kind)
    return out


def summarize(rows: List[Dict[str, Any]], score_locked: bool) -> Dict[str, Any]:
    """Totals over the holdings' rows (as `value_holding` made them, plus the scheme facts). Sums use Decimal; the gain covers only the funds whose cost AND
    value are both known, and says how many that is. `score` is the value-weighted Health Score when EVERY fund has one, else None with the reason."""
    n = len(rows)
    valued = [r for r in rows if r["current"] is not None]
    both = [r for r in valued if r["invested"] is not None]
    cur_all = sum((dec(r["current"]) for r in valued), Decimal(0))
    inv = sum((dec(r["invested"]) for r in both), Decimal(0))
    cur_both = sum((dec(r["current"]) for r in both), Decimal(0))
    gain = cur_both - inv
    dates = [r["navDate"] for r in valued if r["navDate"]]
    out: Dict[str, Any] = {
        "funds": n, "valued": len(valued), "withCost": len(both),
        "invested": num(inv) if both else None, "current": num(cur_all) if valued else None,
        "gain": num(gain) if both else None, "gainPct": pct(gain, inv) if both else None,
        "gainFunds": len(both),
        "navFrom": min(dates) if dates else None, "navTo": max(dates) if dates else None,
    }
    notes = []
    if n and len(valued) < n:
        notes.append(f"{n - len(valued)} of {n} funds could not be valued (no NAV), so they are left out of the totals.")
    if valued and len(both) < len(valued):
        notes.append(f"The gain covers {len(both)} of {len(valued)} valued funds: the others have no amount paid.")
    out["notes"] = notes
    # portfolio XIRR over the funds that can have one (every lot dated and costed, held a year)
    flows: List[Tuple[int, float]] = []
    used = 0
    for r in valued:
        if r["xirr"] is None:
            continue
        used += 1
        for l in r["lots"]:
            if l["invested"] and l["boughtOn"]:
                flows.append((date.fromisoformat(l["boughtOn"]).toordinal(), -float(l["invested"])))
        flows.append((date.fromisoformat(r["navDate"]).toordinal(), float(r["current"])))
    px = mf_xirr(flows) if used else None
    out["xirr"] = round(px * 100, 2) if px is not None and px > -1 else None
    out["xirrFunds"] = used
    out["xirrWhy"] = None if out["xirr"] is not None else ("No fund has a purchase date on every purchase and a year of holding, so no portfolio XIRR is shown." if n else None)
    if score_locked:
        out["score"] = {"locked": True, "value": None, "label": None, "why": None}
    else:
        finals = [(r["score"]["final"], dec(r["current"])) for r in rows if r.get("score") and r["score"].get("final") is not None and r["current"] is not None]
        scored = len(finals)
        if n and scored == n and sum(w for _, w in finals) > 0:
            tot = sum(w for _, w in finals)
            val = round(float(sum(Decimal(str(f)) * w for f, w in finals) / tot), 1)
            out["score"] = {"locked": False, "value": val, "label": label_of(val), "why": None, "funds": n}
        else:
            missing = n - scored
            out["score"] = {"locked": False, "value": None, "label": None, "funds": scored,
                            "why": f"{missing} of {n} funds {'has' if missing == 1 else 'have'} no score, so a portfolio score is not shown." if n else None}
    return out


def label_of(score: float) -> str:
    from ..mfscore.engine import label_of as lab
    return lab(score) or ""


def _share(parts: Dict[str, Decimal], total: Decimal, keep: int = 8) -> List[Dict[str, Any]]:
    items = sorted(parts.items(), key=lambda kv: (-kv[1], kv[0]))
    top, rest = items[:keep], items[keep:]
    out = [{"label": k, "value": num(v), "pct": pct(v, total, 1)} for k, v in top]
    if rest:
        rv = sum((v for _, v in rest), Decimal(0))
        out.append({"label": f"{len(rest)} others", "value": num(rv), "pct": pct(rv, total, 1)})
    return out


def allocation(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Share of the current value by category and by fund house (valued funds only)."""
    valued = [r for r in rows if r["current"] is not None]
    total = sum((dec(r["current"]) for r in valued), Decimal(0))
    cat: Dict[str, Decimal] = {}
    amc: Dict[str, Decimal] = {}
    for r in valued:
        v = dec(r["current"])
        cat[r["categoryLabel"] or "Other"] = cat.get(r["categoryLabel"] or "Other", Decimal(0)) + v
        amc[r["amc"] or "Other"] = amc.get(r["amc"] or "Other", Decimal(0)) + v
    return {"byCategory": _share(cat, total) if total > 0 else [], "byAmc": _share(amc, total) if total > 0 else []}


def concentration(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A plain-words look at how the value is spread. Descriptive only: it says what is, never what to do."""
    valued = sorted((r for r in rows if r["current"] is not None), key=lambda r: -r["current"])
    total = sum((dec(r["current"]) for r in valued), Decimal(0))
    if not valued or total <= 0:
        return {"level": None, "text": "Add funds with a NAV to see how your money is spread.", "top1Pct": None, "top3Pct": None}
    top1 = pct(dec(valued[0]["current"]), total, 1)
    top3 = pct(sum((dec(r["current"]) for r in valued[:3]), Decimal(0)), total, 1)
    amcs: Dict[str, Decimal] = {}
    for r in valued:
        amcs[r["amc"]] = amcs.get(r["amc"], Decimal(0)) + dec(r["current"])
    amc_name, amc_val = max(amcs.items(), key=lambda kv: (kv[1], kv[0]))
    amc_pct = pct(amc_val, total, 1)
    n = len(valued)
    level = "concentrated" if (top1 or 0) >= 35 or (top3 or 0) >= 70 and n > 3 else "moderate" if (top1 or 0) >= 20 or (top3 or 0) >= 55 else "spread"
    if n == 1:
        text = f"All of the value is in one fund ({valued[0]['name']})."
        level = "concentrated"
    else:
        text = f"Your largest fund, {valued[0]['name']}, is {top1:g}% of the current value" + (f"; the three largest together are {top3:g}%." if n > 3 else ".")
        if len(amcs) < n and (amc_pct or 0) >= 40:
            text += f" {amc_pct:g}% sits with one fund house ({amc_name})."
        text += {"concentrated": " The value rests on very few funds.", "moderate": " The value is fairly spread, with a few larger funds.", "spread": " The value is spread across many funds."}[level]
    text += " Different funds can hold the same shares; this counts funds, not what is inside them."
    return {"level": level, "text": text, "top1Pct": top1, "top3Pct": top3, "topFund": valued[0]["name"], "topAmc": amc_name, "topAmcPct": amc_pct}
