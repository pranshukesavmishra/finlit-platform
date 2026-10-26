"""Compliance: the PDF (premium_pdf.py, identical to upstream) must never show the model's buy/sell words, and the web and PDF share one table."""
import itertools
import json
import re
from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from backend import premium_pdf, technical_wording as tw
from backend.premium_technical import build_technical_assessment, resolve_technical_prices, score_rating
from backend.tests.test_premium_reports import sample_report
from backend.tests.test_premium_technical import ASOF, benchmarks, candles

BANNED = re.compile(r"\b(?:buy|buys|buying|bought|sell|sells|selling|sold|hold|holds|holding|reduce|reduces|reduced|reducing|avoid\w*|accumulat\w*|target\w*)\b", re.I)
FRONTEND_COPY = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "technicalWording.json"


def pdf_text(report):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(tw.render_compliant_pdf(report))).pages)


@pytest.fixture(scope="module")
def base_report():
    example = json.loads(Path(__file__).with_name("premium_example.json").read_text())
    report = sample_report(example)
    bars = candles()
    report["technicalAssessment"] = build_technical_assessment(resolve_technical_prices(bars, "FinEdge", ASOF), ASOF, benchmarks(bars), 1000)
    return report


def test_web_and_pdf_read_one_identical_wording_file():
    assert FRONTEND_COPY.read_bytes() == Path(tw.__file__).with_name("technical_wording.json").read_bytes()


def test_stored_model_words_are_advice_words_so_the_relabel_is_needed(base_report):
    # The stored report carries the model's own words (the scan below would fail without the relabel).
    tech = base_report["technicalAssessment"]
    assert BANNED.search(" ".join([tech["shortTerm"]["rating"], tech["longTerm"]["rating"], tech["verdict"]["label"]]))
    assert any(BANNED.search(f["label"]) or "Buying" in f["label"] for f in tech["shortTerm"]["factors"])


def test_full_assessment_pdf_has_no_advice_word(base_report):
    text = pdf_text(base_report)
    assert "Short & long-term assessment" in text
    assert BANNED.findall(text) == []


@pytest.mark.parametrize("st,lt", list(itertools.product((60, 30, 0, -30, -60), repeat=2)))
def test_every_rating_and_verdict_combination_is_relabelled(base_report, st, lt):
    report = deepcopy(base_report)
    tech = report["technicalAssessment"]
    for key, score in (("shortTerm", st), ("longTerm", lt)):
        tech[key]["score"], tech[key]["rating"] = score, score_rating(score)
    from backend.premium_technical import combine_verdict
    tech["verdict"] = combine_verdict(st, lt)
    text = pdf_text(report)
    assert BANNED.findall(text) == []
    words = {"Strongly positive", "Positive", "Neutral", "Negative", "Strongly negative"}
    assert any(w in text for w in words)
    assert re.search(r"Trend: (positive|mixed|negative)", text)


def test_unavailable_assessment_and_unknown_words(base_report):
    report = deepcopy(base_report)
    report["technicalAssessment"] = build_technical_assessment({}, ASOF)
    text = pdf_text(report)
    assert "Trend: not available" in text and BANNED.findall(text) == []
    report = deepcopy(base_report)
    tech = report["technicalAssessment"]
    tech["shortTerm"]["rating"] = "Accumulate"
    tech["notes"] = ["Avoid chasing; the target was reached and holders may sell."]
    tech["shortTerm"]["factors"][0]["detail"] = "Buyers hold the line; stop and exit."
    assert BANNED.findall(pdf_text(report)) == []


def test_relabel_does_not_change_the_stored_report(base_report):
    before = json.dumps(base_report, sort_keys=True)
    tw.render_compliant_pdf(base_report)
    assert json.dumps(base_report, sort_keys=True) == before
    assert base_report["technicalAssessment"]["shortTerm"]["rating"] in ("Strong Buy", "Buy", "Hold", "Reduce", "Sell")


@pytest.mark.parametrize("score,word", [(50, "Strongly positive"), (49.99, "Positive"), (20, "Positive"), (19.99, "Neutral"), (-19.99, "Neutral"),
                                        (-20, "Negative"), (-49.99, "Negative"), (-50, "Strongly negative"), (None, "Not available")])
def test_python_boundaries_match_the_model(score, word):
    assert tw.rating_word(score_rating(score), score) == word
    assert tw.rating_word("something unknown", score) == word


def test_safe_text_is_idempotent_and_keeps_case():
    once = tw.safe_text("Buying and selling volume")
    assert once == "Volume flow (on-balance volume)" and tw.safe_text(once) == once
    assert tw.safe_text("Stop. Target price held.") == "Pause. Price forecast held."
    assert tw.safe_text("Holds back the assessment.") == "Weighs on the assessment."


def test_pdf_route_serves_the_relabelled_pdf(monkeypatch, base_report):
    from backend import server
    from backend.tests.test_premium_reports import asgi_request, auth, memory_report
    memory_report(monkeypatch, deepcopy(base_report))
    status, pdf = asgi_request(server.app, "GET", "/api/premium-reports/" + "a" * 32 + "/pdf", headers=auth())
    assert status == 200 and pdf.startswith(b"%PDF")
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    assert "Trend:" in text and BANNED.findall(text) == []
