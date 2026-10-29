"""Why are companies NOT RATED or PROVISIONAL in FinLit Prism? One database query over the stored reports, no provider calls.

Reads prism_reports (migration 063; the reader view of the newest report per company and statement basis) with jsonb paths, so only the few
fields needed leave the database, and sorts every NOT RATED / PROVISIONAL report into a reason bucket:

  classification        the company's industry label is not mapped to a model group (the report says: 'industry label "X" is not yet mapped').
                        Reports stored before the classification fix carry the older wording ('model group could not be verified'): the same bucket.
  low_confidence        less than 50% of the model's inputs were found (NOT RATED)
  insufficient_history  fewer than 4 quarters (or 2 annual results) of sales: usually a recently listed company (NOT RATED)
  provisional_coverage  RATED-able but 50% to 80% of the inputs found, so the label is capped (PROVISIONAL)
  provisional_history   fewer than 6 comparable quarters (PROVISIONAL)
  other                 anything else (for example a data-integrity blocker, or an older report without reasons)

For the classification bucket it lists each distinct label text with the number of companies and the first 10 symbols; for low_confidence and
insufficient_history it lists the inputs most often missing (factors the report marks "not reported" or "estimated").
The summary is stored in mf_meta under 'prism-audit:last' (like integrity:last and provider-compare:last). Run: python -m finlit.worker audit-prism
docs/prism/AUDIT.md explains how to read it.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

META_LAST = "prism-audit:last"
BUCKETS = ("classification", "low_confidence", "insufficient_history", "provisional_coverage", "provisional_history", "other")
SYMBOLS_SHOWN = 10
MISSING_SHOWN = 10
LABEL_RE = re.compile(r'industry label "(.*?)" is not yet mapped')

QUERY = """
SELECT symbol, status,
       (report #>> '{rating,confidence}')::float                      AS confidence,
       (report #>> '{rating,judgedQuarters}')::int                    AS judged,
       report #> '{rating,alerts}'                                    AS alerts,
       report #> '{rating,notRatedReasons}'                           AS reasons,
       report #>> '{inputMeta,groupLabel}'                            AS group_label,
       report #>> '{company,industry}'                                AS industry,
       report #>> '{company,sector}'                                  AS sector,
       jsonb_path_query_array(report, '$.rating.metrics[*] ? (@.status == "L" || @.status == "F").label') AS missing
FROM prism_reports
WHERE statement = $1 AND status IN ('NOT RATED', 'PROVISIONAL')
"""


def _loads(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def bucket(row: Dict[str, Any]) -> str:
    """The reason bucket of one NOT RATED / PROVISIONAL report (pure: takes the fields QUERY selects)."""
    alerts = [str(a) for a in _loads(row.get("alerts")) or []]
    codes = [r.get("code") for r in _loads(row.get("reasons")) or [] if isinstance(r, dict)]
    confidence = row.get("confidence")
    if row["status"] == "NOT RATED":
        if "classification" in codes or any("model group" in a for a in alerts):
            return "classification"
        if "insufficient_history" in codes or any("Not enough reported history" in a for a in alerts):
            return "insufficient_history"
        if "low_confidence" in codes or (confidence is not None and confidence < 0.5):
            return "low_confidence"
        return "other"
    if row["status"] == "PROVISIONAL":
        if confidence is not None and confidence < 0.8:
            return "provisional_coverage"
        if row.get("judged") is not None and row["judged"] < 6:
            return "provisional_history"
    return "other"


def label_of(row: Dict[str, Any]) -> str:
    """The label text the classification check saw: from the report's own message, else the stored label, else the company's industry / sector."""
    for alert in _loads(row.get("alerts")) or []:
        found = LABEL_RE.search(str(alert))
        if found:
            return found.group(1)
    if row.get("group_label"):
        return row["group_label"]
    parts = [p for p in (row.get("industry"), row.get("sector")) if p]
    return " / ".join(dict.fromkeys(parts)) or "(no label)"


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Counter = Counter()
    status_counts: Counter = Counter()
    labels: Dict[str, List[str]] = defaultdict(list)
    missing: Dict[str, Counter] = {"low_confidence": Counter(), "insufficient_history": Counter()}
    symbols: Dict[str, List[str]] = defaultdict(list)
    for row in rows:
        b = bucket(row)
        counts[b] += 1
        status_counts[row["status"]] += 1
        if len(symbols[b]) < SYMBOLS_SHOWN:
            symbols[b].append(row["symbol"])
        if b == "classification":
            labels[label_of(row)].append(row["symbol"])
        if b in missing:
            missing[b].update(_loads(row.get("missing")) or [])
    return {
        "total": len(rows), "byStatus": dict(status_counts), "buckets": {b: counts.get(b, 0) for b in BUCKETS},
        "symbols": {b: symbols[b] for b in BUCKETS if symbols[b]},
        "classificationLabels": [{"label": k, "count": len(v), "symbols": v[:SYMBOLS_SHOWN]} for k, v in sorted(labels.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
        "topMissing": {b: [{"input": k, "count": n} for k, n in c.most_common(MISSING_SHOWN)] for b, c in missing.items() if c},
    }


async def audit(store, statement: str = "consolidated") -> Dict[str, Any]:
    from .integrity import _meta_set
    started = time.monotonic()
    async with store.pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(QUERY, statement)]
        result = {**summarise(rows), "statement": statement, "at": time.time(), "seconds": round(time.monotonic() - started, 2)}
        await _meta_set(conn, META_LAST, result)
    return result


async def last_result(pool) -> Optional[dict]:
    from .integrity import _meta_get
    try:
        async with pool.acquire() as conn:
            return await _meta_get(conn, META_LAST)
    except Exception:
        return None


def render(result: Dict[str, Any]) -> str:
    lines = [f"Prism audit ({result['statement']}): {result['total']} reports not fully rated  {result['byStatus']}", ""]
    for b in BUCKETS:
        n = result["buckets"].get(b, 0)
        if n:
            lines.append(f"{b:22} {n:5}  e.g. {', '.join(result['symbols'].get(b, []))}")
    if result["classificationLabels"]:
        lines += ["", "Industry labels not mapped to a model group (add them to premium_classification.py):"]
        lines += [f"  {x['count']:4}  {x['label']}   [{', '.join(x['symbols'])}]" for x in result["classificationLabels"]]
    for b, items in result["topMissing"].items():
        lines += ["", f"Inputs most often missing ({b}):"]
        lines += [f"  {x['count']:4}  {x['input']}" for x in items]
    return "\n".join(lines)
