"""The small rule language of a screen's `derived` rules: rules that need a nightly field or a Prism part, which the Query builder's own language cannot see.

    rule   :=  and ("or" and)*          and := cmp ("and" cmp)*          cmp := value op value        op := > >= < <= = !=
    value  :=  number | field | coalesce(field, number) | bankzero(field)

    coalesce(f, n)   f, or n when f is missing
    bankzero(f)      f; a bank's or lender's missing figure counts as 0 (their red-flag count is not computed), anyone else's stays unknown

Three-valued, like the Query builder: a comparison with a missing figure is unknown; AND/OR follow the usual rules; only TRUE passes. The text is parsed by the small parser below; no Python code is ever run from it.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Callable, List, Optional, Tuple

TOKEN = re.compile(r"\s*(>=|<=|!=|=|>|<|\(|\)|,|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z_0-9]*)")
OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
       "=": lambda a, b: abs(a - b) < 1e-9, "!=": lambda a, b: abs(a - b) >= 1e-9}
Node = Tuple[Any, ...]


class RuleError(ValueError):
    pass


def _tokens(text: str) -> List[str]:
    out, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            raise RuleError(f"cannot read {text[pos:pos + 12]!r} in {text!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


class _P:
    def __init__(self, toks: List[str]):
        self.t, self.i = toks, 0

    def peek(self) -> Optional[str]:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        v = self.peek()
        if v is None:
            raise RuleError("rule ends too soon")
        self.i += 1
        return v

    def or_(self) -> Node:
        items = [self.and_()]
        while self.peek() == "or":
            self.take()
            items.append(self.and_())
        return items[0] if len(items) == 1 else ("or", items)

    def and_(self) -> Node:
        items = [self.cmp()]
        while self.peek() == "and":
            self.take()
            items.append(self.cmp())
        return items[0] if len(items) == 1 else ("and", items)

    def cmp(self) -> Node:
        if self.peek() == "(":
            self.take()
            inner = self.or_()
            if self.take() != ")":
                raise RuleError("missing )")
            return inner
        left = self.value()
        op = self.take()
        if op not in OPS:
            raise RuleError(f"expected a comparison, found {op!r}")
        return ("cmp", op, left, self.value())

    def value(self) -> Node:
        t = self.take()
        if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
            return ("num", float(t))
        if t in ("coalesce", "bankzero"):
            if self.take() != "(":
                raise RuleError(f"{t} needs (")
            field = self.take()
            default = None
            if t == "coalesce":
                if self.take() != ",":
                    raise RuleError("coalesce(field, number)")
                default = float(self.take())
            if self.take() != ")":
                raise RuleError(f"{t} needs )")
            return (t, field, default)
        if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", t) and t not in ("and", "or"):
            return ("field", t)
        raise RuleError(f"unexpected {t!r}")


@lru_cache(maxsize=512)
def parse(text: str) -> Node:
    p = _P(_tokens(text))
    node = p.or_()
    if p.peek() is not None:
        raise RuleError(f"unexpected {p.peek()!r} in {text!r}")
    return node


def fields_in(node: Node) -> List[str]:
    k = node[0]
    if k == "field":
        return [node[1]]
    if k in ("coalesce", "bankzero"):
        return [node[1]] + (["is_bank"] if k == "bankzero" else [])
    if k == "cmp":
        return fields_in(node[2]) + fields_in(node[3])
    if k in ("and", "or"):
        return [f for n in node[1] for f in fields_in(n)]
    return []


def _val(node: Node, get: Callable[[str], Optional[float]]) -> Optional[float]:
    k = node[0]
    if k == "num":
        return node[1]
    if k == "field":
        return get(node[1])
    v = get(node[1])
    if k == "coalesce":
        return node[2] if v is None else v
    if v is None:      # bankzero
        return 0.0 if get("is_bank") == 1 else None
    return v


def _state(node: Node, get: Callable[[str], Optional[float]]) -> Optional[bool]:
    k = node[0]
    if k == "cmp":
        a, b = _val(node[2], get), _val(node[3], get)
        return None if a is None or b is None else OPS[node[1]](a, b)
    states = [_state(n, get) for n in node[1]]
    if k == "and":
        return False if any(s is False for s in states) else (None if any(s is None for s in states) else True)
    return True if any(s is True for s in states) else (None if any(s is None for s in states) else False)


def passes(text: str, get: Callable[[str], Optional[float]]) -> bool:
    return _state(parse(text), get) is True
