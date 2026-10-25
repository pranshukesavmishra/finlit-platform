"""Shared dashboard/report resolution: FinEdge, derivation, Upstox, unavailable.

Financial observations retain their statement basis and units. Market risk uses
one complete exchange series; individual candles are never spliced across feeds.
"""
import calendar
from copy import deepcopy
from datetime import date
try:
    from .premium_data import items, field_date, first, CR, resolve_group, profile_from
    from .premium_engine import num
    from .financial_fields import INTEREST_COST_FIELDS
    from .premium_model_config import QUARTERS_STORED, CAGR_MAX_YEARS
except ImportError:
    from premium_data import items, field_date, first, CR, resolve_group, profile_from
    from premium_engine import num
    from financial_fields import INTEREST_COST_FIELDS
    from premium_model_config import QUARTERS_STORED, CAGR_MAX_YEARS


def period_end(label):
    from datetime import datetime
    try:
        day = datetime.strptime(str(label), '%b %Y').date()
        return day.replace(day=calendar.monthrange(day.year, day.month)[1])
    except (ValueError, TypeError):
        return None


def statement_rows(payload, basis, quarterly=False, cashflow=False):
    if not isinstance(payload, dict) or payload.get('type') != basis or payload.get('units_in') != 'crore':
        return []
    if payload.get('time_period') != ('quarterly' if quarterly else 'yearly'):
        return []
    aliases = {'Cash flow from Operations': ('cashFlowsFromOperatingActivities', CR)} if cashflow else {
        'Revenue': ('revenueFromOperations', CR), 'Profit After Tax': ('profitLossForPeriod', CR),
        'Profit Before Tax': ('profitBeforeTax', CR), 'Other Income': ('otherIncome', CR),
        'Finance Costs': ('financeCosts', CR), 'Interest Expense': ('financeCosts', CR),
        'Interest Expended': ('financeCosts', CR),
        'EPS - Basic': ('basicEPS', 1), 'EPS - Diluted': ('dilutedEPS', 1)}
    rows = {}
    # Upstox documents full_statement as annual even for quarterly requests.
    # Its operating_profit category is not assumed to be EBITDA or EPS.
    source = payload.get('income_statement', []) if quarterly else payload.get('full_statement', [])
    quarterly_aliases = {'revenue': ('revenueFromOperations', CR), 'net_profit': ('profitLossForPeriod', CR)}
    for item in source:
        spec = quarterly_aliases.get(item.get('category')) if quarterly else aliases.get(item.get('particular'))
        if not spec:
            continue
        for point in item.get('history', []):
            end, value = period_end(point.get('period')), num(point.get('value'))
            if not end or value is None:
                continue
            # The provider explicitly labels these observations quarterly/yearly.
            start_month = end.month - (2 if quarterly else 11)
            start_year = end.year
            if start_month <= 0:
                start_month += 12
                start_year -= 1
            row = rows.setdefault(end, {'period_end': end.isoformat(), 'period_start': date(start_year, start_month, 1).isoformat()})
            row[spec[0]] = value * spec[1]
    # The documented operating category is usable even when fs=true omits the
    # detailed line. It is net operating cash flow, never cash interest paid.
    if cashflow and not quarterly:
        for item in payload.get('cash_flow', []):
            if item.get('category') != 'operating':
                continue
            for point in item.get('history', []):
                end, value = period_end(point.get('period')), num(point.get('value'))
                if end and value is not None:
                    start = date(end.year if end.month == 12 else end.year-1, end.month % 12+1, 1)
                    row = rows.setdefault(end, {'period_end':end.isoformat(), 'period_start':start.isoformat()})
                    row.setdefault('cashFlowsFromOperatingActivities', value * CR)
    return list(rows.values())


def balance_rows(payload, basis):
    """Preserve only identified Upstox balance fields and reconciled equity."""
    if not isinstance(payload, dict) or payload.get('type') != basis or payload.get('units_in') != 'crore':
        return []
    rows = {}
    for item in payload.get('history', []):
        end = period_end(item.get('period'))
        if not end:
            continue
        row = rows.setdefault(end, {'period_end': end.isoformat()})
        for field, source in (('totalAssets','total_asset'),('totalLiabilities','total_liability')):
            value = num(item.get(source))
            if value is not None:
                row[field] = value * CR
    # "Equity Capital" is an aggregate in this feed; verify its accounting identity
    # rather than treating it as paid-up share capital or assuming missing debt=0.
    for item in payload.get('full_statement', []):
        if item.get('particular') not in ('Equity Capital','Total Equity'):
            continue
        for point in item.get('history', []):
            end, equity = period_end(point.get('period')), num(point.get('value'))
            row = rows.get(end, {})
            assets, liabilities = first(row,'totalAssets'), first(row,'totalLiabilities')
            if equity is not None and assets is not None and liabilities is not None and abs(assets-liabilities-equity*CR) <= max(CR*.02,abs(assets)*.0001):
                row['totalEquity'] = equity*CR
    return list(rows.values())


