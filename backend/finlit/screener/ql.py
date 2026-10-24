"""The query language of the query builder: a tokenizer, a recursive-descent parser and a checker. No `eval`, no `exec`: a query is text that becomes a tree
(AST) and the tree is evaluated against the screener table (finlit/screener/qeval.py).

    query      := line (NEWLINE line)*                      lines are joined with AND, at the lowest precedence: "A OR B <newline> C" is "(A OR B) AND C"
    line       := or_expr
    or_expr    := and_expr (OR and_expr)*
    and_expr   := condition (AND condition)*                AND binds tighter than OR
    condition  := '(' or_expr ')' | expr op expr | expr BETWEEN expr AND expr
    op         := > >= < <= = !=                            (also == <> ≥ ≤ ≠ => =<)
    expr       := term (('+'|'-') term)*
    term       := factor (('*'|'/') factor)*
    factor     := '-' factor | NUMBER [unit] | METRIC | YES | NO | '(' expr ')'
    unit       := % | Cr | crore | lakh | lakh crore | x | times | days      (a "₹" or "Rs" in front of a number means rupees)

A metric is written by any of its names (finlit/screener/qaliases.py); the longest name that fits wins, so "Price / Sales" is the P/S ratio and
"ROE 3 year average" is one metric. Every problem found is returned at once, each with its position, never just the first.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .catalog import BY_KEY, GROUP_LABEL, allowed
from .qaliases import ALIAS, ALIAS_TEXT, PREFIXES, UNIT_WORDS, norm

MAX_CHARS = 2000
MAX_CONDITIONS = 30
CMP_OPS = (">", ">=", "<", "<=", "=", "!=")
OP_WORDS = {">": "is greater than", ">=": "is at least", "<": "is less than", "<=": "is at most", "=": "is equal to", "!=": "is not equal to"}
UNIT_NAME = {"pct": "a percentage (%)", "Cr": "an amount in ₹ crore", "Rs": "an amount in rupees (₹)", "x": "a multiple (times)", "d": "a number of days",
             "n": "a count", "pts": "a score in points", "flag": "a yes/no answer"}
SUFFIX_TEXT = {"pct": "%", "Cr": "Cr", "Rs": "₹", "x": "x", "d": "days", "flag": "yes/no"}
TIER_NAME = {"basic": "Basic", "silver": "Silver", "gold": "Gold"}
# ownership changes are measured in percentage points: "Promoter holding change > 2%" reads naturally
PCT_POINTS = {k for k, m in BY_KEY.items() if m.unit == "pts" and (m.group == "ownership" or k == "opm_change")}
STOP_WORDS = {"the", "of", "a", "an", "to", "in", "and", "or", "ratio", "per", "for", "is", "vs"}


# ------------------------------------------------------------------------------------------------------------------------------ problems
@dataclass
class Problem:
    code: str
    message: str
    start: int
    end: int
    severity: str = "error"          # error: the query cannot run; warning: it runs but may not mean what you think
    fixes: List[dict] = field(default_factory=list)       # one-click repairs: {label, start, end, text}
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, text: str) -> dict:
        start = max(0, min(self.start, len(text)))
        end = max(start, min(self.end, len(text)))
        line = text.count("\n", 0, start) + 1
        col = start - (text.rfind("\n", 0, start) + 1) + 1
        return {"code": self.code, "severity": self.severity, "message": self.message, "start": start, "end": end, "line": line, "col": col,
                "text": text[start:end], "fixes": self.fixes, **self.extra}


def fix(label: str, start: int, end: int, text: str) -> dict:
    return {"label": label, "start": start, "end": end, "text": text}


# ------------------------------------------------------------------------------------------------------------------------------ tokens
@dataclass
class Tok:
    kind: str     # NUM WORD KW OP CMP LP RP PCT CUR SYM NL BAD EOF
    text: str
    start: int
    end: int


NUM_RE = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+")
CMP_MAP = {">": ">", ">=": ">=", "<": "<", "<=": "<=", "=": "=", "==": "=", "!=": "!=", "<>": "!=", "=>": ">=", "=<": "<=", "≥": ">=", "≤": "<=", "≠": "!="}
ARITH_MAP = {"+": "+", "-": "-", "−": "-", "–": "-", "—": "-", "*": "*", "×": "*", "/": "/", "÷": "/"}
SPACE = " \t\r\f\v "


def tokenize(text: str) -> Tuple[List[Tok], List[Problem]]:
    """Text to tokens. A bad character or number becomes a BAD token plus a problem, so the parser can carry on and report the rest."""
    toks: List[Tok] = []
    problems: List[Problem] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in SPACE:
            i += 1
        elif c == "\n":
            toks.append(Tok("NL", "\n", i, i + 1)); i += 1
        elif c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = NUM_RE.match(text, i)
            e = m.end()
            if e < n and text[e] in ".," and e + 1 < n and text[e + 1].isdigit():   # 1.2.3 or 1,2,3: not a number
                e = re.compile(r"[\d.,]+").match(text, i).end()
                toks.append(Tok("BAD", text[i:e], i, e))
                problems.append(Problem("bad_number", f"'{text[i:e]}' is not a valid number. Use digits with one decimal point, like 12.5, or Indian grouping like 1,00,000.", i, e))
            else:
                toks.append(Tok("NUM", text[i:e], i, e))
            i = e
        elif c.isalpha() or c == "_":
            e = i
            while e < n and (text[e].isalnum() or text[e] == "_"):
                e += 1
            toks.append(Tok("WORD", text[i:e], i, e)); i = e
        elif text.startswith("&&", i):
            toks.append(Tok("KW", "and", i, i + 2)); i += 2
        elif text.startswith("||", i):
            toks.append(Tok("KW", "or", i, i + 2)); i += 2
        elif text[i:i + 2] in CMP_MAP:
            toks.append(Tok("CMP", CMP_MAP[text[i:i + 2]], i, i + 2)); i += 2
        elif c in CMP_MAP:
            toks.append(Tok("CMP", CMP_MAP[c], i, i + 1)); i += 1
        elif c in ARITH_MAP:
            toks.append(Tok("OP", ARITH_MAP[c], i, i + 1)); i += 1
        elif c == "(":
            toks.append(Tok("LP", c, i, i + 1)); i += 1
        elif c == ")":
            toks.append(Tok("RP", c, i, i + 1)); i += 1
        elif c == "%":
            toks.append(Tok("PCT", c, i, i + 1)); i += 1
        elif c == "₹":
            toks.append(Tok("CUR", c, i, i + 1)); i += 1
        elif c in ".,&'’":
            toks.append(Tok("SYM", c, i, i + 1)); i += 1
        else:
            toks.append(Tok("BAD", c, i, i + 1))
            hint = {",": "Join conditions with AND / OR, or put each on its own line.", ";": "Join conditions with AND / OR, or put each on its own line.",
                    '"': "Quotes are not needed: write the ratio name as it is.", "!": "For 'not equal' write !=."}.get(c, "")
            problems.append(Problem("bad_character", f"We don't understand the character '{c}'. {hint}".strip(), i, i + 1))
            i += 1
    toks.append(Tok("EOF", "", n, n))
    return toks, problems


# ------------------------------------------------------------------------------------------------------------------------------ tree
class Node:
    __slots__ = ("start", "end")


class Num(Node):
    __slots__ = ("value", "unit", "text")

    def __init__(self, value: float, unit: Optional[str], start: int, end: int, text: str):
        self.value, self.unit, self.start, self.end, self.text = value, unit, start, end, text


class Met(Node):
    __slots__ = ("key", "text")

    def __init__(self, key: str, start: int, end: int, text: str):
        self.key, self.start, self.end, self.text = key, start, end, text


class Bin(Node):
    __slots__ = ("op", "l", "r")

    def __init__(self, op: str, l: Node, r: Node):
        self.op, self.l, self.r, self.start, self.end = op, l, r, l.start, r.end


class Neg(Node):
    __slots__ = ("x",)

    def __init__(self, x: Node, start: int):
        self.x, self.start, self.end = x, start, x.end


class Cmp(Node):
    __slots__ = ("op", "l", "r", "op_start", "op_end")

    def __init__(self, op: str, l: Node, r: Node, op_start: int, op_end: int):
        self.op, self.l, self.r, self.op_start, self.op_end, self.start, self.end = op, l, r, op_start, op_end, l.start, r.end


class Bool(Node):
    __slots__ = ("kind", "items", "lines")

    def __init__(self, kind: str, items: List[Node], lines: bool = False):
        self.kind, self.items, self.lines = kind, items, lines     # kind: and / or
        self.start, self.end = items[0].start, items[-1].end


class Err(Node):
    __slots__ = ()

    def __init__(self, start: int, end: int):
        self.start, self.end = start, end


def walk(node: Node):
    yield node
    if isinstance(node, (Bin, Cmp)):
        yield from walk(node.l); yield from walk(node.r)
    elif isinstance(node, Neg):
        yield from walk(node.x)
    elif isinstance(node, Bool):
        for it in node.items:
            yield from walk(it)


def _is(tok: Tok, word: str) -> bool:
    return tok.kind in ("WORD", "KW") and tok.text.lower() == word


# ------------------------------------------------------------------------------------------------------------------------------ suggestions
def suggest(phrase: str, limit: int = 3) -> List[str]:
    """Up to `limit` real metric keys closest to a phrase the member typed: by spelling, and by shared words."""
    q = norm(phrase)
    if len(q) < 2:
        return []
    score: Dict[str, float] = {}
    for n in difflib.get_close_matches(q, list(ALIAS), n=16, cutoff=0.6):
        k = ALIAS[n]
        score[k] = max(score.get(k, 0), difflib.SequenceMatcher(None, q, n).ratio())
    words = [w for w in re.findall(r"[a-z0-9]+", phrase.lower()) if len(w) >= 3 and w not in STOP_WORDS]
    if words:
        for n, k in ALIAS.items():
            hit = sum(1 for w in words if w in n)
            if hit:
                s = 0.45 + 0.4 * hit / len(words) - min(0.2, max(0, len(n) - len(q)) / 120)
                score[k] = max(score.get(k, 0), s)
    if len(q) >= 3:   # the phrase is part of a longer name ("operating" -> operating margin)
        for n, k in ALIAS.items():
            if q in n:
                score[k] = max(score.get(k, 0), 0.5 + 0.3 * len(q) / len(n))
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], BY_KEY[kv[0]].tier != "basic", kv[0]))
    return [k for k, s in ranked if s >= 0.5][:limit]


def suggestion_text(key: str) -> str:
    return BY_KEY[key].label


# ------------------------------------------------------------------------------------------------------------------------------ parser
class Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks, self.problems = tokenize(text)
        self.i = 0
        self.depth = 0
        self.seen: set = set()

    # ---- plumbing
    def err(self, code: str, message: str, start: int, end: int, fixes: Optional[List[dict]] = None, **extra: Any) -> None:
        key = (code, start, end)
        if key not in self.seen:
            self.seen.add(key)
            self.problems.append(Problem(code, message, start, end, "error", fixes or [], extra))

    def peek(self) -> Tok:
        if self.depth > 0:
            while self.toks[self.i].kind == "NL":
                self.i += 1
        return self.toks[self.i]

    def take(self) -> Tok:
        t = self.peek()
        if t.kind != "EOF":
            self.i += 1
        return t

    def peek_kw(self) -> Tuple[Optional[str], int]:
        """The AND / OR coming next, looking past line breaks (a line that starts with AND continues the one above)."""
        j = self.i
        while self.toks[j].kind == "NL":
            j += 1
        t = self.toks[j]
        for w in ("and", "or"):
            if _is(t, w):
                return w, j
        return None, j

    def txt(self, t: Tok) -> str:
        return self.text[t.start:t.end]

    def starts_condition(self, t: Tok) -> bool:
        return t.kind in ("NUM", "LP", "CUR") or (t.kind == "OP" and t.text == "-") or (t.kind == "WORD" and t.text.lower() not in ("and", "or", "between")) or t.kind == "PCT"

    # ---- query / boolean structure
    def parse_query(self) -> Optional[Node]:
        lines: List[Node] = []
        while self.toks[self.i].kind == "NL":
            self.i += 1
        if self.peek().kind == "EOF":
            return None
        while self.peek().kind != "EOF":
            node = self.parse_or()
            lines.append(node)
            t = self.peek()
            if t.kind == "RP":
                self.err("extra_paren", "There is a ')' with no '(' before it.", t.start, t.end, [fix("Remove the ')'", t.start, t.end, "")])
                self.i += 1
            elif t.kind not in ("NL", "EOF"):
                if self.starts_condition(t):
                    self.err("missing_connector", "Two conditions need AND or OR between them.", t.start, t.start,
                             [fix("Insert AND", t.start, t.start, "AND "), fix("Insert OR", t.start, t.start, "OR ")])
                else:
                    self.err("unexpected", f"We did not expect '{self.txt(t)}' here.", t.start, t.end)
                    self.i += 1
            while self.toks[self.i].kind == "NL":
                self.i += 1
        if not lines:
            return None
        return lines[0] if len(lines) == 1 else Bool("and", lines, lines=True)

    def parse_or(self) -> Node:
        items = [self.parse_and()]
        while True:
            kw, j = self.peek_kw() if self.depth == 0 else (self._kw_in_group(), self.i)
            if kw != "or":
                break
            tok = self.toks[j]
            self.i = j + 1
            if self.dangling(tok):
                break
            items.append(self.parse_and())
        return items[0] if len(items) == 1 else Bool("or", items)

    def _kw_in_group(self) -> Optional[str]:
        t = self.peek()
        for w in ("and", "or"):
            if _is(t, w):
                return w
        return None

    def parse_and(self) -> Node:
        items = [self.parse_cond()]
        while True:
            kw, j = self.peek_kw() if self.depth == 0 else (self._kw_in_group(), self.i)
            if kw != "and":
                # two conditions side by side with no joiner: "PE < 15 ROE > 10"
                t = self.peek()
                if self.depth > 0 and self.starts_condition(t) and not isinstance(items[-1], Err) and self.i > 0 and self.toks[self.i - 1].kind != "NL":
                    self.err("missing_connector", "Two conditions need AND or OR between them.", t.start, t.start,
                             [fix("Insert AND", t.start, t.start, "AND "), fix("Insert OR", t.start, t.start, "OR ")])
                    items.append(self.parse_cond())
                    continue
                if self.depth == 0 and self.starts_condition(t) and t.kind != "NL" and self.toks[self.i].kind != "NL":
                    self.err("missing_connector", "Two conditions need AND or OR between them.", t.start, t.start,
                             [fix("Insert AND", t.start, t.start, "AND "), fix("Insert OR", t.start, t.start, "OR ")])
                    items.append(self.parse_cond())
                    continue
                break
            tok = self.toks[j]
            self.i = j + 1
            if self.dangling(tok):
                break
            items.append(self.parse_cond())
        return items[0] if len(items) == 1 else Bool("and", items)

    def dangling(self, kw: Tok) -> bool:
        """After AND / OR there must be a condition."""
        if self.depth == 0:
            while self.toks[self.i].kind == "NL":
                self.i += 1
        t = self.peek()
        word = kw.text.upper()
        if t.kind in ("EOF", "RP") or _is(t, "and") or _is(t, "or"):
            if _is(t, "and") or _is(t, "or"):
                self.err("double_connector", f"'{word}' is followed by '{t.text.upper()}'. Put a condition between them.", kw.start, t.end,
                         [fix(f"Remove the extra '{t.text.upper()}'", t.start, t.end, "")])
                self.i += 1
                return False
            self.err("dangling_connector", f"'{word}' has nothing after it. Add another condition, or remove the '{word}'.", kw.start, kw.end,
                     [fix(f"Remove '{word}'", kw.start, kw.end, "")])
            return True
        return False

    def group_has_comparison(self, i: int) -> bool:
        depth = 0
        for j in range(i, len(self.toks)):
            t = self.toks[j]
            if t.kind == "LP":
                depth += 1
            elif t.kind == "RP":
                depth -= 1
                if depth == 0:
                    return False
            elif t.kind == "CMP" or _is(t, "between"):
                return True
        return False

    def sync(self) -> None:
        """Skip to the end of a broken condition: the next AND / OR / line break / ')' at this bracket level."""
        depth = 0
        while True:
            t = self.toks[self.i]
            if t.kind == "EOF":
                return
            if t.kind == "NL" and self.depth == 0:
                return
            if t.kind == "LP":
                depth += 1
            elif t.kind == "RP":
                if depth == 0:
                    return
                depth -= 1
            elif depth == 0 and (_is(t, "and") or _is(t, "or")):
                return
            self.i += 1

    # ---- conditions
    def parse_cond(self) -> Node:
        t = self.peek()
        if _is(t, "and") or _is(t, "or"):
            self.err("starts_with_connector", f"A condition cannot start with '{t.text.upper()}'. Remove it, or put a condition before it.", t.start, t.end,
                     [fix(f"Remove '{t.text.upper()}'", t.start, t.end, "")])
            self.i += 1
            return self.parse_cond() if self.peek().kind not in ("EOF", "NL") else Err(t.start, t.end)
        if t.kind == "LP" and self.group_has_comparison(self.i):
            self.i += 1
            self.depth += 1
            node = self.parse_or()
            self.depth -= 1
            c = self.peek()
            if c.kind == "RP":
                self.i += 1
            else:
                self.err("missing_paren", "This '(' is never closed. Add a ')' where the group ends.", t.start, t.end, [fix("Add ')' at the end", len(self.text), len(self.text), ")")])
                if self.depth == 0:
                    self.sync()
            return node
        return self.parse_cmp()

    def parse_cmp(self) -> Node:
        lhs = self.parse_expr("left")
        t = self.peek()
        if t.kind == "CMP":
            self.i += 1
            rhs = self.parse_expr("right", after=t)
            node: Node = Cmp(t.text, lhs, rhs, t.start, t.end)
            n = self.peek()
            if n.kind == "CMP":
                self.err("chained_comparison", "A condition compares two things. To check a range, write two conditions joined by AND, or use BETWEEN.", n.start, n.end)
                self.i += 1
                self.parse_expr("right", after=n)
            return node
        if _is(t, "between"):
            self.i += 1
            lo = self.parse_expr("right", after=t)
            a = self.peek()
            if _is(a, "and"):
                self.i += 1
            else:
                self.err("between_and", "BETWEEN needs two values joined by AND, like: ROE between 10 and 20.", t.start, t.end)
            hi = self.parse_expr("right", after=a if _is(a, "and") else t)
            return Bool("and", [Cmp(">=", lhs, lo, t.start, t.end), Cmp("<=", lhs, hi, t.start, t.end)])
        # no operator
        if not isinstance(lhs, Err):
            self.missing_operator(lhs, t)
        self.sync()
        return lhs if isinstance(lhs, Err) else Err(lhs.start, lhs.end)

    def missing_operator(self, lhs: Node, t: Tok) -> None:
        text = self.text[lhs.start:lhs.end]
        if isinstance(lhs, Met):
            m = BY_KEY[lhs.key]
            if m.unit == "flag":
                self.err("incomplete_condition", f"'{text}' is a yes/no ratio. Say which: {text} = yes, or {text} = no.", lhs.start, lhs.end,
                         [fix("Use = yes", lhs.end, lhs.end, " = yes"), fix("Use = no", lhs.end, lhs.end, " = no")])
                return
            fixes: List[dict] = []
            if t.kind == "NUM":
                for op in (">", "<", ">="):
                    fixes.append(fix(f"{text} {op} {t.text}", lhs.end, t.end, f" {op} {t.text}"))
                self.err("missing_operator", f"'{text}' and '{t.text}' need a comparison between them: >, <, >=, <= or =.", lhs.start, t.end, fixes)
                return
            self.err("incomplete_condition", f"'{text}' needs a comparison and a value, like {text} > 10.", lhs.start, lhs.end,
                     [fix(f"{text} >", lhs.end, lhs.end, " > "), fix(f"{text} <", lhs.end, lhs.end, " < ")])
            return
        if t.kind in ("EOF", "NL", "RP") or _is(t, "and") or _is(t, "or"):
            self.err("incomplete_condition", f"'{text}' is not a condition. A condition compares two things, like ROE > 15.", lhs.start, lhs.end)
        else:
            self.err("missing_operator", f"We expected a comparison (>, <, >=, <=, =) after '{text}' but found '{self.txt(t)}'.", t.start, t.end)

    # ---- expressions
    def parse_expr(self, role: str, after: Optional[Tok] = None) -> Node:
        left = self.parse_term(role, after)
        while self.peek().kind == "OP" and self.peek().text in "+-":
            op = self.take()
            right = self.parse_term("right", op)
            left = Bin(op.text, left, right)
        return left

    def parse_term(self, role: str, after: Optional[Tok]) -> Node:
        left = self.parse_factor(role, after)
        while self.peek().kind == "OP" and self.peek().text in "*/":
            op = self.take()
            right = self.parse_factor("right", op)
            left = Bin(op.text, left, right)
        return left

    def parse_factor(self, role: str, after: Optional[Tok]) -> Node:
        t = self.peek()
        if t.kind == "OP" and t.text == "-":
            self.i += 1
            return Neg(self.parse_factor("right", t), t.start)
        return self.parse_primary(role, after)

    def match_metric(self, i: int) -> Optional[Tuple[str, int]]:
        """The longest metric name starting at token i: (key, index after its last token). Walks the tokens one word at a time, as long as what has been
        read so far is the beginning of some name; punctuation inside a name (P/E, F&O, 3-year) is skipped."""
        buf, depth, best, j = "", 0, None, i
        toks = self.toks
        while j < len(toks):
            t = toks[j]
            piece = ""
            if t.kind == "WORD":
                piece = norm(t.text)
            elif t.kind == "NUM":
                if not t.text.isdigit():
                    break
                piece = t.text
            elif t.kind == "KW" or t.kind in ("NL", "CMP", "EOF", "BAD", "CUR"):
                break
            elif t.kind == "LP":
                depth += 1
            elif t.kind == "RP":
                if depth == 0:
                    break
                depth -= 1
            elif t.kind == "OP" and t.text not in "-/":
                break
            if piece:
                buf += piece
                if buf not in PREFIXES:
                    break
            j += 1
            if (piece or t.kind == "RP") and depth == 0 and buf in ALIAS:
                best = (ALIAS[buf], j)
        return best

    def unknown_extent(self, i: int) -> int:
        """End (token index) of an unknown ratio name starting at token i: words, plus joiners that touch their neighbours (F-score, P/FFO)."""
        toks, j = self.toks, i + 1
        while j < len(toks):
            t, prev = toks[j], toks[j - 1]
            if t.kind == "WORD" and not (_is(t, "and") or _is(t, "or") or _is(t, "between")):
                j += 1
            elif t.kind == "NUM" and t.text.isdigit() and (t.start == prev.end or (j + 1 < len(toks) and toks[j + 1].start == t.end and toks[j + 1].kind == "WORD")):
                j += 1
            elif t.kind in ("SYM", "OP") and (t.kind == "SYM" or t.text in "-/") and t.start == prev.end and j + 1 < len(toks) and toks[j + 1].start == t.end \
                    and toks[j + 1].kind in ("WORD", "NUM"):
                j += 1
            else:
                break
        return j

    def unknown_metric(self, start_tok: int, end_tok: int, shorter: Optional[str] = None) -> Err:
        s, e = self.toks[start_tok].start, self.toks[end_tok - 1].end
        phrase = self.text[s:e]
        keys = suggest(phrase)
        if shorter and shorter not in keys:
            keys = [shorter] + keys[:2]
        fixes = [fix(f"Use {suggestion_text(k)}", s, e, suggestion_text(k)) for k in keys]
        near = f" Closest ratios: {', '.join(suggestion_text(k) for k in keys)}." if keys else ""
        self.err("unknown_metric", f"We don't have a ratio called '{phrase}'.{near}", s, e, fixes, name=phrase, suggestions=[{"key": k, "label": suggestion_text(k)} for k in keys], seeAll=True)
        return Err(s, e)

    def parse_primary(self, role: str, after: Optional[Tok]) -> Node:
        t = self.peek()
        if t.kind == "LP":
            self.i += 1
            self.depth += 1
            inner = self.parse_expr(role, t)
            self.depth -= 1
            c = self.peek()
            if c.kind == "RP":
                self.i += 1
            else:
                self.err("missing_paren", "This '(' is never closed. Add a ')' where it should end.", t.start, t.end)
            if isinstance(inner, (Num, Met)):
                return inner
            return inner
        if t.kind in ("NUM", "CUR", "PCT") or (t.kind == "WORD" and t.text.lower() in ("rs", "inr") and self.toks[self.i + 1].kind == "NUM"):
            hit = self.match_metric(self.i) if t.kind == "NUM" else None
            if hit is None:
                return self.parse_number()
        if t.kind in ("WORD", "NUM"):
            hit = self.match_metric(self.i)
            if hit:
                key, j = hit
                first, last = self.toks[self.i], self.toks[j - 1]
                self.i = j
                nxt = self.peek()
                if nxt.kind == "WORD" and not any(_is(nxt, w) for w in ("and", "or", "between")) and nxt.text.lower() not in ("yes", "no", "true", "false") \
                        and nxt.start >= last.end:
                    # "ROE growth > 5": a longer name that is not one of ours
                    end = self.unknown_extent(j - 1)
                    k0 = self.i - (j - self.toks.index(first))
                    return self.unknown_metric(self.toks.index(first), max(end, j + 1), shorter=key)
                return Met(key, first.start, last.end, self.text[first.start:last.end])
            w = t.text.lower()
            if t.kind == "WORD" and w in ("yes", "true", "no", "false"):
                self.i += 1
                return Num(1.0 if w in ("yes", "true") else 0.0, "flag", t.start, t.end, t.text)
            if t.kind == "WORD" and w in ("and", "or"):
                return self.missing_operand(role, after, t)
            if t.kind == "WORD":
                start = self.i
                end = self.unknown_extent(start)
                self.i = end
                return self.unknown_metric(start, end)
        return self.missing_operand(role, after, t)

    def missing_operand(self, role: str, after: Optional[Tok], t: Tok) -> Err:
        if after is not None and after.kind == "CMP":
            self.err("missing_value", f"'{after.text}' needs a value or a ratio after it, like {after.text} 10.", after.start, after.end if t.start <= after.end else t.start)
        elif after is not None and after.kind == "OP":
            self.err("missing_value", f"'{after.text}' needs a number or a ratio after it.", after.start, after.end)
        elif after is not None and _is(after, "between"):
            self.err("missing_value", "BETWEEN needs two values: BETWEEN 10 AND 20.", after.start, after.end)
        elif t.kind == "CMP":
            self.err("missing_metric", f"A condition starts with a ratio name, like ROE {t.text} 15. Add one before '{t.text}'.", t.start, t.end)
        elif t.kind == "EOF" or t.kind == "NL":
            self.err("missing_value", "The query ends before the condition is finished.", max(0, t.start - 1), t.start if t.start > 0 else 0)
        elif t.kind == "RP":
            self.err("empty_paren", "There is nothing inside these brackets.", t.start, t.end)
        elif t.kind == "BAD":
            pass    # already reported by the tokenizer
        else:
            self.err("unexpected", f"We did not expect '{self.txt(t)}' here. Expected a ratio name or a number.", t.start, t.end)
            self.i += 1
        return Err(t.start, t.end)

    def parse_number(self) -> Node:
        t = self.peek()
        start = t.start
        unit: Optional[str] = None
        if t.kind == "CUR" or (t.kind == "WORD" and t.text.lower() in ("rs", "inr")):
            unit = "Rs"
            self.i += 1
            t = self.peek()
        if t.kind != "NUM":
            if t.kind == "PCT":
                self.err("bad_number", "A '%' goes after a number, like 15%.", t.start, t.end)
                self.i += 1
            else:
                self.err("bad_number", "We expected a number after ₹ / Rs.", start, t.start if t.start > start else t.end)
            return Err(start, t.end)
        self.i += 1
        value = float(t.text.replace(",", ""))
        end = t.end
        n = self.peek()
        if n.kind == "PCT":
            if unit:
                self.err("bad_unit", "A number cannot be both in rupees and a percentage.", start, n.end)
            unit = "pct"; end = n.end; self.i += 1
        elif n.kind == "WORD" and n.text.lower() in UNIT_WORDS and not (_is(n, "x") and self.toks[self.i + 1].kind in ("NUM",)):
            u = UNIT_WORDS[n.text.lower()]
            self.i += 1
            end = n.end
            if u == "lakh":
                nn = self.peek()
                if nn.kind == "WORD" and nn.text.lower() in ("cr", "crore", "crores"):
                    self.i += 1; end = nn.end; value *= 1e5; unit = "Cr"
                else:
                    value /= 100.0; unit = "Cr"
            else:
                unit = u
        elif n.kind == "WORD" and not any(_is(n, w) for w in ("and", "or", "between")):
            # "15xyz" or "15 percent"
            hit = self.match_metric(self.i)
            if hit is None or n.start == end:
                e2 = self.unknown_extent(self.i)
                bad = self.text[n.start:self.toks[e2 - 1].end] if n.start != end else self.text[n.start:n.end]
                self.err("bad_unit", f"We don't understand '{bad}' after {t.text}. Numbers can be plain (15), a percentage (15%), in crore (500 Cr) or a multiple (15x).",
                         n.start, n.end, [fix(f"Use {t.text}", n.start if n.start != end else end, n.end, "")])
                self.i += 1
            # else: the next word starts a metric: the caller reports the missing AND / OR
        return Num(value, unit, start, end, self.text[start:end])


def parse(text: str) -> Tuple[Optional[Node], List[Problem]]:
    """Text to (tree, problems). The tree is None for an empty query; a tree with problems must not be run."""
    p = Parser(text)
    node = p.parse_query()
    if node is None and not p.problems:
        p.problems.append(Problem("empty", "Type a query, or pick an example below. For instance: Market cap > 500 AND P/E < 15.", 0, 0))
    return node, p.problems


# ------------------------------------------------------------------------------------------------------------------------------ checks
def fmt_in(x: float) -> str:
    """Indian digit grouping: 1234567 -> 12,34,567."""
    neg = x < 0
    x = abs(x)
    s = f"{x:.2f}".rstrip("0").rstrip(".") if x != int(x) else str(int(x))
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + whole + ("." + frac if frac else "")


def metric_dim(key: str) -> str:
    m = BY_KEY[key]
    if m.unit == "%":
        return "pct"
    if m.unit == "pts":
        return "pct" if key in PCT_POINTS else "pts"
    return {"Cr": "Cr", "Rs": "Rs", "x": "x", "d": "d", "n": "n", "flag": "flag"}[m.unit]


def count_conditions(node: Node) -> int:
    return sum(1 for n in walk(node) if isinstance(n, Cmp))


class Checker:
    """Units, yes/no values, constant conditions and likely mistakes, found once the tree exists. Errors stop a run; warnings do not."""

    def __init__(self, text: str):
        self.text = text
        self.problems: List[Problem] = []

    def add(self, code: str, message: str, start: int, end: int, severity: str = "error", fixes: Optional[List[dict]] = None, **extra: Any) -> None:
        self.problems.append(Problem(code, message, start, end, severity, fixes or [], extra))

    def dim(self, n: Node) -> Optional[str]:
        """The unit a piece of the query is in: a unit name, None for a plain number, "?" when it cannot be said."""
        if isinstance(n, Met):
            return metric_dim(n.key)
        if isinstance(n, Num):
            return n.unit if n.unit != "flag" else "flag"
        if isinstance(n, Neg):
            return self.dim(n.x)
        if isinstance(n, Bin):
            a, b = self.dim(n.l), self.dim(n.r)
            if a == "?" or b == "?":
                return "?"
            if n.op in "+-":
                if a and b and a != b:
                    self.mismatch(n.l, n.r, a, b, f"add or subtract" if n.op == "+" else "subtract")
                    return "?"
                return a or b
            if n.op == "*":
                if a and b:
                    return "?"
                return a or b
            if a and b:
                return None if a == b else "?"       # same unit over same unit is a plain ratio
            return a if a else "?"
        return "?"

    def label(self, n: Node) -> str:
        return BY_KEY[n.key].label if isinstance(n, Met) else self.text[n.start:n.end]

    def mismatch(self, l: Node, r: Node, a: str, b: str, verb: str) -> None:
        # a number with a unit written on it is the likely mistake: say so and offer to drop the unit
        for num, other, od in ((r, l, a), (l, r, b)):
            if isinstance(num, Num) and num.unit and num.unit != "flag" and not isinstance(other, Num):
                bare = re.sub(r"[^\d.,]", "", num.text) or num.text
                suffix = SUFFIX_TEXT.get(num.unit, num.unit)
                name = self.label(other)
                good = {"pct": "15%", "Cr": "500 Cr", "x": "15x", "d": "30 days"}.get(od, "a plain number")
                self.add("unit_mismatch", f"{name} is {UNIT_NAME.get(od, od)}, so '{suffix}' does not fit here. Write it like {good}, or just the number.",
                         num.start, num.end, "error", [fix(f"Use {bare}", num.start, num.end, bare)] if bare else [])
                return
        self.add("unit_mismatch", f"These two are in different units, so they cannot be compared or combined: {self.label(l)} is {UNIT_NAME.get(a, a)} but "
                                  f"{self.label(r)} is {UNIT_NAME.get(b, b)}.", l.start, r.end)

    def check(self, root: Node) -> None:
        count = 0
        for n in walk(root):
            if isinstance(n, Cmp):
                count += 1
                self.check_cmp(n)
                if count == MAX_CONDITIONS + 1:
                    self.add("too_many_conditions", f"A query can have up to {MAX_CONDITIONS} conditions. Remove some, or split them into two baskets.", n.start, n.end)
            elif isinstance(n, Bin) and n.op == "/" and isinstance(n.r, Num) and n.r.value == 0:
                self.add("divide_by_zero", "This divides by zero.", n.r.start, n.r.end)
        self.contradictions(root)

    def check_cmp(self, c: Cmp) -> None:
        if any(isinstance(n, Err) for n in walk(c)):
            return      # already reported where it went wrong
        mets = [n for n in walk(c) if isinstance(n, Met)]
        if not mets:
            self.add("no_metric", "This condition uses no ratio, so it would be the same for every company. Compare a ratio with a number, like ROE > 15.", c.start, c.end)
            return
        a, b = self.dim(c.l), self.dim(c.r)
        flag_side = [x for x in (c.l, c.r) if isinstance(x, Met) and BY_KEY[x.key].unit == "flag"]
        if flag_side:
            other = c.r if flag_side[0] is c.l else c.l
            name = BY_KEY[flag_side[0].key].label
            if c.op not in ("=", "!="):
                self.add("flag_operator", f"'{name}' is a yes/no ratio. Use = yes or = no.", c.op_start, c.op_end,
                         fixes=[fix("Use = yes", c.op_start, c.end, "= yes"), fix("Use = no", c.op_start, c.end, "= no")] if flag_side[0] is c.l else [])
            if isinstance(other, Num) and other.value not in (0.0, 1.0):
                self.add("flag_value", f"'{name}' is a yes/no ratio. Compare it with yes or no (or 1 or 0), not {other.text}.", other.start, other.end,
                         fixes=[fix("Use yes", other.start, other.end, "yes"), fix("Use no", other.start, other.end, "no")])
            elif isinstance(other, Num) and other.unit not in (None, "flag"):
                self.add("flag_value", f"'{name}' is a yes/no ratio, so '{other.text}' does not fit. Use yes or no.", other.start, other.end,
                         fixes=[fix("Use yes", other.start, other.end, "yes"), fix("Use no", other.start, other.end, "no")])
            elif not isinstance(other, (Num, Met)):
                self.add("flag_value", f"'{name}' is a yes/no ratio. Compare it with yes or no.", other.start, other.end)
            return
        for x in (c.l, c.r):
            if isinstance(x, Num) and x.unit == "flag":
                self.add("yes_no_misuse", "yes / no only work with yes/no ratios such as 'Pays a dividend'. Use a number here.", x.start, x.end)
                return
        if a and b and a != "?" and b != "?" and a != b:
            self.mismatch(c.l, c.r, a, b, "compare")
            return
        # a number's unit against the metric on the other side
        for num, other in ((c.r, c.l), (c.l, c.r)):
            if isinstance(num, Num) and num.unit and isinstance(other, (Met, Bin, Neg)):
                od = self.dim(other)
                if od and od != "?" and od != num.unit:
                    self.mismatch(other, num, od, num.unit, "compare")
                    return
        self.likely_mistakes(c)

    def likely_mistakes(self, c: Cmp) -> None:
        for num, other in ((c.r, c.l), (c.l, c.r)):
            if not (isinstance(num, Num) and isinstance(other, Met)) or num.unit not in (None,):
                continue
            m = BY_KEY[other.key]
            v = abs(num.value)
            if m.unit == "Cr" and v >= (500000 if other.key in ("market_cap", "enterprise_value") else 10_000_000):
                self.add("crore_units", f"{m.label} is counted in ₹ crore. {num.text} means ₹{fmt_in(num.value)} crore (₹{fmt_in(num.value / 100000)} lakh crore), more than almost any "
                                        f"Indian company. If you meant ₹{fmt_in(num.value / 1e7)} crore, type {fmt_in(num.value / 1e7)}.", num.start, num.end, "warning",
                         [fix(f"Use {fmt_in(num.value / 1e7)}", num.start, num.end, fmt_in(num.value / 1e7))] if num.value % 1e7 == 0 else [])
            elif m.unit == "%" and 0 < v < 1 and c.op in (">", ">=", "<", "<="):
                self.add("looks_like_fraction", f"{m.label} is already a percentage: {num.text} means {num.text}%, not {round(v * 100, 4):g}%. If you meant "
                                                f"{round(v * 100, 4):g}%, type {round(v * 100, 4):g}.", num.start, num.end, "warning",
                         [fix(f"Use {round(v * 100, 4):g}", num.start, num.end, f"{round(v * 100, 4):g}")])

    def contradictions(self, root: Node) -> None:
        """AND of simple conditions on one ratio that no number can satisfy, such as PE > 20 AND PE < 10."""
        def chains(n: Node):
            if isinstance(n, Bool) and n.kind == "and":
                yield n
            if isinstance(n, Bool):
                for it in n.items:
                    yield from chains(it)
        for ch in chains(root):
            lo: Dict[str, Tuple[float, bool, Cmp]] = {}
            hi: Dict[str, Tuple[float, bool, Cmp]] = {}
            for it in ch.items:
                if not (isinstance(it, Cmp) and isinstance(it.l, Met) and isinstance(it.r, Num)):
                    continue
                k, v = it.l.key, it.r.value
                if it.op in (">", ">="):
                    cur = lo.get(k)
                    if cur is None or v > cur[0] or (v == cur[0] and it.op == ">"):
                        lo[k] = (v, it.op == ">=", it)
                elif it.op in ("<", "<="):
                    cur = hi.get(k)
                    if cur is None or v < cur[0] or (v == cur[0] and it.op == "<"):
                        hi[k] = (v, it.op == "<=", it)
            for k in lo.keys() & hi.keys():
                (l, lin, lc), (h, hin, hc) = lo[k], hi[k]
                if l > h or (l == h and not (lin and hin)):
                    self.add("contradiction", f"No company can match both of these: {BY_KEY[k].label} cannot be above {l:g} and below {h:g} at the same time. "
                                              "Did you mean OR, or swap the numbers?", lc.start, hc.end, "warning")


def plan_problems(root: Node, plan: str) -> List[Problem]:
    """Every use of a ratio above the member's plan: says which plan opens it."""
    out: List[Problem] = []
    for n in walk(root):
        if isinstance(n, Met):
            m = BY_KEY[n.key]
            if not allowed(plan, m.tier):
                tier = TIER_NAME[m.tier]
                out.append(Problem("plan_locked", f"{m.label} is part of the {tier} plan. Upgrade to {tier} to use it, or pick another ratio.", n.start, n.end, "error", [],
                                   {"plan": m.tier, "key": n.key}))
    return out


