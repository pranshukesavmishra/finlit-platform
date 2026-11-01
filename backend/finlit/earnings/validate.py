"""Checks on what the model returned, before anything is stored (docs/EARNINGS-CALLS.md, "Validation rules").

An answer is shown only if, sentence by sentence: the quote is a real excerpt of the transcript, the sentence is a plain statement (no advice words),
and the sizes are sane. A sentence that fails is dropped; a question left with too few sentences is asked again once, and if it still fails it is not shown.
Nothing here calls a model.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import config as C
from .questions import ADVICE_PHRASES, ADVICE_WORDS

_QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
           "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-", " ": " ", " ": " ", " ": " "}
_TRANS = str.maketrans(_QUOTES)
_ADVICE = re.compile(r"\b(" + "|".join(sorted(ADVICE_WORDS, key=len, reverse=True)) + r")\b", re.I)


def normalise(text: str) -> str:
    """The form both the transcript and a quote are compared in: compatibility characters folded (ligatures, full-width), typographic quotes and dashes made plain,
    soft hyphens and line-break hyphens removed, every run of white space one space, case ignored."""
    t = unicodedata.normalize("NFKC", text or "").translate(_TRANS).replace("­", "")
    t = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", t)        # "invest-\nment" -> "investment"
    return re.sub(r"\s+", " ", t).strip().casefold()


def advice_words(sentence: str) -> List[str]:
    """The advice words and phrases found in `sentence` (empty = clean)."""
    low = (sentence or "").lower()
    found = [p for p in ADVICE_PHRASES if p in low]
    found += [m.group(1).lower() for m in _ADVICE.finditer(sentence or "")]
    return sorted(set(found))


@dataclass
class Transcript:
    """A transcript prepared for checking: the normalised text of the whole call and where each page starts in it."""
    label: str
    normalised: str
    starts: List[int] = field(default_factory=list)       # offset in `normalised` where page i (1-based = index + 1) begins

    @classmethod
    def from_pages(cls, label: str, pages: Sequence[str]) -> "Transcript":
        parts, starts, pos = [], [], 0
        for p in pages:
            n = normalise(p)
            starts.append(pos)
            parts.append(n)
            pos += len(n) + 1
        return cls(label, " ".join(parts), starts)

    @classmethod
    def from_text(cls, label: str, body: str) -> "Transcript":
        return cls.from_pages(label, body.split("\f"))

    def find(self, quote: str) -> Optional[int]:
        """Page number (1-based) where the quote begins, or None when the quote is not in the text. A quote that runs across a page break is found too."""
        q = normalise(quote)
        if len(q) < C.MIN_QUOTE_CHARS:
            return None
        at = self.normalised.find(q)
        if at < 0:
            return None
        page = 1
        for i, s in enumerate(self.starts):
            if s <= at:
                page = i + 1
        return page


@dataclass
class Checked:
    covered: bool
    sentences: List[dict]
    dropped: List[Tuple[str, str]] = field(default_factory=list)      # (reason, sentence) for the report
    claimed: bool = False          # the model said the call covers the question
    malformed: bool = False        # there was no usable answer at all (so "not covered" must not be assumed)

    def as_answer(self) -> dict:
        return {"covered": self.covered, "sentences": self.sentences}


def check_answer(raw: object, current: Transcript, previous: Optional[Transcript] = None, allow_previous: bool = False) -> Checked:
    """Validate one question's answer as the model returned it. Never raises: a malformed answer comes back as covered=False with a dropped note."""
    if not isinstance(raw, dict):
        return Checked(False, [], [("malformed", str(raw)[:80])], malformed=True)
    sentences, dropped = [], []
    for s in raw.get("sentences") or []:
        if not isinstance(s, dict):
            dropped.append(("malformed", str(s)[:80]))
            continue
        text, quote = " ".join(str(s.get("text") or "").split()), " ".join(str(s.get("quote") or "").split())
        source = "previous" if (s.get("source") == "previous" and allow_previous and previous is not None) else "current"
        if not text or not quote:
            dropped.append(("empty", text[:80]))
        elif len(text) > C.MAX_SENTENCE_CHARS:
            dropped.append(("too_long", text[:80]))
        elif len(quote) > C.MAX_QUOTE_CHARS or len(quote) < C.MIN_QUOTE_CHARS:
            dropped.append(("quote_size", text[:80]))
        elif advice_words(text):
            dropped.append(("advice:" + ",".join(advice_words(text)), text[:80]))
        else:
            doc = previous if source == "previous" else current
            page = doc.find(quote) if doc is not None else None
            if page is None:
                dropped.append(("quote_not_found", text[:80]))
            else:
                ref = f"{doc.label}, page {page}" if previous is not None and allow_previous else f"page {page}"
                sentences.append({"text": text, "quote": quote, "quote_ref": ref, "source": source})
    sentences = sentences[: C.MAX_SENTENCES]
    claimed = bool(raw.get("covered", bool(raw.get("sentences"))))
    covered = claimed and bool(sentences)
    return Checked(covered, sentences if covered else [], dropped, claimed=claimed)


def enough(c: Checked, final: bool) -> bool:
    """A covered answer needs MIN_SENTENCES good sentences (one is accepted on the last attempt). 'Not covered' stands only when the model said so;
    a missing answer, or "covered" with nothing that survived the checks, is not an answer."""
    if c.malformed:
        return False
    if not c.claimed:
        return True
    return len(c.sentences) >= (1 if final else C.MIN_SENTENCES)


def parse_json(text: str) -> Dict[str, object]:
    """The model's JSON, tolerating a code fence. Returns the 'answers' mapping or {} when the reply is not what was asked for."""
    import json
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t)
    try:
        data = json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        try:
            data = json.loads(t[i:j + 1]) if 0 <= i < j else {}
        except ValueError:
            return {}
    ans = data.get("answers") if isinstance(data, dict) else None
    return ans if isinstance(ans, dict) else {}
