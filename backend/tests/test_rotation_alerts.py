"""Built-in Sector Rotation alerts: what counts as an event (from the nightly file alone), the closed-week rule, plan, preference and once-per-week delivery."""
import json

import pytest

import sector_fakes as fakes
from finlit import rotation_alerts as ra
from finlit import sector_data as sd
from test_auth import app, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

MAP = json.loads((fakes.ROT / "_map.json").read_text())
ROWS = {r["slug"]: r for r in MAP["rows"]}


def row(**kw):
    base = {"name": "Banks", "slug": "banks", "corner_name": "Ahead and gaining", "previous_corner_name": "Behind but gaining", "weeks_in_corner": 3, "corner_since": "2026-10-16",
            "rank": 12, "ranked": 37, "rank_change_4w": 0, "strength_pts": 0.6, "rank_history": [{"date": f"2026-09-{d:02d}", "rank": 12} for d in range(1, 8)]}
    return {**base, **kw}


def test_a_corner_change_is_an_event_only_in_its_first_confirmed_week_and_only_once_the_week_has_closed():
    r = row(weeks_in_corner=1)
    ev = ra.events_for(r)
    assert [e["kind"] for e in ev] == ["corner"] and ev[0]["from"] == "Behind but gaining" and ev[0]["to"] == "Ahead and gaining" and ev[0]["period"] == "2026-10-16"
    assert ra.events_for(r, week_closed=False) == []
    assert ra.events_for(row(weeks_in_corner=2)) == [] and ra.events_for(row(weeks_in_corner=1, previous_corner_name=None)) == []     # the group's first ranked week is no move


def test_a_rank_move_of_five_places_is_an_event_when_it_newly_reaches_five():
    hist = lambda *ranks: [{"date": f"2026-10-{i + 1:02d}", "rank": x} for i, x in enumerate(ranks)]
    # this week's 4-week change is +6 (rank[-5]=18 -> 12); last week's was +2 (rank[-6]=14 -> rank[-2]=14 is 0)
    h = [15, 14, 18, 17, 16, 14, 12]            # [-1]=12, [-5]=18, [-6]=14, [-2]=14
    r = row(rank_change_4w=6, rank_history=hist(*h))
    ev = ra.events_for(r)
    assert [e["kind"] for e in ev] == ["rank"] and ev[0]["change"] == 6 and ev[0]["period"] == "2026-10-07"
    assert ra.events_for(row(rank_change_4w=6, rank_history=hist(*[30, 20, 19, 18, 17, 14, 12]))) == []      # [-6]=20, [-2]=14: +6 last week too, not new
    assert ra.events_for(row(rank_change_4w=4, rank_history=hist(*h))) == []
    fell = ra.events_for(row(rank_change_4w=-7, rank_history=hist(*[10, 10, 10, 10, 10, 10, 17])))
    assert fell and fell[0]["change"] == -7 and "fell 7 places" in ra.message("X", row(), fell[0])[0]


def test_messages_describe_and_never_advise():
    t, b = ra.message("SAMBHV", row(name="Industrial Products", rank=7), {"kind": "corner", "from": "Ahead and gaining", "to": "Ahead but slowing", "period": "x"})
    assert "moved from Ahead and gaining to Ahead but slowing" in t and "rank 7 of 37" in b and "not investment advice" in b
    flat = (t + b + ra.FOOTER).lower()
    for bad in ("buy", "sell", "hold", "avoid", "accumulate", "target", "signal", "recommend"):
        assert bad not in flat.replace("not investment advice", "") or bad == "recommend", bad


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.setenv("SECTOR_OUT_DIR", str(tmp_path / "out"))
    sd.clear_cache()
    root = tmp_path / "out"
    b = sd.building_dir(root, "20261030-1934")
    fakes.make_release(b, rotation=True)
    m = json.loads((b / "rotation" / "_map.json").read_text())
    m["week_closed"] = True
    (b / "rotation" / "_map.json").write_text(json.dumps(m))
    sd.publish(b, root, "20261030-1934")
    yield sd.live_release(root)
    sd.clear_cache()


async def test_alerts_go_to_silver_watchlists_once_per_week_and_follow_the_preferences(app, release):  # noqa: F811
    on = await signed_in(app, "rot1@example.com", plan="silver")
    basic = await signed_in(app, "rot2@example.com", plan="basic")
    off = await signed_in(app, "rot3@example.com", plan="silver")
    await off.put("/api/me/prefs", json={"palette": "gold", "rotationCorner": False})
    lists = {"lists": [{"id": "main", "name": "Main", "symbols": ["SAMBHV"]}], "meta": {}}
    for m in (on, off):
        assert (await m.put("/api/me/watchlist", json=lists)).status_code == 200
    pool = app.state.store.pool
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM auto_alert_sent WHERE kind LIKE 'rotation_%'")
    n = await ra.auto_rotation_alerts(pool, app.state.mailer, "http://test")
    assert n == 1, n
    got = (await on.get("/api/notifications")).json()["notifications"]
    assert len(got) == 1 and "Industrial Products" in got[0]["title"] and got[0]["link"] == "/sectors/rotation" and "not investment advice" in got[0]["body"]
    assert (await basic.get("/api/notifications")).json()["notifications"] == [] and (await off.get("/api/notifications")).json()["notifications"] == []
    assert await ra.auto_rotation_alerts(pool, app.state.mailer, "http://test") == 0           # once per stock, kind and week
    prefs = (await on.get("/api/me/prefs")).json() if (await on.get("/api/me/prefs")).status_code == 200 else {}
    assert prefs.get("rotationRank", False) is False                                            # the rank alert is opt-in
    # a week still in progress sends nothing
    m = json.loads((release / "rotation" / "_map.json").read_text())
    m["week_closed"] = False
    (release / "rotation" / "_map.json").write_text(json.dumps(m))
    sd.clear_cache()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM auto_alert_sent WHERE kind LIKE 'rotation_%'")
    assert await ra.auto_rotation_alerts(pool, app.state.mailer, "http://test") == 0
    await on.aclose(); await basic.aclose(); await off.aclose()
