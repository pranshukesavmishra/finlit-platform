"""Time rules of the job supervisor: the quiet windows, the market hours and the data-ready times, all in IST (no daylight saving, so no DST edge cases).

Everything takes `now` as an argument and returns plain values: the supervisor's clock (real or a test's fake) is the only source of time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class Window:
    name: str
    start: time
    end: time          # end <= start means the window runs past midnight (NIGHT)

    @property
    def wraps(self) -> bool:
        return self.end <= self.start


WINDOWS: Dict[str, Window] = {
    "MORNING": Window("MORNING", time(5, 0), time(6, 45)),          # fewest visitors; full catch-up chain before the open
    "AFTER_CLOSE": Window("AFTER_CLOSE", time(18, 30), time(21, 30)),   # the day's candles are final; NSE/NSDL/MoSPI/RBI have posted
    "NIGHT": Window("NIGHT", time(23, 30), time(3, 30)),            # the heavy loads
}
READY_AFTER_CLOSE = time(18, 30)   # a trading day's data counts as final from here (the exchange closes 15:30; the reports' own rule is 16:00)


def ist(now: datetime) -> datetime:
    return now.astimezone(IST)


def window_open(name: str, now: datetime) -> bool:
    w, t = WINDOWS[name], ist(now).time()
    return (t >= w.start or t < w.end) if w.wraps else (w.start <= t < w.end)


def open_windows(now: datetime) -> List[str]:
    return [n for n in WINDOWS if window_open(n, now)]


def window_instance(name: str, now: datetime) -> Optional[Tuple[datetime, datetime]]:
    """(start, end) of the instance of the window that is open at `now`, or None."""
    if not window_open(name, now):
        return None
    w, i = WINDOWS[name], ist(now)
    start_day = i.date() - timedelta(days=1) if (w.wraps and i.time() < w.end) else i.date()
    start = datetime.combine(start_day, w.start, IST)
    end = datetime.combine(start_day + timedelta(days=1) if w.wraps else start_day, w.end, IST)
    return start, end


def next_window_start(name: str, after: datetime) -> datetime:
    w, i = WINDOWS[name], ist(after)
    cand = datetime.combine(i.date(), w.start, IST)
    if cand <= i:
        cand += timedelta(days=1)
    return cand


def is_weekday(d: date) -> bool:
    return d.weekday() < 5


def market_open(now: datetime) -> bool:
    """Weekday 09:15 to 15:30 IST (holidays are not guessed: a holiday only means quotes do not move)."""
    i = ist(now)
    return is_weekday(i.date()) and time(9, 15) <= i.time() < time(15, 30)


def market_hours(now: datetime) -> bool:
    """The span in which price jobs run: a little wider than the session (09:00 to 15:45 IST on weekdays)."""
    i = ist(now)
    return is_weekday(i.date()) and time(9, 0) <= i.time() < time(15, 45)


def in_active_hours(now: datetime, span: Optional[Tuple[int, int]]) -> bool:
    """span = (first hour, last hour) inclusive, IST; None = always."""
    if span is None:
        return True
    return span[0] <= ist(now).hour <= span[1]


def next_active_start(after: datetime, span: Tuple[int, int]) -> datetime:
    i = ist(after)
    cand = datetime.combine(i.date(), time(span[0], 0), IST)
    return cand if cand >= i else cand + timedelta(days=1)


def expected_session(now: datetime) -> date:
    """The latest weekday whose session should be complete: today only from 16:00 IST (same rule as prism_candles.expected_session)."""
    i = ist(now)
    day = i.date() if (i.hour, i.minute) >= (16, 0) else i.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def session_ready_at(day: date) -> datetime:
    return datetime.combine(day, READY_AFTER_CLOSE, IST)


def latest_ready(now: datetime) -> Tuple[date, datetime]:
    """The newest trading weekday whose data is final by `now` (18:30 IST of that day), with that moment."""
    d = ist(now).date()
    for _ in range(10):
        if is_weekday(d) and session_ready_at(d) <= now:
            return d, session_ready_at(d)
        d -= timedelta(days=1)
    return d, session_ready_at(d)


def next_ready(after_day: date) -> datetime:
    d = after_day + timedelta(days=1)
    while not is_weekday(d):
        d += timedelta(days=1)
    return session_ready_at(d)


def fmt_ist(t: Optional[datetime]) -> Optional[str]:
    return ist(t).strftime("%d %b %H:%M IST") if t else None


def utc(t: datetime) -> datetime:
    return t.astimezone(timezone.utc)
