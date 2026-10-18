from pathlib import Path

import pytest

from backend.portfolio_report import parse_portfolio_pdf


def test_parse_upstox_portfolio_pdf_summary():
    pdf = Path(__file__).parents[1] / "portfolio_data" / "sources" / "realizedPnL_EQ_2026-04-01_To_2026-09-10_BR2287.pdf"
    if not pdf.is_file():  # the raw broker statement is kept out of the shared repository
        pytest.skip("source statement not present")

    report = parse_portfolio_pdf(pdf, "upstox.pdf")

    assert report["source"] == "pdf"
    assert report["profile"]["reportPeriod"] == "01 Apr 2026 – 10 Sep 2026"
    assert report["headline"] == {"grossPnl": "₹5,65,182.44", "netPnl": "₹5,21,176.62", "grossRoi": "18.84%", "netRoi": "17.37%"}
    assert report["charges"]["total"] == 44005.82
    assert report["charges"]["breakdown"] == {"sebiFees": 23.47, "turnoverCharges": 849.06, "brokerage": 15375.79, "dematTransactionCharges": 4960.0, "integratedGst": 3817.5, "securitiesTransactionTax": 17168.0, "stampDuty": 1812.0}
    assert report["summary"] == {"tradeCount": 426, "winningTrades": 361, "losingTrades": 63, "zeroPnlTrades": 2}
    assert report["metrics"][0]["value"] == "84.74%"
    assert report["metrics"][1]["value"] == "68 Days"
    assert report["charts"]["monthlyRealizedPnl"] == [{"month": "Apr 2026", "realizedPnl": 99050.85}, {"month": "May 2026", "realizedPnl": 121853.9}, {"month": "Jun 2026", "realizedPnl": 126245.03}, {"month": "Jul 2026", "realizedPnl": 45654.43}, {"month": "Aug 2026", "realizedPnl": 131964.55}, {"month": "Sep 2026", "realizedPnl": 40413.68}]
    assert report["charts"]["grossPnl"] == 565182.44
    assert report["charts"]["cumulativeRealizedPnl"][-1]["realizedPnl"] == 565182.44
