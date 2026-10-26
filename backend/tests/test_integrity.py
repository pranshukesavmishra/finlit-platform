"""The nightly data-integrity audit (finlit/integrity.py): the pure checks, the grading, and one run over a recorded company (no live calls)."""
from datetime import date

import pytest

from finlit import integrity as ig
from test_integration import ingested, make_settings, store  # noqa: F401
from finlit.finedge import FinEdgeClient


def test_price_check_flags_missing_and_far_prices_only():
    assert ig.check_price(100, 110) is None and ig.check_price(100, None) is None
    assert "no price shown" in ig.check_price(None, 55)
    assert "shows 50" in ig.check_price(50, 100)
    assert ig.check_price(81, 100) is None and ig.check_price(79, 100) is not None


def test_basis_check_catches_a_stale_statement_set():
    assert "report stops at 2025-03-31" in ig.check_basis("2025-03-31", "2026-09-30")     # SBFC: consolidated stops Mar 2025
    assert ig.check_basis("2026-09-30", "2026-09-30") is None and ig.check_basis(None, "2026-09-30") is None


def test_identities_catch_a_broken_sum_and_a_lost_eps_sign():
    ok = {"periods": ["FY25"], "rows": {"revenue": [100.0], "expenses": [80.0], "operating_profit": [20.0], "eps": [3.0], "net_profit": [9.0]}}
    assert ig.check_identities(ok) == []
    bad = {"periods": ["FY25", "FY24"], "rows": {"revenue": [100.0, 100.0], "expenses": [80.0, 80.0], "operating_profit": [50.0, 20.0], "eps": [5.14, 2.0], "net_profit": [-17.6, 4.0]}}
    out = ig.check_identities(bad)
    assert len(out) == 2 and "operating profit" in out[0] and "opposite sign" in out[1]


def test_declared_results_older_than_three_days_must_not_still_be_updating():
    today, q = date(2026, 10, 26), date(2026, 9, 30)
    assert ig.check_declared(date(2026, 10, 20), q, "2026-06-30", today) is not None
    assert ig.check_declared(date(2026, 10, 24), q, "2026-06-30", today) is None          # inside the grace days
    assert ig.check_declared(date(2026, 10, 20), q, "2026-09-30", today) is None          # figures are in


def test_risk_figures_are_required_once_a_year_of_prices_exists():
    assert ig.check_risk(300, None, 12.0) is not None and ig.check_risk(300, 20.0, 12.0) is None and ig.check_risk(100, None, None) is None


def test_grading_and_wording():
    assert ig.grade(40, 0) == "green" and ig.grade(40, 2) == "amber" and ig.grade(40, 9) == "red"
    c = ig.make_check("price", 10, ["A: x"] * 5)
    assert c["level"] == "red" and "5 of 10" in c["message"] and c["examples"]
    assert ig.overall([ig.make_check("price", 5, []), c]) == "red"
    assert ig.make_check("risk", 0, [])["level"] == "green"


@pytest.mark.integration
async def test_audit_runs_over_a_recorded_company_and_stores_its_result(ingested):  # noqa: F811
    store = ingested
    async with store.pool.acquire() as conn:
        price = await conn.fetchval("SELECT price::float8 FROM scores WHERE symbol = 'RELIANCE' AND model = 'v1' LIMIT 1")
        await conn.execute("INSERT INTO listing_quotes (symbol, price, updated_at) VALUES ('RELIANCE', $1, now()) ON CONFLICT (symbol) DO UPDATE SET price = EXCLUDED.price, updated_at = now()", price * 2)
    async with FinEdgeClient(make_settings()) as client:
        res = await ig.audit(store, client, sample=5)
    by = {c["key"]: c for c in res["checks"]}
    assert by["price"]["bad"] == 1 and by["price"]["level"] in ("amber", "red") and res["sampled"] >= 1
    assert by["basis"]["bad"] == 0 and by["declared"]["checked"] == 0
    assert (await ig.last_result(store.pool))["at"] == res["at"]
