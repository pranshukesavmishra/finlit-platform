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
- `refresh-instruments` (boot, then Sundays 02:20): the instrument file into `dhan_instruments`.
- `dhan-check`: the test above.
- Not yet: batch prices, daily history, cross-checks against FinEdge. Those follow once `dhan-check` passes.
