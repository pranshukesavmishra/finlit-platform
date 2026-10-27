"""Argument checking for tool calls: the subset of JSON Schema the tools use, plus the symbol rule. Out-of-range numbers are clamped (and said so)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

SYMBOL_RE = re.compile(r"^[A-Z0-9&\-\.]{1,20}$")
SYMBOL_SCHEMA = {"type": "string", "description": "NSE symbol, for example RELIANCE or TCS (upper or lower case)", "maxLength": 40}


class ArgError(Exception):
    """The caller's arguments are wrong; the message is plain words for the model."""


def clean_symbol(value: Any, field: str = "symbol") -> str:
    if not isinstance(value, str):
        raise ArgError(f"{field} must be text such as RELIANCE.")
    sym = value.strip().upper()
    if not SYMBOL_RE.fullmatch(sym):
        raise ArgError(f"{field} '{value[:30]}' is not a valid symbol: use letters, digits, & - . only, up to 20 characters.")
    return sym


def validate(args: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Returns (clean arguments, notes). Unknown arguments are an error, so a typo is not silently ignored."""
    props = schema.get("properties", {})
    notes: List[str] = []
    out: Dict[str, Any] = {}
    for k in args:
        if k not in props:
            raise ArgError(f"Unknown argument '{str(k)[:40]}'. Allowed: {', '.join(props) or 'none'}.")
    for k in schema.get("required", []):
        if k not in args or args[k] is None:
            raise ArgError(f"Missing required argument '{k}'.")
    for k, v in args.items():
        if v is None:
            continue
        out[k] = _one(k, v, props[k], notes)
    for k, p in props.items():
        if k not in out and "default" in p:
            out[k] = p["default"]
    return out, notes


def _one(name: str, v: Any, p: Dict[str, Any], notes: List[str]) -> Any:
    t = p.get("type")
    if t == "string":
        if not isinstance(v, str):
            raise ArgError(f"{name} must be text.")
        v = v.strip()
        if len(v) > p.get("maxLength", 200):
            raise ArgError(f"{name} is too long (at most {p.get('maxLength', 200)} characters).")
        if "enum" in p:
            low = v.lower()
            match = [e for e in p["enum"] if e.lower() == low]
            if not match:
                raise ArgError(f"{name} must be one of: {', '.join(p['enum'])}.")
            return match[0]
        if "pattern" in p and not re.match(p["pattern"], v):
            raise ArgError(f"{name} '{v[:30]}' is not in the expected format. {p.get('description', '')}".strip())
        return v
    if t in ("integer", "number"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ArgError(f"{name} must be a number.")
        if t == "integer":
            if isinstance(v, float) and not v.is_integer():
                raise ArgError(f"{name} must be a whole number.")
            v = int(v)
        lo, hi = p.get("minimum"), p.get("maximum")
        if lo is not None and v < lo:
            notes.append(f"{name} was raised to the minimum {lo}.")
            v = lo
        if hi is not None and v > hi:
            notes.append(f"{name} was lowered to the maximum {hi}.")
            v = hi
        return v
    if t == "boolean":
        if not isinstance(v, bool):
            raise ArgError(f"{name} must be true or false.")
        return v
    if t == "array":
        if not isinstance(v, list):
            raise ArgError(f"{name} must be a list.")
        if len(v) > p.get("maxItems", 50):
            raise ArgError(f"{name} can hold at most {p.get('maxItems', 50)} items.")
        if len(v) < p.get("minItems", 0):
            raise ArgError(f"{name} needs at least {p.get('minItems')} item(s).")
        item = p.get("items", {})
        return [_one(f"{name}[]", x, item, notes) for x in v]
    if t == "object":
        if not isinstance(v, dict):
            raise ArgError(f"{name} must be an object.")
        if len(v) > p.get("maxProperties", 40):
            raise ArgError(f"{name} has too many entries.")
        sub = p.get("properties")
        if sub is not None:
            return {kk: _one(f"{name}.{kk}", vv, sub[kk], notes) for kk, vv in v.items() if vv is not None and (kk in sub or _raise(f"{name} has unknown field '{str(kk)[:30]}'."))}
        ap = p.get("additionalProperties")
        if isinstance(ap, dict):
            allowed = (p.get("propertyNames") or {}).get("enum")
            if allowed:
                for kk in v:
                    if kk not in allowed:
                        raise ArgError(f"'{str(kk)[:40]}' is not a filter you can use here. Allowed: {', '.join(allowed)}.")
            return {kk: _one(f"{name}.{kk}", vv, ap, notes) for kk, vv in v.items()}
        return v
    return v


def _raise(msg: str):
    raise ArgError(msg)
