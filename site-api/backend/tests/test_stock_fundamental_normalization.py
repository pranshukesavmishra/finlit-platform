import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "financial_portfolio_test")

from server import (  # noqa: E402
    _derive_bank_roce,
    _derive_income_metrics,
    _merge_category_history,
    _normalize_bank_asset_quality_history,
    _normalize_revenue_segments,
    _normalize_ownership_structure,
    _ratio_lookup,
    _reconcile_valuation_ratios,
    _ttm_net_profit_from_statement,
)


def test_bank_asset_quality_preserves_percentage_scale_and_quarter_dates():
    rows = _normalize_bank_asset_quality_history([
        {"period_end": 20260331, "year": 2026, "percentageOfGrossNpa": 0.0115, "percentageOfNpa": 0.0038, "cET1Ratio": 0.1971},
        {"period_end": 20260630, "year": 2026, "percentageOfGrossNpa": 0.0117, "percentageOfNpa": 0.0041, "cET1Ratio": 0.1957,
         "grossNonPerformingAssets": 358463500000, "nonPerformingAssets": 123572700000},
    ], "quarterly")
    by_category = {row["category"]: row["history"] for row in rows}
    assert [point["period"] for point in by_category["gross_npa_percent"]] == ["Jun 2026", "Mar 2026"]
    assert [point["value"] for point in by_category["gross_npa_percent"]] == [1.17, 1.15]
    assert by_category["net_npa_percent"][0]["value"] == 0.41
    assert by_category["cet1_ratio"][0]["value"] == 19.57


def test_bank_asset_quality_keeps_zero_separate_from_missing_and_ignores_amounts():
    rows = _normalize_bank_asset_quality_history([
        {"year": 2026, "percentageOfGrossNpa": 0, "percentageOfNpa": None},
        {"year": 2025, "percentageOfGrossNpa": "", "percentageOfNpa": 0.002},
        {"year": 2024, "grossNonPerformingAssets": 100000000, "nonPerformingAssets": 50000000},
        {"header": "TTM", "percentageOfNpa": 0.01},
    ], "yearly")
    by_category = {row["category"]: row["history"] for row in rows}
    assert by_category["gross_npa_percent"] == [{"period": "2026", "value": 0.0, "change": None}]
    assert by_category["net_npa_percent"] == [{"period": "2025", "value": 0.2, "change": None}]
    assert "cet1_ratio" not in by_category
    assert _normalize_bank_asset_quality_history([], "yearly") == []


def test_bank_asset_quality_ignores_provider_all_zero_placeholder_disclosures():
    assert _normalize_bank_asset_quality_history([
        {"year": 2026, "percentageOfGrossNpa": 0, "percentageOfNpa": 0, "cET1Ratio": 0},
    ], "yearly") == []


def _row(category, values):
    return {
        "category": category,
        "label": category.replace("_", " ").title(),
        "history": [
            {"period": period, "value": value, "change": None}
            for period, value in values
        ],
    }


def test_revenue_segments_reconcile_to_statement_and_merge_name_variants():
    payload = {"segment_revenues": [
        {"header": "Mar 2026", "data": {"interSegmentRevenue": 20_000_000}, "segments": [
            {"name": "Oil and Gas", "data": {"segmentRevenue": 100_000_000}},
            {"name": "Retail", "data": {"segmentRevenue": 50_000_000}},
        ]},
        {"header": "Mar 2025", "data": {}, "segments": [
            {"name": "Oil & Gas", "data": {"segmentRevenue": 90_000_000}},
            {"name": "Financial Services", "data": {"segmentRevenue": 10_000_000}},
        ]},
    ]}
    result = _normalize_revenue_segments(payload, "yearly", {"income_statement": [_row("revenue", [("2026", 12), ("2025", 10)])]})
    assert len([row for row in result if row["category"] == "segment_oilandgas"]) == 1
    assert result[0]["history"][0] == {"period": "2026", "value": 10, "change": None}
    for period, expected in [("2026", 12), ("2025", 10)]:
        assert sum(point["value"] for row in result for point in row["history"] if point["period"] == period) == expected
    assert result[-2]["label"] == "Less: inter-segment revenue"
    assert result[-1]["history"][0]["value"] == -1
    finserv = next(row for row in result if row["label"] == "Financial Services")
    assert [point["period"] for point in finserv["history"]] == ["2025"]


def test_revenue_segments_preserve_quarters_and_ignore_missing_data():
    payload = {"segment_revenues": [
        {"header": "Jun 2026", "segments": [{"name": "Retail", "data": {"segmentRevenue": 0}}]},
        {"header": "Mar 2026", "segments": [{"name": "Retail", "data": {"segmentRevenue": None}}]},
        {"header": "TTM", "segments": [{"name": "Retail", "data": {"segmentRevenue": 100}}]},
    ]}
    statement = {"income_statement": [_row("revenue", [("Jun 2026", 0), ("Mar 2026", 10)])]}
    result = _normalize_revenue_segments(payload, "quarterly", statement)
    assert result[0]["history"] == [{"period": "Jun 2026", "value": 0, "change": None}]
    assert _normalize_revenue_segments({}, "quarterly", statement) == []


