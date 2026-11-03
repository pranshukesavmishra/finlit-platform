"""My mutual funds, the pure parts: number / date / folio reading, one imported row, matching a row to a scheme (AMFI code, ISIN, exact name, fuzzy that only
suggests), and the maths (invested, current value, gain, XIRR, the summary, allocation and the concentration note). No database."""

from datetime import date
from decimal import Decimal

import pytest

from finlit.mfportfolio import calc
from finlit.mfportfolio.match import Index, analyse, match_row
from finlit.mfportfolio.parse import clean_folio, clean_row, parse_date, parse_decimal, strict_lot

TODAY = date(2026, 10, 30)


# ------------------------------------------------------------------------------------------------------------------ numbers, dates, folios

@pytest.mark.parametrize("raw,want", [
    ("1,23,456.78", Decimal("123456.78")), ("₹ 12,000", Decimal("12000")), ("Rs. 1,500.50", Decimal("1500.50")), ("(500)", Decimal("-500")), ("-12.5", Decimal("-12.5")),
    ("2500 Cr", Decimal("2500")), ("100 Dr", Decimal("-100")), (12.5, Decimal("12.5")), (7, Decimal("7")), (".5", Decimal("0.5")), ("  42  ", Decimal("42")),
])
def test_decimal_understands_indian_formats(raw, want):
    assert parse_decimal(raw) == (want, None)


@pytest.mark.parametrize("raw", ["", "-", "NA", "N/A", "nil", None, "—"])
def test_blank_cells_are_nothing_given_not_zero(raw):
    assert parse_decimal(raw) == (None, None)


@pytest.mark.parametrize("raw", ["abc", "12,5", "1.2.3", "1e5", "inf", "12 units", True])
def test_unreadable_cells_are_a_problem_not_a_default(raw):
    v, why = parse_decimal(raw)
    assert v is None and why


@pytest.mark.parametrize("raw,want", [
    ("2022-03-15", date(2022, 3, 15)), ("15-03-2022", date(2022, 3, 15)), ("15/03/2022", date(2022, 3, 15)), ("15.03.22", date(2022, 3, 15)),
    ("15 Mar 2022", date(2022, 3, 15)), ("15-Mar-2022", date(2022, 3, 15)), ("5-sep-19", date(2019, 9, 5)), ("2022/03/15", date(2022, 3, 15)),
    ("15-03-2022 10:30:00", date(2022, 3, 15)), (44635, date(2022, 3, 15)),
])
def test_dates_are_day_first(raw, want):
    assert parse_date(raw, TODAY) == (want, None)


def test_dates_reject_the_impossible():
    assert parse_date("31-02-2022", TODAY)[1] and parse_date("2030-01-01", TODAY)[1] and parse_date("01-01-1975", TODAY)[1] and parse_date("hello", TODAY)[1]
    assert parse_date("", TODAY) == (None, None) and parse_date(None, TODAY) == (None, None)


def test_folio_tidying():
    assert clean_folio(" 1234567 / 89 ") == "1234567/89" and clean_folio("abc 12") == "ABC 12" and clean_folio(12345.0) == "12345"
    assert clean_folio("NA") == "" and clean_folio("-") == "" and clean_folio("0") == "" and clean_folio(None) == ""
    assert len(clean_folio("9" * 100)) == 40


# ------------------------------------------------------------------------------------------------------------------ one row

def row(**kw):
    return {"row": 5, "name": "Alpha Bluechip Fund - Direct Plan - Growth", "units": "100.5", **kw}


