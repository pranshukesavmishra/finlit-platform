"""The schedule only matters if it runs. Static checks of the AWS start path and of the scheduler's rules, and a real bash run of its time-slot logic."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SH = (ROOT / "deploy/scheduler.sh").read_text()


def test_the_aws_container_starts_the_scheduler():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY deploy/render-start.sh deploy/scheduler.sh ./" in dockerfile and "mv render-start.sh start.sh" in dockerfile and 'CMD ["./start.sh"]' in dockerfile
    compose = (ROOT / "deploy/aws/docker-compose.aws.yml").read_text()
    app = compose.split("\n  app:\n")[1].split("\n  db:\n")[0]
    assert "command:" not in app and "entrypoint:" not in app                  # nothing replaces the image's start.sh
    start = (ROOT / "deploy/render-start.sh").read_text()
    assert 'nohup bash -c "\\"$HERE/scheduler.sh\\"' in start and "/tmp/scheduler.log" in start
    assert start.index("scheduler.sh") < start.index("exec $PY -m uvicorn")       # launched before the web server takes over the shell
    assert subprocess.run(["bash", "-n", str(ROOT / "deploy/scheduler.sh")]).returncode == 0


def test_the_results_jobs_are_scheduled_hourly_without_a_visitor_and_in_every_late_window():
    for needle in ('due "cal-$H" "$H" 5', 'due "res-$H-a" "$H" 20', 'due "res-$H-b" "$H" 50', 'due "light-$H" "$H" 35'):
        assert needle in SH
    assert "RESULTS_NEED_VISITOR:-0" in SH
    for chain in ("chain_morning", "chain_close", "chain_evening1", "chain_evening2", "chain_late"):
        body = SH.split(f"{chain}() {{")[1].split("\n}\n")[0]
        assert "refresh-results" in body, chain


def test_a_late_loop_round_does_not_lose_the_slot_and_the_scheduler_leaves_a_heartbeat():
    assert "wake heartbeat" in SH.split("while true; do\n  now=")[1].split("read -r M H D")[0]          # every minute, before anything that can stall
    assert "wake ran" in SH.split("run() {")[1].split("# Fund data jobs")[0]
    assert "M == 20" not in SH and "M == 0 )) && window" not in SH               # no exact-minute tests left
    assert "loads_paused &&" not in SH.split("results=0 bulk=0")[0].split("run() {")[-1]  # the admin-switch read (a Python start) is inside the background job, not in the main loop


def test_results_jobs_are_exempt_from_the_bulk_lock_the_memory_gate_and_a_slow_database():
    run = SH.split("run() {")[1].split("# Fund data jobs")[0]
    assert "calendars*|results*) results=1" in run and "technicals|prism) bulk=1" in run
    assert 'need="$RESULTS_MIN_FREE_MB"' in run and "loads_paused_explicit" not in run.split("case \"$name\" in quotes")[1].split("esac")[0]
    assert '[ "$results" = 1 ] || renice' in run                                  # results keep normal priority; bulk jobs yield
    assert 'if [ "$bulk" = 1 ]; then flock -w "$BULK_WAIT_S" 6' in run


def test_the_three_bulk_jobs_and_the_prism_loop_take_turns_on_one_lock_and_run_niced():
    assert SH.count('6>"$BULK_LOCK"') >= 3
    assert 'if [ "$name" = score-mf ]; then flock -w "$BULK_WAIT_S" 6' in SH
    loop = SH.split("prism-precompute loop off")[1].split("# ---------------------------------------------------------------------------------------------------------------- the DB windows")[0]
    assert "flock -n 6" in loop and "nice -n 15" in loop and "flock -u 6" in loop
    assert "nice -n 15 $PY -m finlit.worker" in SH.split("run_funds() {")[1].split("# Waits (up to 10 minutes)")[0] or "MALLOC_ARENA_MAX=2 nice -n 15" in SH


def test_the_drain_loop_is_always_on_outside_every_gate_and_restarts_quickly():
    line = [l for l in SH.splitlines() if "drain-queue --loop" in l][0]
    assert "while true" in line and "sleep 10" in line and "run " not in line.split("drain-queue")[0]
    assert "drain-queue --loop" in line


def _slot_script(body: str, h: int, m: int, start_day="2026-10-30", start_min=0, today="2026-10-31") -> str:
    fn = SH[SH.index("declare -A DONE"):SH.index("last=\"\"\nwhile true")]
    fn = re.sub(r"printf -v START_DAY .*?\n", f'START_DAY="{start_day}"; START_MIN={start_min}; LAST_DAY="{today}"\n', fn, count=1, flags=re.S)
    fn = fn.replace("printf -v today '%(%F)T' -1", f'today="{today}"')
    return f"H={h}; M={m}\n{fn}\n{body}"


def _run(script: str) -> str:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.strip()


def test_a_slot_fires_once_at_its_minute_or_up_to_ten_minutes_late_never_twice_never_early():
    for h, m, expect in [(8, 19, "no"), (8, 20, "yes"), (8, 27, "yes"), (8, 30, "yes"), (8, 31, "no")]:
        assert _run(_slot_script('due res 8 20 && echo yes || echo no', h, m)) == expect, (h, m)
    twice = _slot_script('due res 8 20 && echo a; due res 8 20 && echo b; echo end', 8, 21)
    assert _run(twice).split() == ["a", "end"]                                  # the second look in the same slot does nothing


def test_a_slot_already_behind_when_the_scheduler_started_is_not_made_up_but_tomorrows_is():
    started_after = _slot_script('due night 1 0 && echo yes || echo no', 1, 4, start_day="2026-10-31", start_min=1 * 60 + 3)
    assert _run(started_after) == "no"                                          # restart at 01:03: the boot load handles it
    next_day = _slot_script('due night 1 0 && echo yes || echo no', 1, 0, start_day="2026-10-30", start_min=11 * 60)
    assert _run(next_day) == "yes"                                              # the scheduler started yesterday at 11:00: tonight's 01:00 still fires
