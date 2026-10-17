"""News, filings, result dates and documents.

Automatic part: every exchange announcement loaded for a company becomes a feed item, sorted into `result` (financial results),
`document` (reports, presentations, transcripts, prospectuses) or `news` (everything else). Manual part: administrators add curated
news and upcoming result dates. The public reads one endpoint, `/api/feed`.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any, Dict, List, Optional

DOC_WORDS = ("annual report", "presentation", "transcript", "investor", "analyst", "concall", "earnings call", "prospectus", "newspaper", "integrated report")


def classify(category: str, description: str = "") -> str:
    low = f"{category} {description}".lower()
    if "result" in low and "unaudited" in low or "financial result" in low or category.lower().startswith("result"):
        return "result"
    if any(w in low for w in DOC_WORDS):
        return "document"
    return "news"


def dedupe_key(symbol: str, when: str, text: str, link: Optional[str]) -> str:
    return hashlib.sha1(f"{symbol}|{when}|{link or text}".encode()).hexdigest()  # nosec B324 - de-duplication key, not security


def rows_from_announcements(symbol: str, company: str, announcements: List[Dict[str, Any]]) -> List[tuple]:
    out = []
    for a in announcements:
        description = " ".join((a.get("description") or "").split())
        if not a.get("date"):
            continue
        category = a.get("category") or "General"
        title = description if 10 <= len(description) <= 160 else f"{category}: {description[:140]}".strip(": ")
        out.append((classify(category, description), title[:300], symbol, company, "Exchange filing", a.get("link"), date.fromisoformat(a["date"]),
                    category[:80], None, None, True, dedupe_key(symbol, a["date"], description, a.get("link"))))
    return out


async def save_announcements(conn, symbol: str, company: str, announcements: List[Dict[str, Any]]) -> int:
    rows = rows_from_announcements(symbol, company, announcements)
    if not rows:
        return 0
    await conn.executemany(
        "INSERT INTO feed_items (kind, title, symbol, company, source, link, item_date, category, period, summary, auto, dedupe) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) ON CONFLICT (dedupe) DO NOTHING", rows)
    return len(rows)


URL_RE = re.compile(r"^https://[^\s<>\"']+$")
