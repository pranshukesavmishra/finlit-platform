"""A company whose financial year does not end in March (ABB, CRISIL, Castrol...) keeps its yearly ratio rows: the report must show what the provider sent."""
from finlit.normalize import ratios
from finlit.normalize.statements import fiscal_year_end_month

PAYLOAD = {"ratios": [
    {"header": "TTM", "returnOnEquity": 0.18},
    {"header": "Dec 2024", "returnOnEquity": 0.20},
    {"header": "Dec 2023", "returnOnEquity": 0.15},
    {"header": "Mar 2024", "returnOnEquity": 0.99},   # interim for a December company
]}


def test_december_year_end_rows_are_kept_and_labelled_like_the_statements():
    view = ratios.build_ratios({"pr": PAYLOAD}, fy_month=12)
    assert view["history"]["periods"] == ["FY24", "FY25"]      # year ended Dec 2023 -> FY24, Dec 2024 -> FY25 (fiscal_year_label)
    assert view["history"]["rows"]["roe"] == [15.0, 20.0]


def test_march_company_behaviour_is_unchanged():
    payload = {"ratios": [{"header": "Mar 2025", "returnOnEquity": 0.2}, {"header": "Dec 2024", "returnOnEquity": 0.9}]}
    view = ratios.build_ratios({"pr": payload})
    assert view["history"]["periods"] == ["FY25"]


def test_fiscal_year_end_month_from_statement_dates():
    assert fiscal_year_end_month({"periodEnds": ["2022-12-31", "2023-12-31", "2024-12-31"]}) == 12
    assert fiscal_year_end_month({"periodEnds": ["2024-03-31", "2025-03-31"]}) == 3
    assert fiscal_year_end_month({}) == 3
