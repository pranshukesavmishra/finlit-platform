"""The advanced-chart catalogue against the founder's spec (docs/ADVANCED-CHARTS-SPEC.md): every pair present, labels and help VERBATIM,
counts 162 / 133 / 29, every unavailable pair explained, every metric id real, no buy/sell wording, every reason code explained."""

import re
from pathlib import Path

from finlit.advanced import catalog as C
from finlit.advanced.catalog import BY_ID, METRICS, PAIRS, REASONS, catalog_json

SPEC = Path(__file__).resolve().parents[2] / "docs" / "ADVANCED-CHARTS-SPEC.md"
ADV = Path(__file__).resolve().parents[1] / "finlit" / "advanced"


def spec_rows():
    sec, n, out = 0, 0, []
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d+)\. ", line)
        if m:
            sec, n = int(m[1]), 0
            continue
        if sec and line.startswith("|") and not line.startswith("|---") and "What it helps analyse" not in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            n += 1
            out.append((f"{sec}.{n}", cells))
    return out


def test_every_pair_verbatim():
    rows = spec_rows()
    assert len(rows) == 162 == len(PAIRS)
    for pid, cells in rows:
        p = BY_ID[pid]
        if len(cells) == 4:
            assert p["sector"] == cells[0]
        assert (p["xLabel"], p["yLabel"], p["help"]) == tuple(cells[-3:]), pid


def test_counts_and_reasons():
    c = catalog_json()["counts"]
    assert c["pairs"] == 162 and c["ready"] + c["adapted"] == 133 and c["unavailable"] == 29 and c["adapted"] == 2
    assert (c["A"], c["C"], c["N"]) == (54, 79, 29)
    for p in PAIRS:
        if p["status"] == "unavailable":
            assert p["reason"] and p["reason"].startswith("Not available: ") and p["x"] is None and p["modes"] == []
        else:
            assert p["x"] in METRICS and p["y"] in METRICS and p["modes"], p["id"]
        if p["status"] == "adapted":
            assert p["reason"].startswith("Adapted: ")
        if "M" in p["flags"]:
            assert p["mechanical"].startswith("A strong correlation is expected by construction because ")
    assert {p["id"] for p in PAIRS if p["status"] == "adapted"} == {"2.10", "8.8"}
    assert {p["id"] for p in PAIRS if "tech" in p["modes"]} == {"8.5", "8.6", "8.7", "8.8", "8.10"}


def test_lender_rules_and_tiers():
    for p in PAIRS:
        if p["status"] == "unavailable" or "tech" in p["modes"]:
            continue
        sens = METRICS[p["x"]].lenders == "excluded" or METRICS[p["y"]].lenders == "excluded" or "L" in p["flags"]
        assert (p["lenders"] == "excluded") == sens, p["id"]
        assert p["tier"]["cross"] == "silver"
        if "history" in p["modes"]:
            assert p["tier"]["history"] in ("silver", "gold") and p["section"] != 8
    assert all(BY_ID[f"4.{i}"]["lenders"] == "excluded" for i in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15))
    assert BY_ID["1.9"]["lenders"] == "auto" and BY_ID["1.9"]["tier"]["history"] == "gold"
    assert BY_ID["3.2"]["tier"]["history"] == "silver" and "history" not in BY_ID["1.8"]["modes"]
    assert BY_ID["2.11"]["sameAs"] == "2.8" and BY_ID["5.4"]["sameAs"] == "3.4" and BY_ID["8.3"]["sameAs"] == "3.8"


def test_no_advice_wording_and_caveats():
    body = str(catalog_json()).lower()
    assert not re.search(r"\b(buy|sell|buying|selling|recommend)\b", body)
    assert "correlation is not causation." in body and "information only, not advice." in body


def test_every_reason_code_is_explained():
    codes = set()
    for f in ("derive.py", "table.py", "tech.py", "index.py"):
        codes |= set(re.findall(r'"([a-z_0-9]+)"\)', (ADV / f).read_text()))
    candidate = {c for c in codes if c in REASONS or c.endswith(("_le0", "_change")) or c in {"gap", "jump", "basis", "partial", "loss", "lender",
                                                                                         "no_prev", "no_fy", "no_data", "no_debt", "start_gap", "short_history"}}
    assert candidate <= set(REASONS) | {"low_coverage", "no_members", "den_le0"}, candidate - set(REASONS)
    from finlit.advanced.derive import Company
    lt = Company({}).latest({})
    assert set(lt["ax_miss"].values()) <= set(REASONS)


def test_metric_tiers_match_entitlements():
    from finlit.auth.entitlements import BASIC_HISTORY_KEYS
    for mid, key in C.HIST_KEYS.items():
        assert (METRICS[mid].history == "silver") == (key in BASIC_HISTORY_KEYS)
