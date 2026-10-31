"""Data-freshness invariants: is the NEWEST DATA in each dataset as new as the IST clock, the trading calendar and the declaration calendar say it must be?

A job can 'succeed' and still leave stale data (a provider that answers with yesterday's figures, a run that updated nothing). So this module does not look
at jobs at all: it reads the newest data date of every dataset, compares it with what is expected NOW, and says fresh | late | stale per dataset, with the
job that owns it. The supervisor runs it every 10 minutes, forces the owning job to run when a dataset is stale, and alerts if it stays stale after two runs.

Holidays: the expected session comes from the same rule as prism_technical.expected_session (latest weekday whose session is complete: today from 16:00 IST).
Exchange holidays are not guessed: when the technicals job has found the newest session (its Redis target, set only on a day it ran) and that session is
older than the weekday rule says, the older date is what is expected.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from .resources import disk_percent
from .schedule import IST, expected_session, fmt_ist, ist, is_weekday, market_open, session_ready_at

log = logging.getLogger("finlit.jobs.freshness")
REFERENCE = ("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN")     # the large companies that trade every session: the Nifty 50 proxy for "did the market print a bar"
DISK_ALERT_PCT = 85.0


@dataclass
class Dataset:
    key: str
    label: str
    jobs: List[str]
    status: str = "fresh"          # fresh | late | stale | unknown
    expected: Optional[str] = None
    actual: Optional[str] = None
    lag: Optional[float] = None
    lagUnit: Optional[str] = None
    detail: str = ""


def _d(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, datetime):
        return ist(x if x.tzinfo else x.replace(tzinfo=timezone.utc)).date()
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


def _lag_days(a: Optional[date], e: Optional[date]) -> Optional[int]:
    return (e - a).days if a and e else None


def effective_expected(now: datetime, found_target: Optional[date]) -> date:
    exp = expected_session(now)
    return min(exp, found_target) if found_target else exp


def _prev_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while not is_weekday(d):
        d -= timedelta(days=1)
    return d


def judge_session(key: str, label: str, jobs: List[str], actual: Any, expected: date, now: datetime, grace_h: float, stale_h: float, detail: str = "") -> Dataset:
    """A dataset that gets one new bar per trading session. The bar for `expected` is due `grace_h` hours after that session's data is final (18:30 IST);
    from then it is late, and stale `stale_h` hours after it was due. Before it is due, the previous session's bar is what must be there."""
    a = _d(actual)
    ds = Dataset(key, label, jobs, expected=expected.isoformat(), actual=a.isoformat() if a else None, detail=detail)
    if a is None:
        ds.status, ds.detail = "unknown", detail or "no data found"
        return ds
    if a >= expected:
        ds.lag, ds.lagUnit = 0, "sessions"
        return ds
    over = (now - (session_ready_at(expected) + timedelta(hours=grace_h))).total_seconds() / 3600
    if over < 0:      # today's bar is not due yet: the previous session's must be here
        return judge_session(key, label, jobs, actual, _prev_weekday(expected), now, grace_h, stale_h, detail)
    ds.lag, ds.lagUnit = (expected - a).days, "days"
    ds.status = "late" if over < stale_h else "stale"
    return ds


def judge_age(key: str, label: str, jobs: List[str], newest: Optional[datetime], now: datetime, fresh_h: float, stale_h: float, detail: str = "") -> Dataset:
    """A dataset refreshed on a clock: fresh while its newest row is younger than fresh_h hours, stale beyond stale_h."""
    ds = Dataset(key, label, jobs, expected=f"newer than {fresh_h:g} h", detail=detail)
    if newest is None:
        ds.status, ds.detail = "unknown", detail or "no data found"
        return ds
    n = newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
    age = (now - n).total_seconds() / 3600
    ds.actual, ds.lag, ds.lagUnit = fmt_ist(n), round(age, 1), "hours"
    ds.status = "fresh" if age <= fresh_h else "late" if age <= stale_h else "stale"
    return ds


