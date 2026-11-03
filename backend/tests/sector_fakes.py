"""Helpers for the sector tests: a small but consistent release folder built from the trimmed real output of 29 Oct 2026 (tests/fixtures/sectors)."""
import json
import shutil
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "sectors"
SLUGS = ("ferrous-metals", "industrial-products", "banks")


def make_release(dest: Path, date: str = "2026-10-29", stocks: int = 3, errors: int = 0) -> Path:
    """dest/ gets sectors/_board.json (rows cut to the three pages we hold), the three pages, three stock files and _summary.json."""
    (dest / "sectors").mkdir(parents=True, exist_ok=True)
    board = json.loads((FIX / "sectors" / "_board.json").read_text())
    board["rows"] = [r for r in board["rows"] if r["slug"] in SLUGS]
    board["date"] = date
    (dest / "sectors" / "_board.json").write_text(json.dumps(board))
    for s in SLUGS:
        page = json.loads((FIX / "sectors" / f"{s}.json").read_text())
        page["date"] = date
        (dest / "sectors" / f"{s}.json").write_text(json.dumps(page))
    for sym in ("SAMBHV", "KIRLFER", "TATASTEEL"):
        shutil.copy(FIX / f"{sym}.json", dest / f"{sym}.json")
    summary = [{"symbol": f"S{i}"} for i in range(stocks - errors)] + [{"symbol": f"E{i}", "error": "boom"} for i in range(errors)]
    (dest / "_summary.json").write_text(json.dumps({"meta": {"stocks": stocks, "errors": errors}, "stocks": summary}))
    return dest
