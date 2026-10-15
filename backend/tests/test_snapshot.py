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


def test_corrections_from_page_audit(reliance_sections):
    s = reliance_sections
    metrics = {m["key"]: m for m in s["summary"]["keyMetrics"]}
    # 1. P/E re-priced at the live quote (41.36x at the 28 Sep close of 1,198.50 -> 1,184)
    assert metrics["pe"]["value"] == 40.86 and metrics["pe"]["period"] == "Today"
    # 2. FinEdge's TTM ROCE duplicated TTM ROE; we show FY26 ROCE and say so
    assert metrics["roe"]["value"] != metrics["roce"]["value"] and metrics["roce"]["period"] == "FY26"
    assert s["summary"]["dataQuality"]["notes"]
    # 3. One price series: the chart ends at the header price, and returns use the same series
    one_year = s["price-1Y"]["series"]
    assert one_year["c"][-1] == s["summary"]["quote"]["price"]
    # 4. Dividends belong to the year they were declared for, and payout uses the same figures
    dps = s["events"]["dividendsByFY"]
    assert dps["periods"][-1] == "FY26" and dps["dps"][-1] == 6.0
    assert metrics["dividend_payout"]["value"] == 18.52
    # 5. No duplicate announcements
    ann = [(a["date"], a["category"], a["description"]) for a in s["events"]["announcements"]]
    assert len(ann) == len(set(ann))
    # 6. Ranges longer than the price history are marked incomplete
    assert s["price-1Y"]["complete"] and not s["price-5Y"]["complete"]
    assert len(s["price-1Y"]["series"]["ema200"]) == len(one_year["t"])
    # 9. Tiny segments are folded into Others
    assert all((seg["sharePct"] or 0) >= 0.5 for seg in s["segments"]["latest"])
