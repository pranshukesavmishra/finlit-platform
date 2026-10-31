"""When is a job due? Every rule of finlit/jobs/due.py and schedule.py under a fake clock (IST, no DST). Nothing here sleeps or touches a database."""
from datetime import date, datetime, timedelta, timezone

import pytest

from finlit.jobs import due, schedule
from finlit.jobs.due import Ctx, JobState, PauseInfo, evaluate, retry_delay_min, sla_status
from finlit.jobs.registry import JobsConfig, build_jobs
from jobs_fakes import ist as at

JOBS = {j.name: j for j in build_jobs({"FUND_LOADS_ENABLED": "1"})}
FRI, SAT, MON = (2026, 10, 30), (2026, 10, 31), (2026, 11, 2)


def ctx(now, **kw):
    kw.setdefault("env", {"FUND_LOADS_ENABLED": "1"})
    return Ctx(now=now, **kw)


def state(name, now, ok_ago_h=None, **kw):
    st = JobState(job=name, first_seen_at=now - timedelta(days=30), **kw)
    if ok_ago_h is not None:
        st.last_success_at = now - timedelta(hours=ok_ago_h)
        st.last_attempt_at = st.last_success_at
    return st


def test_the_calendar_is_what_the_incident_says():
    assert date(2026, 10, 31).weekday() == 5


def test_windows_open_and_close_in_ist_including_the_midnight_wrap():
    cases = [("NIGHT", (23, 29), False), ("NIGHT", (23, 30), True), ("NIGHT", (0, 0), True), ("NIGHT", (3, 29), True), ("NIGHT", (3, 30), False), ("NIGHT", (12, 0), False),
             ("MORNING", (4, 59), False), ("MORNING", (5, 0), True), ("MORNING", (6, 44), True), ("MORNING", (6, 45), False),
             ("AFTER_CLOSE", (18, 29), False), ("AFTER_CLOSE", (18, 30), True), ("AFTER_CLOSE", (21, 29), True), ("AFTER_CLOSE", (21, 30), False)]
    for name, (h, m), expect in cases:
        assert schedule.window_open(name, at(*FRI, h, m)) is expect, (name, h, m)
    assert schedule.open_windows(at(*FRI, 12, 0)) == []


def test_a_night_window_instance_spans_two_calendar_days():
    start, end = schedule.window_instance("NIGHT", at(*SAT, 1, 0))
    assert start == at(*FRI, 23, 30) and end == at(*SAT, 3, 30)
    start, end = schedule.window_instance("NIGHT", at(*FRI, 23, 45))
    assert start == at(*FRI, 23, 30) and end == at(*SAT, 3, 30)
    assert schedule.window_instance("NIGHT", at(*FRI, 12, 0)) is None


def test_utc_input_is_converted_to_ist():
    # 18:00 UTC is 23:30 IST
    assert schedule.window_open("NIGHT", datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc))
    assert not schedule.window_open("NIGHT", datetime(2026, 10, 30, 17, 59, tzinfo=timezone.utc))


def test_expected_session_rule_matches_the_technicals_module():
    from finlit.prism_candles import expected_session
    for now in (at(*FRI, 15, 59), at(*FRI, 16, 0), at(*SAT, 10, 0), at(*MON, 9, 0), at(*MON, 16, 1)):
        assert schedule.expected_session(now) == expected_session(now)


def test_retry_delays_are_30_60_120_and_capped():
    assert [retry_delay_min(n) for n in (1, 2, 3, 4, 9)] == [30, 60, 120, 120, 120]


# ------------------------------------------------------------------------------------------------ SLA
def test_hours_sla_breaches_and_becomes_overdue_at_one_and_a_half_times():
    j = JOBS["ingest"]                                     # 26 h
    now = at(*FRI, 12, 0)
    assert not sla_status(j, state("ingest", now, 25), now).breached
    s = sla_status(j, state("ingest", now, 27), now)
    assert s.breached and not s.overdue and round(s.lateness_hours) == 1
    assert sla_status(j, state("ingest", now, 40), now).overdue                       # 40 h > 1.5 x 26 h
    assert not sla_status(j, state("ingest", now, 38), now).overdue                   # 38 h < 39 h