def test_clean_row_basic_and_cost_forms():
    c = clean_row(row(invested="10,050"), TODAY)
    assert c.units == Decimal("100.5000") and c.invested == Decimal("10050.00") and c.bought_on is None and c.folio == "" and c.row == 5
    c = clean_row(row(avgCost="100.123"), TODAY)
    assert c.invested == Decimal("10062.36")                       # 100.5 x 100.123 = 10062.3615 -> rounded half up to the paisa
    c = clean_row(row(), TODAY)
    assert c.invested is None                                      # no cost given is "unknown", never 0
    c = clean_row(row(invested="10000", avgCost="5", date="01-04-2020", folio="12/3"), TODAY)
    assert c.invested == Decimal("10000.00") and c.bought_on == date(2020, 4, 1) and c.folio == "12/3"   # the total amount wins over per-unit cost


def test_clean_row_units_rules():
    assert clean_row(row(units=""), TODAY).status == "invalid"
    assert clean_row(row(units="abc"), TODAY).status == "invalid"
    r = clean_row(row(units="-10"), TODAY)
    assert r.status == "invalid" and "redemption" in r.reason
    r = clean_row(row(units="0"), TODAY)
    assert r.status == "ignored" and "Zero units" in r.reason
    assert clean_row(row(units="1e12"), TODAY).status == "invalid"
    assert clean_row(row(units="99999999999"), TODAY).status == "invalid"
    c = clean_row(row(units="10.123456"), TODAY)
    assert c.units == Decimal("10.1235") and any("rounded" in w for w in c.warnings)
    assert clean_row(row(units="0.00001"), TODAY).status == "invalid"


def test_clean_row_bad_optional_cells_warn_and_never_become_zero():
    c = clean_row(row(invested="lots", date="someday"), TODAY)
    assert c.invested is None and c.bought_on is None and len(c.warnings) == 2
    c = clean_row(row(invested="-5"), TODAY)
    assert c.invested is None and c.warnings


def test_stock_rows_are_ignored():
    r = clean_row({"row": 1, "name": "Reliance Industries Ltd", "isin": "INE002A01018", "units": "10"}, TODAY)
    assert r.status == "ignored" and "INE" in r.reason
    assert clean_row({"row": 2, "name": "Some Bond", "kind": "Equity Shares", "units": "10"}, TODAY).status == "ignored"
    assert clean_row({"row": 3, "name": "Infosys Limited", "units": "10"}, TODAY).status == "ignored"       # a company name with no fund wording, no ISIN
    assert clean_row({"row": 4, "name": "Nippon India ETF Nifty BeES", "kind": "Equity", "isin": "INF204KB14I2", "units": "10"}, TODAY).units == Decimal("10.0000")   # an ETF is a scheme


def test_strict_lot_reports_every_problem():
    assert strict_lot("10", "1000", None, "2020-01-01", TODAY) == (Decimal("10.0000"), Decimal("1000.00"), date(2020, 1, 1))
    assert strict_lot("10", None, "12.5", None, TODAY)[1] == Decimal("125.00")
    for bad in [dict(units="0"), dict(units="-1"), dict(units=""), dict(units="x"), dict(units="1", invested="-1"), dict(units="1", invested="x"), dict(units="1", invested="5", avg_cost="5"),
                dict(units="1", bought_on="2030-01-01"), dict(units="1", bought_on="nope"), dict(units="0.00001"), dict(units="1", invested="99999999999999")]:
        with pytest.raises(ValueError):
            strict_lot(today=TODAY, **bad)


# ------------------------------------------------------------------------------------------------------------------ matching

def S(code, name, plan="Direct", opt="Growth", active=True, isin="", isin2="", amc="Alpha Mutual Fund"):
    return {"code": code, "name": name, "amc": amc, "plan": plan, "option_class": opt, "option_label": opt, "active": active, "isin": isin, "isin_reinvest": isin2,
            "category": "Equity Scheme - Large Cap Fund", "nav_date": date(2026, 10, 29)}


