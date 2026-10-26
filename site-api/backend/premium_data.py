"""Provider adapter for premium reports. Dates, units and provenance stay explicit."""
import calendar
import hashlib
import json
import math
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import os
from threading import BoundedSemaphore, Event, Lock
import time
import requests
try:
    from .premium_engine import num
    from .financial_fields import INTEREST_COST_FIELDS
    from .premium_model_config import QUARTERS_STORED, CAGR_MAX_YEARS
except ImportError:
    from premium_engine import num
    from financial_fields import INTEREST_COST_FIELDS
    from premium_model_config import QUARTERS_STORED, CAGR_MAX_YEARS

CR = 10_000_000
# Reports share a bounded provider budget, including industry requests. A report needs about 140 small peer lookups; at two at a
# time that alone took over a minute, so the default is 8 (PREMIUM_PROVIDER_SLOTS, 1 to 24).
def _provider_slots():
    try:
        return max(1, min(24, int(os.getenv("PREMIUM_PROVIDER_SLOTS", "8"))))
    except ValueError:
        return 8


PROVIDER_SLOT_COUNT = _provider_slots()
_PROVIDER_SLOTS = BoundedSemaphore(PROVIDER_SLOT_COUNT)
PEER_BUDGET_SECONDS = 45.0   # peers not looked up by then count as missing (and are listed as such); normally the lookups end in about 10
_BENCHMARK_OBSERVATIONS = {}
_BENCHMARK_CACHE_SECONDS = 15 * 60


class ObservationCache:
    """Peer observations kept across reports: (basis, as-of date, kind, symbol) -> the row (or multiple) the median used. Thread-safe, and two
    callers asking for the same key share one lookup. `preload` is what an earlier report kept; `new` is what this report looked up itself."""

    def __init__(self, preload=None):
        self.rows = dict(preload or {})
        self.new = {}
        self.hits = 0
        self._lock = Lock()
        self._inflight = {}

    def get_or_compute(self, key, compute):
        with self._lock:
            if key in self.rows:
                self.hits += 1
                return self.rows[key]
            event = self._inflight.get(key)
            mine = event is None
            if mine:
                event = self._inflight[key] = Event()
        if not mine:
            event.wait(PEER_BUDGET_SECONDS)
            with self._lock:
                return self.rows.get(key)
        value = None
        try:
            value = compute()
            return value
        finally:
            with self._lock:
                if value is not None:
                    self.rows[key] = self.new[key] = value
                self._inflight.pop(key, None)
            event.set()


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

def items(payload, *keys):
    if isinstance(payload, list): return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list): return items(payload[key])
    return []


def first(row, *names):
    for name in names:
        value = num(row.get(name))
        if value is not None: return value
    return None


def field_date(row):
    for key in ("period_end", "periodEnd", "date_header", "header", "quote_date", "date", "year"):
        value = str(row.get(key) or "")
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%b %Y", "%b-%Y", "%Y"):
            try:
                parsed = datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt).date()
                if fmt in ("%b %Y", "%b-%Y"):
                    parsed = parsed.replace(day=calendar.monthrange(parsed.year, parsed.month)[1])
                if fmt == "%Y": parsed = date(parsed.year, 3, 31)
                return parsed
            except ValueError: pass
    return None


def resolve_group(profile):
    text = " ".join(str(profile.get(key) or "") for key in ("industry", "sector", "sub_industry", "macro_sector")).lower()
    rules = [
        ("INSURANCE", r"insurance"), ("NBFC", r"nbfc|non.?bank|housing finance|financial company|finance company"),
        ("BANK", r"\bbanks?\b|banking"), ("REALTY", r"real estate|realty"),
        ("UTILITY", r"power|utilities|telecom|construction|infrastructure"),
        ("HEAVY", r"cement|metal|steel|mining|oil|petroleum|refiner|gas"),
        ("LIGHT", r"software|information technology|\bit -|fmcg|fast moving|pharma|media|entertainment|asset management|brok|exchange|retail|hotel|restaurant|consumer services"),
    ]
    for group, pattern in rules:
        # Vehicle manufacturing is not construction/infrastructure activity.
        # Preserve the precedence of financial groups and real estate.
        if group == "UTILITY" and re.search(r"\bautomobiles?\b|\bauto parts\b|\bvehicles?\b", text):
            return "MFG", False
        if re.search(pattern, text): return group, False
    known_mfg = bool(re.search(r"auto|capital goods|engineering|chemical|textile|defen|hospital|diagnostic|logistic|transport|consumer durable|manufactur|machiner|electrical|industrial", text))
    return "MFG", not known_mfg


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


def profile_from(raw):
    p = raw.get("profile", {})
    if isinstance(p, list): p = p[0] if p else {}
    if not isinstance(p, dict): return {}
    return p.get("profile", p) if isinstance(p.get("profile", p), dict) else {}


