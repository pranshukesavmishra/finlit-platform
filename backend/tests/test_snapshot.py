import json

from finlit.snapshot import PRICE_RANGES, SECTIONS, build, score_row


def test_all_sections_present(reliance_sections):
    assert set(SECTIONS) <= set(reliance_sections)
    assert {f"price-{r}" for r in PRICE_RANGES} <= set(reliance_sections)
    for name, section in reliance_sections.items():
        assert section["meta"]["symbol"] == "RELIANCE", name


def test_summary_is_small_and_complete(reliance_sections):
    summary = reliance_sections["summary"]
    assert len(json.dumps(summary, separators=(",", ":"))) < 20_000
    assert summary["quote"]["price"] > 0
    assert summary["score"]["overall"] is not None
    assert summary["thesis"]
    assert summary["dataQuality"]["missing"] == []
    keys = {m["key"] for m in summary["keyMetrics"]}
    assert {"market_cap", "pe", "roe"} <= keys
    assert all(m["label"] != m["key"] for m in summary["keyMetrics"])  # every metric has a glossary label


def test_dividend_metrics_are_sane(reliance_sections):
    summary = reliance_sections["summary"]
    dy = next(m["value"] for m in summary["keyMetrics"] if m["key"] == "dividend_yield")
    assert 0 < dy < 5
    for r in summary["returns"]:
        assert r["dividend"] is None or r["dividend"] < 5  # the old site showed 89.14%


def test_missing_payloads_degrade(reliance_bundle):
    sections = build({"symbol": "RELIANCE", "profile": reliance_bundle["profile"]})
    summary = sections["summary"]
    assert "pl_annual" in summary["dataQuality"]["missing"]
    assert summary["score"]["band"]["key"] == "insufficient"
    assert sections["price"]["daily"]["t"] == []


def test_score_row(reliance_sections):
    row = score_row(reliance_sections)
    assert row["symbol"] == "RELIANCE" and row["band"] in {"strong", "healthy", "mixed", "watch"}


def test_price_ranges(reliance_sections):
    one_month = reliance_sections["price-1M"]["series"]
    assert 15 <= len(one_month["t"]) <= 24 and "o" in one_month
    weekly = reliance_sections["price-MAX"]["series"]
    assert len(weekly["t"]) < len(reliance_sections["price"]["daily"]["t"]) / 4
    assert reliance_sections["price-MAX"]["grain"] == "weekly"