SCHEMES = [
    S(100001, "Alpha Bluechip Fund - Direct Plan - Growth", isin="INF000A01011"),
    S(100002, "Alpha Bluechip Fund - Regular Plan - Growth", "Regular", isin="INF000A01029"),
    S(100003, "Alpha Bluechip Fund - Direct Plan - IDCW Payout", "Direct", "IDCW", isin="INF000A01037", isin2="INF000A01045"),
    S(100004, "Beta Flexi Cap Fund - Direct Plan - Growth", isin="INF000B01012", amc="Beta Mutual Fund"),
    S(100005, "Delta Small Cap Fund - Direct Plan - Growth", isin="INF000D01013", amc="Delta Mutual Fund"),
    S(100006, "Delta Small Cap Opportunities Fund - Direct Plan - Growth", isin="INF000D01021", amc="Delta Mutual Fund"),
    S(100007, "Gamma Tax Saver (ELSS) Fund - Direct Plan - Growth", isin="INF000G01017", amc="Gamma Mutual Fund"),
    S(100008, "Epsilon Gilt Fund - Growth", "Unspecified", "Growth", isin="INF000E01014", amc="Epsilon Mutual Fund"),
    S(100009, "Zeta Value Fund - Direct Plan - Growth", isin="INF000Z01010", amc="Zeta Mutual Fund"),
    S(100010, "Zeta Value Fund - Direct Plan - Growth (Old)", active=False, isin="INF000Z01028", amc="Zeta Mutual Fund"),
]
IX = Index(SCHEMES)


def m(**kw):
    return match_row(IX, clean_row({"row": 1, "units": "1", **kw}, TODAY))


def test_name_analysis_agrees_across_styles():
    a = analyse("Alpha BlueChip Fund - Direct Plan - Growth Option")
    b = analyse("ALPHA BLUE CHIP FUND (An open ended equity scheme) Dir Gr")
    assert a == b and a[1] == "Direct" and a[2] == "Growth"
    assert analyse("Delta Small-Cap Fund (G)")[0] == analyse("Delta Small Cap Fund")[0]
    assert analyse("Alpha Bluechip Fund (Formerly known as Old Name Fund) - Regular - Dividend")[1:] == ("Regular", "IDCW")


def test_amfi_code_wins_then_isin():
    r = m(amfi="100001", name="")
    assert (r.status, r.via, r.scheme.code) == ("matched", "amfi", 100001)
    r = m(amfi="100001.0", isin="INF000A01011")
    assert (r.status, r.via, r.scheme.code) == ("matched", "amfi", 100001)
    r = m(isin="INF000B01012", name="whatever fund")
    assert r.status == "choose"                                     # the name does not look like the ISIN's scheme: the member checks
    r = m(isin="INF000B01012", name="Beta Flexi Cap Fund")
    assert (r.status, r.via, r.scheme.code) == ("matched", "isin", 100004)
    r = m(isin="INF000A01045")                                      # the IDCW re-investment ISIN belongs to scheme 3
    assert (r.status, r.scheme.code) == ("matched", 100003)
    r = m(amfi="99999", isin="INF000B01012")                        # unknown code falls through to the ISIN
    assert (r.status, r.via, r.scheme.code) == ("matched", "isin", 100004)


def test_conflicts_are_never_resolved_silently():
    r = m(amfi="100001", isin="INF000B01012")
    assert r.status == "choose" and {s.code for s in r.candidates} == {100001, 100004} and r.scheme is None
    r = m(amfi="100001", name="Beta Flexi Cap Fund - Direct Plan - Growth")
    assert r.status == "choose" and r.scheme.code == 100001 and "does not look like" in r.reason


def test_exact_name_with_plan_and_option():
    for name in ("Alpha Bluechip Fund - Direct Plan - Growth", "ALPHA BLUECHIP FUND DIRECT GROWTH", "Alpha Blue Chip Fund (Direct) (G)"):
        r = m(name=name)
        assert (r.status, r.via, r.scheme.code) == ("matched", "name", 100001), name
    assert m(name="Alpha Bluechip Fund - Regular Plan - Growth").scheme.code == 100002
    assert m(name="Alpha Bluechip Fund - Direct - IDCW").scheme.code == 100003


