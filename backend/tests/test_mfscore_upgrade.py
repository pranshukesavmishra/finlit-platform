"""Mutual Fund Health Score upgrades: weekly history rows (idempotent, same transaction), 'what changed' wording, score alerts, the screener query (filters,
sorting, pagination, CSV), the leaderboard, the compare history, the admin health and calibration views, the prune and the migration. Every Gold-only route is
checked for Basic, Silver and a visitor (locked, no value, no fund) and for Gold."""

import json
import re
from datetime import date, timedelta

import pytest

from finlit.mfscore import job, scorehist, upgrade_api
from finlit.mfscore.engine import label_of, score_universe
from finlit.mfscore.admin import quintile_table, ret_after
from test_auth import app, make_admin, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401
from mfscore_synth import universe

pytestmark = pytest.mark.integration
RUN = date(2026, 10, 23)          # a Friday
CAT = "Equity Scheme - Large Cap Fund"
BASE = 300000


def build(n=12, run_date=RUN):
    funds = universe(n, groups=["EQ-LARGE"])
    for i, f in enumerate(funds):
        f.code, f.key, f.category, f.name = BASE + i, f"mf:{BASE + i}", CAT, f"Test Large Cap Fund {i} {f.plan}"
    return funds, score_universe(funds, run_date)


async def clean(conn):
    for t in ("mf_score_alerts", "mf_score_history", "mf_scores"):
        await conn.execute(f"DELETE FROM {t}")
    await conn.execute("DELETE FROM mf_schemes WHERE code >= $1", BASE)


async def seed(app, n=12, weeks=0):
    """Schemes, current scores and `weeks` earlier weekly rows (scores shifted a little each week)."""
    funds, scores = build(n)
    by = {f.key: f for f in funds}
    async with app.state.store.pool.acquire() as conn:
        await clean(conn)
        await conn.executemany("INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, family, ter, aum_lakh, r1y, r3y, r5y) VALUES ($1,$2,'Test AMC','Open Ended',$3,$4,'Growth',$5,$6,$7,$8,$9,$10) "
                               "ON CONFLICT (code) DO NOTHING", [(f.code, f.name, CAT, f.plan, f.name, f.ter, f.aum_lakh, f.r1y, f.r3y, f.r5y) for f in funds])
        rows = [job.row(s, by[s.key], RUN) for s in scores]
        await conn.executemany(job.UPSERT, rows)
        for k in range(weeks, -1, -1):
            rd = RUN - timedelta(days=7 * k)
            hist = []
            for r in rows:
                h = list(scorehist.history_row(r, rd))
                if h[9] is not None:
                    h[9] = round(h[9] - 1.5 * k, 1)            # final
                    h[14] = label_of(h[9])
                hist.append(tuple(h))
            await conn.executemany(scorehist.HISTORY_INSERT, hist)
    return funds, scores


async def clients(app):
    return {"gold": await signed_in(app, "g@example.com", plan="gold"), "silver": await signed_in(app, "s@example.com", plan="silver"),
            "basic": await signed_in(app, "b@example.com", plan="basic"), "visitor": new_client(app)}


def no_values(text):
    d = json.loads(text)
    assert d["locked"] is True
    assert not d.get("items") and not d.get("points") and not d.get("series")
    assert not re.search(r"\"(final|rank)\": [0-9]", text)


# ------------------------------------------------------------------------------------------------------------------------ pure parts
def test_week_of_and_history_row_shape():
    assert scorehist.week_of(date(2026, 10, 23)) == date(2026, 10, 19) and scorehist.week_of(date(2026, 10, 25)) == date(2026, 10, 19)
    funds, scores = build(9)
    r = job.row(scores[0], funds[0], RUN)
    h = scorehist.history_row(r, RUN)
    assert h[0] == r[0] and h[1] == date(2026, 10, 19) and h[2] == RUN and len(h) == 19


def rowd(d, final, perf=50, risk=50, cost=50, quality=50, label=None, rank=5, of=20):
    return {"run_date": d, "week": scorehist.week_of(d), "final": final, "perf": perf, "risk": risk, "cost": cost, "quality": quality, "label": label or label_of(final),
            "status": "RATED", "rank": rank, "rank_of": of, "percentile": 50.0}