def peer_benchmark(get, peers, statement_type, as_of, group=None, metrics=None, observations=None, budget_seconds=None):
    """Median of available positive industry observations, with explicit coverage."""
    selected = set(metrics) if metrics is not None else {"pe", "pb", "ev_ebitda"}
    symbols = peers.get("peers", []) if isinstance(peers, dict) else []
    symbols = sorted({str(value).upper() for value in symbols if re.fullmatch(r"[A-Za-z0-9.&-]{1,30}", str(value))})
    meta = {"source": "FinEdge industry peer universe", "asOf": as_of.isoformat(), "universeCount": len(symbols), "fetchedCount": 0, "positiveCounts": {}, "basis": statement_type}
    meta["metrics"] = {}
    if not selected or not symbols or len(symbols) > 500:
        return {}, {**meta, "note": "No peer calculation required, or industry universe unavailable or exceeds the on-demand limit."}
    deadline = time.monotonic() + (PEER_BUDGET_SECONDS if budget_seconds is None else budget_seconds)
    scope = (statement_type, as_of.isoformat())
    def remembered(kind, symbol, compute):
        """Through the kept observations when there are any, else straight to the lookup."""
        if observations is None:
            return compute()
        return observations.get_or_compute(scope + (kind, symbol), compute)
    def fetch(symbol):
        # A row looked up for P/E alone may lack the P/B a later report also wants, so the wanted metrics are part of the key.
        return remembered("pr:" + ",".join(sorted(selected & {"pe", "pb"})), symbol, lambda: fetch_ratios(symbol))
    def fetch_ratios(symbol):
        cache_key = (get, symbol, statement_type, as_of)
        cached = _BENCHMARK_OBSERVATIONS.get(cache_key)
        if cached and time.monotonic() - cached[0] < _BENCHMARK_CACHE_SECONDS:
            return cached[1]
        if time.monotonic() > deadline:
            return None
        try:
            p = provider_get(get, f"/daily-price-ratios/{symbol}", {"statement_type": "c" if statement_type == "consolidated" else "s", "from": str(as_of.year - 1), "to": str(as_of.year)})
            rows = [r for r in items(p, "price_ratios", "data") if field_date(r) and 0 <= (as_of - field_date(r)).days <= 31]
            row = max(rows, key=field_date) if rows else None
            if row is None or any(num(row.get(key)) is None for key in selected & {"pe", "pb"}):
                derived = derive_peer_price_ratios(get, symbol, statement_type, as_of)
                if derived:
                    row = {**derived, **(row or {})}
                    for key in ("pe", "pb"):
                        if num(row.get(key)) is None and key in derived:
                            row[key] = derived[key]
            if row is not None:
                if len(_BENCHMARK_OBSERVATIONS) >= 2000:
                    _BENCHMARK_OBSERVATIONS.pop(next(iter(_BENCHMARK_OBSERVATIONS)))
                _BENCHMARK_OBSERVATIONS[cache_key] = (time.monotonic(), row)
            return row
        except Exception: return None
    records = []
    if selected & {"pe", "pb"}:
        with ThreadPoolExecutor(max_workers=PROVIDER_SLOT_COUNT) as pool:
            records = list(pool.map(fetch, symbols))
    meta["fetchedCount"] = sum(row is not None for row in records)
    meta["missingSymbols"] = [symbol for symbol, row in zip(symbols, records) if row is None]
    result = {}
    meta["calculatedPeerCount"] = sum(row is not None and row.get("source") == "calculated_finedge_quote_and_financials" for row in records)
    # Partial coverage is allowed, but never presented as a complete-industry median.
    for key in ("pe", "pb"):
        if key not in selected:
            continue
        positive = [num(row.get(key)) for row in records if row and num(row.get(key)) is not None and num(row[key]) > 0]
        meta["positiveCounts"][key] = len(positive)
        observed = sum(row is not None and num(row.get(key)) is not None for row in records)
        meta["metrics"]["industry_median_" + key] = {
            "value": statistics.median(positive) if len(positive) >= 5 else None,
            "provider": "FinEdge", "scope": "industry", "method": "available peer median",
            "positiveCount": len(positive), "observedCount": observed, "universeCount": len(symbols),
            "partial": observed < len(symbols), "statementBasis": statement_type, "asOf": as_of.isoformat()}
        if len(positive) >= 5:
            result["industry_median_" + key] = statistics.median(positive)
    if "ev_ebitda" in selected and group in ("HEAVY", "UTILITY") and len(symbols) <= 100:
        def enterprise_multiple(symbol):
            return remembered("ev", symbol, lambda: enterprise_multiple_lookup(symbol))
        def enterprise_multiple_lookup(symbol):
            cache_key = (get, symbol, statement_type, as_of, "ev_ebitda")
            cached = _BENCHMARK_OBSERVATIONS.get(cache_key)
            if cached and time.monotonic() - cached[0] < _BENCHMARK_CACHE_SECONDS:
                return cached[1]
            try:
                typ = "c" if statement_type == "consolidated" else "s"
                quote = provider_get(get, "/quote", {"symbol": symbol})
                balance = provider_get(get, f"/financials/{symbol}", {"statement_type": typ, "statement_code": "bs", "period": "quarterly"})
                income = provider_get(get, f"/financials/{symbol}", {"statement_type": typ, "statement_code": "pl", "period": "quarterly"})
                value = derive_peer_ev_ebitda({"quote": quote, "balance_recent": balance, "quarterly": income}, symbol, statement_type, as_of)
                if value is not None:
                    if len(_BENCHMARK_OBSERVATIONS) >= 2000:
                        _BENCHMARK_OBSERVATIONS.pop(next(iter(_BENCHMARK_OBSERVATIONS)))
                    _BENCHMARK_OBSERVATIONS[cache_key] = (time.monotonic(), value)
                return value
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=PROVIDER_SLOT_COUNT) as pool:
            multiples = list(pool.map(enterprise_multiple, symbols))
        positive = [value for value in multiples if value is not None and value > 0]
        meta["evCalculatedCount"] = sum(v is not None for v in multiples)
        meta["positiveCounts"]["ev_ebitda"] = len(positive)
        meta["evMissingSymbols"] = [symbol for symbol, value in zip(symbols, multiples) if value is None]
        meta["metrics"]["industry_median_ev_ebitda"] = {
            "value": statistics.median(positive) if len(positive) >= 5 else None,
            "provider": "FinEdge", "scope": "industry", "method": "available peer median",
            "positiveCount": len(positive), "observedCount": meta["evCalculatedCount"], "universeCount": len(symbols),
            "partial": meta["evCalculatedCount"] < len(symbols), "statementBasis": statement_type, "asOf": as_of.isoformat()}
        if len(positive) >= 5:
            result["industry_median_ev_ebitda"] = statistics.median(positive)
    meta["note"] = "Medians use at least five available positive multiples from the FinEdge industry peer universe. Coverage and exclusions are disclosed for each benchmark; partial coverage is not a complete-industry median."
    return result, meta