def test_a_name_without_plan_or_option_is_not_guessed_unless_the_fund_has_one_scheme():
    r = m(name="Alpha Bluechip Fund")
    assert r.status == "choose" and {s.code for s in r.candidates} == {100001, 100002, 100003}
    r = m(name="Alpha Bluechip Fund - Growth")
    assert r.status == "choose" and {s.code for s in r.candidates} == {100001, 100002}                       # Direct or Regular?
    assert m(name="Beta Flexi Cap Fund").scheme.code == 100004                                           # the only scheme of that fund
    assert m(name="Epsilon Gilt Fund").scheme.code == 100008


def test_plan_not_in_family_asks():
    r = m(name="Beta Flexi Cap Fund - Regular Plan - Growth")
    assert r.status == "choose" and [s.code for s in r.candidates] == [100004] and "not in the plan" in r.reason


def test_an_active_scheme_is_preferred_over_a_stopped_twin():
    r = m(name="Zeta Value Fund - Direct Plan - Growth")
    assert (r.status, r.scheme.code) == ("matched", 100009)


def test_fuzzy_only_suggests():
    r = m(name="Delta Small Cap Opportunities Equity Fund Direct Growth")
    assert r.status == "choose" and r.via == "fuzzy" and r.scheme is None and 100006 in {s.code for s in r.candidates}
    assert m(name="Completely Unknown Thing Fund").status == "not_found"
    assert m(name="").status == "not_found"
    r = m(name="Delta Small Fund")
    assert r.status in ("choose", "not_found") and r.scheme is None


# ------------------------------------------------------------------------------------------------------------------ the maths

def lot(units, invested, d=None, i="x"):
    return {"id": i, "units": Decimal(str(units)), "invested": None if invested is None else Decimal(str(invested)), "bought_on": d}


def scheme(**kw):
    base = {"nav": 25.1234, "nav_date": date(2026, 10, 29), "active": True}
    return {**base, **kw}


def test_value_holding_money_is_rounded_half_up():
    h = {"id": "a", "code": 1, "folio": "", "lots": [lot("100.5", "2000.005")]}
    v = calc.value_holding(h, scheme(), date(2026, 10, 29))
    assert v["units"] == 100.5 and v["invested"] == 2000.01 and v["current"] == 2524.9                    # 100.5 x 25.1234 = 2524.9017 -> 2524.90
    assert v["gain"] == round(2524.90 - 2000.01, 2) and v["gainPct"] == round((2524.90 - 2000.01) / 2000.01 * 100, 2)
    assert v["navDate"] == "2026-10-29" and v["nav"] == 25.1234 and not v["navStale"] and v["gainWhy"] is None


def test_unknown_cost_is_unknown_not_zero():
    h = {"id": "a", "code": 1, "folio": "", "lots": [lot(10, None), lot(5, 100)]}
    v = calc.value_holding(h, scheme(), date(2026, 10, 29))
    assert v["invested"] is None and v["gain"] is None and v["gainPct"] is None and "not known" in v["investedWhy"] and v["investedWhy"] in (v["gainWhy"],)
    assert v["current"] == round(15 * 25.1234, 2)


def test_zero_cost_gives_no_percentage():
    v = calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": [lot(10, 0)]}, scheme(), date(2026, 10, 29))
    assert v["invested"] == 0 and v["gain"] is None and "Nothing was paid" in v["gainWhy"]


def test_no_nav_means_no_value_with_reason():
    v = calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": [lot(10, 100)]}, scheme(nav=None, nav_date=None), date(2026, 10, 29))
    assert v["current"] is None and "no NAV" in v["currentWhy"] and v["gain"] is None and v["gainWhy"] == v["currentWhy"]
    v = calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": [lot(10, 100)]}, None, date(2026, 10, 29))
    assert v["current"] is None and "no longer" in v["currentWhy"]