def derive_fourth_quarters(result, events):
    """Recover additive Q4 amounts from a full year and three matching quarters.

    EPS and balance-sheet stocks are deliberately excluded. An invalid source
    duration is replaced by a calculated observation, never relabelled as Q4.
    Call only on the same-basis FinEdge statements before provider recovery.
    """
    rows = items(result.get('quarterly'), 'financials', 'data')
    valid = {}
    for row in rows:
        end = field_date(row)
        start = field_date({'date': row.get('period_start') or row.get('periodStart')})
        if end and (not start or 70 <= (end-start).days+1 <= 105):
            valid[end] = row
    fields = (
        ('revenueFromOperations', ('netSales','sales','revenueFromOperations','incomeFromOperations')),
        ('profitLossForPeriod', ('profitLossForPeriod','profitLossForThePeriod','profitAfterTax','netProfit')),
        ('profitOrLossAttributableToOwners', ('profitOrLossAttributableToOwners','profitAttributableToOwnersOfParent')),
        ('profitBeforeTax', ('profitBeforeTax','profitLossBeforeTax')),
        ('financeCosts', INTEREST_COST_FIELDS),
        ('depreciation', ('depreciation','depreciationAndAmortisation','depreciationAndAmortization')),
        ('otherIncome', ('otherIncome',)), ('ebitda', ('ebitda','EBITDA')),
        ('netInterestIncome', ('netInterestIncome','netInterestRevenue','netInterestEarnings')),
        ('interestEarned', ('interestEarned','interestIncome')),
        ('netPremiumIncome', ('netPremiumIncome','netPremiumEarned','netPremium','netEarnedPremium')),
    )
    annuals = items(result.get('annual') or result.get('annual_for_quarter_recovery'), 'financials', 'data')
    for annual in annuals:
        end = field_date(annual)
        start = field_date({'date': annual.get('period_start') or annual.get('periodStart')})
        if not end or end.day != calendar.monthrange(end.year,end.month)[1]:
            continue
        expected_start = date(end.year if end.month == 12 else end.year-1, end.month%12+1, 1)
        if start != expected_start:
            continue
        dates = []
        for offset in (9,6,3):
            month = end.year*12+end.month-1-offset
            year, zero_month = divmod(month,12)
            dates.append(date(year,zero_month+1,calendar.monthrange(year,zero_month+1)[1]))
        if not all(day in valid for day in dates):
            continue
        original = valid.get(end)
        quarter = dict(original) if original else {'period_end':end.isoformat(), 'period_start':date(dates[-1].year if dates[-1].month < 12 else dates[-1].year+1,dates[-1].month%12+1,1).isoformat()}
        recovered=[]
        for target, aliases in fields:
            total=first(annual,*aliases)
            prior=[first(valid[day],*aliases) for day in dates]
            if first(quarter,*aliases) is None and total is not None and all(value is not None for value in prior):
                quarter[target]=total-sum(prior)
                recovered.append(target)
        if not recovered:
            continue
        publication_dates=[field_date({'date':row.get('result_date')}) for row in [annual]+[valid[day] for day in dates]]
        publication_dates=[day for day in publication_dates if day]
        if publication_dates:
            quarter['result_date']=max(publication_dates).isoformat()
        rows=[row for row in rows if field_date(row)!=end]+[quarter]
        valid[end]=quarter
        events.append(f'Calculated FinEdge quarterly {", ".join(recovered)} at {end} as same-basis full-year amounts minus the three matching quarters. EPS is not inferred from annual EPS.')
    if rows:
        result['quarterly']={'financials':rows}


