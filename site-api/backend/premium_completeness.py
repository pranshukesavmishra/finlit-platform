"""Explain unresolved dependencies of the factors actually used in a report.

No fetching, rescoring, replacement factors or changes to model coverage here.
An applicable factor can have an estimate, a limited history, or be excluded
because an input was not supplied. All three must remain visible to readers.
"""
try:
    from .premium_engine import num, recent
    from .premium_model_config import QUARTERS_STORED, QUARTERS_JUDGED
except ImportError:
    from premium_engine import num, recent
    from premium_model_config import QUARTERS_STORED, QUARTERS_JUDGED


def input_gaps(row, inputs, meta):
    metric = row['metric']
    info = row.get('details', {})
    gaps = []

    def scalar(key, label, positive=False):
        value = num(inputs.get(key))
        if value is None:
            gaps.append(label)
        elif positive and value <= 0:
            gaps.append(f'Positive {label.lower()} (reported {value:g})')

    def series(key, label, count, frequency='annual'):
        values = inputs.get(key, [])[-count:]
        periods = meta.get('chronology', {}).get(frequency, [])[-count:]
        # Identify the entire required window, including periods older than the
        # provider's first row, rather than only holes inside its returned range.
        if periods and len(periods) == len(values):
            try:
                if frequency == 'quarterly':
                    year, month = map(int,str(periods[-1]).split('-'))
                    end = year*4+(month-1)//3
                    periods = [f'{index//4}-{index%4*3+3:02d}' for index in range(end-count+1,end+1)]
                else:
                    end = int(periods[-1])
                    periods = [str(year) for year in range(end-count+1,end+1)]
                values = [None]*(count-len(values))+values
            except (ValueError,TypeError):
                pass
        absent = [str(periods[i]) for i,v in enumerate(values) if num(v) is None and len(periods) == len(values)]
        if len(values) < count or any(num(v) is None for v in values):
            suffix = '; missing periods: ' + ', '.join(absent) if absent else ''
            gaps.append(f'{label} ({sum(num(v) is not None for v in values)} of {count} observations available{suffix})')

    def pe():
        scalar('price','Market price',True)
        eps = inputs.get('eps_q', [])
        if len(eps) >= 4:
            series('eps_q','Trailing quarterly EPS',4,'quarterly')
        elif num(inputs.get('eps_ttm')) is None and num(inputs.get('eps_fy')) is None:
            gaps.append('Trailing EPS or latest annual EPS')

    if metric.endswith('_STREAK'):
        series('sales_q' if metric.startswith('SALES') else 'net_profit_q',
               'Quarterly income history' if metric.startswith('SALES') else 'Quarterly profit history',QUARTERS_STORED,'quarterly')
    elif metric in ('SALES_GROWTH','PROFIT_GROWTH'):
        if num(info.get('current')) is None: gaps.append('Current income comparison period' if metric.startswith('SALES') else 'Current profit comparison period')
        if num(info.get('previous')) is None: gaps.append('Matching previous income period' if metric.startswith('SALES') else 'Matching previous profit period')
    elif metric in ('SALES_CAGR','PROFIT_CAGR'):
        series('sales_y' if metric.startswith('SALES') else 'net_profit_y', 'Consecutive annual income' if metric.startswith('SALES') else 'Consecutive annual profit',2)
    elif metric == 'MARGIN_CHANGE':
        for key,label in (('sales_q','Quarterly income'),('operating_profit_q','Quarterly EBITDA')):
            now, before, _ = recent(inputs.get(key,[]),[])
            if now is None or before is None or (key == 'sales_q' and (now <= 0 or before <= 0)):
                gaps.append(f'{label} for matching current and prior margin periods')
    elif metric == 'INTEREST_COVER':
        scalar('profit_before_tax','Annual profit before tax')
        scalar('interest_cost','Annual P&L interest expense')
        if num(inputs.get('interest_cost')) is not None and num(inputs['interest_cost']) < 0:
            gaps.append('Non-negative annual interest expense (reported expense is negative)')
    elif metric in ('DEBT_TO_EQUITY','ROE','ROA','NETWORTH_GROWTH','LOAN_GROWTH'):
        specs = {'DEBT_TO_EQUITY': [('total_debt','Total borrowings',False),('net_worth','Book equity',True)],
                 'ROE':[('net_worth','Book equity',True)], 'ROA':[('total_assets','Total assets',True)],
                 'NETWORTH_GROWTH':[('net_worth','Latest book equity',False),('net_worth_1y_ago','Book equity at the matching date a year earlier',True)],
                 'LOAN_GROWTH':[('loans_now','Latest loan book',False),('loans_1y_ago','Loan book at the matching date a year earlier',True)]}
        for key,label,positive in specs[metric]: scalar(key,label,positive)
        if metric in ('ROE','ROA'): series('net_profit_y','Latest annual profit',1)
    elif metric == 'CASH_CONVERSION':
        series('net_profit_y','Matching annual profit',3)
        series('operating_cash_flow_y','Annual operating cash flow',3)
    elif metric.startswith(('PE_VS_','PB_VS_','EV_EBITDA_VS_')) or metric == 'PEG':
        if metric.startswith('PE_') or metric == 'PEG':
            pe()
        else:
            scalar('price','Market price',True)
            scalar('shares','Reconciled outstanding shares',True)
            if metric.startswith('PB_'): scalar('net_worth','Book equity',True)
            else:
                scalar('total_debt','Total borrowings')
                scalar('cash','Cash and bank balances')
                series('operating_profit_q','Trailing quarterly EBITDA',4,'quarterly')
        if metric == 'PEG':
            # The score decides eligibility and loss rules; do not reinterpret
            # either as a missing input. This branch is used only for F/L rows.
            if not gaps:
                gaps.append('Valid profit CAGR or recent profit-growth comparison')
        else:
            prefix = metric.split('_VS_')[0].lower()
            key = ('own_5y_median_' if metric.endswith('HISTORY') else 'industry_median_') + prefix
            scalar(key,'Own-history valuation benchmark' if metric.endswith('HISTORY') else 'Industry or sector valuation benchmark',True)
    else:
        spec = {'GROSS_NPA':('gross_npa_pct','Gross NPA disclosure'), 'NET_NPA':('net_npa_pct','Net NPA disclosure'),
                'PLEDGE':('promoter_pledged_pct','Promoter pledged-share disclosure'),
                'VOLATILITY':('volatility_pct','At least 60 valid daily price returns'),
                'BIGGEST_FALL':('biggest_fall_pct','Complete 250-session closing-price history'),
                'TRADING_VALUE':('trading_value_cr','Closing price and volume for the latest 60 sessions'),
                'CAPITAL_ADEQUACY':('capital_adequacy_pct','Capital adequacy disclosure'),
                'SOLVENCY':('solvency_ratio','Solvency disclosure')}.get(metric)
        if spec: scalar(*spec)
        risk = inputs.get('risk_calculation') or {}
        if gaps and metric in ('BIGGEST_FALL','TRADING_VALUE') and risk.get('sessions') is not None:
            n, bad = risk['sessions'], risk.get('invalidCloseLast250') if metric == 'BIGGEST_FALL' else risk.get('missingVolumeLast60')
            need = 250 if metric == 'BIGGEST_FALL' else 60
            why = f'the provider returned {n} trading sessions' + (f', {need} are needed' if n < need else '') + (f'; {bad} of the latest {need} have no valid ' + ('closing price' if metric == 'BIGGEST_FALL' else 'volume') if bad else '')
            gaps[-1] = f'{gaps[-1]} ({why})'
    return gaps or [info.get('note') or 'Compatible observations for this factor on the selected statement basis']