def test_a_job_that_never_ran_is_measured_from_the_day_it_was_first_seen_not_from_nothing():
    j, now = JOBS["ingest"], at(*FRI, 12, 0)
    st = JobState(job="ingest", first_seen_at=now - timedelta(hours=1))
    assert not sla_status(j, st, now).breached
    st.first_seen_at = now - timedelta(hours=60)
    assert sla_status(j, st, now).overdue


def test_results_sla_counts_only_active_hours_so_the_night_is_never_a_false_alarm():
    j = JOBS["results"]                                    # 1.5 h of active time (08:00 to 23:59 IST)
    last = at(*FRI, 23, 50)
    assert not sla_status(j, state("results", at(*SAT, 3, 0), None, last_success_at=last), at(*SAT, 3, 0)).breached
    assert not sla_status(j, state("results", at(*SAT, 9, 0), None, last_success_at=last), at(*SAT, 9, 0)).breached      # 08:00 + 1h10 spill-over is not reached yet
    s = sla_status(j, state("results", at(*SAT, 9, 45), None, last_success_at=last), at(*SAT, 9, 45))
    assert s.breached                                      # 10 minutes of Friday + 1h25 on Saturday morning = past 1.5 h by 09:45? deadline 09:20
    assert sla_status(j, state("results", at(*SAT, 12, 0), None, last_success_at=at(*SAT, 10, 0)), at(*SAT, 12, 0)).breached
    assert not sla_status(j, state("results", at(*SAT, 11, 0), None, last_success_at=at(*SAT, 10, 0)), at(*SAT, 11, 0)).breached


def test_technicals_sla_is_a_success_after_the_latest_sessions_data_is_final():
    j = JOBS["technicals"]                                 # session SLA: overdue 12 h after 18:30
    fri_ok = at(*FRI, 19, 0)
    # Friday 17:00: the latest final session is Thursday's; a success on Thursday evening is enough
    assert not sla_status(j, state("t", at(*FRI, 17, 0), None, last_success_at=at(2026, 10, 29, 19, 0)), at(*FRI, 17, 0)).breached
    # Saturday 08:00 with only Thursday's success: Friday's bars are 13.5 h overdue -> breached (12 h)
    s = sla_status(j, state("t", at(*SAT, 8, 0), None, last_success_at=at(2026, 10, 29, 19, 0)), at(*SAT, 8, 0))
    assert s.breached and not s.overdue
    assert sla_status(j, state("t", at(*SAT, 8, 0), None, last_success_at=fri_ok), at(*SAT, 8, 0)).breached is False
    # weekend: Friday's success is current all the way to Monday 18:30 + 12 h
    assert not sla_status(j, state("t", at(*MON, 12, 0), None, last_success_at=fri_ok), at(*MON, 12, 0)).breached
    assert sla_status(j, state("t", at(2026, 11, 3, 8, 0), None, last_success_at=fri_ok), at(2026, 11, 3, 8, 0)).breached
    # 19 days stale (the incident) is overdue by a wide margin
    assert sla_status(j, state("t", at(*SAT, 8, 0), None, last_success_at=at(2026, 10, 12, 19, 0)), at(*SAT, 8, 0)).overdue


# ------------------------------------------------------------------------------------------------ due-ness
def test_results_run_every_25_minutes_in_active_hours_and_never_wait_for_a_visitor():
    j, now = JOBS["results"], at(*SAT, 10, 0)
    assert evaluate(j, state("results", now, 0.5), ctx(now)).due                       # 30 min ago
    assert not evaluate(j, state("results", now, 0.2), ctx(now)).due                   # 12 min ago
    night = at(*SAT, 3, 0)
    assert not evaluate(j, state("results", night, 3.2), ctx(night)).due               # 03:00 is outside the active hours and the morning window is closed
    # a visitor is not needed unless RESULTS_NEED_VISITOR=1
    assert evaluate(j, state("results", now, 0.5), ctx(now, visitor_active=False)).due
    v = evaluate(j, state("results", now, 0.5), ctx(now, visitor_active=False, env={"RESULTS_NEED_VISITOR": "1"}))
    assert not v.due
    assert evaluate(j, state("results", now, 0.5), ctx(now, visitor_active=True, env={"RESULTS_NEED_VISITOR": "1"})).due


