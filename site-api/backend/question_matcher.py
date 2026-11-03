"""Recognises which question of the FinLit predefined question bank a user is really asking, in their own words.

The bank (question_bank.json, built from the Sena / FinLit Predefined Question Bank PDF by scripts/build_question_bank.py) holds 457 questions with IDs.
A user rarely types a question word for word, so the match is meaning-based but fully deterministic (no model, no network, no cost per message):
  - words are reduced to a canonical form (plurals, endings, and the finance synonyms: sales = revenue = turnover, PAT = net profit, borrowings = debt ...);
  - every question is a weighted word vector (rare words count more); the user's message is compared by cosine similarity, plus a bonus for shared word pairs;
  - the kind of question the message is about (company, fund, ETF, earnings call, market, screener, concept) nudges the score toward that part of the bank.
A match is `high` only when the best question is clearly ahead of the next one; otherwise the closest questions are returned as `related`, and below that nothing is claimed.
The matcher never answers: it names the question, so the assistant answers exactly that question from FinLit's verified data tools.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

BANK_PATH = Path(__file__).with_name("question_bank.json")
HIGH = 0.42          # best score needed for a confident match
MARGIN = 0.07        # and how far it must be ahead of the second-best question (different question)
SIBLING_MARGIN = 0.12   # two questions of the same section are often near-duplicates ("on demand" / "on pricing"): a clearer lead is needed to call one of them
RELATED = 0.28       # below this nothing is suggested

STOP = frozenset("""a an the of in on at to for from by with and or but is are was were be been being do does did has have had will would can could should may might
what which who whom whose how why when where whether if than then that this these those it its it's their there about over last past latest current currently please tell me show give
us we you your my our i any some each every also still just ever recent recently per into out up down as so not no yes get got s now""".split())

# canonical words: every key (after stemming) becomes its value
SYN: Dict[str, str] = {}
def _syn(canon: str, *words: str) -> None:
    for w in words: SYN[w] = canon
_syn("revenue", "sales", "turnover", "topline", "revenues")
_syn("pat", "pat", "netprofit", "patm")
_syn("ebitda", "ebitda", "ebit", "opm")
_syn("debt", "borrowing", "borrowings", "loan", "loans", "leverage", "leveraged", "indebted", "indebtedness", "liability", "liabilities")
_syn("grow", "growth", "growing", "grew", "grown", "expansion", "expand", "expanding", "increase", "increased", "rise", "risen", "rose", "rising", "improve", "improving", "improved")
_syn("decline", "decline", "declining", "fall", "falling", "fell", "drop", "dropped", "shrink", "shrinking", "decrease", "decreased", "weaken", "weakening")
_syn("compare", "compare", "comparison", "versus", "vs", "against", "relative", "benchmark")
_syn("peer", "peer", "peers", "competitor", "competitors", "rival", "rivals", "comparable", "similar")
_syn("mcap", "mcap", "marketcap", "capitalisation", "capitalization", "size")
_syn("pe", "pe", "pricetoearnings", "earningsmultiple")
_syn("pb", "pb", "pricetobook")
_syn("roe", "roe", "returnonequity")
_syn("roce", "roce", "returnoncapital")
_syn("eps", "eps", "earningspershare")
_syn("dividend", "dividend", "dividends", "payout")
_syn("cashflow", "cashflow", "cashflows")
_syn("fcf", "fcf", "freecashflow")
_syn("shareholding", "shareholding", "shareholder", "shareholders", "stake", "holding", "holdings", "ownership", "owns", "owned")
_syn("promoter", "promoter", "promoters", "founder", "founders")
_syn("fii", "fii", "fpi", "foreign")
_syn("dii", "dii", "domestic")
_syn("fund", "fund", "funds", "scheme", "schemes", "mf", "mutual")
_syn("expense", "expense", "expenses", "ter", "fee", "fees", "charge", "charges", "cost", "costs")
_syn("return", "return", "returns", "performance", "performed", "performing", "perform")
_syn("risk", "risk", "risks", "risky", "volatility", "volatile", "riskier", "safe", "safer")
_syn("price", "price", "prices", "quote", "trading", "traded", "trades")
_syn("etf", "etf", "etfs", "exchangetraded")
_syn("score", "score", "scores", "rating", "ratings", "rated", "grade")
_syn("margin", "margin", "margins", "profitability", "profitable")
_syn("debtequity", "debttoequity", "de")
_syn("workingcapital", "workingcapital", "wc")
_syn("sector", "sector", "sectors", "industry", "industries")
_syn("quarter", "quarter", "quarters", "quarterly", "qtr", "q1", "q2", "q3", "q4")
_syn("year", "year", "years", "annual", "yearly", "fy", "yoy")
_syn("earn", "earning", "earnings")
_syn("concall", "concall", "transcript", "earnings call", "call")
_syn("guidance", "guidance", "outlook", "forecast", "projection", "expects", "expect", "expected")
_syn("diversification", "diversify", "diversified", "diversifying", "diversification")
_syn("manage", "manage", "manager", "managers", "manages", "managed", "managing", "managing")
_syn("split", "split", "breakup", "breakdown", "composition", "mix", "divided", "distribution", "allocation", "makeup")
_syn("repay", "repay", "repaying", "repaid", "repayment", "repays")
_syn("raise", "raise", "raising", "raised", "raises")
_syn("low", "low", "lower", "lowest", "cheap", "cheaper", "inexpensive", "less", "fewer", "below", "under", "beneath")
_syn("high", "high", "higher", "highest", "strong", "stronger", "strongest", "more", "greater", "bigger", "above", "over", "exceeding")
_syn("guidance", "guide", "guided", "guiding")
_syn("management", "management", "ceo", "leadership")
_syn("ratio", "ratio", "ratios", "percentage", "proportion", "percent")
_syn("redflag", "redflag", "redflags", "warning", "warnings", "concern", "concerns")
_syn("undervalued", "undervalued", "bargain")
_syn("expensive", "expensive", "overvalued", "costly", "pricey", "stretched")
_syn("valuation", "valuation", "valuations", "valued")
_syn("nav", "nav", "netassetvalue")
_syn("sip", "sip", "systematic")
_syn("aum", "aum", "assetsundermanagement", "corpus")
_syn("rsi", "rsi", "relativestrength")
_syn("moving", "dma", "sma", "ema", "movingaverage")

PHRASES: Sequence[Tuple[re.Pattern, str]] = tuple((re.compile(p, re.I), r) for p, r in (
    (r"\bnet profit\b|\bprofit after tax\b|\bearnings after tax\b|\bbottom line\b", " pat "),
    (r"\bprofit before tax\b", " pbt "),
    (r"\boperating profit\b|\boperating income\b", " ebitda "),
    (r"\bcompetitors?\b|\brivals?\b", " peer closest "),
    (r"\bcapital work[- ]in[- ]progress\b", " cwip "),
    (r"\bbreak[- ]?up\b|\bbreak down\b", " split "),
    (r"\bpay(?:ing|s)? (?:it )?back\b|\bpaid back\b", " repay "),
    (r"\btak(?:e|es|ing) on\b|\bborrow(?:s|ing|ed)? more\b", " raise "),
    (r"\bsince when\b|\bhow long\b|\bfor how long\b", " tenure "),
    (r"\b(?:going|goes|go|moving|moves|trending|trends|heading)\s+up\b|\bup or down\b", " grow decline trend "),
    (r"\b(?:going|goes|go|moving|moves|trending|trends|heading)\s+down\b", " decline "),
    (r"\bstandard deviation\b|\bstd\.? ?dev\b|\bstdev\b", " risk "),
    (r"\boperat(?:e|es|ing|ed) in\b", " "),
    (r"\bfree cash flow\b", " fcf "),
    (r"\boperating cash flow\b|\bcash from operations\b|\bcfo\b", " cfo cashflow "),
    (r"\bcash flow\b", " cashflow "),
    (r"\bmarket cap(?:itali[sz]ation)?\b", " mcap "),
    (r"\bprice[- ]to[- ]earnings?\b|\bp\s*/\s*e\b|\bp\.e\.?\b", " pe "),
    (r"\bprice[- ]to[- ]book\b|\bp\s*/\s*b\b", " pb "),
    (r"\bdebt[- ]to[- ]equity\b|\bd\s*/\s*e\b", " debtequity "),
    (r"\breturn on equity\b", " roe "),
    (r"\breturn on capital employed\b|\breturn on capital\b", " roce "),
    (r"\bearnings per share\b", " eps "),
    (r"\bexpense ratio\b", " expense "),
    (r"\bworking capital\b", " workingcapital "),
    (r"\bexchange[- ]traded fund\b", " etf "),
    (r"\bmutual funds?\b", " fund "),
    (r"\bnet asset value\b", " nav "),
    (r"\bassets under management\b", " aum "),
    (r"\bearnings call\b|\bconference call\b|\bcon[- ]call\b", " concall "),
    (r"\bred flags?\b", " redflag "),
    (r"\bfinlit iq\b|\bfinlit score\b|\bprism\b", " score "),
    (r"\bgrowth rate\b", " grow "),
    (r"\bcagr\b", " cagr "),
    (r"\b(\d+)[- ]?(?:yr|yrs|year|years|y)\b", r" \1 year "),
    (r"\b(\d+)[- ]?(?:q|quarters?)\b", r" \1 quarter "),
    (r"\bwhat'?s\b|\bwhats\b", " "),
))

# what kind of question the message is about: words that point to a part of the bank
GROUP_HINT: Dict[str, Sequence[str]] = {
    "Mutual Fund": ("fund", "nav", "sip", "aum", "amc", "scheme", "elss", "factsheet", "manage", "folio", "benchmark"),
    "ETF": ("etf", "tracking", "inav", "premium", "discount", "basket", "bees"),
    "Earnings Call": ("concall", "management", "guidance", "analyst", "said", "commentary", "tone"),
    "Screener Presets": ("screen", "screener", "preset", "filter", "list", "stock", "shortlist"),
    "Market and Sector": ("index", "nifty", "sensex", "sector", "breadth", "gainer", "loser", "mover", "market", "flows", "fii", "dii", "advanc", "decliner"),
    "FinLit": ("mean", "meaning", "define", "definition", "explain", "formula", "basics", "tax", "taxation", "glossary", "finlit"),
    "Sector-specific": ("bank", "banks", "nbfc", "insurance", "airline", "pharma", "cement", "auto", "telecom", "steel", "realty", "fmcg", "retail", "oil", "power"),
}

IMPLIED = {"fund": "fund", "fund_2": "fund", "etf": "etf", "sector": "sector", "index": "index"}
LOOSE = frozenset({"sector", "index", "market", "stock"})   # words that sit beside any company name ("which sector is Infosys in"): they do not make the message a market or screener question
_WORD = re.compile(r"[a-z0-9]+")
NUMWORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "twelve": "12", "fifteen": "15", "twenty": "20"}
_NUMW = re.compile(r"\b(" + "|".join(NUMWORDS) + r")\b", re.I)


def stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"): return w[:-3] + "y"
    if len(w) > 4 and w.endswith("sses"): return w[:-2]
    if len(w) > 4 and w.endswith("es") and w[-3] in "sxz": return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")): return w[:-1]
    if len(w) > 5 and w.endswith("ing"): return w[:-3]
    if len(w) > 4 and w.endswith("ed"): w = w[:-2]
    if len(w) > 4 and w.endswith("e") and not w.endswith(("ee", "ye")): return w[:-1]     # advance / advanced / advancing all meet at "advanc"
    return w


def tokens(text: str) -> List[str]:
    t = re.sub(r"\{\w+\}", " ", (text or "").lower().replace("&", " and ").replace("’", "'"))
    t = _NUMW.sub(lambda m: NUMWORDS[m.group(1).lower()], t)
    for rx, rep in PHRASES:
        t = rx.sub(rep, t)
    out: List[str] = []
    for w in _WORD.findall(t):
        if w in STOP: continue
        base = SYN.get(w) or SYN.get(stem(w))
        w = stem(base) if base else stem(w)          # a canonical word and the same word typed literally must reach the same form ("sales" and "revenue")
        if w in STOP: continue
        out.append(w)
    return out


_STARTERS = frozenset("what whats which who how why when where is are does do did can could should would will show give tell explain define list compare hello hi hey thanks thank ok okay please i my".split())


def _known(w: str, vocab) -> bool:
    lw = w.lower()
    return lw in vocab or stem(lw) in vocab or SYN.get(lw) in vocab or SYN.get(stem(lw)) in vocab or lw in STOP or lw in _STARTERS


def mask_entities(text: str, vocab) -> Tuple[str, int]:
    """Blank out the names in a message (a run of capitalised words that includes at least one word the bank does not know: "Parag Parikh Flexi Cap", "TCS", "Mirae Asset Large Cap"),
    so a name's ordinary words ("flexi cap", "large cap") are not read as the question. Returns (the text without the names, how many names were found)."""
    words = list(re.finditer(r"[A-Za-z][A-Za-z&]*", text or ""))
    out, found, i = list(text or ""), 0, 0
    while i < len(words):
        w = words[i].group(0)
        if w[0].isupper() and w.lower() not in _STARTERS:
            j = i
            while j + 1 < len(words) and words[j + 1].group(0)[0].isupper() and words[j + 1].group(0).lower() not in _STARTERS and words[j + 1].start() - words[j].end() <= 1:
                j += 1
            run = words[i:j + 1]
            if any(not _known(x.group(0), vocab) for x in run):
                found += 1
                for x in run:
                    for k in range(x.start(), x.end()): out[k] = " "
            i = j + 1
        else:
            i += 1
    return "".join(out), found