def build_input_completeness(report):
    inputs, rating = report.get('inputs',{}), report['rating']
    items = []
    for row in rating['metrics']:
        state, metric, info = row['status'], row['metric'], row.get('details',{})
        if state == 'N':
            continue
        missing = state in ('F','L') or row.get('points') is None
        limited = metric.endswith('_STREAK') and info.get('judged',QUARTERS_JUDGED) < QUARTERS_JUDGED
        if not missing and not limited:
            continue
        label = row['label']
        if metric.startswith('SALES'):
            subject = 'Net interest income' if rating['group'] in ('BANK','NBFC') else 'Net premium income' if rating['group'] == 'INSURANCE' else 'Revenue'
            label = label.replace('Sales',subject)
        kind = 'missing' if missing else 'limitedHistory'
        if missing:
            if state == 'F' and row.get('points') is not None:
                treatment = f"Group estimate used: {row['points']:g}/100."
            elif state == 'L':
                treatment = 'Excluded from scoring because the input is unavailable.'
            else:
                treatment = 'Factor cannot be calculated from available compatible inputs.'
        else:
            treatment = f"{info.get('judged',0)} of {QUARTERS_JUDGED} year-on-year comparisons available. "
            treatment += 'Current-loss rule applies to the remaining history.' if info.get('lossFill') else 'The remaining history uses the model group estimate.'
        gaps = input_gaps(row,inputs,report.get('inputMeta',{}))
        items.append({'metric':metric,'category':row['part'].title(),'label':label,'kind':kind,
                      'missingInputs':gaps,'reason':'; '.join(gaps)+'.','treatment':treatment})
    return {'complete':not items, 'missingFactorCount':sum(i['kind']=='missing' for i in items),
            'limitedHistoryCount':sum(i['kind']=='limitedHistory' for i in items),'items':items}
