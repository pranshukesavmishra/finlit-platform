import json
from pathlib import Path

from finlit.analytics.scoring import PILLARS
from finlit.normalize import ratios, statements
from finlit.normalize.glossary import METRICS, TERMS, describe
from finlit.screener.catalog import CATALOG

ROOT = Path(__file__).resolve().parents[2]


def _ratio_keys():
    keys = {v[0] for fam in ratios.FAMILY_MAP.values() for v in fam.values()} | set(ratios.GROWTH_MAP.values())
    return keys | {"opm", "npm", "cfo_to_pat", "fcf_to_pat", "sales_growth_latest", "profit_growth_latest", "market_cap", "dividend_yield", "pe", "pb", "ps", "pfcf",
                   "ev_ebitda", "exceptional_share", "sales_cagr", "profit_cagr", "liabilities_to_assets", "dividend_payout", "rsi14"}


def test_every_shown_key_has_a_complete_entry():
    keys = _ratio_keys() | {m.key for m in CATALOG} | {i[0] for p in PILLARS.values() for i in p["inputs"]}
    keys |= set(statements.PL_FIELDS) | set(statements.BS_FIELDS) | set(statements.CF_FIELDS) | {"net_profit_continuing", "discontinued_profit"}
    missing = sorted(k for k in keys if k not in METRICS)
    assert not missing, missing
    for k, e in METRICS.items():
        for f in ("label", "unit", "group", "what", "read", "why", "formula", "term"):
            assert e.get(f) is not None and (e[f] != "" or f == "unit"), (k, f)
        assert e["term"] in TERMS, k
        assert e["better"] in ("higher", "lower", None)


def test_terms_complete_and_unique():
    assert len(TERMS) == 292
    for t in TERMS.values():
        assert t["meaning"] and t["why"] and t["how"] and t["topic"], t["term"]


def test_no_advice_wording():
    text = " ".join(t["meaning"] + t["why"] + t["how"] for t in TERMS.values()).lower()
    for bad in ("run a red-flag check on every stock before buying", "more attractive", "before buying small"):
        assert bad not in text


def test_website_copy_in_sync():
    f = ROOT / "frontend/src/content/glossary.json"
    if f.exists():
        assert json.loads(f.read_text(encoding="utf-8"))["terms"] == list(TERMS.values())


def test_describe_unknown_key():
    assert describe("zzz") == {"key": "zzz", "label": "zzz"}
