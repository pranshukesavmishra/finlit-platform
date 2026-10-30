"""audit-prism (why companies are not rated) and the re-rating of reports withheld by the old classification check."""
import copy
import json
import re
from pathlib import Path

import httpx
import pytest

from finlit import prism, prism_audit
from test_integration import make_settings, store  # noqa: F401  (fixtures)
from test_prism import SECRET, SNAPSHOT, FakeSite

pytestmark = pytest.mark.integration
OLD = "The model group could not be verified from the company classification."
NEW = 'Prism has no model group for this industry yet ("Zzyzx Widgets"). The inputs were available; the rating needs the industry rules extended.'


def report(symbol, status, confidence=1.0, alerts=(), reasons=None, version=None, industry="Finance", sector="Holding Companies", judged=10, missing=()):
    rating = {"status": status, "confidence": confidence, "alerts": list(alerts), "judgedQuarters": judged, "final": None if status == "NOT RATED" else 60.0,
              "label": "NOT RATED" if status == "NOT RATED" else "AVERAGE", "modelVersion": "3.6.10",
              "metrics": [{"label": m, "status": "L"} for m in missing] + [{"label": "Sales streak", "status": "A"}]}
    if reasons is not None:
        rating["notRatedReasons"] = reasons
    meta = {} if version is None else {"classificationVersion": version}
    return {"id": symbol.ljust(32, "0")[:32].lower(), "rating": rating, "inputMeta": meta, "company": {"symbol": symbol, "industry": industry, "sector": sector}}


async def test_label_of_reads_the_old_and_the_new_wording():
    assert prism_audit.label_of({"alerts": [NEW]}) == "Zzyzx Widgets"
    assert prism_audit.label_of({"alerts": ['The company\'s industry label "Old Label" is not yet mapped to a model group.']}) == "Old Label"
    assert prism_audit.label_of({"alerts": ['Prism has no model group for this instrument ("REIT"): Trusts are not rated by this model.']}) == "REIT"


def test_stale_classification_is_counted_and_listed_in_the_rendering():
    rows = [{"symbol": "COALINDIA", "status": "NOT RATED", "alerts": [OLD], "confidence": 1.0, "classification_version": "2"},
            {"symbol": "BBB", "status": "NOT RATED", "alerts": [NEW], "confidence": 1.0, "classification_version": str(prism.CLASSIFICATION_VERSION)}]
    out = prism_audit.summarise(rows)
    assert out["staleClassification"] == {"count": 1, "symbols": ["COALINDIA"]}
    assert "precompute-prism --stale-not-rated" in prism_audit.render({**out, "statement": "consolidated"})


async def put(store, rows):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
        for rep in rows:
            r = rep["rating"]
            await conn.execute("INSERT INTO prism_reports (symbol, statement, id, report, model_version, final, label, status) VALUES ($1,'consolidated',$2,$3::jsonb,'3.6.10',$4,$5,$6)",
                               rep["company"]["symbol"], rep["id"], json.dumps(rep), r["final"], r["label"], r["status"])


ROWS = [
    report("BAJAJFINSV", "NOT RATED", alerts=[OLD, "NOT RATED: 55% data confidence and 10 comparable quarters."]),
    report("AAA", "NOT RATED", alerts=[OLD], industry="Trading", sector="Trading & Distributors"),
    report("BBB", "NOT RATED", alerts=[NEW], version=prism.CLASSIFICATION_VERSION, reasons=[{"code": "classification", "text": NEW}]),
    report("CCC", "NOT RATED", confidence=.3, missing=("PEG", "Pledge")),
    report("DDD", "NOT RATED", confidence=.4, missing=("PEG",)),
    report("EEE", "NOT RATED", reasons=[{"code": "insufficient_history", "text": "x"}], alerts=["Not enough reported history: 2 quarter(s)"], missing=("Sales CAGR",)),
    report("FFF", "PROVISIONAL", confidence=.7),
    report("GGG", "PROVISIONAL", confidence=.9, judged=4),
    report("HHH", "RATED"),
]


