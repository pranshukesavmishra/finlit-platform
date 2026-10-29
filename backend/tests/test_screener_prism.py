"""The Advanced score screener's FinLit Prism columns: the universe carries the newest stored rating per company (one query, no report json),
a plan below Gold never receives the figures, and the nightly widening keeps to its budget, its pauses and its one-week retry rule."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from finlit import prism, prism_screen
from finlit.api import create_app
from finlit.auth.entitlements import MODEL_FIELDS, PRISM_FIELDS, redact_universe
from test_auth import new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401  (fixtures)
from test_prism import SECRET, FakeSite

pytestmark = pytest.mark.integration


def view(final=71.2, label="HEALTHY", status="RATED", parts=True, st=(22.5, "Buy"), lt=(-30.0, "Sell")):
    return {"id": "a" * 32, "rating": {"final": final, "label": label, "status": status, "confidence": 0.9,
            "parts": {"fundamental": 70.1, "valuation": 40.2, "quality": 80.3, "risk": 65.4} if parts else {}},
            "technicalAssessment": {"shortTerm": {"score": st[0], "rating": st[1]}, "longTerm": {"score": lt[0], "rating": lt[1]}}}


async def put(store, symbol, statement="consolidated", **kw):
    v = view(**kw)
    v["id"] = (symbol.ljust(32, "0"))[:32].lower().replace("_", "0")
    await prism._save(store, symbol, statement, v, None)


@pytest.fixture
async def app(ingested):  # noqa: F811
    from finlit.screener import data as screener_data
    app = create_app(make_settings(showcase_symbols=["TCS"]), store=ingested)
    async with app.router.lifespan_context(app):
        await ingested.pool.execute("DELETE FROM prism_reports")
        yield app
    screener_data.reset()


def test_the_card_keeps_only_the_listed_figures_and_hides_parts_of_an_unrated_company():
    card = prism.card_of(view())
    assert card["parts"]["quality"] == 80.3 and card["st"] == {"score": 22.5, "rating": "Buy"} and card["confidence"] == 0.9
    assert prism.card_of(view(final=None, label="NOT RATED", status="NOT RATED"))["parts"] is None
    assert prism.card_of({"rating": {}})["st"] == {"score": None, "rating": None}      # an old report without the technical assessment


def test_the_shape_uses_descriptive_words_never_the_models_and_no_word_without_a_score():
    row = {"symbol": "X", "final": 71.2, "label": "HEALTHY", "status": "RATED", "generated_at": datetime(2026, 10, 20, tzinfo=timezone.utc), "card": json.dumps(prism.card_of(view()))}
    out = prism_screen.shape(row)
    assert out["prism_st"] == "Positive" and out["prism_lt"] == "Strongly negative" and out["prism_st_score"] == 22.5
    assert out["prism_at"] == "2026-10-20" and out["prism_quality"] == 80.3 and out["prism_state"] == "stored"
    assert not {"buy", "sell", "hold"} & {str(v).lower() for v in out.values()}
    bare = prism_screen.shape({**row, "card": {"parts": None, "st": {"score": None, "rating": "Unavailable"}, "lt": {}}})
    assert bare["prism_st"] is None and bare["prism_fundamental"] is None
    assert prism_screen.blank()["prism_state"] == "none" and set(prism_screen.blank()) == set(PRISM_FIELDS)


def test_redaction_by_plan():
    rows = [{"symbol": "TCS", "overall": 80, "prism_final": 60, "prism_state": "stored"}, {"symbol": "INFY", "overall": 70, "prism_final": 50, "prism_state": "stored"}]
    gold = redact_universe(rows, "gold", {"TCS"})
    assert gold == rows
    silver = redact_universe(rows, "silver", {"TCS"})
    assert silver[1]["overall"] == 70 and silver[1]["prism_final"] is None and silver[1]["prism_state"] is None
    assert silver[0]["prism_final"] == 60                                                        # the showcase company stays open
    basic = redact_universe(rows, "basic", {"TCS"})
    assert basic[1]["overall"] is None and all(basic[1][f] is None for f in PRISM_FIELDS) and basic[0]["prism_final"] == 60


def test_two_screeners_two_plans_prism_only_for_gold_and_the_finlit_score_only_for_silver_and_up():
    """Basic score screener = Silver (FinLit score fields); Advanced score screener = Gold (Prism fields). Every field of each model is checked, not a sample."""
    full = {f: 61.5 for f in PRISM_FIELDS + MODEL_FIELDS}
    rows = [{"symbol": "SHOWCASE", **full}, {"symbol": "OTHER", **full}]
    for plan in ("basic", "silver"):                                                              # Prism: not for Basic, not for Silver
        out = {r["symbol"]: r for r in redact_universe(rows, plan, {"SHOWCASE"})}
        assert all(out["OTHER"][f] is None for f in PRISM_FIELDS), plan
        assert not any("61.5" in repr(v) for k, v in out["OTHER"].items() if k.startswith("prism_")), plan
        assert all(out["SHOWCASE"][f] == 61.5 for f in PRISM_FIELDS + MODEL_FIELDS), plan           # the free example company stays open
    assert all(r[f] is None for r in redact_universe(rows, "basic", {"SHOWCASE"}) if r["symbol"] == "OTHER" for f in MODEL_FIELDS)   # FinLit score: not for Basic
    silver = next(r for r in redact_universe(rows, "silver", {"SHOWCASE"}) if r["symbol"] == "OTHER")
    assert all(silver[f] == 61.5 for f in MODEL_FIELDS)                                           # ... but for Silver
    gold = redact_universe(rows, "gold", {"SHOWCASE"})
    assert all(r[f] == 61.5 for r in gold for f in PRISM_FIELDS + MODEL_FIELDS)                  # Gold sees both
    assert redact_universe(rows, "silver", {"SHOWCASE"})[1] is not rows[1] and rows[1]["prism_final"] == 61.5     # the shared cache rows are never changed


async def test_the_universe_lists_the_newest_rating_prefers_consolidated_and_keeps_locked_values_on_the_server(app):
    store = app.state.store
    await put(store, "RELIANCE", "standalone", final=40.0, label="WEAK")
    await put(store, "RELIANCE", "consolidated", final=71.2)
    await put(store, "TCS", "standalone", final=55.0, label="AVERAGE")                      # standalone only: used
    await put(store, "INFY", final=None, label="NOT RATED", status="NOT RATED", parts=False)
    gold = await signed_in(app, "gold@example.com", plan="gold")
    body = (await gold.get("/api/screener/universe")).json()
    rows = {r["symbol"]: r for r in body["rows"]}
    rel = rows["RELIANCE"]
    assert rel["prism_final"] == 71.2 and rel["prism_label"] == "HEALTHY" and rel["prism_status"] == "RATED" and rel["prism_quality"] == 80.3
    assert rel["prism_st"] == "Positive" and rel["prism_lt"] == "Strongly negative" and rel["prism_state"] == "stored" and rel["prism_at"]
    assert rows["TCS"]["prism_final"] == 55.0
    assert rows["INFY"]["prism_state"] == "stored" and rows["INFY"]["prism_label"] == "NOT RATED" and rows["INFY"]["prism_fundamental"] is None
    none = next(r for r in body["rows"] if r["symbol"] not in ("RELIANCE", "TCS", "INFY"))
    assert none["prism_state"] == "none" and none["prism_final"] is None
    cover = body["prism"]
    assert cover["rated"] == 2 and cover["stored"] == 3 and cover["not_rated"] == 1 and cover["total"] == len(body["rows"]) and cover["per_night"] == prism.widen_per_night()
    # the rating is on its way to Gold only: Silver keeps the FinLit score, a visitor neither; the showcase company stays open
    silver = await signed_in(app, "silver@example.com", plan="silver")
    raw = (await silver.get("/api/screener/universe")).content
    srows = {r["symbol"]: r for r in json.loads(raw)["rows"]}
    assert srows["RELIANCE"]["overall"] is not None and all(srows["RELIANCE"][f] is None for f in PRISM_FIELDS)
    assert srows["TCS"]["prism_final"] == 55.0
    assert b"71.2" not in json.dumps({k: v for k, v in srows["RELIANCE"].items() if k.startswith("prism")}).encode()
    async with new_client(app) as visitor:
        v = {r["symbol"]: r for r in (await visitor.get("/api/screener/universe")).json()["rows"]}
        assert v["RELIANCE"]["overall"] is None
        assert all(v["RELIANCE"][f] is None for f in PRISM_FIELDS) and v["TCS"]["prism_final"] == 55.0
        assert (await visitor.get("/api/screener/universe")).json()["prism"]["rated"] == 2          # counts are for everyone, no company is named
    for c in (gold, silver):
        await c.aclose()


async def test_the_card_is_filled_for_ratings_stored_before_it_existed(app):
    store = app.state.store
    await put(store, "RELIANCE")
    await store.pool.execute("UPDATE prism_reports SET card = NULL")
    sql = (__import__("pathlib").Path(prism.__file__).parent / "migrations" / "070_prism_card.sql").read_text()
    await store.pool.execute(sql)
    row = await store.pool.fetchrow("SELECT card FROM prism_reports WHERE symbol = 'RELIANCE'")
    card = json.loads(row["card"])
    assert card["parts"]["risk"] == 65.4 and card["st"]["score"] == 22.5 and card["lt"]["rating"] == "Sell"


# ------------------------------------------------------------------ widening
class Env:
    def __init__(self, store, fake, http, settings):
        self.store, self.fake, self.http, self.settings = store, fake, http, settings

    async def run(self, **kw):
        return await prism.precompute(self.store, self.settings, limit=10, client=self.http, **kw)


@pytest.fixture
async def wide(ingested, monkeypatch):
    store = ingested
    monkeypatch.setattr(prism, "RETRY_AFTER_BACKGROUND", 0.01)
    monkeypatch.setattr(prism, "PRE_PAUSE_TRIES", 2)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
        await conn.execute("DELETE FROM snapshots WHERE section = 'summary'")
        await conn.execute("DELETE FROM listing_quotes")
        for sym, cap in (("WIDEA", 900), ("WIDEB", 800), ("WIDEC", 700), ("WIDED", 600)):
            await conn.execute("INSERT INTO companies (symbol, name) VALUES ($1, $1) ON CONFLICT DO NOTHING", sym)
            await conn.execute("INSERT INTO listing_quotes (symbol, price, market_cap) VALUES ($1, 10, $2)", sym, cap)
        await conn.execute("INSERT INTO companies (symbol, name) VALUES ('NOCAP', 'No cap') ON CONFLICT DO NOTHING")
    for pattern in ("prism:widen:*", "prism:pre:*", "prism:member:*", "prism:obs:*", "prism:univ:*"):
        for key in [k async for k in store.redis.scan_iter(match=pattern)]:
            await store.redis.delete(key)
    fake = FakeSite()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake), base_url="http://site")
    yield Env(store, fake, http, make_settings(site_api_url="http://site", cms_jwt_secret=SECRET))
    await http.aclose()


def asked(env):
    return [r["body"]["query"] for r in env.fake.reports]


async def test_widening_takes_the_next_biggest_within_the_nightly_budget_and_only_once_a_night(wide, monkeypatch):
    monkeypatch.setenv("PRISM_WIDEN_PER_NIGHT", "2")
    out = await wide.run()
    assert asked(wide) == ["WIDEA", "WIDEB"] and out["widened"] == 2          # biggest first; a company with no market value is never picked
    again = await wide.run()                                                   # the next round of the same night: the budget is spent
    assert again["widened"] == 0 and asked(wide) == ["WIDEA", "WIDEB"]
    await wide.store.redis.delete(f"prism:widen:day:{prism._widen_day()}")     # tomorrow: it continues where it stopped
    nxt = await wide.run()
    assert nxt["widened"] == 2 and asked(wide)[2:] == ["WIDEC", "WIDED"]
    stored = {r["symbol"] for r in await wide.store.pool.fetch("SELECT symbol FROM prism_reports")}
    assert {"WIDEA", "WIDEB", "WIDEC", "WIDED"} <= stored and "NOCAP" not in stored


async def test_widening_can_be_switched_off(wide, monkeypatch):
    monkeypatch.setenv("PRISM_WIDEN_PER_NIGHT", "0")
    assert (await wide.run())["widened"] == 0 and asked(wide) == []
    monkeypatch.setenv("PRISM_WIDEN_PER_NIGHT", "lots")
    assert prism.widen_per_night() == 0
    monkeypatch.delenv("PRISM_WIDEN_PER_NIGHT")
    assert prism.widen_per_night() == prism.WIDEN_DEFAULT


async def test_widening_stands_back_while_a_member_uses_prism(wide, monkeypatch):
    monkeypatch.setenv("PRISM_WIDEN_PER_NIGHT", "5")
    await prism._members_active(wide.store.redis)
    out = await wide.run()
    assert out["widened"] == 0 and out["widen_paused_for_members"] is True and asked(wide) == []
    await wide.store.redis.delete(prism.MEMBER_ACTIVE_KEY)
    assert (await wide.run())["widened"] == 4


async def test_a_company_the_provider_refused_waits_a_week_and_three_failures_stop_the_round(wide, monkeypatch):
    monkeypatch.setenv("PRISM_WIDEN_PER_NIGHT", "10")
    wide.fake.per_symbol = {"WIDEA": httpx.Response(502, json={"detail": "upstream"})}
    out = await wide.run()
    assert out["widen_refused"] == 1 and out["widened"] == 3
    assert 0 < await wide.store.redis.ttl("prism:widen:refused:consolidated:WIDEA") <= prism.WIDEN_REFUSED_SECONDS
    await wide.store.redis.delete(f"prism:widen:day:{prism._widen_day()}")
    wide.fake.reports.clear()
    await wide.run(days=0)
    assert "WIDEA" not in asked(wide)                                           # still waiting
    await wide.store.pool.execute("DELETE FROM prism_reports")
    await wide.store.redis.delete(f"prism:widen:day:{prism._widen_day()}")
    wide.fake.reports.clear(); wide.fake.per_symbol = {}
    wide.fake.answer = httpx.Response(503, json={"detail": "down"})
    await wide.store.redis.delete("prism:widen:refused:consolidated:WIDEA")
    down = await wide.run()
    assert down["widened"] == 0 and len(asked(wide)) == 3                       # provider down: three tries, then the round ends


async def test_widening_comes_after_the_companies_that_have_a_full_report(wide, monkeypatch):
    monkeypatch.setenv("PRISM_WIDEN_PER_NIGHT", "1")
    await wide.store.pool.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ('WIDED', 'consolidated', 'summary', '{}', 'x', now())")
    out = await wide.run()
    assert asked(wide) == ["WIDED", "WIDEA"] and out["calculated"] == 1 and out["widened"] == 1
