import asyncio

from finlit import worker


class FakeRedis:
    def __init__(self): self.d = {}
    async def incr(self, k): self.d[k] = self.d.get(k, 0) + 1; return self.d[k]
    async def expire(self, k, s): return True
    async def exists(self, k): return 1 if self.d.get(k) else 0


class FakeStore:
    READER_FLAG = "flag"
    def __init__(self): self.redis, self.queued = FakeRedis(), []
    async def enqueue(self, sym, st): self.queued.append((sym, st))


def test_dropped_report_is_requeued_twice_then_left(monkeypatch):
    async def nosleep(_): return None
    monkeypatch.setattr(worker.asyncio, "sleep", nosleep)
    store = FakeStore()
    res = [{"symbol": "AAA", "status": "failed", "errors": {"error": "provider did not answer for pl_annual"}},
           {"symbol": "BBB", "status": "failed", "errors": {"error": "no statements or prices for symbol"}},
           {"symbol": "CCC", "status": "rejected", "errors": {}}]
    for _ in range(3):
        asyncio.run(worker._retry_dropped(store, res))
    assert store.queued == [("AAA", "consolidated"), ("AAA", "consolidated")]   # BBB (not at the provider) and CCC (rejected) never retried; AAA only twice


def test_bulk_loader_waits_for_a_reader_but_not_forever(monkeypatch):
    slept = []
    async def fake_sleep(s): slept.append(s)
    monkeypatch.setattr(worker.asyncio, "sleep", fake_sleep)
    store = FakeStore(); store.redis.d["flag"] = 1
    asyncio.run(worker._step_aside(store, patience=6.0))
    assert len(slept) == 3                                      # waited, then gave up at the cap
    store.redis.d["flag"] = 0; slept.clear()
    asyncio.run(worker._step_aside(store, patience=6.0))
    assert slept == []                                          # nobody waiting: no delay
