"""audit-coverage must finish with what it has: a deadline, a per-company limit, and an honest failure when nothing could be checked."""
import asyncio
import time

import pytest

from finlit import worker

GOOD = {"summary": {"dataQuality": {"coverage": {"state": "complete", "mismatches": []}}}}


class FakeClient:
    def __init__(self, delay=0.0, hang=(), bad=()):
        self.delay, self.hang, self.bad, self.calls = delay, set(hang), set(bad), []

    async def fetch_bundle(self, sym, statement):
        self.calls.append(sym)
        if sym in self.hang:
            await asyncio.sleep(30)
        await asyncio.sleep(self.delay)
        return {"errors": {"pl_annual": "503"} if sym in self.bad else {}}


@pytest.fixture(autouse=True)
def plain_build(monkeypatch):
    monkeypatch.setattr(worker.snapshot, "build", lambda bundle: GOOD)


async def test_without_a_deadline_every_company_is_checked():
    out = await worker.audit_coverage(FakeClient(), [f"S{i}" for i in range(10)])
    assert out["checked"] == 10 and out["skipped"] == 0 and not out["errors"] and set(out["all"]) == {f"S{i}" for i in range(10)}


async def test_the_deadline_stops_new_companies_and_keeps_what_was_checked():
    syms = [f"S{i}" for i in range(30)]
    out = await worker.audit_coverage(FakeClient(delay=0.05), syms, deadline=time.monotonic() + 0.12)
    assert 0 < out["checked"] < 30 and out["skipped"] > 0
    assert out["checked"] + out["skipped"] + len(out["errors"]) == 30      # every company is accounted for
    assert len(out["all"]) == out["checked"]                              # what was checked is returned (and so recorded)


async def test_one_company_that_hangs_does_not_hold_the_rest_back():
    t0 = time.monotonic()
    out = await worker.audit_coverage(FakeClient(hang={"S1"}), ["S0", "S1", "S2", "S3"], per_company_s=0.2)
    assert time.monotonic() - t0 < 5
    assert out["checked"] == 3 and [s for s, _ in out["errors"]] == ["S1"] and "no answer" in out["errors"][0][1]


async def test_provider_failures_are_listed_not_counted_as_checked():
    out = await worker.audit_coverage(FakeClient(bad={"S2"}), ["S0", "S1", "S2"])
    assert out["checked"] == 2 and out["errors"] == [("S2", "provider did not answer: pl_annual")]