def test_results_also_run_in_the_morning_window_before_the_active_hours_begin():
    j, now = JOBS["results"], at(*SAT, 5, 30)
    v = evaluate(j, state("results", now, 6), ctx(now))
    assert v.due and "morning" in v.reason


def test_a_window_job_runs_when_its_window_is_open_and_its_last_success_is_old_enough():
    j = JOBS["ingest"]
    night = at(*FRI, 23, 45)
    assert evaluate(j, state("ingest", night, 22), ctx(night)).due
    assert not evaluate(j, state("ingest", night, 5), ctx(night)).due                  # ran earlier tonight
    noon = at(*FRI, 12, 0)
    assert not evaluate(j, state("ingest", noon, 5), ctx(noon)).due


def test_the_morning_window_is_a_catch_up_for_what_the_night_missed():
    j, m = JOBS["score"], at(*SAT, 5, 30)
    assert evaluate(j, state("score", m, 15), ctx(m)).due                              # last night failed: 15 h old
    assert not evaluate(j, state("score", m, 6), ctx(m)).due                           # last night worked
    assert evaluate(j, state("score", m, 15), ctx(m)).reason.startswith("morning window")


def test_outside_a_window_a_breached_sla_runs_on_an_idle_box_and_waits_for_a_quiet_moment_when_visitors_are_on():
    j, noon = JOBS["score"], at(*FRI, 12, 0)
    breached = state("score", noon, 30)                                                # 26 h SLA, 4 h late
    assert evaluate(j, breached, ctx(noon, visitor_active=False)).due
    v = evaluate(j, breached, ctx(noon, visitor_active=True))
    assert v.state == "waiting" and not v.due and "quiet moment" in v.reason           # not starved: it is waiting with a reason, never skipped silently
    assert evaluate(j, state("score", noon, 60), ctx(noon, visitor_active=True)).due   # beyond twice the SLA it runs whatever the visitors do


def test_a_weekly_job_runs_on_its_day_only_but_the_sla_still_catches_a_missed_week():
    j = JOBS["leadership"]
    sat_night = at(*SAT, 1, 0)                                                         # Saturday 01:00, NIGHT window
    assert evaluate(j, state("leadership", sat_night, 7 * 24), ctx(sat_night)).due
    fri_night = at(*FRI, 23, 45)
    assert not evaluate(j, state("leadership", fri_night, 7 * 24 - 2), ctx(fri_night)).due     # still Friday by the IST calendar
    tue = at(2026, 11, 3, 23, 45)
    assert not evaluate(j, state("leadership", tue, 5 * 24), ctx(tue)).due
    assert evaluate(j, state("leadership", tue, 9 * 24), ctx(tue, visitor_active=False)).due   # a missed Saturday: the SLA (8 days) brings it back


def test_daily_time_jobs_run_after_their_time_until_they_have_succeeded_once_that_day():
    j = JOBS["alerts-daily"]                                                           # weekdays from 19:10
    assert not evaluate(j, state("a", at(*FRI, 19, 0), 24), ctx(at(*FRI, 19, 0))).due
    assert evaluate(j, state("a", at(*FRI, 19, 10), 24), ctx(at(*FRI, 19, 10))).due
    assert evaluate(j, state("a", at(*FRI, 22, 0), 26), ctx(at(*FRI, 22, 0))).due      # a late supervisor still runs it (no exact-minute slots)
    assert not evaluate(j, state("a", at(*FRI, 22, 0), 1), ctx(at(*FRI, 22, 0))).due   # already done today
    assert not evaluate(j, state("a", at(*SAT, 19, 30), 24), ctx(at(*SAT, 19, 30))).due   # weekends: no


