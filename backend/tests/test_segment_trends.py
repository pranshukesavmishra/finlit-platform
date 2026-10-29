"""Segment history insights: pure functions, the recorded Reliance fixture and synthetic edge cases."""

import json
from pathlib import Path

import pytest

from finlit.normalize import events, segment_trends as st

FIX = Path(__file__).parent / "fixtures" / "finedge" / "segment_revenue_reliance_period_annual_statement_code_pl.json"
CR = 10_000_000  # rupees per crore


def payload(years, **segs):
    """Provider-shaped payload. years: [2019, ...]; segs: name -> list of revenue (crore, None = absent) or (rev, ebit) pairs."""
    rows = []
    for i, y in enumerate(years):
        items = []
        for name, series in segs.items():
            v = series[i]
            if v is None:
                continue
            rev, ebit = v if isinstance(v, tuple) else (v, None)
            data = {"segmentRevenue": rev * CR}
            if ebit is not None:
                data["segmentProfitLossBeforeTaxAndFinanceCosts"] = ebit * CR
            items.append({"name": name.replace("_", " "), "data": data})
        rows.append({"header": f"Mar {y}", "segments": items})
    return {"segment_revenues": rows[::-1]}  # the provider lists newest first


def ins(years, **segs):
    return events.segments(payload(years, **segs))["insights"]


def row(i, name):
    return next(r for r in i["rows"] if r["name"] == name)


# ---------------------------------------------------------------- the recorded fixture

@pytest.fixture(scope="module")
def real():
    return events.segments(json.loads(FIX.read_text()))


def test_real_fixture_keeps_all_eight_years_and_the_old_shape(real):
    assert real["periods"] == [f"FY{y}" for y in range(19, 27)]
    assert real["unit"] == "Cr" and real["latest"] and set(real["latest"][0]) >= {"name", "revenue", "sharePct", "growthPct"}
    assert "Petrochemicals" in real["segments"] and "Financial Services" in real["segments"]  # history kept
    assert all(len(v["revenue"]) == 8 and len(v["ebit"]) == 8 for v in real["segments"].values())
    # the latest-year strip still only has segments that report in FY26
    assert {s["name"] for s in real["latest"]} <= {n for n, v in real["segments"].items() if v["revenue"][-1]}
    assert "Petrochemicals" not in {s["name"] for s in real["latest"]}
    assert sum(s["sharePct"] for s in real["latest"]) == pytest.approx(100, abs=0.1)


def test_real_fixture_trends(real):
    i = real["insights"]
    assert i["status"] == "ok" and i["latestPeriod"] == "FY26"
    og = row(i, "Oil and Gas")  # "Oil & Gas" and "Oil and Gas" are one segment, FY19..FY26 unbroken
    assert og["window"] == ["FY19", "FY26"] and og["years"] == 8
    assert og["cagrPct"] == pytest.approx(((23765 / 2613) ** (1 / 7) - 1) * 100, abs=0.1)
    assert og["trend"] == "growing" and og["shareChangePp"] > 0
    assert row(i, "Petrochemicals")["trend"] == "discontinued" and row(i, "Petrochemicals")["lastReported"] == "FY20"
    assert row(i, "Financial Services")["lastReported"] == "FY23" and row(i, "Financial Services")["cagrPct"] is None
    assert row(i, "Digital Services")["window"] == ["FY21", "FY26"]
    # FY24: Others jumps ~18x while O2C falls by a similar amount -> flagged, not adjusted
    assert row(i, "Others")["definitionChanged"] and row(i, "Others")["windowAffected"]
    assert row(i, "Oil to Chemicals (O2C)")["definitionChanged"]
    assert row(i, "Petrochemicals")["definitionChanged"]
    # numbers are not adjusted
    assert real["segments"]["Others"]["revenue"][-3] == pytest.approx(41120.0, abs=1)