def test_stale_nav_is_flagged_with_its_date():
    v = calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": [lot(10, 100)]}, scheme(nav_date=date(2026, 9, 1)), date(2026, 10, 29))
    assert v["navStale"] and "01 Sep 2026" in v["navNote"]
    v = calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": [lot(10, 100)]}, scheme(active=False), date(2026, 10, 29))
    assert v["navStale"] and "stopped" in v["navNote"]


def test_xirr_single_lot_equals_cagr():
    # 10,000 on 2023-10-29 -> 12,100 on 2025-10-29 (731 days) : (1.21)^(365/731) - 1
    h = {"id": "a", "code": 1, "folio": "", "lots": [lot(100, 10000, date(2023, 10, 29))]}
    v = calc.value_holding(h, scheme(nav=121.0, nav_date=date(2025, 10, 29)), date(2025, 10, 29))
    assert v["xirrKind"] == "cagr" and v["xirrWhy"] is None
    assert v["xirr"] == pytest.approx(((12100 / 10000) ** (365 / 731) - 1) * 100, abs=0.01)


def test_xirr_matches_a_known_spreadsheet_answer():
    # -10000 on 2022-01-01, -10000 on 2023-01-01, +25000 on 2024-01-01 (365 and 730 days): solving 25000x^2 - 10000x - 10000 = 0 with x = 1/(1+r) gives r = 15.83% a year
    h = {"id": "a", "code": 1, "folio": "", "lots": [lot(100, 10000, date(2022, 1, 1), "a"), lot(100, 10000, date(2023, 1, 1), "b")]}
    v = calc.value_holding(h, scheme(nav=125.0, nav_date=date(2024, 1, 1)), date(2024, 1, 1))
    assert v["xirrKind"] == "xirr" and v["xirr"] == pytest.approx(15.83, abs=0.01)


@pytest.mark.parametrize("lots,nav_date,frag", [
    ([lot(10, 100, None)], date(2026, 10, 29), "purchase date"),
    ([lot(10, 100, date(2020, 1, 1)), lot(10, 100, None)], date(2026, 10, 29), "every purchase"),
    ([lot(10, None, date(2020, 1, 1))], date(2026, 10, 29), "not known"),
    ([lot(10, 100, date(2026, 6, 1))], date(2026, 10, 29), "under a year"),
    ([lot(10, 100, date(2026, 11, 1))], date(2026, 10, 29), "after the latest NAV"),
    ([lot(10, 0, date(2020, 1, 1))], date(2026, 10, 29), "Nothing was paid"),
])
def test_xirr_is_blank_with_a_reason(lots, nav_date, frag):
    v = calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": lots}, scheme(nav_date=nav_date), nav_date)
    assert v["xirr"] is None and frag in v["xirrWhy"]


