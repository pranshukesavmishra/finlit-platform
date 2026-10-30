"""A NOT RATED report must say exactly why (classification label, thin history, low coverage)."""
import json
from datetime import date
from pathlib import Path

from backend.premium_data import adapt_inputs
from backend.premium_engine import score_company
from backend.premium_presentation import build_report_review
from backend.premium_classification import CLASSIFICATION_VERSION
from backend.tests.test_premium_reports import sample_report

AS_OF = date(2026, 10, 18)


def example():
    return json.loads(Path(__file__).with_name("premium_example.json").read_text())


def adapt(profile):
    return adapt_inputs({"profile": profile, "quarterly": {"financials": []}}, "X", AS_OF, "consolidated")


def test_bajaj_finserv_style_labels_are_not_blocked():
    d, group, _, meta, _, _ = adapt({"industry": "Finance", "sector": "Holding Companies", "sub_industry": "Holding Companies", "macro_sector": "Financial Services"})
    assert group == "NBFC" and not meta["groupDefaulted"] and not d["rating_blockers"]
    assert meta["classificationVersion"] == CLASSIFICATION_VERSION


def test_unmapped_label_blocker_names_the_label():
    d, group, _, meta, _, _ = adapt({"industry": "Zzyzx Widgets", "sector": "Zzyzx Widgets"})
    assert len(d["rating_blockers"]) == 1 and 'no model group for this industry yet ("Zzyzx Widgets")' in d["rating_blockers"][0]
    assert "inputs were available" in d["rating_blockers"][0]
    assert meta["groupLabel"] == "Zzyzx Widgets"
    data = example()
    data["rating_blockers"] = d["rating_blockers"]
    result = score_company(data, "MFG")
    assert result["status"] == "NOT RATED" and result["confidence"] == 1
    assert result["notRatedReasons"][0]["code"] == "classification"
    assert result["headline"] == "Not rated: " + d["rating_blockers"][0]
    report = sample_report(data)
    report["inputs"] = {"rating_blockers": d["rating_blockers"], "rating_cautions": []}
    notes = build_report_review(report)["notes"]
    assert any('no model group for this industry yet ("Zzyzx Widgets")' in n for n in notes)
    # 100% of inputs found, yet withheld: the page explains the two figures
    assert any("share of model inputs that were found" in n for n in notes)
    assert not any("insufficient verified information" in n for n in notes)


def test_short_history_and_low_confidence_have_their_own_messages():
    data = example()
    for key in ("sales_q", "net_profit_q", "operating_profit_q", "eps_q"): data[key] = data[key][-2:]
    data["sales_y"] = data["sales_y"][-1:]
    result = score_company(data, "MFG")
    assert result["status"] == "NOT RATED"
    codes = [r["code"] for r in result["notRatedReasons"]]
    assert "insufficient_history" in codes
    assert "Not enough reported history" in result["headline"]
    empty = score_company({}, "BANK")
    assert "low_confidence" in [r["code"] for r in empty["notRatedReasons"]]
    assert "Only 0% of the inputs" in " ".join(r["text"] for r in empty["notRatedReasons"])