def test_real_fixture_sentences_are_neutral_numbered_and_capped(real):
    i = real["insights"]
    assert 1 <= len(i["sentences"]) <= st.MAX_SENTENCES
    text = " ".join(i["sentences"] + i["cautions"]).lower()
    for word in ("buy", "sell", "hold ", "avoid", "accumulate", "target", "reduce", "recommend"):
        assert word not in text
    assert all(any(c.isdigit() for c in s) for s in i["sentences"])
    assert any("FY19" in s and "FY26" in s for s in i["sentences"])
    assert not any(s.startswith(("Others", "Oil to Chemicals")) for s in i["sentences"])  # windows with a flagged break make no headline claim
    assert any("Segment definitions can change" in c for c in i["cautions"])
    assert "inter-segment" in i["basis"].lower()


# ---------------------------------------------------------------- pure helpers

def test_cagr():
    assert st.cagr_pct(100, 121, 3) == pytest.approx(10.0)
    assert st.cagr_pct(0, 5, 3) is None and st.cagr_pct(-1, 5, 3) is None and st.cagr_pct(5, 0, 3) is None


def test_window_stops_at_gap_or_nonpositive():
    yrs = [19, 20, 21, 22, 23]
    assert st.comparable_window([1, 2, None, 4, 5], yrs) == (3, 4)
    assert st.comparable_window([1, 2, 0, 4, 5], yrs) == (3, 4)
    assert st.comparable_window([1, 2, 3, 4, 5], yrs) == (0, 4)
    assert st.comparable_window([1, 2, 3, 4, None], yrs) == (None, None)
    assert st.comparable_window([1, 2, 3, 4, 5], [19, 20, 22, 23, 24]) == (2, 4)  # a missing fiscal year breaks the run
    assert st.comparable_window([], []) == (None, None)


# ---------------------------------------------------------------- tags and edge cases

Y = list(range(2020, 2027))  # FY20..FY26


def test_growing_declining_steady_thresholds():
    i = ins(Y, A=[100, 110, 121, 133, 146, 161, 177], B=[100, 98, 96, 94, 92, 90, 88], C=[100, 101, 102, 103, 104, 105, 106])
    assert row(i, "A")["trend"] == "growing"   # +10% a year
    assert row(i, "B")["trend"] == "declining"  # about -2.1% a year
    assert row(i, "C")["trend"] == "steady"
    assert row(i, "A")["cagrPct"] == pytest.approx(9.99, abs=0.05)


def test_growth_boundary_and_share_loss_rule():
    # exactly 5% a year, share rising: Growing. A grows 5% but the rest grows far faster: share falls > 2 pp -> Steady.
    i = ins([2024, 2025, 2026], A=[100, 105, 110.25], B=[100, 100, 100])
    assert row(i, "A")["trend"] == "growing"
    j = ins([2024, 2025, 2026], A=[100, 105, 110.25], B=[100, 300, 900])
    assert row(j, "A")["trend"] == "steady" and row(j, "A")["shareChangePp"] < -2


def test_gap_in_a_segment_shortens_its_window():
    i = ins(Y, A=[10, 20, None, 40, 50, 60, 70], B=[100] * 7)
    a = row(i, "A")
    assert a["window"] == ["FY23", "FY26"] and a["years"] == 4 and a["gap"] is True
    assert any("gaps" in c for c in i["cautions"])


def test_single_year_and_short_history():
    i = ins([2026], A=[100], B=[50])
    assert i["status"] == "short" and i["sentences"] == [] and "no trends" in i["statusText"]
    assert row(i, "A")["trend"] == "short" and row(i, "A")["cagrPct"] is None and row(i, "A")["years"] == 1
    j = ins([2025, 2026], A=[100, 120], B=[50, 40])
    assert j["status"] == "short" and row(j, "A")["yoyPct"] == pytest.approx(20.0) and row(j, "A")["cagrPct"] is None


def test_new_segment():
    i = ins(Y, A=[100] * 7, N=[None] * 5 + [5, 20])
    n = row(i, "N")
    assert n["trend"] == "new" and n["firstReported"] == "FY25" and n["cagrPct"] is None and n["years"] == 2
    # but a segment that is simply there from the first year of data is not "New", even with a short history
    k = ins([2024, 2025, 2026], A=[100, 100, 100], B=[10, 12, 14])
    assert row(k, "B")["trend"] != "new"


