# ETF vs index fund (/etfs/compare-index-funds)

Sub page of the ETF section. API: `GET /api/etf-vs-index/options` (indices and the products of each) and `GET /api/etf-vs-index/compare?index=&etf=&fund=&plan=&sip=&lump=&start=` in `backend/finlit/etf_vs_index.py`, one router line in `api.py`, listed in the Caddy `@research` paths. Public like the ETF and fund compare endpoints (no plan gate). Answers cached in Redis for 30 minutes.

Data used: ETF exchange closes (etf_history; AMFI NAV only if a NAV history is stored, which is rare), index fund AMFI NAV (Direct Growth by default; mirror of AMFI data for up to 10 years), index levels of the PRICE index from the index provider (5 years), TER / exit load / benchmark from the disclosure facts. All measures use only dates every chosen product has a value for.

Not available: total-return (TRI) index levels. Tracking difference is therefore against the price index and labelled so; the summary's tracking line uses tracking error only. A free source to add: NSE Indices historical TRI data (niftyindices.com, "Historical Data > Total Returns Index", `getTotalReturnIndexString`). Also not known: minimum SIP, brokerage, bid-ask and impact cost (shown as not included, never estimated).

Product to index matching: stated benchmark first, else the index in the scheme name; variants ("equal weight", "value 20") and conflicts are left out.