def derive_peer_price_ratios(get, symbol, statement_type, as_of):
    """Calculate missing observations from dated FinEdge quote/financial inputs."""
    try:
        quote_payload = provider_get(get, '/quote', {'symbol': symbol})
        quote = quote_payload.get(symbol, {}) if isinstance(quote_payload, dict) else {}
        observed = field_date({'date': str(quote.get('tradetime') or quote.get('date') or '')[:10]})
        if not observed or not 0 <= (as_of-observed).days <= 10:
            return None
        typ = 'c' if statement_type == 'consolidated' else 's'
        income = provider_get(get, f'/financials/{symbol}', {'statement_type':typ,'statement_code':'pl','period':'quarterly'})
        balance = provider_get(get, f'/financials/{symbol}', {'statement_type':typ,'statement_code':'bs','period':'quarterly'})
        d,_,_,meta,_,_ = adapt_inputs({'profile':{'industry':'Auto Components'},'quote':quote_payload,'quarterly':income,'balance_recent':balance}, symbol, as_of, statement_type)
        row = {'quote_date': observed.isoformat(), 'source':'calculated_finedge_quote_and_financials'}
        eps = d['eps_q'][-4:]
        if d['price'] is not None and len(eps)==4 and all(v is not None for v in eps):
            row['pe'] = d['price']/sum(eps) if sum(eps)>0 else 0.
        cap = first(quote,'market_cap','marketCap')
        end = date.fromisoformat(meta['balanceAsOf']) if meta['balanceAsOf'] else None
        if cap is not None and cap>0 and d['net_worth'] is not None and end and (as_of-end).days<=200:
            row['pb'] = cap/d['net_worth'] if d['net_worth']>0 else 0.
        return row if 'pe' in row or 'pb' in row else None
    except Exception:
        return None


def derive_peer_ev_ebitda(raw, symbol, statement_type, as_of):
    """Same enterprise-value definition and raw financial adapter as the report."""
    quote = raw.get('quote', {}).get(symbol, {})
    observed = field_date({'date': str(quote.get('tradetime') or quote.get('date') or '')[:10]})
    market_cap = first(quote, 'market_cap', 'marketCap')
    if not observed or not 0 <= (as_of-observed).days <= 10 or market_cap is None or market_cap <= 0:
        return None
    inputs, _, _, meta, _, _ = adapt_inputs({**raw, 'profile': {'industry': 'Oil refining'}}, symbol, as_of, statement_type)
    q = inputs['operating_profit_q'][-4:]
    if len(q) != 4 or any(v is None for v in q) or inputs['total_debt'] is None or inputs['cash'] is None:
        return None
    balance_day = date.fromisoformat(meta['balanceAsOf']) if meta['balanceAsOf'] else None
    quarter_day = date.fromisoformat(meta['quarterlyAsOf']) if meta['quarterlyAsOf'] else None
    if not balance_day or not quarter_day or (as_of-balance_day).days > 200 or (as_of-quarter_day).days > 200:
        return None
    ebitda = sum(q)
    # A known nonpositive denominator is an excluded observation, not a missing input.
    return (market_cap + inputs['total_debt'] - inputs['cash']) / ebitda if ebitda > 0 else 0.