def test_listing_runs_every_30_minutes_in_market_hours_and_after_the_close():
    j = JOBS["listing"]
    m = at(*FRI, 11, 0)
    assert evaluate(j, state("listing", m, 0.6), ctx(m)).due and not evaluate(j, state("listing", m, 0.3), ctx(m)).due
    assert evaluate(j, state("listing", at(*FRI, 15, 55), None, last_success_at=at(*FRI, 15, 40)), ctx(at(*FRI, 15, 55))).due     # daily 15:50 final prices
    assert not evaluate(j, state("listing", at(*SAT, 11, 0), 0.6), ctx(at(*SAT, 11, 0))).due   # no market on Saturday


def test_quotes_follow_visitors_and_member_alerts_in_market_hours_only():
    j, m = JOBS["quotes"], at(*FRI, 11, 0)
    assert evaluate(j, state("quotes", m, 2 / 60), ctx(m, visitor_active=True)).due                     # every minute with a visitor
    assert not evaluate(j, state("quotes", m, 10 / 60), ctx(m, visitor_active=False, alerts_active=True)).due   # alerts alone: every 15 minutes
    assert evaluate(j, state("quotes", m, 16 / 60), ctx(m, visitor_active=False, alerts_active=True)).due
    assert not evaluate(j, state("quotes", m, 1), ctx(m, visitor_active=False, alerts_active=False)).due
    night = at(*FRI, 22, 0)
    assert not evaluate(j, state("quotes", night, 1), ctx(night, visitor_active=True)).due


def test_never_run_jobs_are_due_at_once_but_not_the_ones_that_send_mail():
    now = at(*SAT, 12, 0)
    fresh = lambda n: JobState(job=n, first_seen_at=now)            # noqa: E731
    assert evaluate(JOBS["ingest-flagship"], fresh("x"), ctx(now)).due                  # first start: the catch-up
    assert evaluate(JOBS["score"], fresh("x"), ctx(now)).reason.startswith("has never succeeded")
    for mail in ("screens", "digest", "alerts-daily", "backtest-leadership"):
        assert not evaluate(JOBS[mail], fresh("x"), ctx(now)).due, mail


def test_boot_load_disabled_stops_the_first_start_catch_up_but_not_the_windows_or_a_far_breach():
    now = at(*SAT, 12, 0)
    off = ctx(now, config=JobsConfig(boot_load_enabled=False))
    fresh = JobState(job="ingest", first_seen_at=now)
    assert not evaluate(JOBS["ingest"], fresh, off).due
    night = at(*FRI, 23, 45)
    assert evaluate(JOBS["ingest"], state("ingest", night, 22), ctx(night, config=JobsConfig(boot_load_enabled=False))).due
    assert not evaluate(JOBS["ingest"], state("ingest", now, 30), off).due              # only slightly late: left to the windows
    assert evaluate(JOBS["ingest"], state("ingest", now, 60), off).due                  # more than twice the SLA: never starve


def test_probe_driven_jobs_run_only_when_the_probe_says_there_is_work():
    j, now = JOBS["technicals"], at(*FRI, 21, 0)
    done = state("technicals", now, 2)                                                 # succeeded after 18:30 this evening
    assert not evaluate(j, done, ctx(now, probes={"technicals": False})).due
    assert not evaluate(j, done, ctx(now, probes={"technicals": None})).due
    v = evaluate(j, state("technicals", now, 2), ctx(now, probes={"technicals": True}))
    assert v.due and "work waiting" in v.reason
    recent = state("technicals", now, 0.2, last_attempt_at=now - timedelta(minutes=10))
    assert not evaluate(j, recent, ctx(now, probes={"technicals": True})).due          # at least 30 minutes between probe-driven re-runs


def test_technicals_run_in_the_after_close_and_morning_windows_until_the_session_is_processed():
    j = JOBS["technicals"]
    evening = at(*FRI, 18, 45)
    assert evaluate(j, state("technicals", evening, 24), ctx(evening)).due
    assert not evaluate(j, state("technicals", evening, 0.1), ctx(evening)).due
    morning = at(*SAT, 5, 30)
    assert evaluate(j, state("technicals", morning, 24), ctx(morning)).due             # the evening run was lost: the morning catches up
    assert not evaluate(j, state("technicals", morning, 10), ctx(morning)).due         # Friday's evening run did succeed (10 h ago = 19:30)