def derive_finedge(raw):
    """Complete identities only; preserve direct values and zero observations."""
    result, events = deepcopy(raw), []
    for section in ('quarterly', 'annual', 'balance', 'balance_recent'):
        for row in items(result.get(section), 'financials', 'data'):
            def fill(target, aliases, parts, operation):
                if first(row, *aliases) is not None:
                    return
                values = [first(row, *names) for names in parts]
                if all(value is not None for value in values):
                    row[target] = operation(*values)
                    events.append(f'Calculated FinEdge {section} {target} at {field_date(row)} from ' + ', '.join('/'.join(names) for names in parts) + '; existing reported values take precedence.')
            fill('revenueFromOperations', ('revenueFromOperations','incomeFromOperations','netSales','sales','revenue'),
                 [('totalRevenue','totalIncome'), ('otherIncome',)], lambda total, other: total-other)
            fill('taxExpense', ('taxExpense','taxExpenses'), [('currentTax',),('deferredTax',)], lambda a,b:a+b)
            fill('profitLossForPeriod', ('profitLossForPeriod','profitLossForThePeriod','netProfit','profitAfterTax'),
                 [('profitBeforeTax','profitLossBeforeTax'),('taxExpense','taxExpenses')], lambda a,b:a-b)
            # Only explicit EBIT supports this identity. Generic operating
            # profit/EBITDA and cash-flow interest payments are not substitutes.
            ebit, pbt = first(row,'ebit','profitBeforeInterestAndTax'), first(row,'profitBeforeTax','profitLossBeforeTax')
            if ebit is not None and pbt is not None and ebit >= pbt:
                fill('financeCosts', INTEREST_COST_FIELDS,
                     [('ebit','profitBeforeInterestAndTax'),('profitBeforeTax','profitLossBeforeTax')], lambda a,b:a-b)
            if resolve_group(profile_from(raw))[0] in ('BANK','NBFC'):
                earned, nii = first(row,'interestEarned','interestIncome'), first(row,'netInterestIncome','netInterestRevenue','netInterestEarnings')
                if earned is not None and nii is not None and earned >= nii:
                    fill('interestExpended', INTEREST_COST_FIELDS,
                         [('interestEarned','interestIncome'),('netInterestIncome','netInterestRevenue','netInterestEarnings')], lambda a,b:a-b)
            fill('profitOrLossAttributableToOwners', ('profitAttributableToOwnersOfParent','profitOrLossAttributableToOwners','profitLossAttributableToOwnersOfParent','profitOrLossAttributableToOwnersOfParent'),
                 [('profitLossForPeriod','profitLossForThePeriod'),('nonControllingInterests','profitAttributableToNonControllingInterests')], lambda a,b:a-b)
            fill('totalEquity', ('totalEquity','shareholdersEquity','netWorth','equity'),
                 [('equityAttributableToOwnersOfParent',),('nonControllingInterest','nonControllingInterests')], lambda a,b:a+b)
            fill('totalAssets', ('totalAssets','totalAsset','assets'),
                 [('currentAssets','totalCurrentAssets'),('nonCurrentAssets','noncurrentAssets','totalNonCurrentAssets')], lambda a,b:a+b)
            fill('totalLiabilities', ('totalLiabilities','totalLiability','liabilities'),
                 [('currentLiabilities','totalCurrentLiabilities'),('nonCurrentLiabilities','noncurrentLiabilities','totalNonCurrentLiabilities')], lambda a,b:a+b)
            fill('totalEquity', ('totalEquity','shareholdersEquity','netWorth','equity'),
                 [('totalAssets','totalAsset','assets'),('totalLiabilities','totalLiability','liabilities')], lambda a,b:a-b)
            fill('borrowings', ('borrowings','totalBorrowings','totalDebt'),
                 [('shortTermBorrowings','borrowingsCurrent'),('longTermBorrowings','borrowingsNoncurrent')], lambda a,b:a+b)
            fill('depreciation', ('depreciation','depreciationAndAmortisation','depreciationAndAmortization'),
                 [('depreciationExpense',),('amortisationExpense','amortizationExpense')], lambda a,b:a+b)
            fill('ebitda', ('ebitda','EBITDA'), [('ebit','profitBeforeInterestAndTax'),('depreciation','depreciationAndAmortisation','depreciationAndAmortization')], lambda a,b:a+b)
            fill('ebitda', ('ebitda','EBITDA'), [('profitBeforeTax','profitLossBeforeTax'),INTEREST_COST_FIELDS,('depreciation','depreciationAndAmortisation','depreciationAndAmortization'),('otherIncome',)], lambda a,b,c,d:a+b+c-d)
    quarters = {}
    for point in items(result.get('quarterly'),'financials','data'):
        end = field_date(point)
        start = field_date({'date': point.get('period_start') or point.get('periodStart')})
        if end and (not start or 70 <= (end-start).days+1 <= 105):
            quarters[end] = point
    for row in items(result.get('annual'),'financials','data'):
        end = field_date(row)
        if not end:
            continue
        dates = []
        for offset in (0,3,6,9):
            month = end.month-offset
            year = end.year
            if month <= 0:
                month += 12
                year -= 1
            dates.append(date(year,month,calendar.monthrange(year,month)[1]))
        if all(day in quarters for day in dates):
            for target, aliases in (
                ('revenueFromOperations',('netSales','sales','revenueFromOperations','incomeFromOperations')),
                ('profitLossForPeriod',('profitLossForPeriod','profitLossForThePeriod','profitAfterTax','netProfit')),
                ('profitOrLossAttributableToOwners',('profitOrLossAttributableToOwners','profitAttributableToOwnersOfParent')),
                ('depreciation',('depreciation','depreciationAndAmortisation','depreciationAndAmortization')),
                ('financeCosts',INTEREST_COST_FIELDS),
                ('interestEarned',('interestEarned','interestIncome')),
                ('netInterestIncome',('netInterestIncome','netInterestRevenue','netInterestEarnings')),
                ('netPremiumIncome',('netPremiumIncome','netPremiumEarned','netPremium','netEarnedPremium'))):
                values = [first(quarters[day],*aliases) for day in dates]
                if first(row,*aliases) is None and all(v is not None for v in values):
                    row[target] = sum(values)
                    events.append(f'Calculated FinEdge annual {target} at {end} from four matching same-basis quarters.')
    # Match annual depreciation to its same-date cash-flow disclosure before Upstox.
    cash = {field_date(r): r for r in items(result.get('cashflow'),'financials','data')}
    for row in items(result.get('annual'),'financials','data'):
        if first(row,'depreciation','depreciationAndAmortisation','depreciationAndAmortization') is None:
            value = first(cash.get(field_date(row), {}),'adjForDepreciationAndAmortisationExpense','depreciationAndAmortisation','depreciation')
            if value is not None:
                row['depreciation'] = value
                events.append(f'Calculated FinEdge annual depreciation at {field_date(row)} from the matching cash-flow statement.')
    derive_fourth_quarters(result, events)
    return result, list(dict.fromkeys(events))


