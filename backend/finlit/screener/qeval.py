"""Evaluates a parsed query (finlit/screener/ql.py) against the screener table in one pass, a column at a time.

Every condition answers each company with one of three states: 1 true, 0 false, 2 unknown (a figure it needs is missing, or a division by zero).
AND and OR follow the usual three-valued rules (false AND unknown is false; true OR unknown is true), and only a company whose whole query is TRUE is returned:
a company is never listed because something was unknown. The ones left out only because of missing data are counted per ratio.
"""

from __future__ import annotations

import operator
from typing import Dict, List, Optional, Union

from .catalog import BY_KEY
from .ql import Bin, Bool, Cmp, Err, Met, Neg, Node, Num, Problem, fmt_in, metrics_in, walk
from .data import NAN, Table

AND = [0, 0, 0, 0, 1, 2, 0, 2, 2]     # index a*3+b
OR = [0, 1, 2, 1, 1, 1, 2, 1, 2]
CMP = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
FLIP = {">": "<", ">=": "<=", "<": ">", "<=": ">=", "=": "=", "!=": "!="}
Val = Union[float, List[float]]


class Result:
    def __init__(self, index: List[int], unknown: List[int], per_metric: List[dict], divzero: int, recent: Optional[dict]):
        self.index, self.unknown, self.per_metric, self.divzero, self.recent = index, unknown, per_metric, divzero, recent


class Evaluator:
    def __init__(self, t: Table):
        self.t, self.n, self.divzero = t, t.n, 0
        self.memo: Dict[int, Val] = {}

    def expr(self, node: Node) -> Val:
        k = id(node)
        if k in self.memo:
            return self.memo[k]
        v = self._expr(node)
        self.memo[k] = v
        return v

    def _expr(self, node: Node) -> Val:
        if isinstance(node, Met):
            return self.t.cols[node.key]
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Neg):
            x = self.expr(node.x)
            return -x if isinstance(x, float) else [-a for a in x]
        if isinstance(node, Bin):
            return self.arith(node.op, self.expr(node.l), self.expr(node.r))
        raise ValueError("cannot evaluate " + type(node).__name__)

    def arith(self, op: str, l: Val, r: Val) -> Val:
        lc, rc = isinstance(l, float), isinstance(r, float)
        if lc and rc:
            if op == "/":
                return l / r if r else NAN
            return {"+": l + r, "-": l - r, "*": l * r}[op]
        if op == "+":
            return [a + r for a in l] if rc else ([l + b for b in r] if lc else [a + b for a, b in zip(l, r)])
        if op == "-":
            return [a - r for a in l] if rc else ([l - b for b in r] if lc else [a - b for a, b in zip(l, r)])
        if op == "*":
            return [a * r for a in l] if rc else ([l * b for b in r] if lc else [a * b for a, b in zip(l, r)])
        # division: a zero divisor makes the company unknown for this condition, never a match
        if rc:
            return [a / r if r else NAN for a in l]
        if lc:
            self.divzero += sum(1 for b in r if b == 0 and l == l)
            return [l / b if b else NAN for b in r]
        self.divzero += sum(1 for a, b in zip(l, r) if b == 0 and a == a)
        return [a / b if b else NAN for a, b in zip(l, r)]

    def compare(self, c: Cmp) -> List[int]:
        l, r, op = self.expr(c.l), self.expr(c.r), c.op
        digits = max((BY_KEY[k].digits for k in metrics_in(c)), default=2)
        eps = 0.5 * 10 ** -digits      # "=" means equal as shown: ROE = 15 matches 15.0 (a figure of 15.04), as the table displays it
        if isinstance(l, float) and isinstance(r, float):
            s = 2 if (l != l or r != r) else (1 if self.test(op, eps)(l, r) else 0)
            return [s] * self.n
        if isinstance(l, float):       # constant on the left: swap sides and turn the operator round
            l, r, op = r, l, FLIP[op]
        f = self.test(op, eps)
        if isinstance(r, float):
            if r != r:
                return [2] * self.n
            return [2 if a != a else (1 if f(a, r) else 0) for a in l]
        return [2 if (a != a or b != b) else (1 if f(a, b) else 0) for a, b in zip(l, r)]

    @staticmethod
    def test(op: str, eps: float):
        if op == "=":
            return lambda a, b: abs(a - b) <= eps
        if op == "!=":
            return lambda a, b: abs(a - b) > eps
        return CMP[op]

    def state(self, node: Node) -> List[int]:
        if isinstance(node, Cmp):
            return self.compare(node)
        if isinstance(node, Bool):
            tbl = AND if node.kind == "and" else OR
            out = self.state(node.items[0])
            for it in node.items[1:]:
                nxt = self.state(it)
                out = [tbl[a * 3 + b] for a, b in zip(out, nxt)]
            return out
        raise ValueError("cannot evaluate " + type(node).__name__)


def run(t: Table, root: Node, recent: bool = False) -> Result:
    if any(isinstance(n, Err) for n in walk(root)):
        raise ValueError("a query with problems cannot be run")
    ev = Evaluator(t)
    states = ev.state(root)
    keys = metrics_in(root)
    unknown = [i for i, s in enumerate(states) if s == 2]
    index = [i for i, s in enumerate(states) if s == 1]
    info: Optional[dict] = None
    if recent:
        q = t.latest_quarter()
        if q is None:
            raise ValueError("no latest-results date")
        before = len(index)
        index = [i for i in index if t.q_end[i] == q]
        info = {"quarterEnd": q, "dropped": before - len(index), "reported": sum(1 for x in t.q_end if x == q)}
    per = []
    for k in keys:
        col = t.cols[k]
        known = sum(1 for v in col if v == v)
        per.append({"key": k, "label": BY_KEY[k].label, "known": known, "missing": t.n - known, "leftOut": sum(1 for i in unknown if col[i] != col[i])})
    return Result(index, unknown, per, ev.divzero, info)


def data_warnings(t: Table, root: Node) -> List[Problem]:
    """Conditions that, against today's table, can match no company at all (a number beyond every company's figure): almost always a typing slip."""
    out: List[Problem] = []
    for n in walk(root):
        if isinstance(n, Cmp) and isinstance(n.l, Met) and isinstance(n.r, Num) and n.r.unit in (None, "pct", "Cr", "x", "d", "Rs"):
            st = t.stats.get(n.l.key)
            m = BY_KEY[n.l.key]
            if not st or m.unit == "flag":
                continue
            v = n.r.value
            if (n.op in (">", ">=") and v >= st["max"] and not (n.op == ">=" and v == st["max"])) or (n.op in ("<", "<=") and v <= st["min"] and not (n.op == "<=" and v == st["min"])):
                side = "above" if n.op in (">", ">=") else "below"
                edge = st["max"] if side == "above" else st["min"]
                out.append(Problem("no_company_in_range", f"No company has {m.label} {side} {fmt_in(round(edge, 4))}"
                                   f"{' crore' if m.unit == 'Cr' else '%' if m.unit == '%' else ''}, so this condition can match nothing today. Check the number.",
                                   n.r.start, n.r.end, "warning"))
    return out