def test_a_data_freshness_force_runs_the_job_now_outside_every_window_and_visitor_rule():
    j, noon = JOBS["technicals"], at(*FRI, 12, 0)
    st = state("technicals", noon, 1, forced_at=noon, last_attempt_at=noon - timedelta(hours=1))
    v = evaluate(j, st, ctx(noon, visitor_active=True))
    assert v.due and "stale" in v.reason
    st.last_attempt_at = noon + timedelta(seconds=1)                                  # it has been tried since: not forced again
    assert not evaluate(j, st, ctx(noon, visitor_active=True)).due


def test_retry_timing_a_failed_job_is_not_due_before_its_retry_time_and_ignores_windows_after_it():
    j, now = JOBS["score"], at(*SAT, 1, 0)
    st = state("score", now, 30, retry_at=now + timedelta(minutes=20), consecutive_failures=1, last_status="failed")
    v = evaluate(j, st, ctx(now))
    assert not v.due and v.state == "waiting" and "retry at" in v.reason                # inside the night window but still in backoff
    later = now + timedelta(minutes=31)
    v = evaluate(j, st, ctx(later))
    assert v.due and v.reason.startswith("retrying after failed")
    noon = at(*SAT, 12, 0)
    st2 = state("score", noon, 5, retry_at=noon - timedelta(minutes=1), consecutive_failures=2, last_status="killed")
    assert evaluate(j, st2, ctx(noon, visitor_active=True)).due                        # retried at midday: not only in a window, not held back by visitors


def test_a_job_failed_five_times_is_held_in_the_status_but_is_still_retried():
    j, now = JOBS["score"], at(*SAT, 12, 0)
    st = state("score", now, 5, retry_at=now + timedelta(minutes=90), consecutive_failures=5, last_status="failed")
    v = evaluate(j, st, ctx(now))
    assert v.state == "held" and not v.due
    st.retry_at = now - timedelta(minutes=1)
    assert evaluate(j, st, ctx(now)).due


def test_the_admin_pause_holds_the_bulk_jobs_only_and_names_the_expiry():
    now = at(*FRI, 23, 45)
    p = PauseInfo(until=now + timedelta(minutes=20), by="boss@example.com")
    v = evaluate(JOBS["ingest"], state("ingest", now, 22), ctx(now, pause=p))
    assert v.state == "waiting" and not v.due and "paused by the admin until" in v.reason and "resumes automatically" in v.reason
    assert evaluate(JOBS["results"], state("results", now, 1), ctx(now, pause=p)).due                  # results ignore the pause
    assert evaluate(JOBS["calendars"], state("calendars", now, 1), ctx(now, pause=p)).due
    after = now + timedelta(minutes=21)
    assert evaluate(JOBS["ingest"], state("ingest", after, 22), ctx(after, pause=None)).due           # expired = resumed, no manual action


def test_disabled_by_config_is_not_overdue_and_says_why():
    now = at(*FRI, 12, 0)
    v = evaluate(JOBS["mf"], state("mf", now, 300), Ctx(now=now, env={"FUND_LOADS_ENABLED": "0"}))
    assert v.state == "disabled" and "FUND_LOADS_ENABLED=1" in v.reason and not v.due
    assert evaluate(JOBS["prism"], state("prism", now, 300), Ctx(now=now, env={"PRISM_PRECOMPUTE_ENABLED": "0"})).state == "disabled"
    assert evaluate(JOBS["dhan-check"], state("d", now, 500), Ctx(now=now, env={})).state == "disabled"


def test_next_due_is_the_earliest_of_interval_window_daily_and_sla():
    now = at(*FRI, 12, 0)
    nxt = due.next_due_at(JOBS["ingest"], state("ingest", now, 5), ctx(now))
    assert nxt == at(*FRI, 23, 30) + timedelta(0) or nxt >= at(*FRI, 23, 30)
    r = due.next_due_at(JOBS["results"], state("results", now, 0.1), ctx(now))
    assert r == now - timedelta(hours=0.1) + timedelta(minutes=25)