def adapt_inputs(raw, symbol, as_of, statement_type):
    profile = profile_from(raw)
    group, defaulted = resolve_group(profile)
    warnings = []
    if defaulted: warnings.append("Industry mapping used the MFG default; confirm the classification before relying on the score.")
    provenance = {}
    qrows = items(raw.get("quarterly"), "financials", "data")
    arows = items(raw.get("annual"), "financials", "data")
    brows = items(raw.get("balance"), "financials", "data") + items(raw.get("balance_recent"), "financials", "data")
    crows = items(raw.get("cashflow"), "financials", "data")
    def dated(rows):
        selected = {}
        for row in rows:
            day = field_date(row)
            if not day or day > as_of:
                continue
            reported = field_date({"date": row.get("result_date")}) if row.get("result_date") else None
            if reported and reported > as_of:
                continue
            previous = selected.get(day)
            # Prefer the latest restatement when the provider repeats a period.
            filing = str(row.get("result_date") or row.get("result_timestamp") or "")
            old_filing = str((previous or {}).get("result_date") or (previous or {}).get("result_timestamp") or "")
            if previous is None or filing >= old_filing:
                selected[day] = row
        return selected
    def comparable(rows, minimum_days, maximum_days, label):
        valid = []
        for row in rows:
            start = row.get("period_start") or row.get("periodStart")
            end = field_date(row)
            if start and end:
                start_date = field_date({"period_end": start})
                if start_date and not minimum_days <= (end - start_date).days + 1 <= maximum_days:
                    warnings.append(f"Excluded a non-comparable {label} period ending {end}: reported duration differs from a standard period.")
                    continue
            valid.append(row)
        return valid
    q, a, b, cf = map(dated, (comparable(qrows, 70, 105, "quarterly"), comparable(arows, 330, 400, "annual"), brows, comparable(crows, 330, 400, "cash-flow")))
    end_q = max(q) if q else None
    # Calendar-indexed slots retain gaps; arrays always run oldest to newest.
    qindices = sorted({day.year * 4 + (day.month - 1) // 3 for day in q})
    qmap = {day.year * 4 + (day.month - 1) // 3: row for day, row in q.items()}
    qkeys = list(range(max(min(qindices), max(qindices) - QUARTERS_STORED + 1), max(qindices) + 1)) if qindices else []
    years = sorted({day.year for day in a})
    ykeys = list(range(max(min(years), max(years) - CAGR_MAX_YEARS), max(years) + 1)) if years else []
    amap = {day.year: row for day, row in a.items()}
    def record(source, target, names, scale=CR):
        name = next((key for key in names if num(source.get(key)) is not None), None)
        if name: provenance.setdefault(target, set()).add(name)
        return num(source[name]) / scale if name else None
    def revenue(row):
        if group in ("BANK", "NBFC"):
            value = record(row, "sales", ("netInterestIncome", "netInterestRevenue", "netInterestEarnings"))
            if value is None:
                earned = record(row, "sales", ("interestEarned", "interestIncome"))
                paid = record(row, "sales", ("interestExpended", "interestExpense", "interestExpenses", "financeCosts", "financeCost"))
                return earned - paid if earned is not None and paid is not None else None
            return value
        if group == "INSURANCE":
            return record(row, "sales", ("netPremiumEarned", "netPremiumIncome", "netPremium", "netEarnedPremium"))
        return record(row, "sales", ("netSales", "sales", "revenueFromOperations", "incomeFromOperations", "revenue", "totalRevenue"))
    def profit(row):
        # Owner-attributable earnings take precedence over total group profit.
        return record(row, "net_profit", ("profitAttributableToOwnersOfParent", "profitOrLossAttributableToOwners", "profitLossAttributableToOwnersOfParent", "profitOrLossAttributableToOwnersOfParent", "profitLossForPeriod", "profitLossForThePeriod", "netProfitAfterTax", "profitAfterTax", "netProfit", "profitLossAfterTaxAndExtraordinaryItems", "profitLossAfterTaxBeforeExtraordinaryItems"))
    def ebitda(row):
        value = record(row, "operating_profit", ("ebitda", "EBITDA", "earningsBeforeInterestTaxesDepreciationAndAmortization"))
        if value is not None: return value
        ebit = record(row, "operating_profit", ("ebit", "profitBeforeInterestAndTax"))
        depreciation = record(row, "operating_profit", ("depreciation", "depreciationAndAmortisation", "depreciationAndAmortization"))
        if ebit is not None and depreciation is not None: return ebit + depreciation
        # PBT + finance cost + depreciation - other income is an explicit operating EBITDA derivation.
        pbt = record(row, "operating_profit", ("profitBeforeTax", "profitLossBeforeTax"))
        interest = record(row, "operating_profit", INTEREST_COST_FIELDS)
        other = record(row, "operating_profit", ("otherIncome",))
        return pbt + interest + depreciation - other if all(v is not None for v in (pbt, interest, depreciation, other)) else None
    def eps(row): return record(row, "eps", ("basicEPS", "basicEps", "basicReInr", "basicREInr", "basicEPSInRs", "eps", "dilutedEPS", "dilutedReInr"), 1)
    def net_worth(row, target="net_worth"):
        # Model specification section 2 names Total equity, including non-controlling interests.
        value = record(row, target, ("totalEquity", "shareholdersEquity", "netWorth", "equity"))
        if value is None:
            owner, minority = first(row, "equityAttributableToOwnersOfParent"), first(row, "nonControllingInterest", "nonControllingInterests")
            if owner is not None and minority is not None:
                value = (owner + minority) / CR
                provenance.setdefault(target, set()).add("owner equity + non-controlling interest = total equity")
        if value is None and group == "BANK":
            capital, reserves = first(row, "capital"), first(row, "reserves")
            assets, deposits, borrowings, other = (first(row, key) for key in ("assets", "deposits", "borrowings", "otherLiabilitiesAndProvisions"))
            if all(v is not None for v in (capital, reserves, assets, deposits, borrowings, other)):
                equity = capital + reserves
                if abs(assets - deposits - borrowings - other - equity) <= max(1., abs(assets) * .0001):
                    value = equity / CR
                    provenance.setdefault(target, set()).add("capital + reserves (reconciled to assets minus liabilities)")
        return value
    current_a = a[max(a)] if a else {}
    current_b = b[max(b)] if b else {}
    # A report uses one explicit statement basis throughout; no silent standalone fallback.
    d = {
        "sales_q": [revenue(qmap.get(key, {})) for key in qkeys],
        "net_profit_q": [profit(qmap.get(key, {})) for key in qkeys],
        "operating_profit_q": [ebitda(qmap.get(key, {})) for key in qkeys],
        "eps_q": [eps(qmap.get(key, {})) for key in qkeys],
        "sales_y": [revenue(amap.get(key, {})) for key in ykeys],
        "net_profit_y": [profit(amap.get(key, {})) for key in ykeys],
        "operating_cash_flow_y": [], "eps_fy": eps(current_a),
        "annual_net_worth": None, "annual_total_assets": None,
        "net_worth": net_worth(current_b),
        "total_debt": record(current_b, "total_debt", ("borrowings", "totalBorrowings", "totalDebt")),
        "cash": record(current_b, "cash", ("cashAndBankBalances", "cashAndCashEquivalents", "cashEquivalents", "cash")),
        "profit_before_tax": record(current_a, "profit_before_tax", ("profitBeforeTax", "profitLossBeforeTax")),
        "interest_cost": record(current_a, "interest_cost", INTEREST_COST_FIELDS),
        "total_assets": record(current_b, "total_assets", ("totalAssets", "totalAsset", "assets")),
    }
    # Cash and other bank balances are disjoint provider fields. Do not assume all investments are liquid.
    other_bank = record(current_b, "cash", ("otherBankBalances",))
    if d["cash"] is not None and other_bank is not None and num(current_b.get("cashAndBankBalances")) is None:
        d["cash"] += other_bank
    if d["total_debt"] is None:
        short = record(current_b, "total_debt", ("shortTermBorrowings", "borrowingsCurrent"))
        long = record(current_b, "total_debt", ("longTermBorrowings", "borrowingsNoncurrent"))
        if short is not None and long is not None: d["total_debt"] = short + long
    cfmap = {day.year: row for day, row in cf.items()}
    d["operating_cash_flow_y"] = [record(cfmap.get(year, {}), "operating_cash_flow", ("netCashFromOperatingActivities", "cashFromOperatingActivity", "cashFlowsFromOperatingActivities", "cashFlowFromOperatingActivities", "operatingCashFlow")) for year in ykeys]
    def loans(row):
        value = record(row, "loans", ("advances", "loansAndAdvances", "loans", "advancesToCustomers"))
        if value is None:
            short = record(row, "loans", ("loansCurrent",))
            long = record(row, "loans", ("loansNoncurrent",))
            if short is not None and long is not None: value = short + long
        return value
    if b:
        balance_day = max(b)
        # Compare the exact same reporting date a year earlier, never an arbitrary row in that year.
        prior_day = balance_day.replace(year=balance_day.year - 1, day=min(balance_day.day, calendar.monthrange(balance_day.year - 1, balance_day.month)[1]))
        prior_b = b.get(prior_day, {})
        d["net_worth_1y_ago"] = net_worth(prior_b, "net_worth_1y_ago")
        d["loans_now"], d["loans_1y_ago"] = loans(current_b), loans(prior_b)
        # Annual profitability and its denominator must refer to the same year-end.
        annual_b = b.get(max(a), {}) if a else {}
        d["annual_net_worth"] = net_worth(annual_b, "annual_net_worth")
        d["annual_total_assets"] = record(annual_b, "annual_total_assets", ("totalAssets", "totalAsset", "assets"))
    annual_balance = {day: row for day, row in b.items()}
    d["net_worth_y"] = [net_worth(annual_balance.get(field_date(amap[year]), {}), "net_worth_y") if year in amap else None for year in ykeys]
    latest_q = q[end_q] if end_q else {}
    # NPA and capital ratios in FinEdge financials are fractions, not INR amounts.
    for target, names in (("gross_npa_pct", ("percentageOfGrossNpa",)), ("net_npa_pct", ("percentageOfNpa", "percentageOfNetNpa")), ("capital_adequacy_pct", ("capitalAdequacyRatio", "capitalRiskAdequacyRatio", "capitalToRiskWeightedAssetsRatio", "cRAR", "crar"))):
        value = record(latest_q, target, names, 1)
        # FinEdge all-zero NPA/CET1 tuples are unavailable disclosure placeholders.
        placeholder = all(first(latest_q, key) == 0 for key in ("percentageOfGrossNpa", "percentageOfNpa", "cET1Ratio"))
        d[target] = None if value is None or placeholder else value * 100
    quality_rows = dated(items(raw.get("asset_quality"), "financials", "data"))
    if quality_rows:
        quality_day = max(quality_rows)
        quality_row = quality_rows[quality_day]
        if (as_of - quality_day).days <= 200:
            for target, name in (("gross_npa_pct", "percentageOfGrossNpa"), ("net_npa_pct", "percentageOfNpa")):
                placeholder = all(first(quality_row, key) == 0 for key in ("percentageOfGrossNpa", "percentageOfNpa", "cET1Ratio"))
                if d[target] is None and not placeholder and first(quality_row, name) is not None:
                    d[target] = round(first(quality_row, name) * 100, 2)
                    provenance[target] = {f"Dashboard asset-quality disclosure: {raw.get('asset_quality_basis', statement_type)}, {quality_day}, {name}"}
                    if raw.get("asset_quality_basis") != statement_type:
                        warnings.append(f"The dashboard's bank asset-quality disclosures use {raw.get('asset_quality_basis')} statements dated {quality_day}; NPA inputs use that explicitly disclosed basis. Financial statements remain {statement_type}.")
    d["solvency_ratio"] = record(latest_q, "solvency_ratio", ("solvencyRatio",), 1)
    summary = dated(items(raw.get("summary"), "summary"))
    distribution = dated(items(raw.get("distribution"), "distributions"))
    declaration = dated(items(raw.get("declaration"), "declaration"))
    ownership_dates = sorted(set(summary) | set(distribution) | set(declaration))
    own_date = ownership_dates[-1] if ownership_dates else None
    own_summary = summary.get(own_date, {})
    own_distribution = distribution.get(own_date, {})
    promoter = next((row.get("data", {}) for row in own_distribution.get("distributions", []) if row.get("group") == "promoterAndPromoterGroup"), {})
    pledged, total_promoter = first(promoter, "pledgedShares"), first(promoter, "totalShares")
    d["promoter_pledged_pct"] = pledged / total_promoter * 100 if pledged is not None and total_promoter and total_promoter > 0 else first(promoter, "pledgedSharesPct")
    if d["promoter_pledged_pct"] is None and declaration.get(own_date, {}).get("pledgedSharesForPromoterAndGroup") is False:
        d["promoter_pledged_pct"] = 0.
        provenance["promoter_pledged_pct"] = {"declaration: pledgedSharesForPromoterAndGroup=false"}
    if total_promoter == 0:
        d["promoter_pledged_pct"] = 0.
        provenance["promoter_pledged_pct"] = {"distribution: total promoter shares=0"}
    if d["promoter_pledged_pct"] is not None and not 0 <= d["promoter_pledged_pct"] <= 100:
        d["promoter_pledged_pct"] = None
        warnings.append("Reported promoter pledge is outside 0–100%; it is treated as unavailable.")
    d["shares"] = first(own_summary, "paidUpEquityShares")
    if d["shares"] is not None: d["shares"] /= CR
    quote = raw.get("quote", {})
    quote = quote.get(symbol, {}) if isinstance(quote, dict) else {}
    d["price"] = first(quote, "current_price", "currentPrice", "price", "lastPrice", "close")
    if d["price"] is not None and d["price"] <= 0: d["price"] = None
    prices = []
    for row in items(raw.get("prices"), "price", "quotes", "data"):
        day = field_date(row)
        close = first(row, "close_price", "close", "adjClose")
        volume = first(row, "volume", "tradedVolume")
        # The provider pads days it has no trading record for (a holiday, a missed feed) with an all-zero row. That is not a session: keep it out
        # so it neither breaks the 250-session closing-price window nor the 60-session turnover window. A zero close beside real
        # prices or volume is still treated as a bad tick (None) below.
        if not any((first(row, *names) or 0) for names in (("open_price", "open"), ("high_price", "high"), ("low_price", "low"), ("close_price", "close", "adjClose"), ("volume", "tradedVolume"))):
            continue
        if day and day <= as_of: prices.append((day, close if close is not None and close > 0 else None, volume))
    prices = list({day: (day, close, volume) for day, close, volume in prices}.values())
    prices.sort()
    quote_date = str(quote.get("tradetime") or quote.get("tradeTime") or quote.get("date") or "")[:10] or None
    valid_prices = [row for row in prices if row[1] is not None]
    if d["price"] is None and valid_prices:
        d["price"], quote_date = valid_prices[-1][1], valid_prices[-1][0].isoformat()
        warnings.append("Quote unavailable; latest reported historical close was used.")
    shares = first(quote, "shares", "sharesOutstanding")
    market_cap = first(quote, "market_cap", "marketCap")  # FinEdge quote market cap is in INR crore.
    # Paid-up domestic shares can omit shares against depository receipts. Use the
    # complete dated denominator only when both the ownership identity and market cap agree.
    filing_total = first(own_summary, "totalShares")
    filing_paid = first(own_summary, "paidUpEquityShares")
    filing_dr = first(own_summary, "outstandingDepositoryRcpts")
    filing_identity = filing_total is not None and filing_paid is not None and abs(filing_total - filing_paid - (filing_dr or 0)) <= max(1, filing_total * .0001)
    reconciled_shares = filing_identity and market_cap is not None and market_cap > 0 and d["price"] is not None and abs(d["price"] * filing_total / CR / market_cap - 1) <= .02
    if reconciled_shares:
        d["shares"] = filing_total / CR
        provenance["shares"] = {"ownership summary: totalShares including depository receipts; reconciled to price and market cap"}
    quoted_shares = shares / CR if shares is not None and shares > 0 else None
    inconsistent_quote = quoted_shares is not None and market_cap is not None and market_cap > 0 and d["price"] is not None and abs(d["price"] * quoted_shares - market_cap) / market_cap > .02
    inconsistent_filing = quoted_shares is not None and d["shares"] is not None and d["shares"] > 0 and abs(quoted_shares / d["shares"] - 1) > .02
    if not reconciled_shares and quoted_shares is not None and not inconsistent_quote and not inconsistent_filing:
        d["shares"] = quoted_shares
        provenance["shares"] = {"quote: shares"}
    elif (inconsistent_quote or inconsistent_filing) and not reconciled_shares:
        warnings.append("The quote share count conflicts with the dated ownership filing or quoted market cap. The dated paid-up share count is used where available; otherwise P/B and EV inputs remain unavailable.")
        if d["shares"] is not None:
            provenance["shares"] = {"ownership summary: paidUpEquityShares (quote discrepancy)"}
    returns = [prices[i][1] / prices[i - 1][1] - 1 for i in range(max(1, len(prices) - 250), len(prices)) if prices[i][1] is not None and prices[i - 1][1] is not None]
    d["risk_calculation"] = {"returnCount": len(returns), "dailyStdDev": statistics.stdev(returns) if len(returns) >= 2 else None, "annualisationDays": 250, "drawdownWindow": 250, "turnoverWindow": 60,
                          "sessions": len(prices), "invalidCloseLast250": sum(close is None for _, close, _ in prices[-250:]), "missingVolumeLast60": sum(volume is None for _, _, volume in prices[-60:])}
    d["volatility_pct"] = statistics.stdev(returns) * math.sqrt(250) * 100 if len(returns) >= 60 else None
    incomplete_prices = any(close is None for _, close, _ in prices[-250:])
    if len(prices) >= 250 and not incomplete_prices:
        peak, fall = prices[-250][1], 0.
        for _, close, _ in prices[-250:]:
            peak = max(peak, close)
            fall = max(fall, (1 - close / peak) * 100)
        d["biggest_fall_pct"] = fall
    else: d["biggest_fall_pct"] = None
    last60 = prices[-60:]
    d["trading_value_cr"] = statistics.mean(close * volume for _, close, volume in last60) / CR if len(last60) == 60 and all(close is not None and volume is not None and volume >= 0 for _, close, volume in last60) else None
    ratios = [row for row in items(raw.get("ratios"), "price_ratios", "data") if field_date(row) and 0 <= (as_of - field_date(row)).days <= 366 * 5]
    for key, divisor in (("pe", 3), ("pb", 6)):
        buckets = {}
        for row in sorted(ratios, key=field_date):
            day = field_date(row)
            end_month = ((day.month - 1) // divisor + 1) * divisor
            # Use only completed calendar quarter/half-year buckets, not today's unfinished period.
            period_end = date(day.year, end_month, calendar.monthrange(day.year, end_month)[1])
            if period_end > as_of or (period_end - day).days > 10: continue
            value = first(row, key)
            if value is not None: buckets[(day.year, end_month)] = value
        positive = [value for value in buckets.values() if value > 0]
        d[f"own_5y_median_{key}"] = statistics.median(positive) if len(positive) >= 8 else None
        d.setdefault("benchmark_details", {})[f"own_5y_median_{key}"] = {
            "provider": "FinEdge", "scope": "own history", "method": "historical median",
            "positiveCount": len(positive), "minimumCount": 8,
            "value": d[f"own_5y_median_{key}"], "statementBasis": statement_type,
            "asOf": as_of.isoformat()}
    if group in ("BANK", "NBFC") and not any(v is not None for v in d["sales_q"]): warnings.append("Net interest income could not be derived; interest earned was not substituted.")
    warnings.extend(["Group fill values use the supplied October 2026 snapshot, not refreshed market medians.", "Historical filing availability and corporate-action alignment require point-in-time validation; this is a current assessment, not a historical backtest."])
    if quote_date:
        try:
            if (as_of - date.fromisoformat(quote_date)).days > 10:
                warnings.append("The reported market price is more than 10 calendar days old; coverage confidence does not measure freshness.")
        except ValueError:
            warnings.append("The market price date could not be verified.")
    owner_equity = first(current_b, "equityAttributableToOwnersOfParent")
    if owner_equity is not None and d["net_worth"] is not None and abs(d["net_worth"] - owner_equity / CR) > max(1e-6, abs(d["net_worth"]) * .001):
        warnings.append("The model uses total equity, including non-controlling interests, as specified. Provider P/B benchmarks may use owner-attributable equity and need basis reconciliation; they are not silently substituted for the model's book-equity definition.")
    valuation_checks = {}
    reported_ratio = next((row for row in sorted(ratios, key=field_date, reverse=True) if field_date(row).isoformat() == quote_date), {})
    eps4 = d["eps_q"][-4:]
    computed_pe = d["price"] / sum(eps4) if d["price"] is not None and len(eps4) == 4 and all(v is not None for v in eps4) and sum(eps4) > 0 else None
    computed_pb = d["price"] * d["shares"] / d["net_worth"] if all(d[k] is not None and d[k] > 0 for k in ("price", "shares", "net_worth")) else None
    for key, computed in (("pe", computed_pe), ("pb", computed_pb)):
        reported = first(reported_ratio, key)
        error = abs(computed / reported - 1) if computed is not None and reported is not None and reported > 0 else None
        valuation_checks[key] = {"computed": computed, "reported": reported, "relativeError": error, "asOf": quote_date if reported_ratio else None}
    d["valuation_unverified"] = [key for key, check in valuation_checks.items() if check["relativeError"] is not None and check["relativeError"] > .05]
    blockers, cautions = [], []
    solvency = num(d.get("solvency_ratio"))
    if group == "INSURANCE" and solvency is not None and 0 < solvency < .1:
        warnings.append("The reported solvency ratio has unverified units. Solvency is not used in this model version; the raw provider observation is retained for reconciliation.")
    if incomplete_prices:
        cautions.append("Invalid closing prices occur in the recent daily series. Returns across those gaps are excluded; complete-window drawdown and trading value remain unavailable where affected.")
    if defaulted:
        blockers.append("The model group could not be verified from the company classification.")
    if not end_q or (as_of - end_q).days > 200:
        cautions.append("Quarterly financials are missing or more than 200 days old.")
    try:
        market_day = date.fromisoformat(quote_date or "")
        if market_day > as_of or (as_of - market_day).days > 10:
            cautions.append("The market price is outside the permitted freshness window (10 calendar days).")
    except ValueError:
        cautions.append("The market price date is unverified.")
    if (inconsistent_quote or inconsistent_filing) and not reconciled_shares:
        cautions.append("Share-count discrepancies require corporate-action reconciliation.")
    if d["valuation_unverified"]:
        cautions.append("Calculated " + ", ".join(key.upper() for key in d["valuation_unverified"]) + " differs from the same-date provider ratio by more than 5%; review the valuation inputs; the model continues to use its documented calculated ratios.")
    d["rating_blockers"], d["rating_cautions"] = blockers, cautions
    warnings.extend(blockers + cautions)
    chronology = {"quarterly": [f"{key // 4}-{(key % 4) * 3 + 3:02d}" for key in qkeys], "annual": [str(year) for year in ykeys]}
    meta = {"groupDefaulted": defaulted, "statementType": statement_type, "quarterlyAsOf": end_q.isoformat() if end_q else None,
            "annualAsOf": max(a).isoformat() if a else None, "balanceAsOf": max(b).isoformat() if b else None,
            "ownershipAsOf": own_date.isoformat() if own_date else None, "priceAsOf": quote_date,
            "assetQualityStatementType": raw.get("asset_quality_basis", statement_type),
            "provenance": {key: sorted(value) for key, value in provenance.items()}, "chronology": chronology, "valuationChecks": valuation_checks}
    trends = [{"period": period, "revenue": d["sales_y"][i], "profit": d["net_profit_y"][i], "eps": eps(amap.get(ykeys[i], {}))} for i, period in enumerate(chronology["annual"])]
    return d, group, profile, meta, list(dict.fromkeys(warnings)), trends
