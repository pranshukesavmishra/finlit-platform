"""Monthly-portfolio lister for ICICI Prudential Mutual Fund (same contract as amcs.py: list only; download and parsing happen in finlit/portfolios.py).

The site's own file list comes from apimf.icicipruamc.com, which resets connections from the development network, so the zip's name is built and
checked with a 1-byte range request, as list_absl does: www.icicipruamc.com/blob/downloads/Files/Monthly Portfolio Disclosures/<yyyy>/<Mon>/
Monthly-Portfolio-Disclosure-<Month>-<yyyy>.zip, one zip a month with one workbook per scheme. The month folder is 'Sep', 'Feb' ... but 'June' and
'July' for those two months, so both spellings are tried (checked for December 2025 to September 2026).
"""

from __future__ import annotations

from datetime import date
from typing import List

import httpx

from .amcs import MON_FULL, MON_KEYS, Adapter, FileRef

ICICI_BASE = "https://www.icicipruamc.com/blob/downloads/Files/Monthly%20Portfolio%20Disclosures"


def icici_candidates(m: date) -> List[str]:
    """The zip URL for a month-end, in the folder spellings seen so far."""
    name = f"Monthly-Portfolio-Disclosure-{MON_FULL[m.month - 1]}-{m.year}.zip"
    folders = list(dict.fromkeys([MON_KEYS[m.month - 1], MON_FULL[m.month - 1]]))
    return [f"{ICICI_BASE}/{m.year}/{f}/{name}" for f in folders]


async def list_icici(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One zip per month-end with one workbook per scheme (about 150); 404 means not published yet."""
    out: List[FileRef] = []
    for m in months:
        for url in icici_candidates(m):
            r = await client.get(url, headers={"Range": "bytes=0-0"})
            if r.status_code in (200, 206):
                out.append(FileRef("icici", url, m, None, f"ICICI Prudential MF {m:%b %Y}"))
                break
            if r.status_code not in (404, 403):
                r.raise_for_status()
    return out


ADAPTERS: List[Adapter] = [
    Adapter("icici", "ICICI Prudential Mutual Fund", r"icici\s+prudential", list_icici, "icicipruamc.com"),
]
