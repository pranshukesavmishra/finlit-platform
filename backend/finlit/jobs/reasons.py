"""Turns a job's stored run result (the `run:<command>` record the worker writes to mf_meta) into one plain sentence saying WHY it did not fully work.

The supervisor puts this sentence into the run history, the job's state and the alert, so an alert says "TER file: ConnectTimeout" and not only "failed 21 times".
Pure functions, no I/O.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

PARTIAL_EXIT = 10   # a job's exit code for "finished, its essential step is done, an optional step is not": the supervisor records it as degraded, not failed
BAD_STEP =("failed", "refused", "error", "partial")
SKIP_KEYS = {"status", "at", "counts", "dashboard", "hot", "ok", "calls", "cards"}


def _text(v: Any, n: int = 120) -> str:
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_text(x, 60)}" for k, x in list(v.items())[:3])
    if isinstance(v, (list, tuple)):
        return ", ".join(_text(x, 40) for x in v[:4])
    return " ".join(str(v).split())[:n].rstrip(" :")     # "ConnectTimeout: " (an exception with no message) reads "ConnectTimeout"


def failed_steps(info: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """{step name: reason} for every step of the record that did not end ok (a step is a nested dict with its own status and a 'why' or 'error')."""
    out: Dict[str, str] = {}
    for k, v in (info or {}).items():
        if k in SKIP_KEYS or not isinstance(v, dict):
            continue
        if v.get("status") in BAD_STEP:
            out[k] = _text(v.get("why") or v.get("error") or v.get("reason") or v.get("status"))
    return out


def explain(info: Optional[Dict[str, Any]], limit: int = 300) -> Optional[str]:
    """The reason in one sentence, or None when the record says nothing useful."""
    if not info:
        return None
    parts = []
    if info.get("error"):
        parts.append(_text(info["error"], 200))
    steps = failed_steps(info)
    if steps:
        parts.append("; ".join(f"{k} step {info[k].get('status')}: {why}" for k, why in steps.items()))
    for key in ("why", "errors"):
        if info.get(key):
            parts.append(_text(info[key], 160))
    if info.get("stopReason"):
        parts.append(_text(info["stopReason"], 160))
    text = " | ".join(p for p in parts if p)
    return text[:limit] or None


def essential_ok(info: Optional[Dict[str, Any]], essential: str = "master") -> bool:
    """True when the record's essential step (default 'master') ended ok: the job still delivered what everything else stands on."""
    step = (info or {}).get(essential)
    return isinstance(step, dict) and step.get("status") == "ok"
