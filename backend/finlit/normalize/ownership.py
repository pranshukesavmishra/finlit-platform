"""Shareholding pattern -> promoter / FII / DII / public / government series by quarter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import parse_date, rnd

# FinEdge category -> our bucket. 'Indian' and 'Foreign' are promoter sub-groups.
CATEGORY_BUCKET = {
    "indian": "promoters", "foreign": "promoters", "promoters": "promoters", "promoter": "promoters",
    "institutionsforeign": "fii", "fii": "fii", "fpi": "fii",
    "institutionsdomestic": "dii", "dii": "dii", "mutualfunds": "dii",
    "noninstitutions": "public", "public": "public", "retail": "public",
    "goverments": "government", "governments": "government", "government": "government",
    "sharesheldbynonpromoternonpublicshareholders": "others",
}
BUCKETS = ["promoters", "fii", "dii", "public", "government", "others"]
LABELS = {"promoters": "Promoters", "fii": "Foreign institutions (FII)", "dii": "Domestic institutions (DII)",
          "public": "Retail & others", "government": "Government", "others": "Non-promoter non-public"}


def _quarter_key(label: str):
    parsed = parse_date(f"01-{label[:3]}-{label[-4:]}") if label and len(label) >= 8 else None
    return parsed


def shareholding(payload: Any, limit: int = 12) -> dict:
    p = payload if isinstance(payload, dict) else {}
    columns = [c for c in (p.get("columns") or []) if _quarter_key(c)]
    columns = sorted(set(columns), key=_quarter_key)[-max(limit, 5):]
    series: Dict[str, List[Optional[float]]] = {b: [None] * len(columns) for b in BUCKETS}
    for row in p.get("rows") or []:
        bucket = CATEGORY_BUCKET.get(str(row.get("catagory") or row.get("category") or "").replace(" ", "").lower())
        if not bucket:
            continue
        data = row.get("data") or {}
        for i, col in enumerate(columns):
            value = data.get(col)
            if value is None:
                continue
            series[bucket][i] = round((series[bucket][i] or 0) + float(value), 2)
    series = {k: v for k, v in series.items() if any(x not in (None, 0) for x in v)}

    latest_index = len(columns) - 1
    year_ago_index = latest_index - 4 if latest_index >= 4 else None
    latest = []
    for bucket, values in series.items():
        now = values[latest_index] if columns else None
        before = values[year_ago_index] if year_ago_index is not None else None
        latest.append({
            "key": bucket, "label": LABELS[bucket], "value": now,
            "change1yPts": rnd(now - before) if now is not None and before is not None else None,
        })
    latest.sort(key=lambda item: BUCKETS.index(item["key"]))
    keep = columns[-limit:]
    offset = len(columns) - len(keep)
    return {
        "periods": keep,
        "asOf": columns[-1] if columns else None,
        "comparedWith": columns[year_ago_index] if year_ago_index is not None else None,
        "series": {k: v[offset:] for k, v in series.items()},
        "latest": latest,
    }
