# IPO calendar: data path and how to see what the provider sends

Path: FinEdge `/ipo-calendar` -> `backend/finlit/calendars.py` (`ipo_rows`, `details_of`, `ipo_fields`) -> table `ipos` -> `GET /api/ipos` -> `frontend/src/pages/Ipo.tsx` (cards by status) and `IpoDrawer.tsx` (details).
`refresh-calendars` runs daily from the scheduler.

## Check the provider's field list from a browser (no SSH)

1. Open `https://<site>/api/results/status` and find `ipoFields`.
2. `seenKeys` is every field name the provider's IPO rows carried at the last `refresh-calendars` run; `sample` is one full row (the one with most fields, long text cut); `rowCount`, `windowFrom`, `windowTo` and `at` say what was asked and when.
3. Send us a screenshot of the `ipoFields` block. If it is `null`, `refresh-calendars` has not run since this release (or the provider call failed: see `lastRun.calendars.error` and `lastSkipped`).

## What is stored and shown

* `ipos.raw` (jsonb, migration 073): the provider's own row, trimmed (fields over 1,500 characters dropped, secret-looking keys dropped, about 6 KB cap). Not served by the API; kept so later features need no new provider call.
* `ipos.details` (jsonb): the facts we know how to read by tolerant alias (key spelling and case ignored): issue type, exchange, registrar, lead managers, subscription (overall, QIB, NII, retail, employees, shareholders), allotment / refund / credit dates, face value, issue price, fresh issue and offer for sale, promoter holding before and after, objects of the issue, DRHP / RHP / prospectus links (https only), minimum investment if the provider sends one.
* Existing columns now also read more aliases: sector, lot size (market lot), listing price.
* The page shows only what is present. Nothing is estimated: listing-day change is arithmetic on the issue price (or the top of the band when no issue price is sent) and the listing price; minimum investment is one lot times the upper price. GMP is not provided and not shown.

## Adding a field

Send the `ipoFields` screenshot; we add the key to the alias list in `details_of` and to the drawer. Rows already stored can be re-read from `raw` without a provider call.
