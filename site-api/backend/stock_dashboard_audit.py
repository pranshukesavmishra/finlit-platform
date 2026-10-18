"""Compare FinLit stock dashboard numbers with public Screener tables.

This is a developer audit tool, not an application endpoint. It imports the
same backend normalizer used by the admin dashboard, fetches Screener's public
company page, and reports row-level differences for the statement sections we
display.

Usage:
    python stock_dashboard_audit.py SKIPPER HDFCBANK --tolerance 2
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.request import Request, urlopen

from server import _fetch_stock_fundamentals


SCREENER_BASE_URL = "https://www.screener.in/company"
DEFAULT_SECTIONS = ("quarters", "profit-loss")
ROW_MAPPINGS = {
    "quarters": {
        "Sales|Revenue": ("incomeStatement", "revenue"),
        "Expenses": ("incomeStatement", "expenses"),
        "Operating Profit|Financing Profit": ("incomeStatement", "operating_profit"),
        "Other Income": ("incomeStatement", "other_income"),
        "Interest": ("incomeStatement", "interest"),
        "Depreciation": ("incomeStatement", "depreciation"),
        "Profit before tax": ("incomeStatement", "profit_before_tax"),
        "Net Profit": ("incomeStatement", "net_profit"),
    },
    "profit-loss": {
        "Sales|Revenue": ("incomeStatement", "revenue"),
        "Expenses": ("incomeStatement", "expenses"),
        "Operating Profit|Financing Profit": ("incomeStatement", "operating_profit"),
        "Other Income": ("incomeStatement", "other_income"),
        "Interest": ("incomeStatement", "interest"),
        "Depreciation": ("incomeStatement", "depreciation"),
        "Profit before tax": ("incomeStatement", "profit_before_tax"),
        "Net Profit": ("incomeStatement", "net_profit"),
    },
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_number(value: str) -> Optional[float]:
    text = clean_text(value).replace(",", "").replace("%", "")
    if text in {"", "-", "N/A"}:
        return None
    text = text.replace("₹", "").replace("Cr.", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def normalize_label(value: str) -> str:
    return clean_text(value).replace("+", "").strip()


@dataclass
class ParsedTable:
    headers: List[str]
    rows: Dict[str, List[str]]


class ScreenerTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section_stack: List[Optional[str]] = []
        self.current_section: Optional[str] = None
        self.in_table = False
        self.in_cell = False
        self.cell_tag: Optional[str] = None
        self.cell_text: List[str] = []
        self.current_row: List[str] = []
        self.current_table: Optional[ParsedTable] = None
        self.tables: Dict[str, ParsedTable] = {}

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "section":
            section_id = attrs_dict.get("id")
            self.section_stack.append(section_id)
            if section_id:
                self.current_section = section_id
        elif tag == "table" and self.current_section in ROW_MAPPINGS and self.current_section not in self.tables:
            self.in_table = True
            self.current_table = ParsedTable(headers=[], rows={})
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"th", "td"}:
            self.in_cell = True
            self.cell_tag = tag
            self.cell_text = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and self.in_cell and tag == self.cell_tag:
            self.current_row.append(clean_text(" ".join(self.cell_text)))
            self.in_cell = False
            self.cell_tag = None
            self.cell_text = []
        elif self.in_table and tag == "tr":
            if self.current_table and self.current_row:
                first = normalize_label(self.current_row[0])
                if not first:
                    self.current_table.headers = self.current_row[1:]
                elif not self.current_table.headers and self.current_row[0] == "":
                    self.current_table.headers = self.current_row[1:]
                elif self.current_row[0] == "":
                    self.current_table.headers = self.current_row[1:]
                else:
                    self.current_table.rows[first] = self.current_row[1:]
            self.current_row = []
        elif self.in_table and tag == "table":
            if self.current_table and self.current_section:
                self.tables[self.current_section] = self.current_table
            self.in_table = False
            self.current_table = None
        elif tag == "section" and self.section_stack:
            closed = self.section_stack.pop()
            if closed == self.current_section:
                self.current_section = next((item for item in reversed(self.section_stack) if item), None)


SNAPSHOT_METRICS = (
    "Market Cap",
    "Current Price",
    "Stock P/E",
    "Book Value",
    "Dividend Yield",
    "ROCE",
    "ROE",
    "Face Value",
)


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return clean_text(" ".join(self.parts))


def parse_screener_snapshot(html: str) -> Dict[str, float]:
    parser = TextParser()
    parser.feed(html)
    text = parser.text()
    metrics: Dict[str, float] = {}
    for index, label in enumerate(SNAPSHOT_METRICS):
        next_positions = [
            text.find(next_label, text.find(label) + len(label))
            for next_label in SNAPSHOT_METRICS[index + 1 :]
            if text.find(next_label, text.find(label) + len(label)) != -1
        ]
        start = text.find(label)
        if start == -1:
            continue
        end = min(next_positions) if next_positions else text.find("Add ratio to table", start)
        segment = text[start:end if end != -1 else len(text)]
        match = re.search(r"(-?[0-9][0-9,.]*)", segment)
        value = parse_number(match.group(1)) if match else None
        if value is not None:
            metrics[label] = value
    return metrics


def fetch_screener(symbol: str) -> Tuple[Optional[float], Dict[str, ParsedTable], Dict[str, float]]:
    url = f"{SCREENER_BASE_URL}/{symbol.upper()}/consolidated/"
    request = Request(url, headers={"Accept": "text/html", "User-Agent": "FinLit-dashboard-audit/1.0"})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")
    price_match = re.search(r"₹\s*([0-9,.]+)", html)
    parser = ScreenerTableParser()
    parser.feed(html)
    return parse_number(price_match.group(1)) if price_match else None, parser.tables, parse_screener_snapshot(html)


def history_value(data: Dict[str, Any], section: str, category: str, period_label: str) -> Optional[float]:
    if section == "incomeStatement":
        rows = data.get("incomeStatement", {}).get("income_statement") or []
    elif section == "cashFlow":
        rows = data.get("cashFlow", {}).get("cash_flow") or []
    else:
        rows = []
    row = next((item for item in rows if item.get("category") == category), None)
    if not row:
        return None
    candidates = [period_label]
    if period_label.startswith("Mar "):
        candidates.append(period_label.split(" ", 1)[1])
    for point in row.get("history") or []:
        if point.get("period") in candidates:
            value = point.get("value")
            return float(value) if isinstance(value, (int, float)) else parse_number(str(value))
    return None


def pct_diff(actual: Optional[float], expected: Optional[float]) -> Optional[float]:
    if actual is None or expected is None:
        return None
    if expected == 0:
        return 0 if actual == 0 else 100
    return ((actual - expected) / abs(expected)) * 100


def status_for(diff: Optional[float], actual: Optional[float], expected: Optional[float], pct_tolerance: float, abs_tolerance: float) -> str:
    if diff is None or actual is None or expected is None:
        return "MISSING"
    if abs(actual - expected) <= abs_tolerance:
        return "PASS"
    return "PASS" if abs(diff) <= pct_tolerance else "FAIL"


def compare_section(symbol: str, data: Dict[str, Any], table: ParsedTable, section: str, pct_tolerance: float, abs_tolerance: float, include_ttm: bool) -> int:
    failures = 0
    mapping = ROW_MAPPINGS[section]
    title = "Quarterly Results" if section == "quarters" else "Profit & Loss"
    print(f"\n{symbol} / {title}")
    print("-" * 88)
    for row_label, (app_section, app_category) in mapping.items():
        row_labels = row_label.split("|")
        reference_label = next((label for label in row_labels if label in table.rows), row_labels[0])
        screener_values = table.rows.get(reference_label)
        if not screener_values:
            print(f"MISSING reference row: {row_label}")
            failures += 1
            continue
        category = "financing_profit" if reference_label == "Financing Profit" else app_category
        header_values = list(zip(table.headers, screener_values))
        if not include_ttm:
            header_values = [(header, value) for header, value in header_values if header.upper() != "TTM"]
        for header, raw_value in header_values[-3:]:
            expected = parse_number(raw_value)
            actual = history_value(data, app_section, category, header)
            diff = pct_diff(actual, expected)
            status = status_for(diff, actual, expected, pct_tolerance, abs_tolerance)
            if status != "PASS":
                failures += 1
            diff_text = "N/A" if diff is None else f"{diff:+.2f}%"
            print(f"{status:7} {header:8} {reference_label:18} app={actual!s:>10} ref={expected!s:>10} diff={diff_text}")
    return failures


def ratio_value(data: Dict[str, Any], label: str) -> Optional[float]:
    lookup = {}
    for ratio in data.get("ratios") or []:
        if isinstance(ratio, dict) and ratio.get("name"):
            lookup[str(ratio["name"]).upper()] = ratio
    value = (lookup.get(label.upper()) or {}).get("company_value")
    return float(value) if isinstance(value, (int, float)) else parse_number(str(value))


def ratio_source(data: Dict[str, Any], label: str) -> str:
    for ratio in data.get("ratios") or []:
        if isinstance(ratio, dict) and str(ratio.get("name") or "").upper() == label.upper():
            return str(ratio.get("source") or "provider")
    return "missing"


def compare_snapshot_metrics(data: Dict[str, Any], screener_metrics: Dict[str, float], pct_tolerance: float, abs_tolerance: float) -> int:
    failures = 0
    app_metrics = {
        "Market Cap": data.get("profile", {}).get("marketCap"),
        "Current Price": data.get("quote", {}).get("price"),
        "Stock P/E": ratio_value(data, "P/E"),
        "Dividend Yield": ratio_value(data, "Dividend Yield"),
        "ROCE": ratio_value(data, "ROCE"),
        "ROE": ratio_value(data, "ROE"),
    }
    price = parse_number(str(app_metrics.get("Current Price")))
    book_value = screener_metrics.get("Book Value")
    if price is not None and book_value:
        app_metrics["Derived P/B from Screener book"] = ratio_value(data, "P/B")
        screener_metrics = {
            **screener_metrics,
            "Derived P/B from Screener book": round(price / book_value, 2),
        }

    print("\nSnapshot Ratios")
    print("-" * 88)
    for label, actual_raw in app_metrics.items():
        expected = screener_metrics.get(label)
        if expected is None:
            continue
        actual = parse_number(str(actual_raw))
        diff = pct_diff(actual, expected)
        status = status_for(diff, actual, expected, pct_tolerance, abs_tolerance)
        if status != "PASS":
            failures += 1
        source = data.get("quote", {}).get("source") if label == "Current Price" else ratio_source(data, label.replace("Stock ", ""))
        if label == "Market Cap":
            source = "profile"
        if label == "Derived P/B from Screener book":
            source = ratio_source(data, "P/B")
        diff_text = "N/A" if diff is None else f"{diff:+.2f}%"
        print(f"{status:7} {label:34} app={actual!s:>10} ref={expected!s:>10} diff={diff_text:>9} source={source}")
    return failures


def audit_symbol(symbol: str, pct_tolerance: float, abs_tolerance: float, sections: Iterable[str], include_ttm: bool) -> int:
    failures = 0
    print(f"\n{'=' * 88}\nAuditing {symbol.upper()}\n{'=' * 88}")
    screener_price, tables, screener_metrics = fetch_screener(symbol)
    yearly = _fetch_stock_fundamentals(symbol, "consolidated", "yearly")
    quarterly = _fetch_stock_fundamentals(symbol, "consolidated", "quarterly")

    app_price = yearly.get("quote", {}).get("price")
    price_diff = pct_diff(app_price, screener_price)
    price_status = status_for(price_diff, app_price, screener_price, pct_tolerance, abs_tolerance)
    if price_status != "PASS":
        failures += 1
    print(f"{price_status:7} Price app={app_price!s:>10} ref={screener_price!s:>10} diff={'N/A' if price_diff is None else f'{price_diff:+.2f}%'} source={yearly.get('quote', {}).get('source')}")
    failures += compare_snapshot_metrics(yearly, screener_metrics, pct_tolerance, abs_tolerance)

    data_by_section = {"quarters": quarterly, "profit-loss": yearly}
    for section in sections:
        table = tables.get(section)
        if not table:
            print(f"\nMISSING reference section: {section}")
            failures += 1
            continue
        failures += compare_section(symbol.upper(), data_by_section[section], table, section, pct_tolerance, abs_tolerance, include_ttm)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit FinLit stock dashboard values against public Screener statement tables.")
    parser.add_argument("symbols", nargs="+", help="NSE symbols to audit, for example SKIPPER HDFCBANK RELIANCE")
    parser.add_argument("--tolerance", type=float, default=2.0, help="Allowed percentage difference per value.")
    parser.add_argument("--abs-tolerance", type=float, default=2.0, help="Allowed absolute difference in Rs. crores / rupees, depending on row.")
    parser.add_argument("--include-ttm", action="store_true", help="Also audit Screener TTM columns. FinLit does not currently display TTM by default.")
    parser.add_argument("--sections", nargs="+", choices=DEFAULT_SECTIONS, default=list(DEFAULT_SECTIONS))
    args = parser.parse_args()

    failures = 0
    for symbol in args.symbols:
        failures += audit_symbol(symbol, args.tolerance, args.abs_tolerance, args.sections, args.include_ttm)
    print(f"\nAudit complete: {failures} issue(s) outside tolerance.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
