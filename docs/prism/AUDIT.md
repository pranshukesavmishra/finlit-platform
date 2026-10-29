# Prism audit and re-rating

## Why a company is "Not rated"

Run on the server (needs only the database, no provider calls, a few hundred rows at most):

    python -m finlit.worker audit-prism [--statement consolidated|standalone]

It reads `prism_reports` with one query (jsonb paths) and prints the reports that are NOT RATED or PROVISIONAL, by reason:

| bucket | meaning | what to do |
| --- | --- | --- |
| `classification` | the industry label is not mapped to a model group | add the label to `site-api/backend/premium_classification.py` (the audit lists each distinct label with its count and the first 10 symbols), bump `CLASSIFICATION_VERSION` in it and in `backend/finlit/prism.py`, deploy, run the re-rate below |
| `low_confidence` | under 50% of the inputs found | read "Inputs most often missing": a missing input shared by many companies is a data-loading gap to fix, not a rating decision |
| `insufficient_history` | under 4 quarters (or 2 annual results) of sales | normal for recently listed companies; many old companies here point to a statement-loading gap |
| `provisional_coverage` | 50% to 80% of the inputs found (label capped at Healthy) | as low_confidence |
| `provisional_history` | fewer than 6 comparable quarters | usually a recent listing |
| `other` | e.g. a data-integrity blocker, or an old report without reasons | open one report and read its alerts |

The result is also stored in `mf_meta` under `prism-audit:last` (`finlit.prism_audit.last_result`), like `integrity:last` and `provider-compare:last`. Reports stored before the classification fix use the older wording ("model group could not be verified"); they are counted in `classification` and the label is taken from the company's stored industry / sector.

## Re-rating after the classification fix

A stored NOT RATED report is reused for 6 hours and the nightly job only recalculates reports older than 7 days, so without help a fixed classification would not show until each user pressed Recalculate. Each report now carries `inputMeta.classificationVersion`. A report that is NOT RATED with the classification message and an older version (or none) is **stale**:

* a member opening it gets a fresh calculation instead of the stored one;
* the nightly and boot `precompute-prism` runs put stale ones first in the queue (all the usual pacing, three-failures-stop and member-yielding rules apply);
* a company whose recalculation is still answered with the old rules (site backend not yet deployed) is left alone until the next night, so the loop cannot hammer the provider.

Once after deploying both the site backend and the research API, run:

    python -m finlit.worker precompute-prism --stale-not-rated
    python -m finlit.worker audit-prism

`--stale-not-rated` handles only those companies, at most 300 per run, one second apart; run it again while it reports `remaining_candidates`. (The scheduler's `precompute-prism` loop would also pick them up first on its own.) The second command should show an empty `classification` bucket, or only genuinely new labels.
