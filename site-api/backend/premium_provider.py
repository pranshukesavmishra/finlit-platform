"""Bounded provider access and the standalone FinEdge report loader.

Production report generation uses the dashboard loader; this standalone loader
is available to service tests and offline tools with an injected connector.
"""
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import BoundedSemaphore

import requests

# Reports share a bounded provider budget, including industry requests. A report needs about 140 small peer lookups; at two at a
# time that alone took over a minute, so the default is 16 (PREMIUM_PROVIDER_SLOTS, 1 to 24; 8 took 30 s, 12 took 20 s, 16 took 18 s for a 137-peer industry).
def _provider_slots():
    try:
        return max(1, min(24, int(os.getenv("PREMIUM_PROVIDER_SLOTS", "16"))))
    except ValueError:
        return 16


PROVIDER_SLOT_COUNT = _provider_slots()
_PROVIDER_SLOTS = BoundedSemaphore(PROVIDER_SLOT_COUNT)


def provider_get(get, path, params):
    attempts = 1 if getattr(get, "_handles_transient_retries", False) else 3
    for attempt in range(attempts):
        try:
            with _PROVIDER_SLOTS:
                return get(path, params)
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
            transient = status in (429, 500, 502, 503, 504) or isinstance(exc, (TimeoutError, requests.exceptions.Timeout, requests.exceptions.ConnectionError))
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(.5 * (2 ** attempt))

def fetch_inputs(get, symbol, statement_type, now):
    typ = "c" if statement_type == "consolidated" else "s"
    year = now.year
    specs = {
        "profile": (f"/company-profile/{symbol}", {}),
        "quarterly": (f"/financials/{symbol}", {"statement_type": typ, "statement_code": "pl", "period": "quarterly"}),
        "annual": (f"/financials/{symbol}", {"statement_type": typ, "statement_code": "pl", "period": "annual"}),
        "balance_recent": (f"/financials/{symbol}", {"statement_type": typ, "statement_code": "bs", "period": "quarterly"}),
        "balance": (f"/financials/{symbol}", {"statement_type": typ, "statement_code": "bs", "period": "annual"}),
        "cashflow": (f"/financials/{symbol}", {"statement_type": typ, "statement_code": "cf", "period": "annual"}),
        "quote": ("/quote", {"symbol": symbol}),
        "prices": (f"/daily-quotes/{symbol}", {"from": str(year - 1), "to": str(year)}),
        "ratios": (f"/daily-price-ratios/{symbol}", {"statement_type": typ, "from": str(year - 5), "to": str(year)}),
        "summary": (f"/shareholdings/summary/{symbol}", {"period": "quarterly"}),
        "distribution": (f"/shareholdings/distribution/{symbol}", {"period": "quarterly"}),
        "declaration": (f"/shareholdings/declaration/{symbol}", {"period": "quarterly"}),
        "peers": (f"/peers/{symbol}", {"group": "industry"}),
        "leverage": (f"/ratios/{symbol}", {"statement_type": typ, "ratio_type": "le"}),
    }
    raw, sources = {}, []
    def fetch(spec):
        key, (path, params) = spec
        try:
            payload = provider_get(get, path, params)
            return key, payload, True
        except Exception:
            # Do not copy provider errors, URLs or API keys into a report.
            return key, {}, False
    with ThreadPoolExecutor(max_workers=5) as pool:
        for key, payload, success in pool.map(fetch, specs.items()):
            raw[key] = payload
            sources.append({"section": key, "endpoint": specs[key][0], "parameters": specs[key][1], "available": success,
                            "retrievedAt": datetime.now(timezone.utc).isoformat(),
                            "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest() if success else None})
    return raw, sources