def judge_quotes(newest: Optional[datetime], now: datetime, found_target: Optional[date], exp: date) -> Dataset:
    """Stock quotes: during market hours the newest quote must be minutes old; outside them the newest quote must be the last close's."""
    jobs = ["listing", "quotes"]
    if newest is None:
        return Dataset("quotes", "Stock quotes", jobs, status="unknown", detail="no quotes held")
    n = newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
    age_min = (now - n).total_seconds() / 60
    if market_open(now):
        ds = Dataset("quotes", "Stock quotes", jobs, expected="within 60 minutes (market open)", actual=fmt_ist(n), lag=round(age_min), lagUnit="minutes")
        ds.status = "fresh" if age_min <= 60 else "late" if age_min <= 180 else "stale"
        return ds
    # outside market hours: the newest quote must have been taken at or after the close of the expected session
    close = datetime.combine(exp, time(15, 30), IST)
    ds = Dataset("quotes", "Stock quotes", jobs, expected=f"taken after the {exp.isoformat()} close", actual=fmt_ist(n), lag=round(age_min), lagUnit="minutes")
    if n >= close:
        return ds
    over = (now - (session_ready_at(exp) + timedelta(hours=0))).total_seconds() / 3600
    if over < 0:       # the close is final from 18:30; until then the previous close's quote is what must be there
        prev_close = datetime.combine(_prev_weekday(exp), time(15, 30), IST)
        ds.status = "fresh" if n >= prev_close else "late"
        return ds
    ds.status = "late" if over < 14 else "stale"
    ds.detail = "the newest quote was taken before the close"
    return ds


def judge_technicals(total: int, behind: int, newest_bar: Any, expected: date, now: datetime) -> Dataset:
    """Technical views: the share of Prism reports whose bar date is older than the expected session."""
    a = _d(newest_bar)
    ds = Dataset("technicals", "Technical views", ["technicals"], expected=expected.isoformat(), actual=a.isoformat() if a else None)
    if total <= 0:
        ds.status, ds.detail = "unknown", "no Prism reports yet"
        return ds
    share = behind / total
    ds.lag, ds.lagUnit = behind, "reports"
    ds.detail = f"{behind} of {total} reports ({share:.0%}) are behind the expected session"
    if share <= 0.02:
        return ds
    over = (now - (session_ready_at(expected) + timedelta(hours=1))).total_seconds() / 3600
    if over < 0:
        return ds           # the new session's bars are not due yet
    ds.status = "stale" if (share > 0.25 and over >= 10) else "late"
    return ds


def judge_results(waiting: List[date], today: date, declared: int) -> Dataset:
    """Results: companies whose declaration date has passed but still have no figures. Target: figures within 6 h of the declaration, flagged at 24 h.
    The declaration is known by DATE only, so: declared two or more days ago and still waiting = certainly over 24 h = stale; yesterday = late; today = counted."""
    ds = Dataset("results", "Quarterly results", ["results", "results-light"], expected="figures within 6 hours of the declaration")
    old = [d for d in waiting if (today - d).days >= 2]
    yest = [d for d in waiting if (today - d).days == 1]
    ds.actual = f"{len(waiting)} of {declared} declared companies waiting for figures"
    ds.lag, ds.lagUnit = (today - min(waiting)).days if waiting else 0, "days"
    ds.detail = f"{len(old)} waiting since 2+ days, {len(yest)} since yesterday, {len(waiting) - len(old) - len(yest)} today; oldest declaration {min(waiting).isoformat() if waiting else 'none'}"
    ds.status = "stale" if old else "late" if yest else "fresh"
    return ds


def judge_calendar(upcoming: int, ran_at: Optional[datetime], now: datetime) -> Dataset:
    ds = judge_age("results_calendar", "Results calendar", ["calendars"], ran_at, now, 3.0, 12.0)
    ds.detail = f"{upcoming} upcoming results dates held"
    if upcoming == 0 and ds.status == "fresh":
        ds.status, ds.detail = "late", "no upcoming results dates are held at all"
    return ds


def judge_nav(newest_nav: Any, now: datetime) -> Dataset:
    """Mutual fund NAV: AMFI publishes by about 11 pm IST. Expected NAV date = the last business day that has passed 23:30 (so yesterday's, until tonight)."""
    ist_now = ist(now)
    d = ist_now.date() if ist_now.time() >= time(23, 30) else ist_now.date() - timedelta(days=1)
    while not is_weekday(d):
        d -= timedelta(days=1)
    a = _d(newest_nav)
    ds = Dataset("mf_nav", "Mutual fund NAV", ["mf"], expected=d.isoformat(), actual=a.isoformat() if a else None)
    if a is None:
        ds.status, ds.detail = "unknown", "no NAV held"
        return ds
    lag = 0
    t = d
    while t > a and lag < 30:
        t -= timedelta(days=1)
        if is_weekday(t):
            lag += 1
    ds.lag, ds.lagUnit = lag, "business days"
    ds.status = "fresh" if a >= d else "late" if lag <= 1 else "stale"     # one business day behind can be an AMFI holiday
    return ds


