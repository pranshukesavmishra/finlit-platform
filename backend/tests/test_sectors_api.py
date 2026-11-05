"""Sector pages over HTTP: plan gating on the server, slug and symbol validation, the 'not loaded yet' answers, caching, the status route."""
import json
import os

import pytest

import sector_fakes as fakes
from finlit import sector_data as sd
from finlit.auth.entitlements import redact_sector_board, redact_sector_industry, redact_sector_stock, sector_plan
from test_auth import anon, app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_earnings_api import admin_client  # noqa: F401
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration
BOARD = json.loads((fakes.FIX / "sectors" / "_board.json").read_text())
FERROUS = json.loads((fakes.FIX / "sectors" / "ferrous-metals.json").read_text())
SAMBHV = json.loads((fakes.FIX / "SAMBHV.json").read_text())["sector"]


@pytest.fixture
def out(tmp_path, monkeypatch):
    """A live release (as the nightly job leaves it) under SECTOR_OUT_DIR."""
    monkeypatch.setenv("SECTOR_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("SECTORS_ENABLED", "1")
    sd.clear_cache()
    root = tmp_path / "out"
    b = sd.building_dir(root, "20261029-1934")
    fakes.make_release(b)
    sd.publish(b, root, "20261029-1934")
    yield root
    sd.clear_cache()


# ------------------------------------------------------------------------------------------------ the pure redaction rules
def test_basic_loses_flags_stock_tables_and_peer_labels_but_keeps_states_and_breadth():
    b = redact_sector_board(BOARD, "basic")
    assert all(r["leader_flags"] is None for r in b["rows"]) and b["leader_flags"] is None and b["locked"] == {"leader_flags": "silver"}
    assert [r["state"] for r in b["rows"]] == [r["state"] for r in BOARD["rows"]] and b["rows"][0]["breadth"] == BOARD["rows"][0]["breadth"]
    page = redact_sector_industry(FERROUS, "basic")
    assert page["stocks"] is None and page["not_counted"] is None and page["leader_flags"] is None
    assert page["history"] == FERROUS["history"] and page["breadth"] == FERROUS["breadth"] and page["summary"] == FERROUS["summary"] and page["study"] == FERROUS["study"]
    assert set(page["locked"]) == {"stocks", "not_counted", "leader_flags"}
    assert "peer_label" in FERROUS["stocks"][0]                      # the input was not changed
    assert redact_sector_stock(SAMBHV, "SAMBHV", "basic")["locked"] == {"stock": "gold"}


def test_silver_adds_tables_and_flags_but_not_peer_labels_gold_adds_both():
    page = redact_sector_industry(FERROUS, "silver")
    assert len(page["stocks"]) == len(FERROUS["stocks"]) and all(s["peer_label"] is None for s in page["stocks"]) and page["not_counted"] == FERROUS["not_counted"]
    assert page["locked"] == {"peer_label": "gold"} and page["stocks"][0]["rank_6m"] == 1
    assert redact_sector_board(BOARD, "silver")["rows"][0]["leader_flags"] == BOARD["rows"][0]["leader_flags"] and redact_sector_board(BOARD, "silver")["leader_flags"] == BOARD["leader_flags"]
    gold = redact_sector_industry(FERROUS, "gold")
    assert gold["stocks"][0]["peer_label"] == "In line" and gold["locked"] == {}
    assert redact_sector_stock(SAMBHV, "SAMBHV", "silver")["locked"] == {"stock": "gold"}
    full = redact_sector_stock(SAMBHV, "SAMBHV", "gold")
    assert full["rank_6m"] == SAMBHV["rank_6m"] and full["locked"] == {}


def test_a_locked_stock_answer_carries_no_value_above_the_plan():
    t = redact_sector_stock(SAMBHV, "SAMBHV", "basic")
    flat = json.dumps(t)
    for secret in ("rank_6m", "return_6m_pct", "quarter_name", "leader_flag_text", "above_9", "last_thrust", "summary", "peer_label"):
        assert secret not in flat, secret
    assert t["group"]["state"] == "Washout" and t["group"]["slug"] == "industrial-products" and t["name"]


def test_plan_resolution_admin_is_gold_unknown_is_basic():
    assert sector_plan("basic", "admin") == "gold" and sector_plan("silver") == "silver" and sector_plan("weird") == "basic" and sector_plan("basic", "visitor") == "basic"


# ------------------------------------------------------------------------------------------------ not loaded
async def test_nothing_loaded_says_why_never_a_bare_error(anon, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SECTOR_OUT_DIR", str(tmp_path / "empty"))
    monkeypatch.delenv("SECTORS_ENABLED", raising=False)
    sd.clear_cache()
    for url in ("/api/sectors", "/api/sectors/ferrous-metals", "/api/technicals/SAMBHV/sector"):
        r = await anon.get(url)
        b = r.json()
        assert r.status_code == 503 and b["available"] is False and b["reason"].startswith("Sector data is not loaded yet:") and "switched off" in b["reason"], (url, r.text)
        assert r.headers["cache-control"] == "no-store"
    monkeypatch.setenv("SECTORS_ENABLED", "1")
    assert "first nightly run has not finished" in (await anon.get("/api/sectors")).json()["reason"]
    sd.write_last_run(tmp_path / "empty", {"status": "error", "reason": "Cannot run: the NSE data folder /data/nse does not exist"})
    why = (await anon.get("/api/sectors")).json()["reason"]
    assert why.startswith("Sector data is not loaded yet:") and "NSE data folder" in why
    s = (await anon.get("/api/sectors/status")).json()
    assert s["loaded"] is False and s["enabled"] is True and s["lastRun"]["status"] == "error" and s["reason"] == why


async def test_a_board_slug_with_no_page_file_is_a_503_that_says_so(anon, out):  # noqa: F811
    (out / "current").resolve().joinpath("sectors", "banks.json").unlink()
    sd.clear_cache()
    r = await anon.get("/api/sectors/banks")
    assert r.status_code == 503 and "missing from the current data set" in r.json()["reason"]


# ------------------------------------------------------------------------------------------------ plans over HTTP
async def test_basic_visitor_sees_states_and_breadth_but_not_tables_flags_or_cards(anon, out):  # noqa: F811
    b = (await anon.get("/api/sectors")).json()
    assert b["plan"] == "basic" and len(b["rows"]) == 3 and all(r["leader_flags"] is None for r in b["rows"]) and b["leader_flags"] is None
    assert b["rows"][0]["state"] and b["rows"][0]["breadth"]["above_50"] is not None and b["disclaimer"] and b["counts"]
    r = await anon.get("/api/sectors/ferrous-metals")
    p = r.json()
    assert r.status_code == 200 and p["stocks"] is None and p["not_counted"] is None and p["history"]["dates"] and p["summary"] and p["locked"]["stocks"] == "silver"
    assert "KIRLFER" not in r.text and "MANAKSTEEL" not in r.text                         # no stock symbol leaks below Silver
    s = await anon.get("/api/technicals/SAMBHV/sector")
    assert s.status_code == 200 and s.json()["locked"] == {"stock": "gold"} and "rank_6m" not in s.text


async def test_silver_sees_ranked_tables_and_flags_gold_sees_peer_labels_and_stock_cards(app, out):  # noqa: F811
    silver = await signed_in(app, "s@example.com", plan="silver")
    p = (await silver.get("/api/sectors/ferrous-metals")).json()
    assert p["plan"] == "silver" and p["stocks"][0]["symbol"] == "KIRLFER" and p["stocks"][0]["peer_label"] is None and p["not_counted"] and p["locked"] == {"peer_label": "gold"}
    assert (await silver.get("/api/sectors")).json()["leader_flags"] and (await silver.get("/api/technicals/SAMBHV/sector")).json()["locked"] == {"stock": "gold"}
    await silver.aclose()
    gold = await signed_in(app, "g@example.com", plan="gold")
    p = (await gold.get("/api/sectors/ferrous-metals")).json()
    assert p["stocks"][0]["peer_label"] == "In line" and p["locked"] == {}
    s = (await gold.get("/api/technicals/SAMBHV/sector")).json()
    assert s["rank_6m"] == 20 and s["ranked_6m"] == 105 and s["group"]["slug"] == "industrial-products" and s["leader_flag_text"] and s["locked"] == {}
    await gold.aclose()


async def test_an_administrator_below_gold_still_sees_everything(app, out):  # noqa: F811
    admin = await admin_client(app, "boss@example.com")
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan = 'basic' WHERE lower(email) = 'boss@example.com'")
    from finlit.auth.service import forget_cached
    async with app.state.store.pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id::text FROM users WHERE lower(email) = 'boss@example.com'")
    await forget_cached(app, uid)
    r = await admin.post("/api/auth/login", json={"email": "boss@example.com", "password": "a-long-unusual-phrase-42"})
    admin.headers.update({"X-CSRF-Token": r.json()["csrf"]})
    p = (await admin.get("/api/sectors/ferrous-metals")).json()
    assert p["plan"] == "gold" and p["stocks"][0]["peer_label"] == "In line"
    await admin.aclose()


# ------------------------------------------------------------------------------------------------ validation
@pytest.mark.parametrize("slug", ["nope", "FERROUS-METALS", "ferrous-metals.json", "..", "%2e%2e", "ferrous-metals%2f..%2f_board", "a" * 200, "_board", "-x", "ferrous_metals"])
async def test_only_a_slug_the_board_lists_is_served(anon, out, slug):  # noqa: F811
    r = await anon.get(f"/api/sectors/{slug}")
    assert r.status_code in (404, 422) or r.json().get("status") == "not_found"
    assert "disclaimer" not in r.text or r.status_code == 404
    assert r.status_code != 200


@pytest.mark.parametrize("symbol", ["..", ".hidden", "A%2FB", "SAMBHV.json", "-X", "X" * 40, "NOPE", "_summary", "%2e%2e%2f_summary"])
async def test_a_symbol_that_is_not_a_stock_file_is_a_clean_404(anon, out, symbol):  # noqa: F811
    r = await anon.get(f"/api/technicals/{symbol}/sector")
    assert r.status_code == 404 and "disclaimer" not in r.text


async def test_a_symbol_is_case_insensitive_and_the_status_route_is_not_taken_by_the_slug_route(anon, out):  # noqa: F811
    assert (await anon.get("/api/technicals/sambhv/sector")).status_code == 200
    st = await anon.get("/api/sectors/status")
    assert st.status_code == 200 and st.json()["loaded"] is True and st.json()["dataDate"] == "2026-10-29" and "groups" in st.json()


# ------------------------------------------------------------------------------------------------ caching and the swap
async def test_etag_gives_304_and_the_answer_is_private_because_it_depends_on_the_plan(anon, out):  # noqa: F811
    r = await anon.get("/api/sectors")
    assert r.headers["cache-control"].startswith("private") and "Cookie" in r.headers["vary"] and r.headers["etag"]
    again = await anon.get("/api/sectors", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


async def test_a_swap_changes_what_is_served_at_once_and_the_old_release_is_kept_for_readers(anon, out):  # noqa: F811
    assert (await anon.get("/api/sectors")).json()["date"] == "2026-10-29"
    first = (out / "current").resolve()
    b = sd.building_dir(out, "20261030-1934")
    fakes.make_release(b, date="2026-10-30")
    assert (await anon.get("/api/sectors")).json()["date"] == "2026-10-29"       # a half-built folder is never served
    sd.publish(b, out, "20261030-1934")
    assert (await anon.get("/api/sectors")).json()["date"] == "2026-10-30" and first.is_dir()
    assert os.path.islink(out / "current")


# ------------------------------------------------------------------------------------------------ Sector Rotation
@pytest.fixture
def rot_out(tmp_path, monkeypatch):
    """A live release that also holds the rotation files (the real output of 29 Oct 2026, three groups)."""
    monkeypatch.setenv("SECTOR_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("SECTORS_ENABLED", "1")
    sd.clear_cache()
    root = tmp_path / "out"
    b = sd.building_dir(root, "20261029-1934")
    fakes.make_release(b, rotation=True)
    sd.publish(b, root, "20261029-1934")
    yield root
    sd.clear_cache()


async def test_rotation_map_and_cards_are_open_to_every_plan_but_the_leader_flag_count_follows_the_board(anon, app, rot_out):  # noqa: F811
    r = await anon.get("/api/rotation")
    m = r.json()
    assert r.status_code == 200 and m["plan"] == "basic" and len(m["rows"]) == 3 and m["disclaimer"] and m["study"]["corners"]
    assert all(x["corner"] and x["rank"] and x["tail"] for x in m["rows"]) and all(x["leader_flags"] is None for x in m["rows"]) and m["locked"] == {"leader_flags": "silver"}
    assert r.headers["cache-control"].startswith("private") and r.headers["etag"]
    card = await anon.get("/api/rotation/banks")
    c = card.json()
    assert card.status_code == 200 and c["reading"] is True and c["name"] == "Banks" and c["summary"] and c["study"]
    silver = await signed_in(app, "rs@example.com", plan="silver")
    assert (await silver.get("/api/rotation")).json()["locked"] == {}
    await silver.aclose()


async def test_rotation_says_why_when_it_is_missing_and_serves_only_listed_slugs(anon, rot_out, tmp_path, monkeypatch):  # noqa: F811
    for slug in ("nope", "..", "_map", "BANKS", "banks.json", "a" * 200):
        r = await anon.get(f"/api/rotation/{slug}")
        assert r.status_code in (404, 422) and "disclaimer" not in r.text, slug
    (rot_out / "current").resolve().joinpath("rotation", "banks.json").unlink()
    sd.clear_cache()
    r = await anon.get("/api/rotation/banks")
    assert r.status_code == 503 and "rotation card is missing" in r.json()["reason"]
    # a release with no rotation folder (built before rotation existed)
    older = tmp_path / "older"
    b = sd.building_dir(older, "20261028-1934")
    fakes.make_release(b)
    sd.publish(b, older, "20261028-1934")
    monkeypatch.setenv("SECTOR_OUT_DIR", str(older))
    sd.clear_cache()
    r = await anon.get("/api/rotation")
    assert r.status_code == 503 and r.json()["reason"].startswith("Rotation data is not loaded yet:") and r.headers["cache-control"] == "no-store"
    assert (await anon.get("/api/sectors")).status_code == 200 and (await anon.get("/api/sectors/status")).json()["rotationLoaded"] is False


async def test_nothing_loaded_rotation_gives_the_sector_reason(anon, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SECTOR_OUT_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("SECTORS_ENABLED", "1")
    sd.clear_cache()
    for url in ("/api/rotation", "/api/rotation/banks"):
        r = await anon.get(url)
        assert r.status_code == 503 and r.json()["reason"].startswith("Sector data is not loaded yet:")


async def test_the_old_capital_goods_address_answers_with_the_renamed_group(anon, rot_out, monkeypatch):  # noqa: F811
    assert sd.resolve_slug("capital-goods") == "agricultural-commercial-construction-vehicles" and sd.resolve_slug("banks") == "banks"
    monkeypatch.setattr(sd, "SLUG_ALIASES", {"capital-goods": "banks"})                     # the fixture holds no vehicles group: alias a group it does hold
    a, b = await anon.get("/api/sectors/capital-goods"), await anon.get("/api/sectors/banks")
    assert a.status_code == 200 and a.json()["slug"] == b.json()["slug"] == "banks"
    assert (await anon.get("/api/rotation/capital-goods")).json()["slug"] == "banks"


async def test_a_basic_stock_teaser_carries_the_industrys_rotation_line(anon, rot_out):  # noqa: F811
    doc = json.loads((fakes.FIX / "SAMBHV.json").read_text())["sector"]
    doc["rotation"] = {"corner": "ahead_slowing", "corner_name": "Ahead but slowing", "rank": 7, "ranked": 37}
    t = redact_sector_stock(doc, "SAMBHV", "basic")
    assert t["rotation"]["rank"] == 7 and t["locked"] == {"stock": "gold"} and "rank_6m" not in json.dumps(t)