async def test_audit_buckets_labels_and_missing_inputs_from_one_query(store):  # noqa: F811
    await put(store, ROWS)
    res = await prism_audit.audit(store)
    assert res["total"] == 8 and res["byStatus"] == {"NOT RATED": 6, "PROVISIONAL": 2}
    assert res["buckets"] == {"classification": 3, "low_confidence": 2, "insufficient_history": 1, "provisional_coverage": 1, "provisional_history": 1, "other": 0}
    labels = {x["label"]: x for x in res["classificationLabels"]}
    assert labels["Zzyzx Widgets"]["symbols"] == ["BBB"] and labels["Finance / Holding Companies"]["symbols"] == ["BAJAJFINSV"]
    assert labels["Trading / Trading & Distributors"]["count"] == 1
    assert res["topMissing"]["low_confidence"][0] == {"input": "PEG", "count": 2}
    assert res["topMissing"]["insufficient_history"] == [{"input": "Sales CAGR", "count": 1}]
    stored = await prism_audit.last_result(store.pool)
    assert stored["buckets"]["classification"] == 3
    text = prism_audit.render(res)
    assert "Zzyzx Widgets" in text and "low_confidence" in text


def test_symbols_are_capped_at_ten_per_label():
    rows = [{"symbol": f"S{i}", "status": "NOT RATED", "alerts": [NEW], "confidence": 1.0} for i in range(25)]
    out = prism_audit.summarise(rows)
    assert out["classificationLabels"][0]["count"] == 25 and len(out["classificationLabels"][0]["symbols"]) == 10


def test_python_and_site_classification_versions_agree():
    site = (Path(__file__).parents[2] / "site-api" / "backend" / "premium_classification.py").read_text()
    assert int(re.search(r"^CLASSIFICATION_VERSION = (\d+)", site, re.M).group(1)) == prism.CLASSIFICATION_VERSION


def test_only_old_classification_reports_are_stale():
    assert prism.stale_classification(ROWS[0]) and prism.stale_classification(json.dumps(ROWS[1]))
    assert not prism.stale_classification(ROWS[2])            # already calculated by the current rules
    assert not prism.stale_classification(ROWS[3])            # low confidence is legitimate
    assert not prism.stale_classification(ROWS[8])
    assert not prism.stale_classification("not json")


async def test_stale_not_rated_flag_recalculates_only_those_and_does_not_loop(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr(prism, "STALE_PAUSE", 0)
    syms = ["BAJAJFINSV", "AAA", "BBB", "CCC", "HHH"]
    await put(store, [r for r in ROWS if r["company"]["symbol"] in syms])
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots WHERE symbol = ANY($1::text[])", syms)
        for sym in syms:
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1, 'consolidated', 'summary', '{}', 'x', now())", sym)
    for sym in syms:
        await store.redis.delete(f"prism:pre:fail:consolidated:{sym}")
    settings = make_settings(site_api_url="http://site", cms_jwt_secret=SECRET)
    fake = FakeSite()
    old_backend = copy.deepcopy(SNAPSHOT)
    old_backend["rating"].update(status="NOT RATED", final=None, label="NOT RATED", alerts=[OLD])
    old_backend["inputMeta"] = {}
    fake.per_symbol["AAA"] = httpx.Response(200, json=old_backend)       # this one is still answered by a site backend with the old rules
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake), base_url="http://site")
    out = await prism.precompute(store, settings, limit=50, client=http, stale_not_rated=True)
    assert sorted(r["body"]["query"] for r in fake.reports) == ["AAA", "BAJAJFINSV"]     # not BBB (current), CCC (legitimate), HHH (rated)
    assert out["calculated"] == 2
    rows = {r["symbol"]: r["status"] for r in await store.pool.fetch("SELECT symbol, status FROM prism_reports")}
    assert rows["BAJAJFINSV"] == "RATED" and rows["CCC"] == "NOT RATED"
    again = await prism.precompute(store, settings, limit=50, client=http, stale_not_rated=True)
    assert len(fake.reports) == 2 and again["calculated"] == 0       # AAA waits for tomorrow instead of being hammered every round
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots WHERE symbol = ANY($1::text[])", syms)
    for sym in syms:
        await store.redis.delete(f"prism:pre:fail:consolidated:{sym}")


async def test_nightly_run_takes_stale_ones_first_and_members_do_not_get_the_stored_one(store):  # noqa: F811
    await put(store, [ROWS[0], ROWS[8]])
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT report, generated_at FROM prism_reports WHERE symbol = 'BAJAJFINSV'")
    assert not prism._fresh(row)           # stored a moment ago, yet recalculated when a member asks
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT report, generated_at FROM prism_reports WHERE symbol = 'HHH'")
    assert prism._fresh(row)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots WHERE symbol IN ('BAJAJFINSV','HHH')")
        for sym in ("BAJAJFINSV", "HHH"):
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1, 'consolidated', 'summary', '{}', 'x', now())", sym)
    assert await prism._pending(store, "consolidated", 7, 10, []) == ["BAJAJFINSV"]
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots WHERE symbol IN ('BAJAJFINSV','HHH')")
