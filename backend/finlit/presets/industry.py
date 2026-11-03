"""The cleaned industry name (spec p16, "Clean the industry list"): trim, case-fix and merge duplicate spellings.

DERIVED, never written back: the stored raw industry stays as the provider sent it. The mapping is rebuilt from the raw names every night
(table `industry_clean`); `industry_override` (the research team's own list) always wins, which is also how a company is moved off a generic industry.

What is done:   trim and collapse spaces ("Industrials " -> "Industrials"), fix SHOUTED names ("SERVICES" -> "Services"), merge spellings that differ only
                in case, punctuation, "&" against "and" ("Oil, Gas & Consumable Fuels" / "Oil Gas & Consumable Fuels"), merge the "Media ... Publication" spellings,
                and drop stray values that are not an industry ("DVR", "Engineering": spec p16) to "no industry".
What is NOT done: moving companies off the generic industries (Capital Goods, Financial Services, Services, FMCG, Healthcare, Information Technology) onto the
                exchange's specific industry. The store holds no such field; fill `industry_override` (symbol, industry) to do it. Until then generic industries are
                left out of theme status.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

STRAY = {"dvr", "engineering"}          # spec p16: "stray DVR, Engineering": not industries
GENERIC = {"capital goods", "financial services", "services", "fmcg", "healthcare", "information technology"}   # spec p10 and p16 (the six named)
SMALL_WORDS = {"and", "of", "the", "for", "in"}


def key(name: Optional[str]) -> str:
    """Comparison key: lower case, '&' read as 'and', punctuation and extra spaces gone."""
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canon(name: Optional[str]) -> str:
    """The key two spellings of one industry share (the 'Media ... Publication' pair collapses here)."""
    k = key(name)
    if k.startswith("media") and "publication" in k.split():
        return "media publication"
    return k


def is_generic(clean: Optional[str]) -> bool:
    return key(clean) in GENERIC


def _tidy(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip()


def _shout_fix(name: str) -> str:
    """'SERVICES' -> 'Services'; short all-capitals names (FMCG) are acronyms and stay."""
    letters = [c for c in name if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(name) > 5:
        words = name.lower().split(" ")
        return " ".join(w if (i and w in SMALL_WORDS) else w[:1].upper() + w[1:] for i, w in enumerate(words))
    return name


def build_map(raw_counts: Dict[str, int]) -> Dict[str, Tuple[Optional[str], str]]:
    """raw spelling -> (clean name or None, rule). `raw_counts` is how many companies carry each raw spelling (the commonest spelling names a merged group)."""
    groups: Dict[str, List[str]] = {}
    out: Dict[str, Tuple[Optional[str], str]] = {}
    for raw in raw_counts:
        k = canon(raw)
        if not k or k in STRAY:
            out[raw] = (None, "stray")
        else:
            groups.setdefault(k, []).append(raw)
    for k, raws in groups.items():
        tidy = Counter()
        for r in raws:
            tidy[_tidy(r)] += raw_counts[r]
        # prefer a spelling that is not shouted; among those the commonest, then the longest (the fuller name), then alphabetical for a stable answer
        best = sorted(tidy, key=lambda t: (_shout_fix(t) != t, -tidy[t], -len(t), t))[0]
        name = _shout_fix(best)
        for r in raws:
            t = _tidy(r)
            rule = "same" if r == name else "trim" if t == name else "case" if t.lower() == name.lower() else "merge"
            out[r] = (name, rule)
    return out


def sector_map(raw_counts: Dict[str, int]) -> Dict[str, str]:
    """raw Sector label -> the label shown for it. Spellings that differ only in case, punctuation, spacing or "&" against "and" share one label (the commonest
    spelling that is not shouted names the group). Unlike industries nothing is dropped as stray and no spelling is moved to another group: the raw label stays in the store."""
    groups: Dict[str, List[str]] = {}
    for raw in raw_counts:
        if key(raw):
            groups.setdefault(key(raw), []).append(raw)
    out: Dict[str, str] = {}
    for raws in groups.values():
        tidy = Counter()
        for r in raws:
            tidy[_tidy(r)] += raw_counts[r]
        name = _shout_fix(sorted(tidy, key=lambda t: (_shout_fix(t) != t, -tidy[t], -len(t), t))[0])
        out.update({r: name for r in raws})
    return out


def derive(rows: Iterable[Tuple[str, Optional[str]]], overrides: Optional[Dict[str, str]] = None) -> Dict[str, Tuple[Optional[str], Optional[str], str]]:
    """symbol -> (raw, clean, rule) for (symbol, raw industry) rows. An override is applied last and wins."""
    rows = list(rows)
    counts = Counter(r for _, r in rows if r)
    mapping = build_map(counts)
    out: Dict[str, Tuple[Optional[str], Optional[str], str]] = {}
    for sym, raw in rows:
        clean, rule = mapping.get(raw, (None, "none")) if raw else (None, "none")
        if overrides and sym in overrides:
            clean, rule = overrides[sym], "override"
        out[sym] = (raw, clean, rule)
    return out
