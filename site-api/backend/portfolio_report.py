import json
import math
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader


PORTFOLIO_DATA_DIR = Path(__file__).parent / "portfolio_data"
PORTFOLIO_SOURCE_DIR = PORTFOLIO_DATA_DIR / "sources"
PORTFOLIO_CURRENT_JSON = PORTFOLIO_DATA_DIR / "current.json"
MAX_PORTFOLIO_UPLOAD_BYTES = 15 * 1024 * 1024
PDF_TRADE_PATTERN = re.compile(
    r"(?P<security>.+?)\s+"
    r"(?P<scripCode>[A-Z]?\d{3,6})\s+"
    r"(?P<symbol>[A-Z0-9&.-]+)\s+"
    r"(?P<isin>IN[A-Z0-9]{10})\s+"
    r"(?P<tradeType>[A-Z]+)\s+"
    r"(?P<quantity>-?\d+(?:\.\d+)?)\s+"
    r"(?P<buyDate>\d{2}-\d{2}-\d{4})\s+"
    r"(?P<buyRate>-?\d+(?:\.\d+)?)\s+"
    r"(?P<buyAmount>-?\d+(?:\.\d+)?)\s+"
    r"(?P<sellDate>\d{2}-\d{2}-\d{4})\s+"
    r"(?P<sellRate>-?\d+(?:\.\d+)?)\s+"
    r"(?P<sellAmount>-?\d+(?:\.\d+)?)\s+"
    r"(?P<days>-?\d+(?:\.\d+)?)\s+"
    r"(?P<totalPl>-?\d+(?:\.\d+)?)\s+"
    r"(?P<taxBucket>-?\d+(?:\.\d+)?)"
    r"(?:\s+(?P<turnover>-?\d+(?:\.\d+)?))?$"
)


