"""The site's words for the technical view, for the PDF. Reads technical_wording.json, which the web view (frontend/src/lib/prismTechnical.ts)
reads as an identical copy, so the screen and the PDF can never disagree.

COMPLIANCE: the model's own rating words (Strong Buy ... Sell) and verdict labels are never shown to readers. premium_pdf.py is kept
identical to upstream, so the report data is relabelled on a COPY before rendering, and every paragraph the PDF writes passes through
`safe_text` as a last line of defence (this also rewrites the 'target price' disclaimer that upstream prints)."""
import copy
import json
import re
import threading
from pathlib import Path

WORDING = json.loads((Path(__file__).with_name("technical_wording.json")).read_text(encoding="utf-8"))
BANDS = WORDING["bands"]
FORBIDDEN = re.compile(WORDING["forbidden"], re.I)
_PHRASES = [(re.compile(pattern, re.I), to) for pattern, to in WORDING["phrases"]]


def _match_case(source, to):
    return to[0].upper() + to[1:] if source[:1].isalpha() and source[0] == source[0].upper() else to


def safe_text(text):
    """Model text as it may be shown: advice words are replaced by descriptive ones. Idempotent."""
    if not text:
        return ""
    out = str(text)
    for pattern, to in _PHRASES:
        out = pattern.sub(lambda m, to=to: _match_case(m.group(0), to), out)
    return FORBIDDEN.sub(lambda m: _match_case(m.group(0), WORDING["words"][m.group(0).lower()]) if m.group(0).lower() in WORDING["words"] else "—", out)


def score_band(score):
    """Band of a full-precision score: >= 50, >= 20, > -20, > -50, else lowest."""
    if not isinstance(score, (int, float)) or isinstance(score, bool) or score != score or score in (float("inf"), float("-inf")):
        return "na"
    if score >= BANDS["strongPositive"]:
        return "strongpos"
    if score >= BANDS["positive"]:
        return "pos"
    if score > BANDS["neutral"]:
        return "neutral"
    return "neg" if score > BANDS["negative"] else "strongneg"


def rating_word(rating, score):
    """Same rule as ratingWord in prismTechnical.ts: no score means 'Not available'; the model's rating if known, else the score decides."""
    if not isinstance(score, (int, float)) or isinstance(score, bool) or score != score or score in (float("inf"), float("-inf")):
        return WORDING["bandWords"]["na"]
    known = WORDING["ratings"].get(" ".join(str(rating).lower().split())) if rating else None
    if known and known["tone"] != "na":
        return known["word"]
    return WORDING["bandWords"][score_band(score)]


def verdict_tone(label, tone):
    normal = re.sub(r"\s+", " ", str(label or "").replace("‘", "'").replace("’", "'").replace("ʼ", "'")).strip().upper()
    return WORDING["verdicts"].get(normal) or WORDING["toneAlias"].get(str(tone or "").strip().lower()) or "na"


def relabel_technical(technical):
    """A relabelled COPY of a technicalAssessment: descriptive rating and verdict words, safe factor text and notes."""
    out = copy.deepcopy(technical)
    for key in ("shortTerm", "longTerm"):
        part = out.get(key)
        if not isinstance(part, dict):
            continue
        part["rating"] = rating_word(part.get("rating"), part.get("score"))
        for factor in part.get("factors", []):
            factor["label"] = safe_text(factor.get("label"))
            factor["detail"] = safe_text(factor.get("detail"))
    verdict = out.get("verdict") or {}
    both = all(isinstance((out.get(k) or {}).get("score"), (int, float)) for k in ("shortTerm", "longTerm"))
    tone = verdict_tone(verdict.get("label"), verdict.get("tone")) if both else "na"
    out["verdict"] = {**verdict, "label": WORDING["verdictWords"][tone], "tone": tone}
    out["notes"] = [safe_text(note) for note in out.get("notes", [])]
    return out


def relabel_report(report):
    """The report with a relabelled technical assessment. The stored report (and its signed snapshot) is never changed."""
    if not isinstance(report, dict) or not isinstance(report.get("technicalAssessment"), dict):
        return report
    return {**report, "technicalAssessment": relabel_technical(report["technicalAssessment"])}


_installed = False
_install_lock = threading.Lock()


def render_compliant_pdf(report):
    """render_premium_pdf on the relabelled copy, with every paragraph passed through `safe_text`."""
    global _installed
    try:
        from . import premium_pdf
    except ImportError:
        import premium_pdf
    with _install_lock:
        if not _installed:
            original = premium_pdf.Paragraph

            class SafeParagraph(original):
                def __init__(self, text, *args, **kwargs):
                    super().__init__(safe_text(text), *args, **kwargs)

            premium_pdf.Paragraph = SafeParagraph
            _installed = True
    return premium_pdf.render_premium_pdf(relabel_report(report))
