# FinLit Prism: how coverage grows (Advanced score screener)

The Advanced score screener (`/advanced-score-screener`, Gold only) lists every listed company with the FinLit Prism rating, its four parts and its two technical views. (The FinLit score has its own page, the Basic score screener at `/score-screener`, Silver.)
A Prism rating takes about 30 seconds and about 25 FinEdge calls, and the provider calls are rate limited and shared, so the rating cannot be
calculated for 5,800 companies at once. Coverage grows in steps, and the page always says how far it has got ("Prism has rated X of Y companies").

## What the page shows

* One query (`Store.prism_cards`) reads the newest stored rating per company (consolidated if there is one, else standalone): the columns
  `final`, `label`, `status`, `generated_at` and the small `card` jsonb (migration `070_prism_card.sql`: the four category scores and the short and
  long term technical readings). The big `report` json is never read for the list. `card` is written in `prism._save` and was filled once for the
  reports that already existed.
* The list is built once and kept in Redis for 3 minutes, one copy per access level (`universe:basic|silver|gold`).
* A company with no stored rating shows "Not rated yet" with the reason and a **Rate now** link to `/prism/<SYMBOL>`, which starts the calculation
  in the background when it opens (docs/prism/CONTRACT.md). A company the model could not rate shows "Not rated" and says its data is not enough.
* Counts for "rated X of Y" come from `prism_coverage` (`{rated, provisional, not_rated, stored, total, per_night}`); they name no company and are
  shown to every plan.

## Plan gating (enforced on the server)

| Plan | FinLit score | Prism |
| --- | --- | --- |
| Basic / visitor | locked (null) | locked (null) |
| Silver | yes | locked (null) |
| Gold, administrator | yes | yes |

`redact_universe` (auth/entitlements.py) sets every `MODEL_FIELDS` / `PRISM_FIELDS` value to null for a plan that does not include it, before the
list is cached, and the Gold list is never served from a lower plan's cache key. Below Gold the Prism query only reads the showcase companies
(`settings.showcase_symbols`, open to everyone as on the Prism page). The page shows a lock and an upgrade prompt for a locked column; a locked
value is never in the response, so it cannot be recovered in the browser.

## Widening: the rule

`python -m finlit.worker precompute-prism` (nightly window plus the `deploy/scheduler.sh` loop) works in two steps:

1. **Companies with a full stored report** (about 510): never-rated first, then the biggest, refreshed when older than `--days` (7). As before.
2. **Widening**, only when step 1 is finished for this worker and its queue is not cut off by `--limit`: the next companies **by market cap**
   (from `listing_quotes`, market cap above zero, symbol valid for the Prism page) that have no rating, then ratings older than 30 days.

Rules of step 2, all of which keep the free tier safe:

* **Budget.** `PRISM_WIDEN_PER_NIGHT` (default 30, `0` switches widening off, anything unreadable counts as 0, at most 2000). The count is kept in
  Redis (`prism:widen:day:<Indian date>`), per attempt, shared by both workers and by repeated rounds, so a day never exceeds it. If Redis cannot be
  read, widening does not run. 30 a night is about 750 provider calls and 15 minutes of one worker; at that rate the 5,300 companies without a
  report are reached in about half a year. Raise it when the provider quota allows: it is the only knob.
* **Members first.** Whenever a member starts a Prism calculation, `prism:member:active` is set for 10 minutes; widening stops (and the round
  reports `widen_paused_for_members`) while it is set. The site backend also turns the nightly job away (429 "member is waiting") and the job
  waits, as step 1 always did.
* **One refusal, one week.** A company whose calculation the provider refused, timed out on, or the model could not rate is remembered for 7 days
  (`prism:widen:refused:<statement>:<symbol>`) and not tried again before that. Three provider failures in a row (no answer, 429, 502, 503) end
  the round, so a provider that is down is not hammered.
* **Resumable.** A stored rating counts as done, so a stopped round continues with the next company; the daily count carries over rounds.
* **Same calculation.** Widening runs exactly the calculation a member's button runs (background priority, `prism:nightly` subject), and stores
  the same report, so a widened company opens on its Prism page like any other.

Observe it in `prism:pre:last` (Redis; fields `widened`, `widen_refused`, `widen_paused_for_members`, `remaining_candidates`) and in
`/tmp/job-prism-loop.log`. Other env vars that already apply: `PRISM_PRECOMPUTE_ENABLED`, `PRISM_WORKERS` (2), `PRISM_ROUND_MAX_MIN`,
`PRISM_ROUND_LIMIT`, `PRISM_SLOTS`.