def has_entity(text: str, vocab) -> bool:
    return mask_entities(text, vocab)[1] > 0


@dataclass(frozen=True)
class Match:
    id: str
    text: str
    group: str
    path: Tuple[str, ...]
    score: float
    placeholders: Tuple[str, ...] = ()


@dataclass
class Result:
    confidence: str                      # "high" | "related" | "none"
    best: Optional[Match] = None
    related: List[Match] = field(default_factory=list)
    term: Optional[str] = None           # for the "What is {term}?" question
    years: Optional[int] = None          # the {n} the user named ("last 3 years")


class QuestionBank:
    def __init__(self, questions: Sequence[dict]):
        self.q = list(questions)
        self.toks = [tokens(x["text"]) + sorted({IMPLIED[p] for p in x.get("placeholders") or () if p in IMPLIED}) + tokens(" ".join(x.get("path") or ())) for x in self.q]   # the section title is meaning the question sits in   # a {fund} question is about a fund even when the word is not written
        df: Counter = Counter()
        for t in self.toks: df.update(set(t))
        n = len(self.q)
        self.idf = {w: math.log(1 + n / c) for w, c in df.items()}
        self.vec = [self._vector(t) for t in self.toks]
        self.big = [self._bigrams(t) for t in self.toks]

    def _vector(self, toks: Sequence[str]) -> Dict[str, float]:
        tf = Counter(toks)
        v = {w: (1 + math.log(c)) * self.idf.get(w, 0.0) for w, c in tf.items() if w in self.idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    @staticmethod
    def _bigrams(toks: Sequence[str]) -> frozenset:
        return frozenset(zip(toks, toks[1:]))

    def score_all(self, message: str) -> List[Tuple[float, int]]:
        masked, n_names = mask_entities(message, self.idf)
        entity = n_names > 0
        qt = tokens(masked)
        known = [w for w in qt if w in self.idf]
        if not known: return []
        concept = bool(re.search(r"\b(how (?:do|to|can|should) (?:i|you|we)|explain|meaning|mean|what does|why does|how is|how are)\b", message or "", re.I))
        qv, qb = self._vector(qt), self._bigrams(known)
        words = set(known)
        out: List[Tuple[float, int]] = []
        for i, v in enumerate(self.vec):
            dot = sum(x * v.get(w, 0.0) for w, x in qv.items())
            if dot <= 0: continue
            both = len(qb & self.big[i])
            bonus = 0.12 * both / max(1, min(len(qb), len(self.big[i]))) if qb and self.big[i] else 0.0
            cover = sum(self.idf[w] for w in set(self.toks[i]) if w in words) / (sum(self.idf[w] for w in set(self.toks[i])) or 1.0)   # how much of the question's own meaning the message covers
            s = 0.62 * dot + 0.26 * cover + bonus
            g = self.q[i]["group"]
            if any(h in words for h in GROUP_HINT.get(g, ())): s += 0.05
            ph = bool(set(self.q[i].get("placeholders") or ()) & {"company", "fund", "etf"})
            if "redflag" in self.toks[i] and "redflag" not in words: s -= 0.08                    # the red-flag variants of a question are for a message that asks about red flags
            two = any(p.endswith("_2") for p in self.q[i].get("placeholders") or ())
            if two and n_names < 2: s -= 0.12                                           # a question about two funds / companies needs two names
            elif two and n_names >= 2: s += 0.06
            if concept and g == "FinLit": s += 0.08                                  # "how do I read ...", "explain ...": a concept question
            elif entity: s += 0.07 if ph else (-0.40 if g == "FinLit" else -0.10)   # a named company / fund asks about that one: a concept lookup or a generic list is not it
            else: s += -0.05 if ph else (0.05 if g == "FinLit" else 0.0)           # no name: a concept question is likelier than one about "a company"
            if g in ("Mutual Fund", "ETF") and not any(h in words for h in GROUP_HINT[g]): s -= 0.15       # a message that never speaks of a fund or ETF is not about one
            elif g in ("Market and Sector", "Screener Presets", "Earnings Call") and not any(h in words for h in GROUP_HINT[g] if not (entity and h in LOOSE)): s -= 0.12   # nor of the market, a screen or a call
            if g == "Sector-specific" and not any(h in words for h in GROUP_HINT["Sector-specific"]): s -= 0.12   # sector sets only when the message is about that kind of company
            out.append((s, i))
        out.sort(key=lambda x: -x[0])
        return out

    def match(self, message: str, top: int = 3) -> Result:
        text = (message or "").strip()
        res = Result("none")
        yrs = re.search(r"\b(?:last|past|previous|over|for)\s+(\d{1,2})\s*(?:years?|yrs?|y)\b", text, re.I) or re.search(r"\b(\d{1,2})[- ]?(?:years?|yrs?)\b", text, re.I)
        if yrs: res.years = int(yrs.group(1))
        scored = self.score_all(text)
        define = re.match(r"^\s*(?:what\s+(?:is|are|does)|what's|whats|define|meaning of|explain|tell me about)\s+(?:a |an |the )?(.{2,60}?)\s*(?:mean|\?)?\s*$", text, re.I)
        term = define.group(1).strip() if define and len(define.group(1).split()) <= 5 else None
        pure = bool(term) and not re.search(r"\b(of|for|in|at|by|between)\b|'s\b", term, re.I) and not re.search(r"\b[A-Z][a-z]{2,}", term)     # "what is EBITDA", not "what is the PE of TCS" or "what is Reliance's debt to EBITDA"
        gen = next((m for m in self.q if m["id"] == "F.1.1.1"), None)
        if pure:
            concept = [(sc, i) for sc, i in scored if self.q[i]["group"] == "FinLit" and self.q[i]["id"] != "F.1.1.1"]
            if concept and concept[0][0] >= 0.45:
                scored = concept + [x for x in scored if x not in concept]
            else:
                res.confidence, res.term, res.best = "high", term, _m(gen, 0.6)
                res.related = [_m(self.q[i], sc) for sc, i in scored[:top - 1]]
                return res
        elif scored:
            # an off-topic message shares a stray word with the bank ("today", "list"): most of what it says must be words the bank knows (company names do not count against it)
            known = unknown = 0
            for w in re.findall(r"[A-Za-z0-9]+", text):
                canon = tokens(w)
                if not canon: continue
                if canon[0] in self.idf: known += 1
                elif not (w[0].isupper() or w.isupper()): unknown += 1
            if (known < 2 and unknown >= known or known + unknown and known / (known + unknown) < 0.45) and scored[0][0] < 0.50: scored = []
        if not scored:
            if term and gen:
                res.confidence, res.term, res.best = "related", term, _m(gen, 0.3)
            return res
        ms = [_m(self.q[i], s) for s, i in scored[:top + 2]]
        best, second = ms[0], (ms[1] if len(ms) > 1 else None)
        if best.score >= HIGH and (second is None or best.score - second.score >= (SIBLING_MARGIN if second.id.rsplit('.', 1)[0] == best.id.rsplit('.', 1)[0] else MARGIN)):
            res.confidence, res.best, res.related = "high", best, ms[1:top]
        elif best.score >= RELATED:
            res.confidence, res.best, res.related = "related", best, ms[1:top]
        return res


def _m(x: dict, score: float) -> Match:
    return Match(x["id"], x["text"], x["group"], tuple(x.get("path") or ()), round(score, 3), tuple(x.get("placeholders") or ()))


_bank: Optional[QuestionBank] = None


def bank() -> QuestionBank:
    global _bank
    if _bank is None:
        _bank = QuestionBank(json.loads(BANK_PATH.read_text(encoding="utf-8"))["questions"])
    return _bank


# which verified data tools answer which part of the bank (names are FinLit's MCP tools); a hint for the assistant, never a limit
TOOL_HINTS: Dict[str, str] = {
    "C.1": "search_stocks, get_company_profile, get_stock_quote", "C.2": "get_financials (profit and loss, quarterly and annual)", "C.3": "get_financials (balance sheet)",
    "C.4": "get_financials (cash flow)", "C.5": "get_ratios, get_financials", "C.6": "get_ratios, get_stock_quote", "C.7": "get_shareholding", "C.8": "get_price_history, get_stock_quote",
    "C.9": "get_finlit_score", "C.10": "get_financials, get_quarter_results", "C.11": "search_stocks, get_ratios, get_stock_quote for each company", "C.12": "get_ratios, get_financials, get_shareholding",
    "M": "search_funds, get_fund_details", "E": "list_etfs, get_etf", "S.1": "get_market_overview", "S.2": "get_market_overview", "S.3": "screen_stocks, get_market_overview", "S.4": "get_fii_dii_flows", "S.5": "get_market_overview",
    "P": "screen_stocks", "X": "search_stocks, get_company_profile, get_financials, get_ratios",
}


def tool_hint(qid: str) -> str:
    parts = qid.split(".")
    for key in (".".join(parts[:2]), parts[0]):
        if key in TOOL_HINTS: return TOOL_HINTS[key]
    return ""


def directive(res: Result) -> str:
    """The instruction added to the assistant's system prompt for one message: answer the matched bank question, completely, from the data tools. Empty when nothing matched."""
    if res.best and res.confidence == "related" and res.best.score >= 0.34 and not res.term:
        cands = [res.best] + [m for m in res.related[:1] if res.best.score - m.score <= 0.08]
        listed = " ".join(f'({c.id}) "{c.text}"' for c in cands)
        return ("\n\nFinLit question bank: the message is close to " + ("these predefined questions: " if len(cands) > 1 else "this predefined question: ") + listed + " "
                "If it is what the user means, answer it in full from the data tools (every part of it, and say plainly what is not available); if the user means both, answer both; "
                "if it is not what they asked, answer their own question as usual.")
    if res.confidence != "high" or not res.best: return ""
    b = res.best
    what = f"What is {res.term}?" if res.term else b.text
    hint = tool_hint(b.id)
    n = f" The user named {res.years} years: use that for {{n}}." if res.years and "n" in b.placeholders else ""
    return (f"\n\nFinLit question bank: the user's message is this predefined question ({b.id}, {b.group}, {' > '.join(b.path)}): \"{what}\" "
            f"Answer exactly this question, in full: cover every part of it (each period, each ratio, each comparison it names), and say plainly which part is not available rather than skipping it.{n} "
            + (f"The data tools that answer it: {hint}. " if hint and b.group not in ("FinLit",) else "")
            + ("It is a concept question: explain it simply with an Indian example, and where FinLit shows the metric, say where. " if b.group == "FinLit" else "")
            + "Keep the figures, the period and the as-of date together. Do not drift to other questions. This question may use up to 170 words and up to 6 lines starting with '- '.")


def related_lines(res: Result, limit: int = 2) -> List[str]:
    """Up to `limit` closest other questions, worded as the user could ask them next (the {company} placeholder is dropped when the message did not name one)."""
    out = []
    for m in res.related[:limit]:
        t = re.sub(r"\{\w+\}'s", "its", m.text); t = re.sub(r"\{\w+\}", "it", t)
        out.append(t)
    return out