def test_change_sentence_uses_stored_rows_and_neutral_words():
    assert scorehist.changed_since([]) is None
    assert scorehist.changed_since([rowd(RUN, 60)]) is None
    assert scorehist.changed_since([rowd(RUN - timedelta(days=7), 60), rowd(RUN, 62)]) is None      # a week apart: too near for a month sentence
    c = scorehist.changed_since([rowd(RUN - timedelta(days=28), 68, perf=70, rank=4), rowd(RUN - timedelta(days=14), 65), rowd(RUN, 61, perf=60, risk=49, rank=9)])
    assert c["delta"] == -7.0 and c["from"] == 68 and c["to"] == 61 and c["pillar"]["key"] == "performance" and c["pillar"]["delta"] == -10.0
    assert c["rankFrom"] == 4 and c["rankTo"] == 9
    assert "moved down 7 points" in c["text"] and "Performance moved most (-10.0)" in c["text"] and "Healthy to Average" in c["text"] and "4 to 9 of 20" in c["text"]
    flat = scorehist.changed_since([rowd(RUN - timedelta(days=28), 61), rowd(RUN, 61)])
    assert "unchanged" in flat["text"]
    for w in ("buy", "sell", "hold", "recommend", "best", "winner", "avoid", "top pick"):
        assert not re.search(rf"\b{w}\b", c["text"] + flat["text"], re.I)


def test_alert_rules_and_message():
    a, b = rowd(RUN, 68), rowd(RUN, 61)
    assert scorehist.alert_hit("band", None, a, b) and not scorehist.alert_hit("band", None, a, rowd(RUN, 70))
    assert scorehist.alert_hit("move", 5, a, b) and not scorehist.alert_hit("move", 8, a, b)
    assert not scorehist.alert_hit("band", None, a, rowd(RUN, None))
    title, body = scorehist.alert_text("Test Fund", a, b)
    assert body.startswith("The FinLit Mutual Fund Health Score of Test Fund moved from Healthy (68) to Average (61).") and "not investment advice" in body


def test_quintiles_and_returns_are_descriptive():
    pairs = [(float(i), float(i) * 0.5) for i in range(100)]
    t = quintile_table(pairs)
    assert [q["funds"] for q in t] == [20] * 5 and t[0]["avgReturnRank"] > t[4]["avgReturnRank"]     # a higher score went with a higher later return in this made-up sample
    assert quintile_table(pairs[:10]) == []
    days = [date(2024, m, 28) for m in range(1, 13)] + [date(2025, m, 28) for m in range(1, 13)]
    navs = [100 + i for i in range(24)]
    assert ret_after(days, navs, date(2024, 1, 1), 12) == pytest.approx((112 / 100 - 1) * 100) and ret_after(days, navs, date(2025, 6, 1), 12) is None


def test_csv_guards_formulas_and_carries_the_footer():
    assert upgrade_api.safe_cell("=1+1") == "'=1+1" and upgrade_api.safe_cell("Axis") == "Axis" and upgrade_api.safe_cell(5) == 5
    item = {"name": "=BAD", "amc": "A", "plan": "Direct", "categoryLabel": "Large Cap", "final": 71.2, "label": "Healthy", "status": "RATED", "pillars": {"performance": 70, "risk": 65, "cost": None, "quality": 80},
            "rank": 2, "rankOf": 40, "aumCr": 1200.5, "ageYears": 8.1, "ter": 0.7, "r1y": 12.0, "r3y": 15.0, "r5y": None}
    out = upgrade_api.csv_text([item], "2026-10-23").splitlines()
    assert out[0].split(",")[:6] == ["Fund", "Fund house", "Plan", "Category", "Score", "Label"] and out[1].startswith("'=BAD,A,Direct,Large Cap,71.2,Healthy")
    assert "not investment advice" in out[-1]


