# Secondary data source (Upstox)

Some companies (for example Spicy Entertainment & Media, BSE 540084) have nothing at FinEdge. When that happens, FinLit asks Upstox for the missing sections only. FinEdge figures are never overwritten.

## Set up (no secret is stored in the code)
1. Open the Render dashboard of the OLD site-api service, Environment, and copy the value of `UPSTOX_ACCESS_TOKEN`.
2. Open the NEW platform service (and the worker/cron service, if separate), Environment, add `UPSTOX_ACCESS_TOKEN` with that value, save and redeploy.
3. Admin, Data health shows one line: "Secondary source: connected", "not configured" (variable missing, feature fully off) or "token expired".

## Renewal
**Use an Analytics Token, not the daily login token.** The normal Upstox access token ends every morning and cannot be renewed without a person logging in, so it is not suitable for a server. Upstox's *Analytics Token* is read-only (market data, historical candles, fundamentals; it cannot place orders), needs no static IP for those, and is valid for one year. Create it once: Upstox developer apps page, your app, the Analytics tab, "Generate Token"; paste it into the Render variable UPSTOX_ACCESS_TOKEN. Admin, Data health then shows how many days it has left, and turns to a warning 30 days before it ends. Renew it once a year the same way. When the line says "token expired", paste a fresh token into the same variable. Until you do, companies FinEdge covers are unaffected; only the companies that rely on the secondary source show gaps.

## What it does
- Used only when FinEdge's price, annual statements, balance sheet, cash flow or quarterly results are empty for a company (checked at every rebuild, including when a visitor opens a company).
- The company is matched by ISIN, trading code or exact name (never a similar name); the match is cached 30 days.
- Reports built this way say "Some figures come from our secondary data source" (`summary.dataQuality.secondarySource` lists which sections) and the coverage audit records "complete via secondary source".
- If both sources hold revenue, net profit or price and differ by more than 5%, FinEdge is kept and the gap is listed in `dataQuality.sourceDisagreements` and the worker log ("SOURCES DISAGREE").

## Not verified
Written from the old site's request shapes without a live token: field names, period labels and units (crore for statements, rupees for prices) are assumed from the old code. Check one live company after adding the token (e.g. `python -m finlit.worker ingest 540084`) against the old site. Balance sheet gives total assets only; P/B and equity-based ratios appear only when computable.
