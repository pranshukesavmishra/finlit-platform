"""Regression tests for the valuation rule: FinEdge's own figure wins; ours is only a labelled fallback; one market cap on the whole page.

Found on LUMAXTECH: the ratio strip said Rs 13,931 Cr and the Company overview card Rs 12,409 Cr (quote vs profile), and P/E 37.17 / P/B 9.91 were
our own figures re-priced over FinEdge's 34.72 / 9.49. See docs/KNOWN-ISSUES.md, "Valuation figures: FinEdge wins, one market cap".
"""

import copy

from finlit.screener import compute as screener_compute
from finlit.snapshot import build


def _metric(sections, key):
    return next((m for m in sections["summary"]["keyMetrics"] if m["key"] == key), None)


def _bundle(base, **changes):
    b = copy.deepcopy(base)
    b.update(changes)
    return b


def _set_latest_price_ratios(bundle, **values):
    rows = bundle["daily_price_ratios"]["price_ratios"]
    last = max(rows, key=lambda r: r["quote_date"])
    last.update(values)
    return last


def test_one_market_cap_on_the_whole_page(reliance_bundle):
    s = build(reliance_bundle)
    quote_cap = reliance_bundle["quote"]["RELIANCE"]["market_cap"]
    profile_cap = reliance_bundle["profile"]["market_cap"]
    assert round(quote_cap, 2) != round(profile_cap, 2)   # the recorded payloads really do disagree (quote = price x shares; profile = older file)
    strip = _metric(s, "market_cap")["value"]
    assert strip == s["summary"]["profile"]["marketCapCr"] == s["summary"]["quote"]["marketCapCr"] == s["ratios"]["latest"]["market_cap"]["value"] == round(quote_cap, 2)
    assert s["summary"]["profile"]["marketCapSource"] == "quote"
    assert screener_compute.compute(s)["market_cap"] == strip


def test_market_cap_falls_back_to_the_profile_everywhere(reliance_bundle):
    b = _bundle(reliance_bundle)
    b["quote"]["RELIANCE"].pop("market_cap")
    s = build(b)
    cap = round(b["profile"]["market_cap"], 2)
    assert _metric(s, "market_cap")["value"] == s["summary"]["profile"]["marketCapCr"] == s["summary"]["quote"]["marketCapCr"] == cap
    assert s["summary"]["profile"]["marketCapSource"] == "profile" and _metric(s, "market_cap")["period"] == "Company profile"
    assert screener_compute.compute(s)["market_cap"] == cap


def test_finedge_pe_and_pb_are_shown_as_sent(reliance_bundle):
    b = _bundle(reliance_bundle)
    row = _set_latest_price_ratios(b, pe=34.72, pb=9.49, ps=3.1, pfcf=21.5)
    s = build(b)
    for key, sent in (("pe", 34.72), ("pb", 9.49)):
        m = _metric(s, key)
        assert m["value"] == sent and m["period"].startswith("As of ")   # not re-priced at the live quote
        assert s["ratios"]["latest"][key]["rule"] == "finedge" and "note" not in s["ratios"]["latest"][key]
    assert s["ratios"]["latest"]["ps"]["value"] == 3.1 and s["ratios"]["latest"]["pfcf"]["value"] == 21.5
    assert row["quote_date"]
    # the screener shows the same number, even after the price has moved since the report was built
    s["summary"]["quote"]["refPrice"] = s["summary"]["quote"]["price"] * 1.1
    m = screener_compute.compute(s)
    assert m["pe"] == 34.72 and m["pb"] == 9.49


def test_pe_and_pb_fall_back_to_ours_with_a_note_when_finedge_sends_none(reliance_bundle):
    b = _bundle(reliance_bundle)
    _set_latest_price_ratios(b, pe=0, pb=0, ps=0, pfcf=0)   # FinEdge's way of saying "no figure"
    s = build(b)
    cap = _metric(s, "market_cap")["value"]
    pe, pb = s["ratios"]["latest"]["pe"], s["ratios"]["latest"]["pb"]
    assert pe["rule"] == pb["rule"] == "fallback"
    assert "FinEdge sent no P/E" in pe["note"] and "FinEdge sent no P/B" in pb["note"]
    fin = s["financials"]
    profit_ttm = sum(fin["quarterly"]["pl"]["rows"]["net_profit"][-4:])
    equity = fin["yearly"]["bs"]["rows"]["total_equity"][-1]
    assert abs(pe["value"] - cap / profit_ttm) < 0.01 and pe["period"] == "TTM"
    assert abs(pb["value"] - cap / equity) < 0.01 and pb["period"] == fin["yearly"]["bs"]["periods"][-1]
    assert s["ratios"]["blanks"] == {k: v for k, v in s["ratios"]["blanks"].items() if k not in s["ratios"]["latest"]}


def test_a_loss_gives_no_pe_and_says_why(reliance_bundle):
    b = _bundle(reliance_bundle)
    _set_latest_price_ratios(b, pe=0)
    for row in b["pl_quarterly"]["financials"]:
        row["profitLossForPeriod"] = -abs(row.get("profitLossForPeriod") or 1e9)
        row.pop("profitOrLossAttributableToOwners", None)
    s = build(b)
    assert "pe" not in s["ratios"]["latest"]
    assert "FinEdge sent no P/E" in s["ratios"]["blanks"]["pe"]


def test_derived_overrides_that_remain_are_labelled(reliance_sections):
    latest = reliance_sections["ratios"]["latest"]
    assert latest["dividend_payout"]["rule"] == "override"
    assert latest["ev_ebitda"]["rule"] == "fallback" and "FinEdge sends no EV/EBITDA" in latest["ev_ebitda"]["note"]
    assert latest["dividend_yield"]["rule"] == "fallback" and "FinEdge sends no dividend yield" in latest["dividend_yield"]["note"]
    assert latest["roe"]["rule"] == "finedge"