def recover_balance_inputs(result, basis, as_of, load, events):
    """Fill only compatible dated balance fields, preserving the accounting identity."""
    annual = items(result.get('annual'), 'financials', 'data')
    # Partial balance sheets need the same fallback as entirely absent ones.
    # Recover dated assets/liabilities and reconciled total equity; never infer
    # debt from liabilities or use an older annual balance as the latest quarter.
    balances = items(result.get('balance'),'financials','data')
    targets = {field_date(r) for r in annual if field_date(r) and field_date(r) <= as_of}
    dated_balances = {field_date(r):r for r in balances if field_date(r) and field_date(r) <= as_of}
    if dated_balances:
        targets.add(max(dated_balances))
    balance_aliases = {'totalAssets':('totalAssets','totalAsset','assets'),
                       'totalLiabilities':('totalLiabilities','totalLiability','liabilities'),
                       'totalEquity':('totalEquity','shareholdersEquity','netWorth','equity')}
    if targets and any(any(first(dated_balances.get(day,{}),*balance_aliases[k]) is None for k in ('totalAssets','totalEquity')) for day in targets):
        recovered = []
        for row in balance_rows(load('balance'),basis):
            end = field_date(row)
            if end not in targets or end > as_of:
                continue
            old = dated_balances.get(end)
            if old is None:
                old = {'period_end':end.isoformat()}
                balances.append(old)
                dated_balances[end] = old
            fields = [key for key in balance_aliases if key in row and first(old,*balance_aliases[key]) is None]
            if fields:
                candidate = {key:first(old,*names) if first(old,*names) is not None else row.get(key) for key,names in balance_aliases.items()}
                assets, liabilities, equity = (candidate[k] for k in ('totalAssets','totalLiabilities','totalEquity'))
                if all(value is not None for value in (assets,liabilities,equity)) and abs(assets-liabilities-equity) > max(CR*.02,abs(assets)*.0001):
                    events.append(f'Upstox balance at {end} conflicts with the retained FinEdge accounting identity; missing fields remain unavailable.')
                    continue
                old.update({key:row[key] for key in fields})
                recovered.append(end.isoformat()+' ['+', '.join(fields)+']')
        if recovered:
            result['balance'] = {'financials':balances}
            events.append(f'Upstox balance ({basis}, crore): recovered periods {", ".join(sorted(recovered))}; only matching dated balances used.')