def test_summary_totals_cover_only_comparable_funds_and_say_so():
    a = {**calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": [lot(10, 200)]}, scheme(nav=30), date(2026, 10, 29)), "amc": "X", "categoryLabel": "Large Cap", "name": "A"}
    b = {**calc.value_holding({"id": "b", "code": 2, "folio": "", "lots": [lot(10, None)]}, scheme(nav=40), date(2026, 10, 29)), "amc": "X", "categoryLabel": "Large Cap", "name": "B"}
    c = {**calc.value_holding({"id": "c", "code": 3, "folio": "", "lots": [lot(10, 100)]}, scheme(nav=None, nav_date=None), date(2026, 10, 29)), "amc": "Y", "categoryLabel": "Debt", "name": "C"}
    for r in (a, b, c):
        r["score"] = {"final": None}
    s = calc.summarize([a, b, c], score_locked=True)
    assert s["funds"] == 3 and s["valued"] == 2 and s["withCost"] == 1
    assert s["current"] == 700.0 and s["invested"] == 200.0 and s["gain"] == 100.0 and s["gainPct"] == 50.0
    assert len(s["notes"]) == 2 and "could not be valued" in s["notes"][0] and "covers 1 of 2" in s["notes"][1]
    assert s["score"] == {"locked": True, "value": None, "label": None, "why": None}
    assert s["navFrom"] == s["navTo"] == "2026-10-29"


def test_weighted_score_needs_every_fund_scored():
    def mk(cur, final):
        return {"current": cur, "invested": cur, "navDate": "2026-10-29", "xirr": None, "lots": [], "score": {"final": final}}
    s = calc.summarize([mk(300, 80), mk(100, 60)], score_locked=False)
    assert s["score"]["value"] == 75.0 and s["score"]["label"] == "Healthy" and s["score"]["why"] is None            # (300x80 + 100x60) / 400
    s = calc.summarize([mk(300, 80), mk(100, None)], score_locked=False)
    assert s["score"]["value"] is None and "1 of 2 funds has no score" in s["score"]["why"]
    assert calc.summarize([], score_locked=False)["score"]["value"] is None


def rows_for_alloc():
    def r(name, amc, cat, cur):
        return {"name": name, "amc": amc, "categoryLabel": cat, "current": cur}
    return [r("A", "X MF", "Large Cap", 600), r("B", "X MF", "Flexi Cap", 300), r("C", "Y MF", "Large Cap", 100), r("D", "Z MF", "Debt", None)]


def test_allocation_shares_add_to_the_whole():
    a = calc.allocation(rows_for_alloc())
    assert a["byCategory"] == [{"label": "Large Cap", "value": 700.0, "pct": 70.0}, {"label": "Flexi Cap", "value": 300.0, "pct": 30.0}]
    assert a["byAmc"][0] == {"label": "X MF", "value": 900.0, "pct": 90.0}
    assert calc.allocation([])["byAmc"] == []


def test_concentration_is_plain_and_never_advice():
    c = calc.concentration(rows_for_alloc())
    assert c["top1Pct"] == 60.0 and c["top3Pct"] == 100.0 and c["level"] == "concentrated"
    assert "60% of the current value" in c["text"] and "90% sits with one fund house (X MF)" in c["text"]
    assert not any(w in c["text"].lower() for w in ("buy", "sell", "should", "switch", "redeem", "reduce", "diversify"))
    one = calc.concentration([{"name": "Solo", "amc": "X", "categoryLabel": "c", "current": 10}])
    assert "one fund" in one["text"] and one["level"] == "concentrated"
    spread = calc.concentration([{"name": f"F{i}", "amc": f"A{i}", "categoryLabel": "c", "current": 100} for i in range(10)])
    assert spread["level"] == "spread" and spread["top1Pct"] == 10.0
    assert calc.concentration([])["level"] is None


# ------------------------------------------------------------------------------------------------------------------ a fund that is only followed

def test_a_followed_fund_has_no_money_figures_and_is_never_valued_as_zero():
    v = calc.value_holding({"id": "a", "code": 1, "folio": "", "lots": []}, scheme(), date(2026, 10, 29))
    assert v["followed"] is True and v["units"] is None and v["current"] is None and v["invested"] is None and v["gain"] is None and v["xirr"] is None
    assert "No units were added" in v["currentWhy"] and v["nav"] == 25.1234 and v["navDate"] == "2026-10-29"


def test_followed_funds_are_not_reported_as_unvalued_and_share_the_score_equally():
    def mk(final):
        return {"followed": True, "current": None, "invested": None, "navDate": "2026-10-29", "xirr": None, "lots": [], "score": {"final": final}}
    s = calc.summarize([mk(80), mk(60)], score_locked=False)
    assert s["valued"] == 0 and s["notes"] == [] and s["score"]["value"] == 70.0 and s["score"]["funds"] == 2
    held = {"current": 300, "invested": 300, "navDate": "2026-10-29", "xirr": None, "lots": [], "score": {"final": 80}}
    m = calc.summarize([held, mk(10)], score_locked=False)
    assert m["score"]["value"] == 80.0 and m["notes"] == []               # beside a fund with a value, a followed one stays out of the weighted score
