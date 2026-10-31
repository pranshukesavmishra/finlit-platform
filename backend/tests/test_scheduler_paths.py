"""The schedule only matters if it runs. Static checks of the AWS start path: start.sh launches scheduler.sh, which keeps the job supervisor, the on-demand
lane and the commodity loop alive. (All timing rules are tested with a fake clock in test_jobs_*.py.)"""
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
    for f in ("deploy/scheduler.sh", "deploy/render-start.sh"):
        assert subprocess.run(["bash", "-n", str(ROOT / f)]).returncode == 0


def test_the_scheduler_only_keeps_the_supervisor_the_on_demand_lane_and_the_commodity_loop_alive():
    assert "finlit.worker supervise" in SH and "PIPESTATUS[0]" in SH                      # the supervisor, restarted by the loop around it
    assert "delay * 2 > 300 ? 300" in SH and '"$rc" = 3' in SH                            # growing delay capped at 5 minutes; 3 = lock held by another copy
    line = [l for l in SH.splitlines() if "drain-queue --loop" in l and "while true" in l][0]
    assert "sleep 10" in line and "supervise" not in line and "loads_paused" not in line   # the on-demand lane: always on, outside every gate
    assert "refresh-commodities --loop" in SH
    code = "\n".join(l for l in SH.splitlines() if not l.lstrip().startswith("#"))
    for gone in ("due()", "run()", "run_funds", "fund_step", "flock", "loads_paused", "chain_night", "declare -A DONE", "wake heartbeat"):
        assert gone not in code, gone                              # the bash scheduling logic is gone (only mentioned in the comment)


def test_the_supervisor_is_started_by_hand_with_one_flag():
    from finlit.worker import main  # noqa: F401 - the command exists
    import inspect
    from finlit import worker
    src = inspect.getsource(worker)
    assert '"supervise"' in src and "--once" in src and "--dry-run" in src


def test_swap_is_created_only_when_missing_and_jobs_are_the_first_oom_victims():
    boot = (ROOT / "deploy/aws/bootstrap.sh").read_text()
    assert "swapon --show=NAME --noheadings | grep -q ." in boot and "swap already active" in boot            # idempotent: nothing done if swap exists
    assert "vm.swappiness=10" in boot and "SWAP_GB" in boot
    compose = (ROOT / "deploy/aws/docker-compose.aws.yml").read_text()
    assert compose.count("oom_score_adj: -300") == 3 and "mem_limit: 1200m" in compose                         # db, redis, caddy protected; app limit unchanged
    runner = (ROOT / "backend/finlit/jobs/runner.py").read_text()
    assert "/proc/self/oom_score_adj" in runner and "oom_adj: int = 500" in runner and "start_new_session=True" in runner