def test_revenue_segments_reject_mismatched_provider_totals():
    warnings = []
    result = _normalize_revenue_segments({"segment_revenues": [
        {"header": "Dec 2023", "data": {"segmentRevenue": 100_000_000}, "segments": [
            {"name": "Retail", "data": {"segmentRevenue": 300_000_000}},
        ]},
    ]}, "quarterly", {"income_statement": [_row("revenue", [("Dec 2023", 10)])]}, warnings)
    assert result == []
    assert warnings[0]["code"] == "segment_revenue_total_mismatch"


def test_ownership_structure_uses_correct_pledge_denominators():
    summary = {"summary": [{"header": "Sep 2026", "totalShares": 1353722600, "pledgedShares": 7700000,
                            "totalShareholders": 572522, "lockedInShares": 0}]}
    distribution = {"distributions": [{"date_header": "Sep 2026", "distributions": [
        {"group": "promoterAndPromoterGroup", "data": {"totalShares": 974234560, "pledgedShares": 7700000}},
        {"group": "publicShareholding", "data": {"totalShares": 379488030, "pledgedShares": 500000}},
    ]}]}
    rows = {row["category"]: row["history"][0]["value"] for row in _normalize_ownership_structure(summary, distribution)}
    assert round(rows["pledged_percent"], 2) == 0.57
    assert round(rows["promoter_pledged_percent"], 2) == 0.79
    assert round(rows["total_shares"], 2) == 135.37
    assert rows["total_shareholders"] == 572522
    assert rows["locked_in_percent"] == 0


def test_ownership_structure_preserves_missing_and_zero_disclosures():
    rows = _normalize_ownership_structure({"summary": [
        {"header": "Mar 2026", "totalShares": 10000000, "pledgedShares": 0},
        {"header": "Jun 2026", "totalShares": 10000000},
    ]}, {"distributions": [{"date_header": "Jun 2026", "distributions": [
        {"group": "promoterAndPromoterGroup", "data": {"pledgedSharesPct": 2.5}},
    ]}]})
    by_category = {row["category"]: row["history"] for row in rows}
    assert by_category["pledged_percent"] == [{"period": "Mar 2026", "value": 0, "change": None}]
    assert by_category["promoter_pledged_percent"][0]["value"] == 2.5
    assert by_category["total_shares"][0]["period"] == "Jun 2026"
    assert "locked_in_percent" not in by_category
    assert _normalize_ownership_structure({}, {}) == []


def test_bank_annual_depreciation_backfill_reconciles_financing_profit():
    rows = [
        _row("revenue", [("Mar 2026", 348615.15)]),
        _row("interest", [("Mar 2026", 185491.23)]),
        _row("expenses", [("Mar 2026", 207830.13)]),
        _row("profit_before_tax", [("Mar 2026", 102141.45)]),
        _row("other_income", [("Mar 2026", 146847.66)]),
        _row("provisions_for_loan_loss", [("Mar 2026", 1)]),
    ]
    rows = _merge_category_history(rows, "depreciation", [{"period": "Mar 2026", "value": 4194.9, "change": None}])

    derived = _derive_income_metrics(rows)
    expenses = next(row for row in derived if row["category"] == "expenses")["history"][0]["value"]
    financing_profit = next(row for row in derived if row["category"] == "financing_profit")["history"][0]["value"]

    assert round(expenses, 2) == 203635.23
    assert round(financing_profit, 2) == -40511.31


def test_daily_finedge_pe_is_preferred_over_market_cap_derived_pe():
    ratios = _reconcile_valuation_ratios(
        [{"name": "P/E", "company_value": 15.94, "sector_value": None}],
        {"marketCap": 1262369.85},
        {"income_statement": [_row("net_profit", [("Mar 2026", 79219.46)])]},
        price_ratio_snapshot={"pe": 13.71},
    )

    pe = _ratio_lookup(ratios)["P/E"]
    assert pe["company_value"] == 13.71
    assert pe["source"] == "finedge_daily_price_ratios"


def test_negative_pe_uses_ttm_profit_when_available():
    ratios = _reconcile_valuation_ratios(
        [{"name": "P/E", "company_value": -26.4, "sector_value": None}],
        {"marketCap": 8515.55},
        {"income_statement": [_row("net_profit", [("Mar 2026", -336.89)])]},
        ttm_net_profit=3.72,
    )

    pe = _ratio_lookup(ratios)["P/E"]
    assert round(pe["company_value"], 2) == 2289.13
    assert pe["source"] == "derived_ttm_net_profit"


