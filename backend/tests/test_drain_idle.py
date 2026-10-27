import asyncio

from finlit import worker


class StubRedis:
    def __init__(self):
        self.flag = False

    async def exists(self, key):
        return 1 if self.flag else 0

    async def delete(self, key):
        self.flag = False


class StubStore:
    QUEUE_FLAG = "ingest:queue:pending"

    def __init__(self):
        self.redis, self.claims = StubRedis(), 0

    async def claim(self, limit):
        self.claims += 1
        return []


async def test_idle_drain_loop_does_not_poll_postgres():
    store = StubStore()
    task = asyncio.create_task(worker.drain_queue(None, store, loop=True, idle_seconds=0.01))
    await asyncio.sleep(0.3)
    assert store.claims == 0  # no look at start-up either (a restart must not wake the database): it only watches Redis
    store.redis.flag = True   # a visitor opens a company that is not loaded yet
    await asyncio.sleep(0.1)
    assert store.claims == 1 and store.redis.flag is False
    await asyncio.sleep(0.2)
    assert store.claims == 1
    task.cancel()