def test_disappearing_segment_and_same_year_new_segment_is_flagged():
    i = ins(Y, A=[100] * 7, P=[50, 50, 50, None, None, None, None], Q=[None, None, None, 60, 70, 80, 90])
    p, q = row(i, "P"), row(i, "Q")
    assert p["trend"] == "discontinued" and p["lastReported"] == "FY22" and p["note"] == "Not reported in FY26; last reported in FY22."
    assert p["definitionChanged"] and q["definitionChanged"] and q["definitionYear"] == "FY23"
    assert not row(i, "A")["definitionChanged"]
    assert any("before FY23" in c and "P" in c for c in i["cautions"])


def test_disappearing_segment_without_a_new_one_is_not_a_definition_change():
    i = ins(Y, A=[100] * 7, P=[50, 50, 50, 50, None, None, None])
    p = row(i, "P")
    assert p["trend"] == "discontinued" and not p["definitionChanged"]
    assert any("P (last reported FY23)" in s for s in i["sentences"])


def test_renamed_segment_shows_as_stop_plus_start_and_is_flagged():
    i = ins(Y, Old=[40, 42, 44, 46, None, None, None], New=[None, None, None, None, 50, 54, 58], Core=[100] * 7)
    assert row(i, "Old")["definitionChanged"] and row(i, "New")["definitionChanged"]
    assert row(i, "Old")["trend"] == "discontinued" and row(i, "New")["years"] == 3


def test_reclassification_jump_is_flagged_not_adjusted_and_excluded_from_claims():
    series = dict(Big=[500, 510, 520, 300, 305, 310, 315], Other=[10, 11, 12, 232, 235, 240, 245], Z=[100, 100, 100, 100, 100, 100, 100])
    p = events.segments(payload(Y, **series))
    i = p["insights"]
    assert row(i, "Other")["definitionChanged"] and row(i, "Big")["definitionChanged"] and row(i, "Other")["windowAffected"]
    assert p["segments"]["Other"]["revenue"][3] == 232.0  # numbers untouched
    assert not any(s.startswith(("Other", "Big")) for s in i["sentences"])
    assert not row(i, "Z")["definitionChanged"]


def test_a_jump_without_an_offset_is_only_a_caution():
    i = ins(Y, A=[100, 100, 100, 400, 410, 420, 430], B=[100] * 7)
    assert not row(i, "A")["definitionChanged"]
    assert any("more than three times" in c and "A (FY23)" in c for c in i["cautions"])


def test_all_zero_or_empty_segment_is_dropped():
    p = events.segments(payload(Y, A=[100] * 7, Z=[0] * 7, E=[None] * 7))
    assert list(p["segments"]) == ["A"]
    assert p["insights"]["status"] == "single" and p["insights"]["statusText"] == "This company reports a single business segment."
    assert p["insights"]["rows"] == [] and p["insights"]["sentences"] == []


def test_segment_that_turns_zero_in_latest_year_is_discontinued():
    i = ins(Y, A=[100] * 7, B=[10, 10, 10, 10, 10, 10, 0])
    assert row(i, "B")["trend"] == "discontinued" and row(i, "B")["lastReported"] == "FY25"


def test_negative_ebit_margin_and_change():
    i = ins(Y, A=[(100, -10), (100, -8), (100, -5), (100, 0), (100, 5), (100, 8), (100, 10)], B=[100] * 7)
    a = row(i, "A")
    assert a["marginPct"] == pytest.approx(10.0) and a["marginChangePp"] == pytest.approx(20.0)
    j = ins(Y, A=[(100, 10), (100, 5), (100, 0), (100, -3), (100, -5), (100, -8), (100, -12)], B=[100] * 7)
    assert row(j, "A")["marginPct"] == pytest.approx(-12.0) and row(j, "A")["marginChangePp"] == pytest.approx(-22.0)


def test_missing_ebit_gives_no_margin():
    i = ins(Y, A=[100] * 7, B=[100] * 7)
    assert row(i, "A")["marginPct"] is None and row(i, "A")["marginChangePp"] is None