# ------------------------------------------------------------------------------------------------------------------------------ reading back
_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}


def canonical(n: Node) -> str:
    """The query written in full with the real ratio names. Parsing it again gives the same tree."""
    return _canon(n, 0)


def _canon(n: Node, ctx: int) -> str:
    if isinstance(n, Met):
        return BY_KEY[n.key].label
    if isinstance(n, Num):
        return {"flag": "yes" if n.value else "no"}.get(n.unit or "", n.text)
    if isinstance(n, Neg):
        return "-" + _canon(n.x, 3)
    if isinstance(n, Bin):
        p = _PREC[n.op]
        s = f"{_canon(n.l, p)} {n.op} {_canon(n.r, p + 1)}"
        return f"({s})" if p < ctx else s
    if isinstance(n, Cmp):
        return f"{_canon(n.l, 0)} {n.op} {_canon(n.r, 0)}"
    if isinstance(n, Bool):
        if n.lines:
            return "\n".join(_canon(i, 0) for i in n.items)
        word = " AND " if n.kind == "and" else " OR "
        s = word.join(_canon(i, 1 if n.kind == "and" else 0) if not (isinstance(i, Bool) and i.kind == "or" and n.kind == "and") else f"({_canon(i, 0)})" for i in n.items)
        return s
    return "?"


