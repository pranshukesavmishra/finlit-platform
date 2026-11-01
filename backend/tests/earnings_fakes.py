"""Test helpers for the earnings-call summaries: a tiny PDF writer, a synthetic transcript, and a FAKE language-model provider (no network, no key)."""
from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Callable, Dict, List, Optional

from finlit.earnings.provider import NotConfigured, ProviderError, RateLimited

FIX = Path(__file__).parent / "fixtures" / "earnings"

# A synthetic transcript of a made-up company (nothing here is a real company's statement).
PAGES = [
    ["Acme Industries Limited, Q2 FY27 earnings conference call, 20 October 2026.",
     "Moderator: Good evening and welcome to the Acme Industries Q2 FY27 earnings call.",
     "Rahul Mehta, Managing Director: Thank you. Our strategy is to deepen our presence in specialty chemicals where we have a cost advantage from our integrated plants.",
     "Our integrated plants at Dahej give us a cost position that competitors find hard to match, and long-term contracts with our top ten customers protect volumes.",
     "Revenue for the quarter grew 14 percent year on year to 4,820 crore rupees, driven by volumes in the specialty segment."],
    ["Anita Rao, Chief Financial Officer: EBITDA margin improved to 21.5 percent from 19.8 percent a year ago as raw material prices softened.",
     "We expect margins to stay in a range of 20 to 22 percent for the rest of the year, subject to crude oil prices.",
     "On capital expenditure, we plan to spend 1,200 crore rupees this year on the new Dahej expansion, funded largely from internal accruals.",
     "Net debt to EBITDA stands at 0.8 times and we repaid 300 crore rupees of borrowings during the quarter.",
     "The board has declared an interim dividend of 6 rupees per share for the year."],
    ["Analyst, Brokerage One: Can you explain what is driving the order book, and how worried should we be about Chinese imports?",
     "Rahul Mehta: The order book stands at 3,900 crore rupees, up 18 percent from the last quarter, and enquiries from European customers have increased.",
     "Chinese imports remain a risk to pricing in two product lines and we are watching anti-dumping duty decisions closely.",
     "Analyst, Brokerage Two: What is your thinking on acquisitions and the share buyback?",
     "Anita Rao: We are not planning a share buyback this year, and we will consider small acquisitions only if they add to our specialty portfolio.",
     "Moderator: Thank you. That concludes the call."],
]
TEXT = "\f".join("\n".join(textwrap.fill(line, 90) for line in page) for page in PAGES)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: List[List[str]], wrap: int = 90) -> bytes:
    """A valid multi-page PDF (Helvetica, one text line per row), built by hand so the tests need no PDF library to WRITE one."""
    objs: Dict[int, bytes] = {}
    n_pages = len(pages)
    page_ids = [4 + 2 * i for i in range(n_pages)]
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = ("<< /Type /Pages /Kids [" + " ".join(f"{i} 0 R" for i in page_ids) + f"] /Count {n_pages} >>").encode()
    objs[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    for i, lines in enumerate(pages):
        rows = [r for line in lines for r in textwrap.wrap(line, wrap) or [""]]
        body = ["BT", "/F1 10 Tf", "13 TL", "40 800 Td"] + [f"({_esc(r)}) Tj T*" for r in rows] + ["ET"]
        stream = "\n".join(body).encode("latin-1", "replace")
        pid, cid = page_ids[i], page_ids[i] + 1
        objs[pid] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>".encode()
        objs[cid] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n")
    offs = {}
    for k in sorted(objs):
        offs[k] = len(out)
        out += f"{k} 0 obj\n".encode() + objs[k] + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {max(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for k in range(1, max(objs) + 1):
        out += f"{offs[k]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {max(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return bytes(out)


def fixture_pdf() -> bytes:
    return (FIX / "transcript_q2fy27.pdf").read_bytes()


class FakeProvider:
    """Answers from a function (question ids asked -> raw `answers` dict). Counts requests. Can be told to rate-limit or fail."""
    name = "fake"
    model = "fake-1"

    def __init__(self, answer: Optional[Callable[[List[str], str], dict]] = None, configured: bool = True):
        self.answer, self._configured, self.requests, self.prompts = answer, configured, 0, []
        self.raises: List[Exception] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def generate(self, system: str, user: str) -> str:
        if not self._configured:
            raise NotConfigured("no key")
        self.requests += 1
        self.prompts.append((system, user))
        if self.raises:
            raise self.raises.pop(0)
        ids = re.findall(r'^- id "([a-z-]+)"', user, re.M)
        return json.dumps({"answers": self.answer(ids, user) if self.answer else {}})

    async def aclose(self) -> None:
        pass


def good(text: str, quote: str, source: str = "current") -> dict:
    return {"text": text, "quote": quote, "source": source}


Q1 = "Our integrated plants at Dahej give us a cost position that competitors find hard to match"
Q2 = "long-term contracts with our top ten customers protect volumes"
Q3 = "EBITDA margin improved to 21.5 percent from 19.8 percent a year ago as raw material prices softened"
Q4 = "We expect margins to stay in a range of 20 to 22 percent for the rest of the year"
Q5 = "The order book stands at 3,900 crore rupees, up 18 percent from the last quarter"
Q6 = "Chinese imports remain a risk to pricing in two product lines"
Q7 = "we plan to spend 1,200 crore rupees this year on the new Dahej expansion"
Q8 = "Net debt to EBITDA stands at 0.8 times and we repaid 300 crore rupees of borrowings"


def honest_answers(ids: List[str], user: str) -> dict:
    """What a careful model would return for the synthetic transcript: real quotes for the questions it covers, not covered for the rest."""
    table = {
        "strategy-moat": {"covered": True, "sentences": [good("Management aims to grow in specialty chemicals using its cost advantage.", Q1), good("Long-term customer contracts protect its volumes.", Q2)]},
        "margins-costs": {"covered": True, "sentences": [good("EBITDA margin rose to 21.5 percent from 19.8 percent.", Q3), good("Management expects margins of 20 to 22 percent for the rest of the year.", Q4)]},
        "demand-orders": {"covered": True, "sentences": [good("The order book is 3,900 crore rupees, up 18 percent from last quarter.", Q5), good("Chinese imports are a pricing risk in two product lines.", Q6)]},
        "capex-debt": {"covered": True, "sentences": [good("The company plans to spend 1,200 crore rupees on the Dahej expansion this year.", Q7), good("Net debt to EBITDA is 0.8 times after repaying 300 crore rupees.", Q8)]},
    }
    return {i: table.get(i, {"covered": False, "sentences": []}) for i in ids}
