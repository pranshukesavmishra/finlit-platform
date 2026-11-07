# Relay (free Cloudflare Worker): AMFI files and exchange pages

**Why:** `www.amfiindia.com` does not answer from the AWS server's address, so the nightly `facts` job cannot read each fund's expense ratio and fund size
(the Data health banner shows "ConnectTimeout"). A Cloudflare Worker fetches the same three public AMFI files from a place AMFI does answer, and the server reads them from it.

**What the relay does:** answers GET requests for exactly three paths (`/api/populate-ter-month`, `/api/populate-te-rdata-revised`, `/api/average-aum-schemewise`) by fetching the same path on
`www.amfiindia.com`. It rejects every other path, every other method and any request without the shared key. It stores nothing.

## Set-up (founder, once, about 10 minutes, free plan)
1. Create a free account at https://dash.cloudflare.com/sign-up (no card needed).
2. Workers & Pages > Create > Create Worker > name it `finlit-amfi-relay` > Deploy, then Edit code: replace everything with the contents of `worker.js` in this folder > Deploy.
3. Worker > Settings > Variables and Secrets > Add: type **Secret**, name `RELAY_KEY`, value = a long random string you make up (30+ characters). Do not share it in chat.
4. Note the worker address (looks like `https://finlit-amfi-relay.<your-name>.workers.dev`).
5. On the FinLit server, in `/opt/finlit/.env.aws` add two lines (never in chat or in the repo):
   `AMFI_RELAY_URL=https://finlit-amfi-relay.<your-name>.workers.dev`
   `AMFI_RELAY_KEY=<the same long random string>`
   then restart the app (the auto-deploy does it with the next deploy, or `docker compose ... up -d`).
6. Run the facts job once and check `/api/jobs/status` > `facts`: it should no longer say ConnectTimeout, and fund pages show the expense ratio and fund size.

If `facts` still times out after this, AMFI also blocks Cloudflare's addresses: then use the admin upload in Console > Data health (download AMFI's two files in a browser and upload them).

## The exchange route (company brief, earnings calls), added 7 Nov 2026
NSE and BSE answer the AWS server's address with HTTP 403 (verified live: `www.nseindia.com refused the request (403)`), so the company brief could never find an annual report.
The same worker now also answers `GET /fetch?u=<https address>` for hosts ending in `nseindia.com` or `bseindia.com` only (https, port 443), with the same `X-Relay-Key`.
For NSE's `/api/` addresses it first fetches NSE's home page and sends the cookie it sets (NSE's API refuses a request without it). Redirects are passed back to the server, which asks again.
The server needs nothing new: it uses `AMFI_RELAY_URL` and `AMFI_RELAY_KEY` (or `EXCHANGE_RELAY_URL` / `EXCHANGE_RELAY_KEY` if you want a separate worker). To update: paste the new `worker.js` over the old code in Cloudflare and Deploy.
Answers written by the worker carry `X-Relay: 1`; an error of its own also carries `X-Relay-Error`. An answer without `X-Relay` (a wrong key, a Cloudflare error page) is never mistaken for the exchange refusing.
**Not guaranteed:** an exchange may refuse Cloudflare's addresses too. Then the brief job says `report_blocked` as before and the administrator's annual-report URL override is the way.