def test_negative_pe_is_hidden_when_ttm_profit_is_not_positive():
    ratios = _reconcile_valuation_ratios(
        [{"name": "P/E", "company_value": -26.4, "sector_value": None}],
        {"marketCap": 8515.55},
        {"income_statement": [_row("net_profit", [("Mar 2026", -336.89)])]},
        ttm_net_profit=None,
    )

    pe = _ratio_lookup(ratios)["P/E"]
    assert pe["company_value"] is None
    assert pe["source"] == "unavailable_negative_earnings"


def test_ttm_net_profit_uses_latest_four_quarters():
    income_statement = {
        "income_statement": [
            _row("net_profit", [
                ("Jun 2026", 64.71),
                ("Mar 2026", -494.0),
                ("Dec 2025", 25.11),
                ("Sep 2025", 407.9),
                ("Jun 2025", 5.0),
            ])
        ]
    }

    assert round(_ttm_net_profit_from_statement(income_statement), 2) == 3.72


def test_bank_roce_uses_finedge_capital_employed_convention():
    income_statement = {
        "income_statement": [
            _row("profit_before_tax", [("Mar 2026", 102141.45)]),
            _row("interest", [("Mar 2026", 185491.23)]),
        ]
    }
    balance_sheet = {
        "balance_sheet": [
            _row("deposits", [("Mar 2026", 3099638.29), ("Mar 2025", 2710898.23)]),
            _row("borrowings", [("Mar 2026", 588484.55), ("Mar 2025", 634605.57)]),
            _row("capital", [("Mar 2026", 1539.34), ("Mar 2025", 765.22)]),
            _row("reserves", [("Mar 2026", 579975.02), ("Mar 2025", 517218.98)]),
        ]
    }

    assert round(_derive_bank_roce(income_statement, balance_sheet), 2) == 7.07


def test_missing_roce_is_derived_for_banks_from_finedge_rows():
    ratios = _reconcile_valuation_ratios(
        [],
        {},
        {
            "income_statement": [
                _row("profit_before_tax", [("Mar 2026", 102141.45)]),
                _row("interest", [("Mar 2026", 185491.23)]),
            ]
        },
        {
            "balance_sheet": [
                _row("deposits", [("Mar 2026", 3099638.29), ("Mar 2025", 2710898.23)]),
                _row("borrowings", [("Mar 2026", 588484.55), ("Mar 2025", 634605.57)]),
                _row("capital", [("Mar 2026", 1539.34), ("Mar 2025", 765.22)]),
                _row("reserves", [("Mar 2026", 579975.02), ("Mar 2025", 517218.98)]),
            ]
        },
    )

    roce = _ratio_lookup(ratios)["ROCE"]
    assert roce["company_value"] == 7.07
    assert roce["source"] == "derived_bank_capital_employed"


def test_detailed_shareholding_preserves_named_holders_without_double_counting():
    from server import _normalize_detailed_shareholding
    result = _normalize_detailed_shareholding({"rows": [
        {"catagory": "Indian", "name": "Promoter Indian", "data": {"Mar 2026": 50, "Jun 2026": 51},
         "shareholders": [{"name": "Holder A", "data": {"Mar 2026": 0, "Jun 2026": None}},
                          {"name": "Holder B", "data": {"Jun 2026": "20.5"}}]},
        {"name": "Government", "data": {"Jun 2026": 0}},
    ]})
    assert result[0]["label"] == "Promoter Indian"
    assert result[0]["history"][0]["value"] == 51
    assert result[0]["children"][0]["history"] == [
        {"period": "Jun 2026", "value": None, "change": None},
        {"period": "Mar 2026", "value": 0, "change": None}]
    assert result[0]["children"][1]["history"][0]["value"] == 20.5
    assert result[1]["history"][0]["value"] == 0
    assert _normalize_detailed_shareholding([]) == []


def test_ownership_uses_explicit_declarations_without_assuming_missing_means_zero():
    summary = {"summary": [
        {"header": "Jun 2026", "totalShares": 13532538722, "lockedInShares": 2744},
        {"header": "Mar 2026", "totalShares": 10000000},
    ]}
    declaration = {"declaration": [
        {"header": "Jun 2026", "lockedInShares": True, "pledgedSharesForPromoterAndGroup": False},
        {"header": "Mar 2026", "lockedInShares": False, "pledgedSharesForPromoterAndGroup": False},
        {"header": "Dec 2025", "lockedInShares": True, "pledgedSharesForPromoterAndGroup": True},
        {"header": "Sep 2025", "lockedInShares": "false"},
    ]}
    rows = {row["category"]: row["history"] for row in _normalize_ownership_structure(summary, {}, declaration)}
    assert rows["locked_in_percent"][0]["value"] == 0.00002
    assert rows["locked_in_percent"][1] == {"period": "Mar 2026", "value": 0, "change": None, "source": "declaration_no_shares"}
    assert [p["value"] for p in rows["promoter_pledged_percent"]] == [0, 0]
    assert "pledged_percent" not in rows
    assert len(rows["locked_in_percent"]) == 2
