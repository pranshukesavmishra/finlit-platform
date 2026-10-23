import asyncio
import gc

from finlit.background import _running, etag_matches, spawn


def test_if_none_match_follows_rfc_9110():
    tag = '"abc123"'
    assert etag_matches('"abc123"', tag)
    assert etag_matches('W/"abc123"', tag)                    # weak comparison for GET
    assert etag_matches('"zzz", "abc123"', tag)               # a list of cached copies
    assert etag_matches("*", tag)
    assert not etag_matches(None, tag) and not etag_matches("", tag)
    assert not etag_matches('"abc1234"', tag)                 # a longer tag is a different tag
    assert not etag_matches('"xabc123"', tag)
    assert not etag_matches('abc123', tag)                    # unquoted is not the same tag


async def test_spawned_tasks_are_kept_until_done_and_failures_are_logged(caplog):
    done = asyncio.Event()

    async def work():
        await asyncio.sleep(0.01)
        done.set()

    async def boom():
        raise RuntimeError("provider down")

    t = spawn(work())
    spawn(boom())
    gc.collect()                                              # nothing else holds the task: it must still run to the end
    assert t in _running
    await asyncio.wait_for(done.wait(), 1)
    await asyncio.sleep(0.01)
    assert not _running
    assert any("provider down" in r.getMessage() for r in caplog.records)
