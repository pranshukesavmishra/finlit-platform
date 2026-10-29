"""The site's words for the technical view (research API copy of site-api/backend/technical_wording.py; technical_wording.json is an identical copy of the
site-api file, and tests compare both). The API never sends the model's buy/sell/hold words to a browser: `relabel_technical` maps them.
Only model-produced technical fields are touched."""
import copy
import json
import re
from pathlib import Path

WORDING = json.loads((Path(__file__).with_name("technical_wording.json")).read_text(encoding="utf-8"))
BANDS = WORDING["bands"]
ALIGNMENT = WORDING["alignment"]
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


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and value not in (float("inf"), float("-inf"))


def trend_band(score):
    """positive (+20 or more), negative (-20 or less), neutral in between; None without a score. The band rule of the trend alignment."""
    if not _number(score):
        return None
    return "positive" if score >= ALIGNMENT["bands"]["positive"] else "negative" if score <= ALIGNMENT["bands"]["negative"] else "neutral"


def trend_alignment(short_score, long_score):
    """How the short-term and the long-term trend line up (short-term band x long-term band, 9 cells; finlit_technicals v1.1 stlt.ALIGNMENT).
    None unless both scores are numbers. The label only describes the two trends. Derived from the two scores alone, so a report stored before
    this existed gets it too."""
    st, lt = trend_band(short_score), trend_band(long_score)
    if st is None or lt is None:
        return None
    cells = [{"stBand": c["st"], "ltBand": c["lt"], "code": c["code"], "label": c["label"], "tone": c["tone"], "current": c["st"] == st and c["lt"] == lt} for c in ALIGNMENT["cells"]]
    now = next(c for c in cells if c["current"])
    words = ALIGNMENT["bandWords"]
    return {"label": now["label"], "code": now["code"], "tone": now["tone"], "stBand": st, "ltBand": lt, "stBandWord": words[st], "ltBandWord": words[lt],
            "rule": ALIGNMENT["rule"], "cells": cells}


def relabel_technical(technical):
    """A relabelled COPY of a technicalAssessment: descriptive rating and verdict words, safe factor text and notes."""
    out = copy.deepcopy(technical)
    for key in ("shortTerm", "longTerm"):
        part = out.get(key)
        if not isinstance(part, dict):
            continue
        if "rating" in part:
            part["rating"] = rating_word(part.get("rating"), part.get("score"))
        for factor in part.get("factors") or []:
            if isinstance(factor, dict):
                for key in ("label", "detail"):
                    if key in factor:
                        factor[key] = safe_text(factor[key])
    both = all(isinstance(out.get(k), dict) for k in ("shortTerm", "longTerm"))
    align = trend_alignment(out["shortTerm"].get("score"), out["longTerm"].get("score")) if both else None
    if align:
        out["trendAlignment"] = align
    if isinstance(out.get("verdict"), dict):   # the model's verdict label is replaced by the descriptive alignment label (same nine cells, same tone)
        out["verdict"] = {**out["verdict"], "label": align["label"] if align else ALIGNMENT["notAvailable"], "tone": align["tone"] if align else "na"}
    if isinstance(out.get("notes"), list):
        out["notes"] = [safe_text(note) for note in out["notes"]]
    return out


def relabel_report(report):
    """The report with a relabelled technical assessment. The stored report (and its signed snapshot) is never changed."""
    if not isinstance(report, dict) or not isinstance(report.get("technicalAssessment"), dict):
        return report
    return {**report, "technicalAssessment": relabel_technical(report["technicalAssessment"])}
