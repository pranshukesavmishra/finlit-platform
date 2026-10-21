"""The glossary: ONE data file (glossary_data.json) feeds the API payloads and, through scripts/sync_glossary.py, the website.

`terms` are the A-Z entries (meaning, why it matters, how to use it, formula, how FinLit measures it).
`metrics` map every metric key the product shows (ratios, screener, scores, statement rows, results columns) to a label, unit, direction,
group, a term, and the formula FinLit actually computes.
"""

import json
from pathlib import Path
from typing import Dict

_DATA = json.loads((Path(__file__).with_name("glossary_data.json")).read_text(encoding="utf-8"))
TERMS = {t["id"]: t for t in _DATA["terms"]}
METRICS: Dict[str, dict] = _DATA["metrics"]
GLOSSARY = METRICS   # the mapping ratios.py reads label / unit / better / group from


def describe(key: str) -> dict:
    entry = METRICS.get(key)
    if not entry:
        return {"key": key, "label": key}
    term = TERMS.get(entry["term"], {})
    return {"key": key, **entry, "note": term.get("finlit", "")}