def test_names_differing_only_by_ampersand_are_one_segment():
    p = events.segments(payload(Y, **{"Oil_&_Gas": [10, 11, 12, None, None, None, None], "Oil_and_Gas": [None, None, None, 13, 14, 15, 16], "X": [50] * 7}))
    assert [n for n in p["segments"] if "Gas" in n] == ["Oil and Gas"]
    assert row(p["insights"], "Oil and Gas")["window"] == ["FY20", "FY26"]


def test_bank_like_segment_tables_and_no_data_do_not_break():
    bank = ins(Y, **{"Treasury": [30, 31, 32, 33, 35, 36, 38], "Corporate_Wholesale_Banking": [40, 41, 45, 50, 52, 58, 60], "Retail_Banking": [70, 75, 82, 90, 100, 112, 125], "Other_Banking": [2, 2, 2, 3, 3, 3, 3]})
    assert bank["status"] == "ok" and len(bank["rows"]) == 4
    for payload_ in (None, {}, {"segment_revenues": []}, {"segment_revenues": None}, [], "junk", {"segment_revenues": [{"header": "Mar 2026", "segments": []}]}):
        out = events.segments(payload_)
        assert out["insights"]["status"] == "none" and out["insights"]["statusText"] == "Segment history is not available for this company."
        assert out["segments"] == {} and out["latest"] == []


def test_junk_values_never_raise():
    out = st.build_insights(["FY25", "FY26", "oops"], {"A": {"revenue": [1, "x", None], "ebit": None}, "B": {"revenue": [float("nan"), 2]}, "C": "bad"})
    assert out["status"] in ("short", "ok", "single", "none")
    assert st.build_insights([], {})["status"] == "none"


def test_percentages_are_computed_from_unrounded_values():
    # 3 comparable years; CAGR from exact 100 -> 133.3333 must not use a pre-rounded share
    i = ins([2024, 2025, 2026], A=[100.004, 120, 133.336], B=[50, 50, 50])
    assert row(i, "A")["cagrPct"] == pytest.approx(((133.336 / 100.004) ** 0.5 - 1) * 100, abs=0.01)


def test_shares_sum_and_changes_are_consistent():
    i = ins(Y, A=[60, 60, 60, 60, 60, 60, 60], B=[40, 50, 60, 70, 80, 90, 100])
    a, b = row(i, "A"), row(i, "B")
    assert a["shareStartPct"] + b["shareStartPct"] == pytest.approx(100, abs=0.02)
    assert a["sharePct"] + b["sharePct"] == pytest.approx(100, abs=0.02)
    assert b["shareChangePp"] == pytest.approx(-a["shareChangePp"], abs=0.02)
    assert any("gained the most share" in s and s.startswith("B ") for s in i["sentences"])
    assert any("lost the most share" in s and s.startswith("A ") for s in i["sentences"])


def test_at_most_five_sentences():
    many = {f"S{k}": [100 + k * 3 * j * (1 if k % 2 else -1) for j in range(7)] for k in range(1, 6)}
    many["Gone"] = [30, 30, None, None, None, None, None]
    assert len(ins(Y, **many)["sentences"]) <= 5


def test_the_stored_shape_stays_backward_compatible():
    p = events.segments(payload(Y, A=[100] * 7, B=[50] * 7))
    assert {"unit", "periods", "segments", "latest", "insights"} == set(p)
    assert p["periods"] == [f"FY{y % 100}" for y in Y]


def test_others_is_never_named_fastest_or_a_share_mover():
    i = ins(Y, Others=[10, 20, 40, 80, 160, 320, 640], A=[100] * 7, B=[100, 101, 102, 103, 104, 105, 106])
    assert not any(s.startswith("Others") for s in i["sentences"])
    assert row(i, "Others")["cagrPct"] > 50  # still in the table


def test_fastest_growth_sentence_mentions_a_big_single_year_jump():
    i = ins(Y, A=[100, 100, 100, 400, 410, 420, 430], B=[100] * 7)
    assert any(s.startswith("A had the fastest") and "FY23" in s and "more than three times" in s for s in i["sentences"])