# ------------------------------------------------------------------------------------------------------------------------ database
async def test_migration_tables_and_indexes(app):
    async with app.state.store.pool.acquire() as conn:
        idx = {r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename IN ('mf_score_history', 'mf_score_alerts')")}
    assert {"mf_score_history_pkey", "mf_score_history_week_idx", "mf_score_history_code_idx", "mf_score_history_symbol_idx", "mf_score_alerts_key_idx", "mf_score_alerts_user_idx"} <= idx


async def test_history_is_one_row_per_scheme_per_week_and_idempotent(app):
    funds, scores = build()
    by = {f.key: f for f in funds}
    async with app.state.store.pool.acquire() as conn:
        await clean(conn)
        for rd in (RUN, RUN, RUN - timedelta(days=2), RUN + timedelta(days=7)):    # the same run twice, an earlier day of the week, the next week
            rows = [job.row(s, by[s.key], rd) for s in scores]
            async with conn.transaction():
                await conn.executemany(job.UPSERT, rows)
                await conn.executemany(scorehist.HISTORY_INSERT, [scorehist.history_row(r, rd) for r in rows])
        n = await conn.fetchval("SELECT count(*) FROM mf_score_history")
        weeks = await conn.fetch("SELECT DISTINCT week FROM mf_score_history ORDER BY week")
        dates = {r["run_date"] for r in await conn.fetch("SELECT run_date FROM mf_score_history WHERE week = $1", date(2026, 10, 19))}
    assert n == 2 * len(funds) and [w["week"] for w in weeks] == [date(2026, 10, 19), date(2026, 10, 26)]
    assert dates == {RUN - timedelta(days=2)}            # the last run written for the week stays (a re-run replaces, never adds)


async def test_job_writes_history_in_the_same_transaction_and_fires_alerts(app, monkeypatch):
    funds, _ = build()
    for f in funds:
        async def _l(conn, limit=None, _f=funds):
            return _f, {}
        monkeypatch.setattr(job, "load_mf", _l)
        break

    async def _e(conn, limit=None):
        return []
    monkeypatch.setattr(job, "load_etf", _e)
    gold = await signed_in(app, "alerts@example.com", plan="gold")
    await seed(app, weeks=1)                                       # last week's rows exist: this week's run compares with them
    async with app.state.store.pool.acquire() as conn:
        code = funds[0].code
        uid = await conn.fetchval("SELECT id FROM users WHERE lower(email) = 'alerts@example.com'")
        await conn.execute("DELETE FROM mf_score_history WHERE week = $1", date(2026, 10, 19))
        await conn.execute("UPDATE mf_score_history SET final = 40, label = 'Weak' WHERE key = $1", f"mf:{code}")      # last week's stored row differs
    r = await gold.post("/api/mf/score-alerts", json={"code": code, "kind": "band", "channels": ["app", "email"]})
    assert r.status_code == 201 and r.json()["kind"] == "band"
    sent = []

    class M:
        async def send(self, to, subject, body):
            sent.append((to, subject, body))
    out = await job.run(app.state.store, None, run_date=RUN, mailer=M())
    assert out["status"] == "ok" and out["alertsFired"] == 1
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_score_history WHERE week = $1", date(2026, 10, 19)) == len(funds)
        note = await conn.fetchrow("SELECT * FROM notifications WHERE user_id = $1", uid)
    assert note and note["body"].startswith("The FinLit Mutual Fund Health Score of Test Large Cap Fund 0 Direct moved from Weak (40) to ") and sent and "not investment advice" in sent[0][2]
    again = await job.run(app.state.store, None, run_date=RUN, mailer=M())      # the same run again: no second message, same rows
    assert again["alertsFired"] == 0
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM notifications WHERE user_id = $1", uid) == 1
        assert await conn.fetchval("SELECT count(*) FROM mf_score_history WHERE week = $1", date(2026, 10, 19)) == len(funds)


async def test_prune_keeps_three_years(app):
    await seed(app)
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("INSERT INTO mf_score_history (key, week, run_date, kind, code, plan, grp, sub, status) VALUES ('mf:1', $1, $1, 'mf', 1, 'Direct', 'EQ-LARGE', 'large-cap', 'RATED')", date(2022, 1, 3))
        n = await scorehist.prune(conn, today=RUN)
        left = await conn.fetchval("SELECT count(*) FROM mf_score_history WHERE key = 'mf:1'")
    assert n == 1 and left == 0


# ------------------------------------------------------------------------------------------------------------------------ gating
async def test_every_gold_route_is_locked_below_gold(app):
    funds, _ = await seed(app, weeks=5)
    c = await clients(app)
    code = funds[0].code
    paths = [f"/api/mf/{code}/score/history", "/api/mf/etf/NIFTYBEES/score/history", "/api/mf/score-screener", "/api/mf/score-screener/facets",
             "/api/mf/leaderboard?sub=large-cap&plan=Direct", f"/api/mf/scores/history?codes={code}"]
    for who in ("basic", "silver", "visitor"):
        for p in paths:
            r = await c[who].get(p)
            assert r.status_code == 200, (who, p, r.text)
            no_values(r.text)
            assert r.headers["cache-control"] == "private, no-store"
        assert (await c[who].get("/api/mf/score-screener?format=csv")).headers["content-type"].startswith("application/json")   # the locked answer, never a file
    for who in ("basic", "silver"):
        assert (await c[who].post("/api/mf/score-alerts", json={"code": code, "kind": "band"})).status_code == 403
        assert (await c[who].get("/api/mf/score-alerts")).status_code == 403
    assert (await c["visitor"].get("/api/mf/score-alerts")).status_code in (401, 403)
    for cl in c.values():
        await cl.aclose()


async def test_history_endpoint_for_gold(app):
    funds, _ = await seed(app, weeks=5)
    gold = await signed_in(app, "g@example.com", plan="gold")
    d = (await gold.get(f"/api/mf/{funds[0].code}/score/history")).json()
    assert d["locked"] is False and d["count"] == 6 and d["points"][0]["date"] < d["points"][-1]["date"] and set(d["points"][0]["pillars"]) == {"performance", "risk", "cost", "quality"}
    assert d["changes"]["delta"] > 0 and "moved up" in d["changes"]["text"] and d["note"] is None
    assert (await gold.get("/api/mf/999999/score/history")).status_code == 404
    short = (await gold.get(f"/api/mf/{funds[1].code}/score/history")).json()
    assert short["count"] == 6
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_score_history WHERE key = $1 AND week < $2", f"mf:{funds[1].code}", date(2026, 10, 19))
    one = (await gold.get(f"/api/mf/{funds[1].code}/score/history")).json()
    assert one["count"] == 1 and one["changes"] is None and one["note"].startswith("Not enough history yet: the score is stored weekly from 23 Oct 2026")
    many = (await gold.get(f"/api/mf/scores/history?codes={funds[0].code},{funds[2].code}")).json()
    assert len(many["series"][f"mf:{funds[0].code}"]) == 6


async def test_score_payload_gains_the_breakdown_texts_and_category_median(app):
    funds, _ = await seed(app)
    gold = await signed_in(app, "g@example.com", plan="gold")
    d = (await gold.get(f"/api/mf/{funds[0].code}/score")).json()
    assert d["categoryMedian"]["n"] >= 12 and set(d["categoryMedian"]) >= {"performance", "risk", "cost", "quality", "final", "plan"}
    assert all("whyText" in m for m in d["metrics"]) and d["months"] and d["peers"]["n"]
    basic = await signed_in(app, "b@example.com", plan="basic")
    t = (await basic.get(f"/api/mf/{funds[0].code}/score")).text
    assert "categoryMedian" not in t and json.loads(t)["final"] is None


async def test_screener_filters_sort_pages_and_csv(app):
    funds, scores = await seed(app, n=20)
    gold = await signed_in(app, "g@example.com", plan="gold")
    g = lambda q: gold.get("/api/mf/score-screener?" + q)  # noqa: E731
    d = (await g("")).json()
    assert d["locked"] is False and d["total"] == 20 and all(i["plan"] == "Direct" for i in d["items"]) and d["items"][0]["final"] >= d["items"][-1]["final"]
    assert set(d["items"][0]) >= {"name", "final", "label", "pillars", "categoryLabel", "aumCr", "ageYears", "ter", "r1y", "r3y", "r5y", "plan", "rank", "rankOf"}
    assert (await g("plan=all")).json()["total"] == 40 and (await g("plan=Regular")).json()["total"] == 20
    page1, page2 = (await g("limit=8")).json(), (await g("limit=8&offset=8")).json()
    assert len(page1["items"]) == 8 and not {i["key"] for i in page1["items"]} & {i["key"] for i in page2["items"]}
    asc = (await g("sort=final&dir=asc&limit=200")).json()["items"]
    assert [i["final"] for i in asc] == sorted(i["final"] for i in asc)
    mid = sorted(i["final"] for i in asc)[10]
    f = (await g(f"min={mid}&limit=200")).json()
    assert f["total"] == sum(1 for i in asc if i["final"] >= mid) and all(i["final"] >= mid for i in f["items"])
    f = (await g(f"cost_min=0&risk_max=100&perf_min={asc[5]['pillars']['performance']}")).json()
    assert all(i["pillars"]["performance"] >= asc[5]["pillars"]["performance"] for i in f["items"])
    lab = asc[-1]["label"]
    assert all(i["label"] == lab for i in (await g(f"labels={lab}&limit=200")).json()["items"])
    assert (await g("sub=no-such-category")).json()["total"] == 0
    assert (await g("status=PROVISIONAL")).json()["total"] + (await g("status=RATED")).json()["total"] == 20
    assert (await g("ter_max=0.01")).json()["total"] == 0 and (await g("aum_min=1&aum_max=100000000")).json()["total"] == 20 and (await g("age_min=1&age_max=30")).json()["total"] == 20
    assert (await g("full=1")).json()["total"] <= 20
    assert (await g("q=Large%20Cap%20Fund%203")).json()["total"] >= 1
    for bad in ("sort=nope", "plan=X", "min=abc", "min=101", "limit=0", "offset=-1", "labels=Best", "group=XX", "dir=up"):
        assert (await g(bad)).status_code == 400, bad
    # missing values sort last either way
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE mf_schemes SET ter = NULL WHERE code = $1", funds[0].code)
    for dr in ("asc", "desc"):
        items = (await g(f"sort=ter&dir={dr}&limit=200")).json()["items"]
        assert items[-1]["ter"] is None
    csv_r = await g("format=csv&plan=all")
    assert csv_r.headers["content-type"].startswith("text/csv") and "attachment" in csv_r.headers["content-disposition"] and csv_r.headers["cache-control"] == "private, no-store"
    lines = csv_r.text.splitlines()
    assert lines[0].startswith("Fund,Fund house,Plan,Category,Score,Label,Status,Performance,Risk,Cost,Quality") and len(lines) == 1 + 40 + 2
    fx = (await gold.get("/api/mf/score-screener/facets")).json()
    assert fx["categories"][0]["sub"] == "large-cap" and fx["categories"][0]["n"]["Direct"] == 20


async def test_leaderboard_stats_and_neutral_wording(app):
    await seed(app, n=15)
    gold = await signed_in(app, "g@example.com", plan="gold")
    d = (await gold.get("/api/mf/leaderboard?sub=large-cap&plan=Direct")).json()
    finals = [i["final"] for i in d["items"]]
    assert finals == sorted(finals, reverse=True) and d["stats"]["n"] == 15 and d["stats"]["min"] <= d["stats"]["p25"] <= d["stats"]["median"] <= d["stats"]["p75"] <= d["stats"]["max"]
    assert d["categoryLabel"] and d["nearIdentical"] is False and set(d["stats"]) >= {"performance", "risk", "cost", "quality"}
    assert (await gold.get("/api/mf/leaderboard?sub=large-cap&plan=Nope")).status_code == 422
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE mf_scores SET flags = ARRAY['NEAR_IDENTICAL'] WHERE sub = 'large-cap'")
    for k in await app.state.store.redis.keys("mfs:up:*"):      # the ten-minute cache of the Gold answer
        await app.state.store.redis.delete(k)
    d = (await gold.get("/api/mf/leaderboard?sub=large-cap&plan=Direct")).json()
    assert d["nearIdentical"] and "near-identical" in d["nearIdenticalText"]
    assert not re.search(r"\b(best|winner|top pick|buy|sell|avoid|recommend)", json.dumps({k: v for k, v in d.items() if k != "disclaimer"}), re.I)


async def test_score_alert_crud_limits_and_duplicates(app):
    funds, _ = await seed(app, weeks=1)
    gold = await signed_in(app, "g@example.com", plan="gold")
    c = funds[0].code
    r = await gold.post("/api/mf/score-alerts", json={"code": c, "kind": "move", "points": 5, "channels": ["app", "email", "browser"]})
    assert r.status_code == 201 and r.json()["channels"] == ["app", "email", "browser"] and r.json()["points"] == 5
    assert (await gold.post("/api/mf/score-alerts", json={"code": c, "kind": "move", "points": 5})).status_code == 409
    assert (await gold.post("/api/mf/score-alerts", json={"code": c, "kind": "move"})).status_code == 422
    assert (await gold.post("/api/mf/score-alerts", json={"kind": "band"})).status_code == 422
    assert (await gold.post("/api/mf/score-alerts", json={"code": 5, "kind": "band"})).status_code == 404
    assert (await gold.post("/api/mf/score-alerts", json={"code": c, "kind": "band", "channels": ["sms"]})).status_code == 422
    listed = (await gold.get("/api/mf/score-alerts")).json()["alerts"]
    assert len(listed) == 1 and listed[0]["name"].startswith("Test Large Cap Fund 0")
    other = await signed_in(app, "o@example.com", plan="gold")
    assert (await other.delete(f"/api/mf/score-alerts/{listed[0]['id']}")).status_code == 404       # someone else's alert
    assert (await gold.delete(f"/api/mf/score-alerts/{listed[0]['id']}")).status_code == 200
    assert (await gold.get("/api/mf/score-alerts")).json()["alerts"] == []


async def test_admin_views_are_admin_only(app):
    await seed(app, n=15, weeks=2)
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE mf_scores SET status = 'NOT RATED', final = NULL, label = NULL, reason = 'Under 12 months of NAV history' WHERE key = (SELECT key FROM mf_scores ORDER BY key LIMIT 1)")
        from finlit.mf import _set_meta
        await _set_meta(conn, "run:score-mf", {"status": "ok", "runDate": "2026-10-23", "universe": 30, "written": 30, "seconds": 2.1, "zeroRules": {"ter_zero": 3, "aum_zero": 1, "top10_zero": 2, "equity_zero": 0}})
    gold = await signed_in(app, "g@example.com", plan="gold")
    for p in ("/api/admin/mf-score/health", "/api/admin/mf-score/calibration"):
        assert (await gold.get(p)).status_code == 403, p
    assert (await new_client(app).get("/api/admin/mf-score/health")).status_code in (401, 403)
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    import time
    from finlit.auth import crypto
    assert (await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    h = (await admin.get("/api/admin/mf-score/health")).json()
    assert h["total"] == 30 and h["status"]["NOT RATED"] == 1 and h["lastRun"]["status"] == "ok" and h["zeroCounters"]["ter_zero"] == 3
    assert h["notRated"][0]["reason"] == "Under 12 months of NAV history" and sum(h["distribution"]["byGroup"]["EQ-LARGE"]) == 29 and len(h["distribution"]["bins"]) == 10
    assert h["history"]["rows"] == 30 * 3 and h["peerSizes"]["buckets"][0] == "0 to 7" and isinstance(h["topMissing"], list)
    cal = (await admin.get("/api/admin/mf-score/calibration?months_ago=12")).json()
    assert cal["internal"] is True and "not a forecast" in cal["label"] and cal["funds"] == 0 and cal["quintiles"] == [] and "too short" in cal["note"]