def _say(n: Node) -> str:
    if isinstance(n, Met):
        return BY_KEY[n.key].label
    if isinstance(n, Num):
        if n.unit == "flag":
            return "yes" if n.value else "no"
        v = fmt_in(n.value)
        return {"pct": f"{v}%", "Cr": f"₹{v} crore", "Rs": f"₹{v}", "x": f"{v} times", "d": f"{v} days"}.get(n.unit or "", v)
    if isinstance(n, Neg):
        return "-" + _say(n.x)
    if isinstance(n, Bin):
        return f"({_say(n.l)} {({'*': '×', '/': '÷'}).get(n.op, n.op)} {_say(n.r)})"
    return "?"


def reading(n: Node) -> dict:
    """The query as a tree of plain sentences, for the page to show 'here is how we read it'."""
    if isinstance(n, Cmp):
        if isinstance(n.l, Met) and BY_KEY[n.l.key].unit == "flag" and isinstance(n.r, Num):
            word = "is" if n.op == "=" else "is not"
            return {"type": "cond", "text": f"{_say(n.l)} {word} {'yes' if n.r.value else 'no'}"}
        return {"type": "cond", "text": f"{_say(n.l)} {OP_WORDS[n.op]} {_say(n.r)}"}
    if isinstance(n, Bool):
        return {"type": n.kind, "items": [reading(i) for i in n.items]}
    return {"type": "cond", "text": "?"}