def judge_weekly(key: str, label: str, jobs: List[str], newest: Any, today: date, fresh_days: int, stale_days: int) -> Dataset:
    a = _d(newest)
    ds = Dataset(key, label, jobs, expected=f"within {fresh_days} days", actual=a.isoformat() if a else None)
    if a is None:
        ds.status, ds.detail = "unknown", "no data held"
        return ds
    ds.lag, ds.lagUnit = (today - a).days, "days"
    ds.status = "fresh" if ds.lag <= fresh_days else "late" if ds.lag <= stale_days else "stale"
    return ds


def judge_index(newest_t: Optional[float], now: datetime, visitors: bool) -> Dataset:
    ds = Dataset("index_levels", "Index levels", [], expected="fetched on demand while a visitor is looking")
    if newest_t is None:
        ds.status, ds.detail = "unknown", "no index level cached"
        return ds
    age = now.timestamp() - newest_t
    ds.actual, ds.lag, ds.lagUnit = fmt_ist(datetime.fromtimestamp(newest_t, timezone.utc)), round(age / 60), "minutes"
    if market_open(now) and visitors:
        ds.status = "fresh" if age <= 600 else "late" if age <= 1800 else "stale"
        ds.expected = "within 10 minutes while the market is open and someone is looking"
    return ds


def judge_system(disk_pct: Optional[float], db_mb: Optional[float]) -> Dict[str, Any]:
    return {"diskPercent": disk_pct, "diskAlertAt": DISK_ALERT_PCT, "diskOk": disk_pct is None or disk_pct < DISK_ALERT_PCT, "databaseMb": db_mb}


def assemble(datasets: List[Dataset], system: Dict[str, Any], credentials: List[Dict[str, str]], now: datetime) -> Dict[str, Any]:
    stale = [d.key for d in datasets if d.status == "stale"]
    late = [d.key for d in datasets if d.status == "late"]
    return {"checkedAt": now.isoformat(timespec="seconds"), "dataFresh": not stale, "stale": stale, "late": late,
            "datasets": [asdict(d) for d in datasets], "system": system, "credentials": credentials}


# ------------------------------------------------------------------------------------------------ reading the facts
async def _one(conn: Any, sql: str, *args: Any) -> Any:
    try:
        return await conn.fetchval(sql, *args)
    except Exception as exc:
        log.warning("freshness fact failed (%s): %s", type(exc).__name__, sql[:60])
        return None


async def gather(store: Any, now: datetime) -> Dict[str, Any]:
    today = ist(now).date()
    f: Dict[str, Any] = {}
    async with store.pool.acquire() as conn:
        f["listing_newest"] = await _one(conn, "SELECT max(updated_at) FROM listing_quotes")
        f["price_ref"] = await _one(conn, "SELECT max(day) FROM price_daily WHERE symbol = ANY($1)", list(REFERENCE))
        f["scores_newest"] = await _one(conn, "SELECT max(updated_at) FROM scores")
        f["prism_newest"] = await _one(conn, "SELECT max(generated_at) FROM prism_reports")
        f["calendars_ran"] = None
        raw = await _one(conn, "SELECT value FROM mf_meta WHERE key = 'run:refresh-calendars'")
        if raw:
            v = json.loads(raw) if isinstance(raw, str) else raw
            try:
                f["calendars_ran"] = datetime.fromisoformat(v["at"])
            except Exception:   # nosec B110
                pass
        f["results_upcoming"] = int(await _one(conn, "SELECT count(*) FROM feed_items WHERE kind = 'result' AND item_date >= $1", today) or 0)
        f["ipo_updated"] = await _one(conn, "SELECT max(updated_at) FROM ipos")
        f["flows_newest"] = await _one(conn, "SELECT max(d) FROM flows_daily")
        f["mf_nav"] = await _one(conn, "SELECT max(nav_date) FROM mf_schemes WHERE active")
        f["mf_score_run"] = await _one(conn, "SELECT max(run_date) FROM mf_scores")
        f["etf_price"] = await _one(conn, "SELECT max(price_date) FROM etf_funds WHERE active")
        f["news_newest"] = await _one(conn, "SELECT max(item_date) FROM feed_items WHERE kind = 'news'")
        f["leadership"] = await _one(conn, "SELECT max(as_of) FROM leadership")
        f["db_mb"] = await _one(conn, "SELECT pg_database_size(current_database()) / 1048576.0")
        f["tech_total"] = int(await _one(conn, "SELECT count(DISTINCT symbol) FROM prism_reports") or 0)
    from ..prism_technical import current_target
    expected = expected_session(now)
    target = await current_target(store.redis, now)
    f["tech_target"] = target
    async with store.pool.acquire() as conn:
        f["tech_behind"] = int(await _one(conn, "SELECT count(*) FROM (SELECT symbol, min(COALESCE(card->>'technicalBarDate', report #>> '{technicalAssessment,asOf}')) AS bar "
                                                "FROM prism_reports GROUP BY symbol) t WHERE bar IS NULL OR bar < $1", target.isoformat()) or 0)
        f["tech_newest_bar"] = await _one(conn, "SELECT max(COALESCE(card->>'technicalBarDate', report #>> '{technicalAssessment,asOf}')) FROM prism_reports")
    f["expected"] = expected
    try:
        raw = await store.redis.get("prism:tech:target")
        got = json.loads(raw) if raw else None
        f["found_target"] = date.fromisoformat(got["target"]) if got and got.get("expected") == expected.isoformat() else None
    except Exception:
        f["found_target"] = None
    try:
        from .. import indices
        raw = await store.redis.get(indices.DHAN_KEY)
        f["index_t"] = json.loads(raw)["t"] if raw else None
    except Exception:
        f["index_t"] = None
    try:
        from .. import wake
        f["visitors"] = await wake.visitor_active(store.redis)
    except Exception:
        f["visitors"] = False
    try:
        from ..results_light import recent_declarations, states
        from .. import results
        recent = await recent_declarations(store, today, 6, force=False)
        st = await states(store, recent)
        f["results_declared"] = len(st)
        f["results_waiting"] = sorted(recent[s][1] for s, v in st.items() if v["source"] in ("provider", "ours"))
    except Exception as exc:
        log.warning("results freshness fact failed: %s", type(exc).__name__)
        f["results_declared"], f["results_waiting"] = 0, None
    return f


