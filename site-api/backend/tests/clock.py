"""A frozen clock for tests whose fixtures are built around a fixed date. Production code reads the real clock (it must); a test that feeds it sample prices
ending on 23 Oct 2026 and then runs on 4 Nov sees them as "too old" and fails for no reason of its own (the CI failures of 3 Nov 2026). Such a test freezes the
clock instead: `monkeypatch.setattr(module, "datetime", frozen_datetime(NOW))` for every module whose `datetime.now()` the code under test calls."""
from datetime import datetime


def frozen_datetime(now: datetime):
    """A datetime class whose now() is `now` (a timezone-aware moment); everything else behaves as datetime."""
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz is not None else now.replace(tzinfo=None)
    return FrozenDatetime
