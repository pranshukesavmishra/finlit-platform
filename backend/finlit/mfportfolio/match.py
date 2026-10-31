"""A cleaned row -> a mutual fund scheme. Pure code over an `Index` of the schemes in mf_schemes (about 14,000 rows, built once per data version).

Order, first rule that answers wins, and a rule that is not sure never guesses, it hands the choice to the member:
  1. AMFI scheme code   the code exists -> matched. If the file also names the fund and the name does not look like that scheme (a mis-read column),
                        the row is `choose` with that scheme as the suggestion.
  2. ISIN               the ISIN (or its IDCW re-investment twin) belongs to one scheme -> matched; to several -> `choose`.
                        An ISIN that disagrees with the AMFI code -> `choose` with both.
  3. exact name         the name, with plan / option / filler words taken out, equals one scheme family's name; then the plan (Direct / Regular) and option
                        (Growth / IDCW) the file states narrow it. One scheme left -> matched (via "name"). The file gives no plan or option and the family has
                        several -> `choose` (a Direct and a Regular plan of one fund are different holdings).
  4. fuzzy              names that share most of their words (Jaccard >= 0.7) -> `choose` with the closest first. A fuzzy match is NEVER matched on its own.
  otherwise `not_found`.
Statuses: matched | choose | not_found. Candidates are the schemes to pick from (at most MAX_CANDIDATES), best first, active schemes before stopped ones.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from .parse import Clean

MAX_CANDIDATES = 8
FUZZY_MIN = 0.7
SANITY_MIN = 0.5          # an AMFI code / ISIN match whose scheme name shares less than this with the file's name is double-checked by the member

_STOP = frozenset("the and of scheme fund funds mutual plan plans option options an open ended openended".split())
_PLAN_WORDS = {"direct": "Direct", "dir": "Direct", "regular": "Regular", "reg": "Regular"}
_OPT_GROWTH = frozenset({"growth", "gr"})
_OPT_IDCW = frozenset({"idcw", "dividend", "div", "payout", "reinvestment", "reinvest"})
_FREQ = frozenset("daily weekly fortnightly monthly quarterly half yearly annual annually halfyearly".split())
_FORMERLY = re.compile(r"\((?:\s*(?:formerly|erstwhile|earlier|previously|ex|renamed|w\.?e\.?f\.?)\b[^)]*)\)", re.I)
_PAREN = re.compile(r"\([^)]*\)")
_JOIN = [(re.compile(r"\b(mid|large|small|flexi|multi|micro|blue)\s*-?\s*(cap|chip)\b"), r"\1\2"), (re.compile(r"\bhalf\s+yearly\b"), "halfyearly"),
         (re.compile(r"\bult(?:ra)?\s*-?\s*short\b"), "ultrashort"), (re.compile(r"\bnifty\s*-?\s*(\d+)\b"), r"nifty\1")]


def _words(name: str) -> List[str]:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9()]+", " ", s)
    s = _FORMERLY.sub(" ", s)
    s = _PAREN.sub(lambda m: " " + m.group(0)[1:-1] + " " if re.fullmatch(r"\(\s*(g|d|growth|idcw|dividend|direct|regular|payout|reinvest\w*)\s*\)", m.group(0)) else " ", s)
    s = s.replace("(", " ").replace(")", " ")
    for rx, rep in _JOIN:
        s = rx.sub(rep, s)
    return s.split()


def analyse(name: str) -> Tuple[FrozenSet[str], Optional[str], Optional[str]]:
    """(family words, plan, option class). The family words are the fund's own name with the plan, option, IDCW frequency and filler words taken out
    ('X Fund - Direct Plan - Growth' and 'X FUND (an open ended scheme) Direct Growth' agree). plan / option are None when the name does not say."""
    toks = _words(name)
    plan: Optional[str] = None
    option: Optional[str] = None
    keep = []
    for t in toks:
        if t in _PLAN_WORDS:
            plan = plan or _PLAN_WORDS[t]
        elif t in _OPT_GROWTH or t == "g":            # '(G)' is how some statements write Growth, '(D)' Dividend
            option = option or "Growth"
        elif t in _OPT_IDCW or t == "d":
            option = "IDCW"
        elif t in _FREQ or t in _STOP or t == "bonus":
            continue
        else:
            keep.append(t)
    return frozenset(keep), plan, option


@dataclass(frozen=True)
class Scheme:
    code: int
    name: str
    amc: str
    plan: str
    option: str           # option_class: Growth | IDCW | Other
    label: str
    active: bool
    isin: str
    isin2: str
    category: str
    nav_date: Optional[str]
    words: FrozenSet[str]

    def view(self) -> Dict[str, Any]:
        return {"code": self.code, "name": self.name, "amc": self.amc, "plan": self.plan, "option": self.label or self.option, "active": self.active, "navDate": self.nav_date}


class Index:
    """The schemes, looked up by code, by ISIN and by family words."""

    def __init__(self, rows: Iterable[Any]):
        self.by_code: Dict[int, Scheme] = {}
        self.by_isin: Dict[str, List[Scheme]] = defaultdict(list)
        self.by_words: Dict[FrozenSet[str], List[Scheme]] = defaultdict(list)
        self.by_token: Dict[str, Set[FrozenSet[str]]] = defaultdict(set)
        for r in rows:
            words, _, _ = analyse(r["name"])
            s = Scheme(int(r["code"]), r["name"], r["amc"], r["plan"], r["option_class"], r["option_label"] or "", bool(r["active"]), (r["isin"] or "").upper(),
                       (r["isin_reinvest"] or "").upper(), r["category"] or "", r["nav_date"].isoformat() if r["nav_date"] else None, words)
            self.by_code[s.code] = s
            for i in {s.isin, s.isin2} - {""}:
                self.by_isin[i].append(s)
            if words:
                self.by_words[words].append(s)
        for w in self.by_words:
            for t in w:
                self.by_token[t].add(w)

    def __len__(self) -> int:
        return len(self.by_code)


def _order(schemes: List[Scheme]) -> List[Scheme]:
    return sorted(schemes, key=lambda s: (not s.active, s.plan != "Direct", s.option != "Growth", s.name, s.code))


def _jaccard(a: FrozenSet[str], b: FrozenSet[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass
class Match:
    status: str                            # matched | choose | not_found
    via: Optional[str] = None              # amfi | isin | name
    scheme: Optional[Scheme] = None        # the scheme when matched; the suggestion when it is a sanity `choose`
    candidates: Optional[List[Scheme]] = None
    reason: str = ""


def _narrow(cands: List[Scheme], plan: Optional[str], option: Optional[str]) -> List[Scheme]:
    out = cands
    if plan:
        out = [s for s in out if s.plan == plan]
    if option:
        out = [s for s in out if s.option == option]
    return out


def match_row(ix: Index, row: Clean) -> Match:
    words, plan, option = analyse(row.name) if row.name else (frozenset(), None, None)
    by_amfi = ix.by_code.get(row.amfi) if row.amfi else None
    by_isin = _order(ix.by_isin.get(row.isin, [])) if row.isin else []
    if by_amfi and row.isin and by_isin and by_amfi.code not in {s.code for s in by_isin}:
        return Match("choose", None, None, _order([by_amfi] + by_isin)[:MAX_CANDIDATES], "The AMFI code and the ISIN in the file point to different funds. Choose the right one.")
    if by_amfi:
        if row.name and words and _jaccard(words, by_amfi.words) < SANITY_MIN:
            return Match("choose", "amfi", by_amfi, [by_amfi], "The AMFI code in the file belongs to a fund whose name does not look like the name in the file. Check it, then choose.")
        return Match("matched", "amfi", by_amfi)
    if by_isin:
        act = [s for s in by_isin if s.active]
        pick = by_isin[0] if len(by_isin) == 1 else act[0] if len(act) == 1 else None
        if pick is None:
            return Match("choose", "isin", None, by_isin[:MAX_CANDIDATES], "More than one fund shares this ISIN. Choose the right one.")
        if row.name and words and _jaccard(words, pick.words) < SANITY_MIN:
            return Match("choose", "isin", pick, [pick], "The ISIN in the file belongs to a fund whose name does not look like the name in the file. Check it, then choose.")
        return Match("matched", "isin", pick)
    if not words:
        return Match("not_found", None, None, [], "The row has no fund name, ISIN or AMFI code to match on." if not row.name else "The name has no usable words.")
    exact = ix.by_words.get(words, [])
    if exact:
        narrowed = _narrow(exact, plan, option)
        act = [s for s in narrowed if s.active]
        stated = bool(plan and option)
        if narrowed and (stated or len(exact) == 1):
            pick = narrowed[0] if len(narrowed) == 1 else act[0] if len(act) == 1 else None
            if pick is not None:
                return Match("matched", "name", pick)
        pool = narrowed or exact
        why = ("The fund was found, but not in the plan and option the file names. Choose yours." if not narrowed and (plan or option) else
               "The name does not say Direct or Regular, or Growth or IDCW, and this fund has more than one plan or option. Choose yours."
               if not stated else "More than one scheme has this name, plan and option. Choose yours.")
        return Match("choose", "name", None, _order(pool)[:MAX_CANDIDATES], why)
    # fuzzy: families that share most words. Suggestions only.
    seen: Dict[FrozenSet[str], int] = defaultdict(int)
    for t in words:
        for fam in ix.by_token.get(t, ()):
            seen[fam] += 1
    scored = sorted(((_jaccard(words, fam), fam) for fam, n in seen.items() if n >= 2 or len(words) == 1), key=lambda x: (-x[0], sorted(x[1])))
    near = [(j, fam) for j, fam in scored[:6] if j >= FUZZY_MIN]
    if not near:
        return Match("not_found", None, None, [], "No fund with this name was found. Search for it below.")
    cands: List[Scheme] = []
    for _, fam in near:
        cands += _order(_narrow(ix.by_words[fam], plan, option) or ix.by_words[fam])
    return Match("choose", "fuzzy", None, cands[:MAX_CANDIDATES], "The name is close to these funds but not the same. Choose yours; nothing is picked for you.")