def _to_float(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("₹", "")
    if not text or text.lower() == "nan":
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _to_int(value, default=0):
    return int(round(_to_float(value, default)))


def _clean_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _format_inr(value):
    sign = "-" if value < 0 else ""
    value = abs(float(value))
    whole, decimal = f"{value:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}.{decimal}"


def _format_percent(value):
    return f"{value:.2f}%"


def _format_report_date(value):
    if not value:
        return ""
    parsed = _parse_date(value)
    if not parsed:
        return _clean_text(value)
    return parsed.strftime("%d %b %Y")


def _iso_date(value):
    if not value:
        return ""
    parsed = _parse_date(value)
    if not parsed:
        return _clean_text(value)
    return parsed.date().isoformat()


def _financial_year_label(start_date):
    parsed = _parse_date(start_date)
    if not parsed:
        return ""
    year = parsed.year if parsed.month >= 4 else parsed.year - 1
    return f"FY {year}-{str(year + 1)[-2:]}"


def _parse_date(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) and value > 20000:
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    text = _clean_text(value)
    for date_format in ("%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            pass
    return None


def _extract_report_period(text):
    match = re.search(r"Report Time Period\s*:\s*([0-9-]+)\s+To\s+([0-9-]+)", text, re.I)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _find_text_amount(text, label):
    match = re.search(rf"{re.escape(label)}\s+(-?\d+(?:\.\d+)?)", text, re.I)
    return _to_float(match.group(1)) if match else 0.0


def _extract_charge_breakdown(text):
    labels = {
        "sebiFees": "[SEBI FEES]",
        "turnoverCharges": "[TURNOVER CHG]",
        "brokerage": "BROKERAGE",
        "dematTransactionCharges": "DEMAT TRAN CHG",
        "integratedGst": "INTEGRATED GST",
        "securitiesTransactionTax": "SECURITIES TRANSACTION TAX",
        "stampDuty": "STAMP DUTY",
    }
    return {key: _find_text_amount(text, label) for key, label in labels.items()}


def _build_derived_charts(trades, gross_pnl):
    """Build only charts that can be reproduced from the realised-P&L ledger."""
    by_symbol = {}
    by_month = {}
    daily_pnl = {}
    holding_buckets = {"Same day": 0, "1-7 days": 0, "8-30 days": 0, "31-90 days": 0, "91+ days": 0}

    for trade in trades:
        realized_pnl = trade["realizedPnl"]
        symbol = trade["symbol"]
        by_symbol[symbol] = by_symbol.get(symbol, 0) + realized_pnl

        sell_date = _parse_date(trade["sellDate"])
        if sell_date:
            month = sell_date.strftime("%b %Y")
            by_month[month] = by_month.get(month, 0) + realized_pnl
            day = sell_date.date().isoformat()
            daily_pnl[day] = daily_pnl.get(day, 0) + realized_pnl

        days = trade["holdingDays"]
        bucket = "Same day" if days <= 0 else "1-7 days" if days <= 7 else "8-30 days" if days <= 30 else "31-90 days" if days <= 90 else "91+ days"
        holding_buckets[bucket] += 1

    ordered_symbols = sorted(by_symbol.items(), key=lambda item: item[1], reverse=True)
    top_symbols = ordered_symbols[:9]
    other_symbols = ordered_symbols[9:]
    attribution = [{"stock": symbol, "realizedPnl": round(value, 2)} for symbol, value in top_symbols]
    if other_symbols:
        attribution.append({"stock": f"Other symbols ({len(other_symbols)})", "realizedPnl": round(sum(value for _, value in other_symbols), 2)})

    month_order = sorted(by_month, key=lambda item: datetime.strptime(item, "%b %Y"))
    monthly = [{"month": month, "realizedPnl": round(by_month[month], 2)} for month in month_order]

    running_total = 0.0
    cumulative = []
    for day in sorted(daily_pnl):
        running_total += daily_pnl[day]
        cumulative.append({"date": day, "realizedPnl": round(running_total, 2)})

    return {
        "pnlAttribution": attribution,
        "monthlyRealizedPnl": monthly,
        "cumulativeRealizedPnl": cumulative,
        "holdingPeriodDistribution": [{"bucket": bucket, "trades": count} for bucket, count in holding_buckets.items()],
        "outcomes": [
            {"outcome": "Profitable", "trades": len([trade for trade in trades if trade["realizedPnl"] > 0])},
            {"outcome": "Loss-making", "trades": len([trade for trade in trades if trade["realizedPnl"] < 0])},
            {"outcome": "Zero P&L", "trades": len([trade for trade in trades if trade["realizedPnl"] == 0])},
        ],
        "grossPnl": round(gross_pnl, 2),
    }


def _trade_from_pdf_line(line):
    match = PDF_TRADE_PATTERN.match(line)
    if not match:
        return None
    data = match.groupdict()
    return {
        "security": _clean_text(data["security"]),
        "scripCode": _clean_text(data["scripCode"]),
        "symbol": _clean_text(data["symbol"]),
        "isin": _clean_text(data["isin"]),
        "tradeType": _clean_text(data["tradeType"]) or "EQ",
        "quantity": _to_float(data["quantity"]),
        "buyDate": _iso_date(data["buyDate"]),
        "buyRate": _to_float(data["buyRate"]),
        "buyAmount": _to_float(data["buyAmount"]),
        "sellDate": _iso_date(data["sellDate"]),
        "sellRate": _to_float(data["sellRate"]),
        "sellAmount": _to_float(data["sellAmount"]),
        "holdingDays": _to_int(data["days"]),
        "realizedPnl": _to_float(data["totalPl"]),
        "turnover": _to_float(data.get("turnover") or data["taxBucket"]),
    }


def _extract_pdf_text(path: Path):
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Portfolio PDF could not be read.") from exc


def _extract_pdf_trades(text):
    trades = []
    pending = ""
    in_trade_table = False
    for raw_line in text.splitlines():
        line = _clean_text(raw_line)
        if not line:
            continue
        if line.startswith("Scrip Name"):
            pending = ""
            in_trade_table = True
            continue
        if (
            line.startswith(("UCC :", "Name :", "PAN :", "Segment :", "Report Time Period", "Generated On"))
            or line in {"Realised P&L Details", "P&L Summary", "Charges"}
            or line.startswith(("Description Amount", "Opt Qty", "UPSTOX SECURITIES", "(Formerly", "Dealing Office", "From "))
        ):
            pending = ""
            continue
        if not in_trade_table:
            continue
        candidate = f"{pending} {line}".strip() if pending else line
        trade = _trade_from_pdf_line(candidate)
        if trade:
            trades.append(trade)
            pending = ""
            continue
        pending = candidate
    return trades


def _build_report_payload(original_filename, from_date, to_date, gross_pnl, net_pnl, charges_total, trades, source, charge_breakdown=None):
    if not trades:
        raise HTTPException(status_code=400, detail="No realised P&L trades were found in the report.")
    if not gross_pnl:
        gross_pnl = round(sum(trade["realizedPnl"] for trade in trades), 2)
    if not net_pnl:
        net_pnl = round(gross_pnl - charges_total, 2)

    deployed_capital = _to_float(os.environ.get("PORTFOLIO_DEPLOYED_CAPITAL", "3000000"), 3_000_000)
    wins = [trade for trade in trades if trade["realizedPnl"] > 0]
    losses = [trade for trade in trades if trade["realizedPnl"] < 0]
    # Average holding is the arithmetic mean of the report's Days field across every realised ledger row.
    avg_holding = round(sum(trade["holdingDays"] for trade in trades) / len(trades))
    # The published performance metric uses all realised ledger rows as the
    # denominator, including zero-P&L rows (384 / 455 = 84.40% for the
    # current report). The outcome chart still keeps zero-P&L rows distinct.
    total_trades = len(trades)

    metrics = [
        {"key": "winrate", "label": "Win Rate", "value": _format_percent((len(wins) / total_trades) * 100 if total_trades else 0), "tone": "positive"},
        {"key": "holding", "label": "Avg Holding Period", "value": f"{avg_holding} Days", "tone": "neutral"},
        {"key": "active-trades", "label": "Realised Trades", "value": str(len(trades)), "tone": "neutral"},
    ]

    return {
        "source": source,
        "sourceFileName": original_filename,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "reportPeriod": f"{_format_report_date(from_date)} – {_format_report_date(to_date)}" if from_date and to_date else "",
            "financialYear": _financial_year_label(from_date),
            "deployedCapital": _format_inr(deployed_capital),
        },
        "headline": {
            "grossPnl": _format_inr(gross_pnl),
            "netPnl": _format_inr(net_pnl),
            "grossRoi": _format_percent((gross_pnl / deployed_capital) * 100 if deployed_capital else 0),
            "netRoi": _format_percent((net_pnl / deployed_capital) * 100 if deployed_capital else 0),
        },
        "metrics": metrics,
        "charges": {
            "total": charges_total,
            "totalFormatted": _format_inr(charges_total),
            "breakdown": charge_breakdown or {},
        },
        "tradeLedger": trades,
        "summary": {
            "tradeCount": len(trades),
            "winningTrades": len(wins),
            "losingTrades": len(losses),
            "zeroPnlTrades": len([trade for trade in trades if trade["realizedPnl"] == 0]),
        },
        "charts": _build_derived_charts(trades, gross_pnl),
    }


def parse_portfolio_pdf(path: Path, original_filename: str):
    text = _extract_pdf_text(path)
    from_date, to_date = _extract_report_period(text)
    gross_pnl = _find_text_amount(text, "Gross P&L")
    net_pnl = _find_text_amount(text, "Net P&L")
    charges_total = _find_text_amount(text, "TOTAL")
    charge_breakdown = _extract_charge_breakdown(text)
    trades = _extract_pdf_trades(text)
    return _build_report_payload(original_filename, from_date, to_date, gross_pnl, net_pnl, charges_total, trades, "pdf", charge_breakdown)


async def save_portfolio_upload(file: UploadFile):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    allowed_types = {"application/pdf", "application/octet-stream"}
    if extension != ".pdf":
        raise HTTPException(status_code=400, detail="Upload the Upstox realised P&L report as a .pdf file.")
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported portfolio file type.")

    PORTFOLIO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = str(uuid.uuid4())
    destination = PORTFOLIO_SOURCE_DIR / f"{upload_id}{extension}"
    total = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_PORTFOLIO_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds the 15 MB limit.")
                output.write(chunk)
        header = destination.read_bytes()[:8]
        if not header.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="File contents do not match a PDF report.")
        parsed = parse_portfolio_pdf(destination, original_name)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    parsed["uploadId"] = upload_id
    parsed["fileSize"] = total
    parsed["storedFileName"] = destination.name
    tmp_json = PORTFOLIO_CURRENT_JSON.with_suffix(".tmp")
    tmp_json.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.move(str(tmp_json), PORTFOLIO_CURRENT_JSON)
    return parsed


def read_current_portfolio_report():
    if not PORTFOLIO_CURRENT_JSON.is_file():
        raise HTTPException(status_code=404, detail="No uploaded portfolio report is published yet.")
    return json.loads(PORTFOLIO_CURRENT_JSON.read_text(encoding="utf-8"))
