# Dhan market data: setup

Dhan is a second source of prices and history, next to FinEdge. It has no company financials, news or fund data. Everything here is off until the variables below are set; the public instrument file (ISIN, surveillance flag, F&O) needs no account and loads on its own.

## 1. On Dhan (web.dhan.co)
1. **Data API:** My Profile, then "Access DhanHQ APIs" / DhanHQ Trading APIs, and subscribe to the Data API (about ₹499 a month plus tax; check the price shown there). Trading APIs are free, and we use none of them.
2. **TOTP:** in the same section choose **Setup TOTP**, confirm with the OTP sent to your mobile/email, and when the QR code appears, **also copy the secret text shown beside it** (a long string of letters and digits). Scan the QR in an authenticator app as well, and confirm with the first code. The secret text is what the server needs.
3. Note your **Dhan client ID** (shown on your profile) and your 6-digit **Dhan PIN**.

## 2. On Render (the service that runs FinLit): Environment tab
Add these as secrets (never in a file, never in chat), then **Save Changes**; the service redeploys by itself.

| Variable | Value |
|---|---|
| `DHAN_CLIENT_ID` | your Dhan client ID |
| `DHAN_PIN` | your 6-digit Dhan PIN |
| `DHAN_TOTP_SECRET` | the secret text from step 1.2 (spaces do not matter) |

With these three the server makes its own 24-hour token every day: nothing to paste again.
Simpler fallback (needs a new token pasted every day): `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` (Generate Access Token on web.dhan.co).

## 3. Check it works
Each time the service starts with `DHAN_CLIENT_ID` set, it runs the check by itself and writes the result (no secret) to `https://<your site>/api/mf/status`, under `run:dhan-check`. A good result reads `"status": "ok"` with `"data_plan": "Active"`, the number of instruments, and RELIANCE's last price. `"failed"` names the problem (client ID, PIN or secret wrong; token refused); `"incomplete"` usually means the Data API subscription is not active yet.
On a plan with a Render Shell tab you can also run `python -m finlit.worker dhan-check` yourself. During market hours the last price is live; outside them it is the last close.

## 4. Before using Dhan prices on the public site
Ask Dhan support, in writing, whether a personal Data API subscription may be used to show prices to the public on a website (redistribution). The same question applies to every price provider; keep the answer with the other licences.

## What is wired now
- `refresh-instruments` (boot, then daily at 07:50): the instrument file into `dhan_instruments` (ISIN, surveillance flag, F&O, and which rows are ETFs).
- `dhan-check` (boot): the test above.
- **Live stock prices** (`refresh-quotes`, every market minute): every company Dhan can match (NSE symbol, else BSE code) is priced in batch
  calls of 1,000. A company Dhan does not match, or whose Dhan price is more than 25% from the price we hold (a wrong match, an unadjusted
  split), is asked of FinEdge as before; if Dhan is down, FinEdge prices everyone.
- **ETFs** (`refresh-etf`, nightly): prices and 10 years of history from Dhan when it is set up (one quote call for every ETF, history paced at
  3 calls a second), else Upstox. `ETF_SOURCE=upstox` forces Upstox back. `/api/mf/status` shows `"source"` under `run:refresh-etf`.
- **Index strip and index prices** (`/api/indices`): during the session (09:15 to 15:30 IST, weekdays) the level, day move and day range of 170 mapped
  indices (the whole strip) come from Dhan, in ONE `/marketfeed/quote` call (segment `IDX_I`) at most once a minute however many people read the site. The
  fixed mapping (our name to Dhan security id) is `DHAN_INDEX` in `indices.py`, checked against `dhan_indices` (loaded by `refresh-instruments`). An
  unmapped index, one Dhan does not answer for, or a Dhan level more than 10% from the last one held, keeps FinEdge's figures (logged). Outside the session
  nothing is asked of Dhan and FinEdge's last close is shown. P/E, P/B and yield, and history, stay FinEdge's. Upstox is no longer involved in the strip:
  the old `UPSTOX_ACCESS_TOKEN` ticker (`/api/market-ticker`) is not used by the site.
- Mutual funds: unchanged. Dhan publishes no NAV, AUM or expense ratio; those stay with AMFI.
