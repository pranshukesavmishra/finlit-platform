# Memory rules and the 503 after a deploy (KNOWN-ISSUES h)

The free Render plan gives ONE container 512 MB for everything: the web server, the site backend (Prism, about 90 MB), the scheduler and every job.
Going over the limit kills the container; Render shows 503 until the new instance answers (about a minute, longer while it migrates).

Rules every change must keep:

1. One heavy job at a time. Data loads share `/tmp/finlit-heavy.lock`; every light job has its own lock; a job still running when its next slot arrives is skipped, not stacked (`deploy/scheduler.sh`, `run`).
2. A job starts only with enough free memory: `SCHED_MIN_FREE_MB` (default 120), fund jobs `SCHED_FUNDS_MIN_FREE_MB` (180; the largest measured job peaks at 174 MB).
3. No job reads a whole table or all report bodies into memory. Page, stream, or sample (the integrity audit takes 40 companies a night, one at a time).
4. `MALLOC_ARENA_MAX=2` for every Python process; one uvicorn worker; caches are bounded (`STOCK_FUNDAMENTALS_CACHE_ENTRIES`).
5. The admin switch "Heavy data loads" (Console > System) pauses all loads, which also pause the integrity audit. Use it before a risky deploy or when memory is short.
6. Boot-time loads wait until the web server answers (`wait_web`), so a deploy never starts loading while it is still starting.
7. Never deploy during market hours (09:00-15:45 IST) unless it is a fix; check `scripts/smoke.sh` afterwards.

If the site shows 503: wait 2 minutes; check the Render log for "Out of memory" or "SIGKILL"; pause the loads switch from the admin Console (or set `BOOT_LOAD_ENABLED=0`); restart once; run `scripts/smoke.sh https://finlit-arug.onrender.com`.
The keep-alive workflow (`.github/workflows/keepalive.yml`) stops the free instance from sleeping; `smoke.yml` catches a broken deploy within 6 hours.