def evaluate_facts(f: Dict[str, Any], now: datetime, credentials: Optional[List[Dict[str, str]]] = None, disk: Optional[float] = None) -> Dict[str, Any]:
    today = ist(now).date()
    exp = effective_expected(now, f.get("found_target"))
    ds: List[Dataset] = []
    ds.append(judge_quotes(f.get("listing_newest"), now, f.get("found_target"), exp))
    ds.append(judge_session("daily_prices", "Daily price history", ["technicals", "ingest"], f.get("price_ref"), exp, now, 1.0, 14.0, "newest bar of the large reference companies"))
    ds.append(judge_index(f.get("index_t"), now, bool(f.get("visitors"))))
    ds.append(judge_technicals(int(f.get("tech_total") or 0), int(f.get("tech_behind") or 0), f.get("tech_newest_bar"), exp, now))
    ds.append(judge_age("prism", "Prism ratings", ["prism"], f.get("prism_newest"), now, 30.0, 60.0))
    ds.append(judge_age("scores", "FinLit scores", ["score"], f.get("scores_newest"), now, 30.0, 60.0))
    if f.get("results_waiting") is not None:
        ds.append(judge_results(f["results_waiting"], today, int(f.get("results_declared") or 0)))
    ds.append(judge_calendar(int(f.get("results_upcoming") or 0), f.get("calendars_ran"), now))
    ipo = judge_age("ipo_calendar", "IPO calendar", ["calendars"], f.get("ipo_updated"), now, 30.0, 96.0)
    ds.append(ipo)
    flows = judge_session("flows", "FII / DII flows", ["flows", "flows-nse"], f.get("flows_newest"), exp, now, 3.0, 16.0)
    ds.append(flows)
    ds.append(judge_nav(f.get("mf_nav"), now))
    ds.append(judge_age("fund_scores", "Fund scores", ["score-mf"], datetime.combine(_d(f["mf_score_run"]), time(12, 0), IST) if f.get("mf_score_run") else None, now, 40.0, 80.0))
    ds.append(judge_session("etf_prices", "ETF prices", ["etf"], f.get("etf_price"), exp, now, 3.0, 16.0))
    ds.append(judge_weekly("news", "News and filings", ["calendars"], f.get("news_newest"), today, 3, 6))
    ds.append(judge_weekly("leadership", "Leadership labels", ["leadership"], f.get("leadership"), today, 9, 14))
    ticker = judge_quotes(f.get("listing_newest"), now, f.get("found_target"), exp)
    ticker.key, ticker.label = "ticker", "Ticker quotes"
    ds.append(ticker)
    sysd = judge_system(disk if disk is not None else disk_percent(), f.get("db_mb"))
    return assemble(ds, sysd, credentials or [], now)


async def check(store: Any, signals: Any, now: datetime) -> Dict[str, Any]:
    f = await gather(store, now)
    creds = []
    try:
        for k, v in (await signals.credential_refused()).items():
            creds.append({"provider": k, "detail": v})
    except Exception:   # nosec B110
        pass
    return evaluate_facts(f, now, creds)
