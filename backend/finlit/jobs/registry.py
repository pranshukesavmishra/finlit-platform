"""The declarative list of every background job (docs/JOBS.md, "How to add a job").

One Job per thing the supervisor runs. Nothing here runs anything: due.py decides WHEN from this data, supervisor.py runs it.
Changing a schedule, an SLA or a priority is a one-line edit here plus a test; there is no scheduling logic to touch.

Fields in plain words
  cls            bulk: strictly one (BULK_CONCURRENCY) at a time, niced, first by priority. light: up to LIGHT_CONCURRENCY beside the bulk job.
                 ondemand: its own always-on process kept by deploy/scheduler.sh (visible in the status, never started by the supervisor).
  windows        quiet windows in which the job runs when its last success is at least min_age_h old (not_before: not earlier than that IST time).
  interval_min   also run when the last success is this old (inside active_hours / market hours when those are set).
  daily_at       also run once a day from this IST time (until it has succeeded since).
  day_rule       the job's windows / daily_at / interval apply only on days where this is true (Saturday, weekdays ...); never starves: the SLA still applies.
  sla            the freshness promise. 'hours': a success within N hours. 'active': N hours, counted only from 08:00 IST (results). 'session': a success
                 after the latest trading day's data is final (18:30 IST), and overdue N hours after that. 'none': no promise (visitor-driven jobs).
  probe          a cheap question ("is there anything to do?") asked at most every 5 minutes; the job runs when the answer is yes (unknown = run on the clock).
  prerequisites  jobs that must not be running or due right now (a failing prerequisite never blocks for long: it is held or in backoff).
  resumable      the job continues where it stopped, so reaching max_runtime is a polite yield (retried in 2 minutes), not a failure.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Callable, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class WindowRun:
    window: str
    min_age_h: float
    not_before: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class Sla:
    kind: str = "none"          # none | hours | active | session
    hours: float = 0.0


@dataclass(frozen=True)
class Gate:
    """An environment switch. kind 'equals': enabled only when env[var] == wants (default used when unset). kind 'set': enabled when env[var] is non-empty."""
    var: str
    message: str
    wants: str = "1"
    default: str = "1"
    kind: str = "equals"

    def disabled_reason(self, env: Mapping[str, str]) -> Optional[str]:
        if self.kind == "set":
            return None if env.get(self.var) else self.message
        return None if str(env.get(self.var, self.default)).strip() == self.wants else self.message


@dataclass(frozen=True)
class Job:
    name: str
    args: Tuple[str, ...] = ()
    module: str = "finlit.worker"
    cls: str = "light"
    priority: int = 50
    max_runtime_min: float = 30
    weight_mb: int = 100
    group: Optional[str] = None
    windows: Tuple[WindowRun, ...] = ()
    interval_min: Optional[float] = None
    interval_idle_min: Optional[float] = None       # quotes: the slower rhythm when only member alerts (no visitor) need the prices
    interval_market: bool = False                   # the interval applies only in market hours
    active_hours: Optional[Tuple[int, int]] = None
    daily_at: Optional[Tuple[int, int]] = None
    day_rule: Optional[Callable[[date], bool]] = None
    sla: Sla = field(default_factory=Sla)
    probe: Optional[str] = None
    min_gap_min: float = 30.0                       # probe-driven re-runs: at least this long after the last attempt
    prerequisites: Tuple[str, ...] = ()
    resumable: bool = False
    max_attempts: int = 5
    honours_pause: bool = True
    stall_min: Optional[float] = 25.0               # no output and no heartbeat for this long: the job is hung and is killed
    shards: int = 1
    ok_exit: Tuple[int, ...] = (0,)
    gate: Optional[Gate] = None
    visitor_gate: Optional[str] = None              # visitor | alerts | visitor_or_alerts | env:NAME (only when that env var is 1)
    catchup: bool = True                            # a job that never succeeded is due at once (first start / boot catch-up); False for jobs that send mail or follow visitors
    boot: bool = False                              # a first-start load: BOOT_LOAD_ENABLED=0 stops it from starting just because it never ran
    external: bool = False
    owns: Tuple[str, ...] = ()                      # freshness datasets this job keeps current
    what: str = ""

    @property
    def command(self) -> str:
        return " ".join(self.args)

    @property
    def argv(self) -> List[str]:
        return ["-m", self.module, *self.args]


def _weekdays(d: date) -> bool:
    return d.weekday() < 5


def _saturday(d: date) -> bool:
    return d.weekday() == 5


def _sunday(d: date) -> bool:
    return d.weekday() == 6


def _first_sunday_of_quarter(d: date) -> bool:
    return d.weekday() == 6 and d.day <= 7 and d.month % 3 == 1


@dataclass(frozen=True)
class JobsConfig:
    """Resource and behaviour knobs, all from the environment with safe defaults (docs/JOBS.md, "Resource knobs")."""
    bulk_concurrency: int = 1
    light_cap: int = 2
    tick_s: float = 60.0
    poll_s: float = 5.0
    reserve_mb: int = 100                   # memory left alone for the website beyond a job's own weight
    max_load_per_cpu: float = 3.0           # a new job waits while the 1-minute load average per CPU is above this
    boot_delay_s: float = 240.0
    boot_load_enabled: bool = True
    quotes_every_min: float = 1.0
    web_port: int = 8000
    oom_score_adj: int = 500
    nice: int = 15

    @staticmethod
    def from_env(env: Mapping[str, str]) -> "JobsConfig":
        def num(k, d, cast=float):
            try:
                return cast(env.get(k, d))
            except (TypeError, ValueError):
                return cast(d)
        return JobsConfig(
            bulk_concurrency=max(1, num("BULK_CONCURRENCY", 1, int)), light_cap=max(1, num("LIGHT_CONCURRENCY", 2, int)),
            tick_s=max(5.0, num("JOBS_TICK_S", 60.0)), poll_s=max(1.0, num("JOBS_POLL_S", 5.0)),
            reserve_mb=max(0, num("JOBS_RESERVE_MB", 100, int)), max_load_per_cpu=num("JOBS_MAX_LOAD_PER_CPU", 3.0),
            boot_delay_s=max(0.0, num("BOOT_LOAD_DELAY_S", 240.0)), boot_load_enabled=str(env.get("BOOT_LOAD_ENABLED", "1")) == "1",
            quotes_every_min=max(1.0, num("QUOTES_EVERY_MINUTES", 1.0)), web_port=num("PORT", 8000, int))


FUNDS_GATE = Gate("FUND_LOADS_ENABLED", "ETF and fund loads are switched off: set FUND_LOADS_ENABLED=1 in /opt/finlit/.env.aws and restart", wants="1", default="0")


def build_jobs(env: Optional[Mapping[str, str]] = None) -> List[Job]:
    env = os.environ if env is None else env
    W = WindowRun
    limit = ["--limit", env["INGEST_LIMIT"]] if env.get("INGEST_LIMIT", "0") not in ("", "0") else []
    qe = JobsConfig.from_env(env).quotes_every_min
    ingest_cap = float(env.get("NIGHT_INGEST_MAX_MIN", 90) or 90)
    prism_workers = max(1, int(env.get("PRISM_WORKERS", 2) or 2))
    parallel = str(env.get("INGEST_PARALLEL", 2) or 2)
    night_morning = (W("NIGHT", 18), W("MORNING", 14))
    jobs = [
        # ---------------------------------------------------------------- results and calendars: light, never paused by the admin switch, never starved
        Job("results", ("refresh-results",), priority=1, max_runtime_min=20, weight_mb=60, honours_pause=False, stall_min=15,
            interval_min=25, active_hours=(8, 23), windows=(W("MORNING", 4),), sla=Sla("active", 1.5), visitor_gate="env:RESULTS_NEED_VISITOR",
            owns=("results",), what="rebuild companies that have just declared quarterly results"),
        Job("results-light", ("refresh-results-light",), priority=2, max_runtime_min=30, weight_mb=60, honours_pause=False, stall_min=15,
            interval_min=55, active_hours=(8, 23), windows=(W("MORNING", 4),), sla=Sla("active", 2.0), visitor_gate="env:RESULTS_NEED_VISITOR",
            owns=("results",), what="quarter figures of smaller companies that declared (one provider call each)"),
        Job("calendars", ("refresh-calendars",), priority=3, max_runtime_min=10, weight_mb=60, honours_pause=False, stall_min=10,
            interval_min=40, active_hours=(8, 23), windows=(W("MORNING", 4),), sla=Sla("active", 1.0), visitor_gate="env:RESULTS_NEED_VISITOR",
            owns=("results_calendar", "ipo_calendar"), what="IPO and results calendars (board-meeting dates)"),
        # ---------------------------------------------------------------- prices and alerts
        Job("quotes", ("refresh-quotes",), priority=4, max_runtime_min=10, weight_mb=100, honours_pause=False, stall_min=10,
            interval_min=qe, interval_idle_min=15, interval_market=True, visitor_gate="visitor_or_alerts", owns=("quotes",),
            catchup=False, what="live prices into stored summaries: every minute while a visitor is on the site, every 15 minutes when only member alerts need them"),
        Job("alerts-live", ("check-alerts", "--kind", "live"), priority=5, max_runtime_min=10, weight_mb=80, honours_pause=False, stall_min=10,
            interval_min=15, interval_market=True, visitor_gate="alerts", prerequisites=("quotes",), catchup=False, what="member price alerts during market hours"),
        Job("listing", ("refresh-listing", "--force"), priority=6, max_runtime_min=15, weight_mb=100, honours_pause=False, stall_min=10,
            interval_min=30, interval_market=True, daily_at=(15, 50), windows=(W("AFTER_CLOSE", 2), W("MORNING", 6)),
            sla=Sla("hours", 6), owns=("quotes", "ticker"), what="price, market cap and 52-week range of every listed company (two provider calls); final prices after the close"),
        Job("alerts-flag", ("refresh-alerts",), module="finlit.wake", priority=8, max_runtime_min=3, weight_mb=40, honours_pause=False, stall_min=3,
            windows=(W("MORNING", 4), W("AFTER_CLOSE", 4), W("NIGHT", 4)), what="refreshes the 'any member alert exists' flag"),
        Job("alerts-daily", ("check-alerts", "--kind", "daily"), priority=9, max_runtime_min=10, weight_mb=80, honours_pause=False, stall_min=10,
            daily_at=(19, 10), day_rule=_weekdays, sla=Sla("hours", 80), catchup=False, what="daily member alerts, weekdays after the close"),
        Job("screens", ("check-screens",), priority=9, max_runtime_min=15, weight_mb=80, windows=(W("MORNING", 20),), day_rule=_weekdays,
            sla=Sla("hours", 80), catchup=False, what="emails members when a company newly matches a saved screen"),
        Job("digest", ("send-digest",), priority=9, max_runtime_min=15, weight_mb=80, daily_at=(19, 10), day_rule=_sunday, sla=Sla("hours", 192),
            catchup=False, what="weekly week-ahead email"),
        # ---------------------------------------------------------------- bulk: one at a time, in this order
        Job("prune", ("prune",), cls="bulk", priority=5, max_runtime_min=30, weight_mb=150, windows=(W("NIGHT", 20),), sla=Sla("hours", 30),
            owns=("disk",), what="old prices and logs out of the database (keeps the disk from filling)"),
        Job("technicals", ("refresh-technicals",), cls="bulk", priority=10, max_runtime_min=75, weight_mb=350, resumable=True, probe="technicals",
            windows=(W("AFTER_CLOSE", 0), W("MORNING", 0)), sla=Sla("session", 12), owns=("technicals", "daily_prices"),
            what="technical view of every stored Prism report from fresh Dhan daily candles (resumable, yields to members)"),
        Job("ingest-flagship", ("ingest", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "BHARTIARTL", "HINDUNILVR"), cls="bulk",
            priority=15, max_runtime_min=30, weight_mb=300, windows=(W("NIGHT", 144),), sla=Sla("hours", 400), boot=True, resumable=True,
            what="the ten flagship companies first (first start: visitors see them before the long load)"),
        Job("ingest", ("ingest-all", "--hours", "20", *limit, "--parallel", parallel), cls="bulk", priority=20, max_runtime_min=ingest_cap, weight_mb=450,
            windows=night_morning, sla=Sla("hours", 26), resumable=True, boot=True, owns=("daily_prices",), prerequisites=("ingest-flagship",),
            what="load or reload every company's statements (resumable; one run is capped so other bulk jobs get their turn)"),
        Job("score", ("score-all",), cls="bulk", priority=30, max_runtime_min=90, weight_mb=300, windows=night_morning, sla=Sla("hours", 26), resumable=True,
            boot=True, prerequisites=("ingest",), owns=("scores",), what="FinLit score of every listed company"),
        Job("prism", ("precompute-prism", "--max-minutes", "55", "--limit", "800"), cls="bulk", priority=40, max_runtime_min=60, weight_mb=250 * prism_workers,
            shards=prism_workers, resumable=True, probe="prism", interval_min=10, windows=(W("NIGHT", 20), W("MORNING", 14)), sla=Sla("hours", 26), boot=True, prerequisites=("ingest", "score"),
            gate=Gate("PRISM_PRECOMPUTE_ENABLED", "Prism pre-compute is switched off: PRISM_PRECOMPUTE_ENABLED is not 1"), owns=("prism",),
            what="FinLit Prism rating of every company with a full report (resumable, one company at a time per worker)"),
        Job("leadership", ("refresh-leadership", "--if-stale", "--backfill-from", "2022-10-01"), cls="bulk", priority=45, max_runtime_min=60, weight_mb=250,
            windows=(W("NIGHT", 144),), day_rule=_saturday, sla=Sla("hours", 192), boot=True, owns=("leadership",),
            what="weekly Leader / In line / Laggard labels (Saturday, after Friday's close)"),
        Job("portfolios", ("refresh-portfolios",), cls="bulk", priority=50, max_runtime_min=120, weight_mb=200, group="funds", windows=night_morning,
            sla=Sla("hours", 26), resumable=True, gate=FUNDS_GATE, boot=True, what="fund holdings, sector split and exit loads (resumable)"),
        Job("score-mf", ("score-mf",), cls="bulk", priority=55, max_runtime_min=60, weight_mb=250, group="funds", windows=night_morning,
            sla=Sla("hours", 26), prerequisites=("portfolios",), gate=FUNDS_GATE, boot=True, owns=("fund_scores",), what="Mutual Fund Health Score (after the portfolios)"),
        Job("backfill-mf", ("backfill-mf",), cls="bulk", priority=60, max_runtime_min=120, weight_mb=200, group="funds", windows=night_morning,
            sla=Sla("hours", 192), resumable=True, gate=FUNDS_GATE, boot=True, what="five years of NAV history, one fund house at a time (resumable)"),
        Job("backfill-history", ("backfill-history",), cls="bulk", priority=65, max_runtime_min=120, weight_mb=250, windows=night_morning,
            sla=Sla("hours", 192), resumable=True, boot=True, what="weekly closes back to 2004 for the leadership backtest (resumable)"),
        Job("backtest-leadership", ("backtest-leadership",), cls="bulk", priority=70, max_runtime_min=60, weight_mb=250, windows=(W("NIGHT", 24 * 80),),
            day_rule=_first_sunday_of_quarter, sla=Sla("hours", 24 * 100), catchup=False, what="quarterly: has leadership held in each peer group?"),
        Job("rebuild-metrics", ("rebuild-metrics", "--only-missing"), cls="bulk", priority=71, max_runtime_min=45, weight_mb=250, windows=(W("NIGHT", 144),),
            sla=Sla("hours", 400), boot=True, what="screener filters for companies loaded before they existed (database only)"),
        Job("short-history", ("refresh-short-history",), cls="bulk", priority=72, max_runtime_min=60, weight_mb=250, windows=(W("NIGHT", 144),),
            sla=Sla("hours", 400), resumable=True, boot=True, what="reload stored reports with four years or fewer of statements"),
        # ---------------------------------------------------------------- light jobs of the nightly chain and the evening data
        Job("universe", ("refresh-universe",), priority=12, max_runtime_min=15, weight_mb=150, windows=(W("NIGHT", 144),), day_rule=_sunday,
            sla=Sla("hours", 192), what="the company list (Sundays)"),
        Job("indices", ("refresh-indices",), priority=60, max_runtime_min=15, weight_mb=100, windows=night_morning, sla=Sla("hours", 30), owns=("indices",),
            what="NIFTY index membership"),
        Job("coverage", ("audit-coverage", "--sample", "80", "--record"), priority=62, max_runtime_min=20, weight_mb=100, ok_exit=(0, 1), windows=night_morning,
            sla=Sla("hours", 30), what="compares what the provider sends with what the reports show (exit 1 = mismatches found, recorded)"),
        Job("integrity", ("audit-integrity",), priority=63, max_runtime_min=25, weight_mb=100, ok_exit=(0, 1), windows=night_morning, sla=Sla("hours", 30),
            what="nightly data integrity sample"),
        Job("logos", ("refresh-logos",), priority=80, max_runtime_min=30, weight_mb=100, windows=(W("NIGHT", 20),), sla=Sla("hours", 60), what="company and fund-house logos"),
        Job("macro", ("refresh-macro",), priority=20, max_runtime_min=20, weight_mb=100, windows=(W("AFTER_CLOSE", 18, (19, 10)), W("MORNING", 14)),
            sla=Sla("hours", 30), owns=("macro",), what="India macro data (MoSPI, RBI)"),
        Job("flows-nse", ("refresh-flows", "--only", "nse"), priority=19, max_runtime_min=10, weight_mb=100, windows=(W("AFTER_CLOSE", 1.5, (19, 10)), W("MORNING", 6)),
            sla=Sla("hours", 30), owns=("flows",), what="the exchange's own FII/DII figures for the latest session"),
        Job("flows", ("refresh-flows",), priority=21, max_runtime_min=20, weight_mb=100, windows=(W("AFTER_CLOSE", 1.5, (19, 10)), W("MORNING", 6)),
            sla=Sla("hours", 30), owns=("flows",), what="FII/DII flows (NSDL, NSE archive files)"),
        Job("history-probe", ("history-probe",), priority=85, max_runtime_min=15, weight_mb=100, windows=(W("NIGHT", 144),), sla=Sla("hours", 400),
            what="read-only count of yearly statements per source"),
        Job("dhan-check", ("dhan-check",), priority=85, max_runtime_min=5, weight_mb=60, windows=(W("NIGHT", 144), W("MORNING", 144)), sla=Sla("hours", 400),
            gate=Gate("DHAN_CLIENT_ID", "Dhan is not set up (DHAN_CLIENT_ID empty)", kind="set"), what="proves the Dhan credentials work"),
        Job("canary", ("canary",), priority=7, max_runtime_min=10, weight_mb=100, honours_pause=False, windows=(W("MORNING", 10), W("AFTER_CLOSE", 10, (19, 0))),
            sla=Sla("hours", 30), owns=("canary",), what="re-fetches a few reference companies from the provider and compares them with what we hold"),
        # ---------------------------------------------------------------- funds (one at a time among themselves: group 'funds')
        Job("instruments", ("refresh-instruments",), priority=22, max_runtime_min=15, weight_mb=180, group="funds", windows=(W("MORNING", 20),), sla=Sla("hours", 30),
            gate=FUNDS_GATE, what="Dhan's public instrument file"),
        Job("mf", ("refresh-mf",), priority=23, max_runtime_min=20, weight_mb=180, group="funds",
            windows=(W("AFTER_CLOSE", 20, (21, 10)), W("NIGHT", 1.5), W("MORNING", 6)), sla=Sla("hours", 26), gate=FUNDS_GATE, owns=("mf_nav",),
            what="mutual fund NAVs (AMFI publishes by 11 pm)"),
        Job("facts", ("refresh-facts",), priority=24, max_runtime_min=20, weight_mb=180, group="funds", windows=(W("AFTER_CLOSE", 20, (21, 10)), W("MORNING", 14)),
            sla=Sla("hours", 30), prerequisites=("mf",), gate=FUNDS_GATE, what="fund size, expense ratios, launch dates (AMFI)"),
        Job("industry", ("refresh-industry",), priority=25, max_runtime_min=20, weight_mb=180, group="funds", windows=(W("AFTER_CLOSE", 20, (19, 10)), W("MORNING", 14)),
            sla=Sla("hours", 30), gate=FUNDS_GATE, what="AMFI monthly category report"),
        Job("etf", ("refresh-etf", "--resume"), priority=26, max_runtime_min=30, weight_mb=180, group="funds", day_rule=_weekdays,
            windows=(W("AFTER_CLOSE", 20, (21, 10)), W("NIGHT", 1.5), W("MORNING", 14)), sla=Sla("hours", 80), prerequisites=("instruments",), gate=FUNDS_GATE,
            owns=("etf_prices",), what="ETF prices and metrics, weekdays (a second pass picks up what the first could not reach)"),
        # ---------------------------------------------------------------- always-on processes kept alive by deploy/scheduler.sh (shown, not scheduled)
        Job("drain-queue", ("drain-queue", "--loop"), cls="ondemand", external=True, honours_pause=False, what="builds stocks a visitor opened before they were loaded; its own always-on process, outside every gate"),
        Job("commodities", ("refresh-commodities", "--loop"), cls="ondemand", external=True, honours_pause=False,
            gate=Gate("COMMODITIES_WORKER", "COMMODITIES_WORKER=0", wants="1", default="1"), what="commodity prices into Redis (always-on loop)"),
    ]
    return jobs


def by_name(env: Optional[Mapping[str, str]] = None) -> Dict[str, Job]:
    return {j.name: j for j in build_jobs(env)}


def disabled_reason(job: Job, env: Mapping[str, str]) -> Optional[str]:
    return job.gate.disabled_reason(env) if job.gate else None
