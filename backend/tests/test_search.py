

def test_a_score_row_written_on_saturday_is_labelled_with_fridays_close():
    from datetime import datetime, timezone, timedelta
    from finlit.search import session_of
    ist = timezone(timedelta(hours=5, minutes=30))
    assert session_of(datetime(2026, 10, 24, 2, 13, tzinfo=ist)).isoformat() == "2026-10-23"     # Saturday 02:13
    assert session_of(datetime(2026, 10, 23, 10, 0, tzinfo=ist)).isoformat() == "2026-10-22"     # Friday before the close
    assert session_of(datetime(2026, 10, 23, 16, 0, tzinfo=ist)).isoformat() == "2026-10-23"     # Friday after the close
    assert session_of(datetime(2026, 10, 26, 9, 0, tzinfo=ist)).isoformat() == "2026-10-23"      # Monday morning


def test_the_symbols_filter_keeps_only_the_asked_for_rows():
    from finlit.search import MAX_SYMBOLS, _only, wanted_symbols
    assert wanted_symbols(None) is None                                   # no parameter: the whole list
    assert wanted_symbols("") == set()                                    # an empty value is no company, not every company
    assert wanted_symbols(" wheels, SSWL ,,wheels") == {"WHEELS", "SSWL"}
    assert len(wanted_symbols(",".join(f"S{i}" for i in range(500)))) == MAX_SYMBOLS
    doc = {"fields": ["symbol"], "rows": [["WHEELS", 1], ["TCS", 2], ["SSWL", 3]], "amcLogos": {"a": "b"}, "level": "basic"}
    out = _only(doc, {"WHEELS", "SSWL", "NOPE"})
    assert [r[0] for r in out["rows"]] == ["WHEELS", "SSWL"] and out["amcLogos"] == {"a": "b"} and out["level"] == "basic"


async def test_quotes_endpoint_serves_only_the_symbols_asked_for():
    import json
    import os
    import httpx
    import pytest
    from finlit.api import create_app
    from finlit.config import Settings
    from finlit.store import Store
    s = Settings(finedge_api_key="t", finedge_mode="fixtures", database_url=os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test"),
                 redis_url=os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15"))
    try:
        st = await Store.connect(s)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    from finlit.store import dumps, etag_for
    body = dumps({"fields": ["symbol", "price"], "rows": [["WHEELS", 2322.6], ["TCS", 3000.0], ["SSWL", 519.75]], "amcLogos": {}, "level": "basic", "builtAt": 1})
    await st.redis.hset("search-quotes:basic", mapping={"body": body, "gzip": __import__("gzip").compress(body), "etag": etag_for(body).encode()})
    app = create_app(s, store=st)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
                every = await api.get("/api/search/quotes")
                some = await api.get("/api/search/quotes?symbols=wheels,SSWL", headers={"Accept-Encoding": "identity"})
                none = await api.get("/api/search/quotes?symbols=", headers={"Accept-Encoding": "identity"})
                assert len(json.loads(every.content)["rows"]) == 3
                assert [r[0] for r in some.json()["rows"]] == ["WHEELS", "SSWL"] and some.headers["etag"] != every.headers["etag"]
                assert none.json()["rows"] == []
    finally:
        await st.redis.delete("search-quotes:basic")
        await st.close()
