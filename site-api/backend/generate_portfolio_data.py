"""Generate the published API payload and matching frontend fallback from an Upstox PDF."""

import json
import shutil
import sys
from pathlib import Path

from portfolio_report import PORTFOLIO_CURRENT_JSON, PORTFOLIO_SOURCE_DIR, parse_portfolio_pdf


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_FALLBACK = REPO_ROOT / "frontend" / "src" / "data" / "portfolio.generated.json"
FRONTEND_REPORTS = REPO_ROOT / "frontend" / "public" / "reports"


def generate(pdf_path: Path):
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    source_path = PORTFOLIO_SOURCE_DIR / pdf_path.name
    PORTFOLIO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if pdf_path.resolve() != source_path.resolve():
        shutil.copy2(pdf_path, source_path)

    report = parse_portfolio_pdf(source_path, source_path.name)
    report["storedFileName"] = source_path.name
    report["fileSize"] = source_path.stat().st_size
    PORTFOLIO_CURRENT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    FRONTEND_FALLBACK.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    FRONTEND_REPORTS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, FRONTEND_REPORTS / source_path.name)
    return report


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python backend/generate_portfolio_data.py <upstox-realised-pnl.pdf>")
    generated = generate(Path(sys.argv[1]).resolve())
    print(f"Generated {generated['profile']['reportPeriod']} with {generated['summary']['tradeCount']} realised trades.")