def recover_inputs(raw, basis, as_of, load, period="yearly", recover_prices=True):
    """Optional loader(section) returns a verified identity's Upstox payload."""
    result, events = derive_finedge(raw)
    equivalents = {
        'revenueFromOperations': ('revenueFromOperations', 'incomeFromOperations', 'revenue', 'totalRevenue'),
        'profitLossForPeriod': ('profitAttributableToOwnersOfParent', 'profitOrLossAttributableToOwners', 'profitLossAttributableToOwnersOfParent', 'profitOrLossAttributableToOwnersOfParent', 'profitLossForPeriod', 'profitLossForThePeriod', 'netProfitAfterTax', 'profitAfterTax', 'netProfit', 'profitLossAfterTaxAndExtraordinaryItems', 'profitLossAfterTaxBeforeExtraordinaryItems'),
        'cashFlowsFromOperatingActivities': ('netCashFromOperatingActivities', 'cashFromOperatingActivity', 'cashFlowsFromOperatingActivities', 'cashFlowFromOperatingActivities', 'operatingCashFlow'),
        'basicEPS': ('basicEPS', 'basicEps', 'basicReInr', 'basicREInr', 'basicEPSInRs', 'eps', 'dilutedEPS', 'dilutedReInr'),
        'dilutedEPS': ('basicEPS', 'basicEps', 'basicReInr', 'basicREInr', 'basicEPSInRs', 'eps', 'dilutedEPS', 'dilutedReInr'),
        'profitBeforeTax': ('profitBeforeTax', 'profitLossBeforeTax'),
        'otherIncome': ('otherIncome',),
        'financeCosts': INTEREST_COST_FIELDS,
    }
    def fetch(section):
        try:
            return load(section)
        except Exception:
            events.append(f'Upstox {section} fallback unavailable; original missing inputs remain disclosed.')
            return None
    def merge(section, payload, quarterly=False, cashflow=False):
        existing = items(result.get(section), 'financials', 'data')
        current = {field_date(r): r for r in existing if field_date(r)}
        recovered = []
        for row in statement_rows(payload, basis, quarterly, cashflow):
            if resolve_group(profile_from(raw))[0] in ('BANK','NBFC','INSURANCE'):
                row.pop('revenueFromOperations', None)
            if len(row) <= 2:
                continue
            end = field_date(row)
            # Publication dates are unavailable: do not use future periods or
            # claim point-in-time availability for these provider observations.
            if not end or end > as_of:
                continue
            old = current.get(end)
            bad_duration = False
            if old and old.get('period_start'):
                start = field_date({'date': old['period_start']})
                bad_duration = bool(start and not (70 if quarterly else 330) <= (end-start).days+1 <= (105 if quarterly else 400))
            if old and not bad_duration:
                # Keep all actuals, including zero and alternate field names.
                fields = [k for k in row if k in equivalents and first(old, *equivalents[k]) is None]
                if fields:
                    old.update({k: row[k] for k in fields})
                    recovered.append(end.isoformat() + ' [' + ', '.join(fields) + ']')
                continue
            if old:
                existing.remove(old)
            existing.append(row)
            recovered.append(end.isoformat())
        if recovered:
            result[section] = {'financials': existing}
            events.append(f'Upstox {section} ({basis}, crore): recovered periods {", ".join(sorted(recovered))}. Annual/quarterly labels are provider reported; publication dates are unavailable, so this is not point-in-time backtest data.')
    section = 'annual' if period == 'yearly' else 'quarterly'
    annual = items(result.get(section), 'financials', 'data')
    def income_gaps(rows):
        quarterly = period == 'quarterly'
        count = QUARTERS_STORED if quarterly else CAGR_MAX_YEARS + 1
        valid = {}
        for row in rows:
            end = field_date(row)
            start = field_date({'date': row.get('period_start') or row.get('periodStart')})
            reported = field_date({'date': row.get('result_date')})
            if not end or end > as_of or (reported and reported > as_of):
                continue
            if start and not (70 if quarterly else 330) <= (end-start).days+1 <= (105 if quarterly else 400):
                continue
            valid[end] = row
        recent = sorted(valid, reverse=True)[:count]
        if len(recent) < count:
            return True
        periods = [day.year * 4 + (day.month - 1)//3 if quarterly else day.year for day in recent]
        if len(set(periods)) < count or max(periods)-min(periods)+1 != count:
            return True
        fin = resolve_group(profile_from(raw))[0] in ('BANK','NBFC','INSURANCE')
        for day in recent:
            row = valid[day]
            if first(row,*equivalents['profitLossForPeriod']) is None:
                return True
            if not fin and first(row,*equivalents['revenueFromOperations']) is None:
                return True
            if not quarterly and first(row,*equivalents['basicEPS']) is None:
                return True
        # PBT is required for interest coverage even with complete profit,
        # revenue and EPS histories. A missing expense must not suppress this
        # provider attempt. Upstox still needs an explicit matching line item.
        latest = valid[recent[0]]
        if not quarterly and (first(latest,'profitBeforeTax','profitLossBeforeTax') is None or
                              first(latest,*INTEREST_COST_FIELDS) is None):
            return True
        return False
    # Only absent observations are fetched; generic revenue cannot replace NII.
    if income_gaps(annual):
        merge(section, fetch(section), quarterly=period == 'quarterly')
    annual = items(result.get('annual'), 'financials', 'data')
    cf = items(raw.get('cashflow'), 'financials', 'data')
    cf_dates = {field_date(r) for r in cf if first(r, 'netCashFromOperatingActivities', 'cashFromOperatingActivity', 'cashFlowsFromOperatingActivities', 'cashFlowFromOperatingActivities', 'operatingCashFlow') is not None and (not r.get('period_start') or (field_date(r) and field_date({'date':r['period_start']}) and 330 <= (field_date(r)-field_date({'date':r['period_start']})).days+1 <= 400))}
    if any(field_date(r) not in cf_dates for r in sorted(annual, key=lambda r: field_date(r) or date.min, reverse=True)[:3]):
        merge('cashflow', fetch('cashflow'), cashflow=True)
    recover_balance_inputs(result, basis, as_of, fetch, events)
    prices = sorted((r for r in items(raw.get('prices'), 'price','quotes','data') if field_date(r) and field_date(r) <= as_of), key=field_date)
    invalid = len(prices) < 251 or any((first(r,'close_price','close','adjClose') or 0) <= 0 for r in prices[-251:]) or any(first(r,'volume','tradedVolume') is None for r in prices[-60:])
    if invalid and recover_prices:
        payload = fetch('prices')
        candles = payload.get('prices', []) if isinstance(payload, dict) else []
        candles = sorted({field_date(r): r for r in candles if field_date(r) and field_date(r) <= as_of}.values(), key=field_date)
        if len({field_date(r) for r in candles[-251:]}) == 251 and all((first(r,'close') or 0) > 0 for r in candles[-251:]) and all(first(r,'volume') is not None and first(r,'volume') >= 0 for r in candles[-60:]) and (as_of-field_date(candles[-1])).days <= 10:
            result['prices'] = {'price': candles}
            events.append(f'Risk inputs use one complete Upstox {payload.get("exchange", "exchange")} daily series ({payload.get("instrumentKey", "")}), {field_date(candles[-251])} to {field_date(candles[-1])}; 251 closes and 60 volume observations. FinEdge quote and financials remain their original source. Exchange prices and volumes can differ; corporate-action adjustment is not independently verified.')
    # Apply the same period validity rules to dashboard and report tables.
    for section, quarterly in (('annual',False),('quarterly',True),('cashflow',period == 'quarterly')):
        payload = result.get(section)
        if not isinstance(payload, dict) or 'financials' not in payload:
            continue
        selected = {}
        for row in payload['financials']:
            end = field_date(row)
            start = field_date({'date': row.get('period_start') or row.get('periodStart')})
            reported = field_date({'date': row.get('result_date')})
            if end is None or end > as_of or (reported and reported > as_of):
                continue
            if start and not (70 if quarterly else 330) <= (end-start).days+1 <= (105 if quarterly else 400):
                events.append(f'FinEdge {section} period ending {end} remains unavailable: inconsistent duration and no verified same-period recovery.')
                continue
            previous = selected.get(end)
            if previous is None or str(row.get('result_date') or '') >= str(previous.get('result_date') or ''):
                selected[end] = row
        result[section] = {'financials': list(selected.values())}
    return result, events