def metrics_in(n: Node) -> List[str]:
    out: List[str] = []
    for x in walk(n):
        if isinstance(x, Met) and x.key not in out:
            out.append(x.key)
    return out


# ------------------------------------------------------------------------------------------------------------------------------ one call
@dataclass
class Analysis:
    text: str
    root: Optional[Node]
    problems: List[Problem]

    @property
    def ok(self) -> bool:
        return self.root is not None and not any(p.severity == "error" for p in self.problems)


def analyze(text: str, plan: str = "gold") -> Analysis:
    """Parse and check a query for a member on `plan`. Every problem is returned together, sorted by position."""
    if len(text) > MAX_CHARS:
        return Analysis(text, None, [Problem("too_long", f"This query is {len(text):,} characters long; the limit is {MAX_CHARS:,}. Shorten it or split it into two baskets.",
                                             MAX_CHARS, len(text))])
    root, problems = parse(text)
    if root is not None:
        errors = [p for p in problems if p.severity == "error"]
        # semantic checks only make sense on a tree that parsed; a tree with holes is still checked for plan locks and unit slips we can see
        ck = Checker(text)
        ck.check(root)
        problems = problems + ck.problems + plan_problems(root, plan)
        _ = errors
    seen, uniq = set(), []
    for p in sorted(problems, key=lambda p: (p.start, p.end, p.code)):
        k = (p.code, p.start, p.end)
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return Analysis(text, root, uniq)
