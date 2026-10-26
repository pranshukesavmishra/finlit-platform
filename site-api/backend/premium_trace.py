"""Explanations of a saved scoring run. No fetching or rescoring in this module."""
try:
    from .premium_engine import complete_sum, num
    from .premium_model_config import TRADING_VALUE_STEPS
except ImportError:
    from premium_engine import complete_sum, num
    from premium_model_config import TRADING_VALUE_STEPS


def fmt(value):
    return f'{value:,.4f}'.rstrip('0').rstrip('.') if isinstance(value, (int, float)) else 'N/A'


def divide(a, b):
    return a / b if a is not None and b is not None and b > 0 else None


def build_calculation_trace(d, rating, meta):
    """Persist the inputs, equations and arithmetic with the rating that produced them."""
    chronology = meta.get('chronology', {})
    quarterly = [{'period': period, **{key: (d.get(series, [])[i] if i < len(d.get(series, [])) else None)
                  for key, series in [('sales','sales_q'),('profit','net_profit_q'),('ebitda','operating_profit_q'),('eps','eps_q')]}}
                 for i, period in enumerate(chronology.get('quarterly', []))]
    annual = [{'period': period, **{key: (d.get(series, [])[i] if i < len(d.get(series, [])) else None)
               for key, series in [('sales','sales_y'),('profit','net_profit_y'),('cashFlow','operating_cash_flow_y'),('netWorth','net_worth_y')]}}
              for i, period in enumerate(chronology.get('annual', []))]
    eps = complete_sum(d.get('eps_q', []),4) if len(d.get('eps_q', [])) >= 4 else num(d.get('eps_ttm'))
    if eps is None and len(d.get('eps_q', [])) < 4: eps = num(d.get('eps_fy'))
    price, shares, nw, debt, cash = (num(d.get(k)) for k in ('price','shares','net_worth','total_debt','cash'))
    market_cap = price * shares if price is not None and shares is not None else None
    ev = market_cap + debt - cash if all(v is not None for v in (market_cap,debt,cash)) else None
    ebitda = complete_sum(d.get('operating_profit_q',[]),4)
    pe, pb, ev_ebitda = divide(price,eps), divide(market_cap,nw), divide(ev,ebitda)
    values = dict(d, eps_ttm=eps, pe=pe, pb=pb, market_cap=market_cap, ev=ev, ev_ebitda=ev_ebitda)
    latest_specs = [('price','Price','INR/share'),('eps_ttm','Trailing EPS','INR/share'),('pe','P/E','x'),
        ('own_5y_median_pe','Own 5-year P/E median','x'),('industry_median_pe','Industry P/E median','x'),('pb','P/B','x'),
        ('own_5y_median_pb','Own 5-year P/B median','x'),('industry_median_pb','Industry P/B median','x'),
        ('ev_ebitda','EV/EBITDA','x'),('industry_median_ev_ebitda','Industry EV/EBITDA median','x'),
        ('market_cap','Market capitalisation','Cr'),('ev','Enterprise value','Cr'),('total_debt','Total debt','Cr'),
        ('cash','Cash and bank balances','Cr'),('net_worth','Latest book equity','Cr'),('shares','Shares including reconciled receipts','Cr shares'),
        ('profit_before_tax','Last FY profit before tax','Cr'),('interest_cost','Last FY interest cost','Cr'),
        ('annual_net_worth','Book equity matching annual profit','Cr'),('annual_total_assets','Assets matching annual profit','Cr'),
        ('volatility_pct','Annualised volatility','%'),('biggest_fall_pct','Maximum one-year drawdown','%'),
        ('trading_value_cr','Average daily trading value','Cr'),('promoter_pledged_pct','Promoter pledged shares','%')]
    latest = [{'key':key,'label':label,'value':values.get(key),'unit':unit} for key,label,unit in latest_specs]
    for row in latest:
        info = d.get('benchmark_details', {}).get(row['key'], {})
        if info.get('scope') == 'sector':
            ratio = {'industry_median_pe':'P/E', 'industry_median_pb':'P/B', 'industry_median_ev_ebitda':'EV/EBITDA'}.get(row['key'])
            if ratio: row['label'] = f'Upstox sector {ratio} benchmark'
    rows=[]
    for row in rating['metrics']:
        metric, info, state = row['metric'], row.get('details',{}), row['status']
        formula='Reported input from the selected statement basis.'
        if metric.endswith('_STREAK'):
            j, good, slips = info.get('judged',0), info.get('good',0), info.get('slips',0)
            formula = f'YoY comparisons: {good} good, {slips} forgiven slips, {j} judged. Strict growth means current quarter > same quarter last year. Two consecutive failures end the run.'
            if metric == 'PROFIT_STREAK' and rating.get('loss'):
                formula += ' A good profit quarter must also have positive net profit.'
            scoring = (f'Base = max(0, 10 x {good} - 5 x {slips}) x 10 / {j} = {fmt(info.get("base"))}. '
                       f'Magnitude = median growth points of good quarters = {fmt(info.get("magnitudePoints"))}. '
                       f'Own = base x (0.8 + 0.2 x magnitude / 100) = {fmt(info.get("ownPoints"))}. '
                       f'Short-history blend = own x {j}/10 + {fmt(info.get("fillPoints"))} x (1 - {j}/10) = {fmt(row["points"])}.') if j else 'No judgeable comparisons; group fill applies.'
        else:
            scoring = f'clamp(({fmt(row["value"])} - {fmt(row.get("worst"))}) / ({fmt(row.get("best"))} - {fmt(row.get("worst"))}) x 100, 0, 100) = {fmt(row["points"])} points.'
            if metric.endswith('_GROWTH') and 'current' in info:
                formula=f'({fmt(info.get("current"))} / {fmt(info.get("previous"))} - 1) x 100 = {fmt(row["value"])}%. {info.get("basis", "")}'
            elif metric.endswith('_CAGR'):
                years=info.get('years',0)
                formula=(f'({fmt(info.get("current"))} / {fmt(info.get("previous"))})^(1/{years}) - 1, then x 100 = {fmt(row["value"])}%. Uses the latest {years+1} consecutive year-ends ({years} years); preference is 5 years, then 3, then available.'
                         if years else 'CAGR unavailable: at least two consecutive annual observations ending in the latest financial year are required.')
            elif metric == 'MARGIN_CHANGE':
                sales=d.get('sales_q',[]); op=d.get('operating_profit_q',[])
                if len(sales)>=8:
                    sn,so,on,oo=complete_sum(sales,4),complete_sum(sales[-8:-4],4),complete_sum(op,4),complete_sum(op[-8:-4],4)
                else:
                    sn,so = (sales[-1],sales[-5]) if len(sales)>=5 else (None,None)
                    on,oo = (op[-1],op[-5]) if len(op)>=5 else (None,None)
                formula=f'(({fmt(on)} / {fmt(sn)}) - ({fmt(oo)} / {fmt(so)})) x 100 = {fmt(row["value"])} percentage points. Operating profit uses EBITDA; current and comparison periods match.'
            elif metric in ('LOAN_GROWTH','NETWORTH_GROWTH'):
                a,b = ('loans_now','loans_1y_ago') if metric=='LOAN_GROWTH' else ('net_worth','net_worth_1y_ago')
                formula=f'({fmt(d.get(a))} / {fmt(d.get(b))} - 1) x 100 = {fmt(row["value"])}%. Exact same reporting date a year earlier.'
            elif metric=='DEBT_TO_EQUITY': formula=f'Total debt / book equity = {fmt(debt)} / {fmt(nw)} = {fmt(row["value"])}x.'
            elif metric=='FINANCIAL_LEVERAGE': formula=f'Total assets / book equity = {fmt(d.get("total_assets"))} / {fmt(nw)} = {fmt(row["value"])}x. Lower means less borrowed money behind the assets.'
            elif metric=='INTEREST_COVER': formula=f'(Annual PBT + interest cost) / interest cost = ({fmt(d.get("profit_before_tax"))} + {fmt(d.get("interest_cost"))}) / {fmt(d.get("interest_cost"))} = {fmt(row["value"])}x.'
            elif metric in ('ROE','ROA'):
                profit = d.get('net_profit_y',[])[-1] if d.get('net_profit_y') else None
                denominator = nw if metric=='ROE' else d.get('total_assets')
                formula=f'Last FY owner-attributable profit / latest {"equity" if metric=="ROE" else "assets"} x 100 = {fmt(profit)} / {fmt(denominator)} x 100 = {fmt(row["value"])}%.'
            elif metric=='CASH_CONVERSION': formula=f'Sum of latest 3 annual operating cash flows / sum of matching annual profits = {fmt(complete_sum(d.get("operating_cash_flow_y",[]),3))} / {fmt(complete_sum(d.get("net_profit_y",[]),3))} = {fmt(row["value"])}x.'
            elif metric.startswith(('PE_VS_','PB_VS_','EV_EBITDA_VS_')):
                key = 'pe' if metric.startswith('PE_') else 'pb' if metric.startswith('PB_') else 'ev_ebitda'
                current=values.get(key)
                benchmark=d.get('own_5y_median_'+key) if metric.endswith('HISTORY') and state!='S' else d.get('industry_median_'+key)
                base = f'P/E = {fmt(price)} / {fmt(eps)} = {fmt(pe)}x.' if key=='pe' else f'P/B = ({fmt(price)} x {fmt(shares)}) / {fmt(nw)} = {fmt(pb)}x.' if key=='pb' else f'EV/EBITDA = ({fmt(market_cap)} + {fmt(debt)} - {fmt(cash)}) / {fmt(ebitda)} = {fmt(ev_ebitda)}x.'
                formula=f'{base} Relative multiple = {fmt(current)} / {fmt(benchmark)} = {fmt(row["value"])}x.'
            elif metric=='PEG': formula=f'P/E / positive profit growth capped at 40% = {fmt(pe)} / {fmt(info.get("growthUsed"))} = {fmt(row["value"])}. {info.get("note", "")}'
            elif metric=='VOLATILITY':
                risk=d.get('risk_calculation',{})
                formula=f'Sample daily-return standard deviation x sqrt(250) x 100 = {fmt(risk.get("dailyStdDev"))} x sqrt(250) x 100 = {fmt(row["value"])}%. Uses {risk.get("returnCount","available")} valid returns, minimum 60; missing sessions are not bridged.'
            elif metric=='BIGGEST_FALL': formula=f'Maximum of (1 - close / running peak) x 100 over a complete 250-session window = {fmt(row["value"])}%.'
            elif metric=='TRADING_VALUE':
                formula=f'Mean(close x volume) over the latest 60 complete sessions / 10,000,000 = {fmt(row["value"])} crore.'
                scoring='Step table (Cr >= threshold): '+', '.join(f'{threshold}: {points} points' for threshold,points in TRADING_VALUE_STEPS)+f'. Result = {fmt(row["points"])} points.'
            elif metric=='PLEDGE': formula=f'Pledged promoter shares / total promoter shares x 100 = {fmt(row["value"])}%. Explicit no-pledge declarations support zero; unknown pledge is excluded.'
            elif metric in ('GROSS_NPA','NET_NPA','CAPITAL_ADEQUACY'): formula=f'Reported ratio fraction x 100 = {fmt(row["value"])}%. Unavailable placeholders are excluded; CET1 is not total capital adequacy.'
            elif metric=='SOLVENCY': formula=f'Reported solvency ratio = {fmt(row["value"])}x.'
        if state=='F': scoring=f'Input unavailable: group fill {fmt(row["points"])} points (snapshot {rating["fillVersion"]}). Counts as missing in input coverage.'
        elif state in ('N','L'): scoring='Excluded from the component denominator. '+info.get('note', 'Not supplied.' if state=='L' else 'Not applicable.')
        elif state=='Z' or (row['value'] is None and row['points'] is not None):
            scoring=f'Special rule: {info.get("note") or "Non-positive denominator or zero interest cost under model rules"}. Assigned {fmt(row["points"])} points; linear scaling does not apply.'
        if info.get('note'): formula += ' '+info['note']
        if metric == 'PROFIT_STREAK' and info.get('lossFill') and not j:
            scoring = 'Current profit is non-positive and no quarter is judgeable; the loss rule assigns 0 points.'
        if row.get('fallbackFor'): formula += ' Replaces unavailable '+row['fallbackFor']+' in the same scoring slot.'
        rows.append({'metric':metric,'part':row['part'],'label':row['label'],'state':state,'valueCalculation':formula,'pointsCalculation':scoring,'points':row['points'],'weight':row['weight'],'share':row['share'],'worst':row.get('worst'),'best':row.get('best'),'value':row.get('value'),'unit':row.get('unit')})
    parts=[]
    rated=rating['status']!='NOT RATED'
    for part,weight in rating['partWeights'].items():
        members=[r for r in rating['metrics'] if r['part']==part and r['status'] not in ('N','L')]
        denominator=sum(r['weight'] for r in members)
        terms=' + '.join(f'{fmt(r["weight"])} x {fmt(r["points"])}' for r in members)
        raw=sum(r['weight']*(r['points'] or 0) for r in members)/denominator if denominator else None
        formula=f'({terms}) / {fmt(denominator)} = {fmt(raw)}.' if rated else 'Weighted mean of eligible metric points; component result withheld for this unrated report.'
        if rated and part=='fundamental' and rating.get('lossCapped'):
            formula += f' Loss cap ({rating["loss"]["tier"]}): min({fmt(raw)}, {fmt(rating["loss"]["cap"])}) = {fmt(rating["parts"][part])}.'
        if rated and part=='valuation' and rating.get('valuationCapped'): formula+=f' Weak-business cap: min({fmt(raw)}, 60) = 60.'
        parts.append({'part':part,'weight':weight,'denominator':denominator,'calculation':formula,'score':rating['parts'][part] if rated else None})
    active=sum(weight for part,weight in rating['partWeights'].items() if rating['parts'][part] is not None)
    terms=' + '.join(f'{fmt(weight)} x {fmt(rating["parts"][part])}' for part,weight in rating['partWeights'].items() if rating['parts'][part] is not None)
    return {'version':2,'quarterly':quarterly,'annual':annual,'latest':latest,'metrics':rows,'parts':parts,
            'finalCalculation':f'({terms}) / {fmt(active)} = {fmt(rating["final"])} -> {rating["label"]} ({rating["status"]}).' if rated else 'Overall score withheld: '+rating['headline'],
            'coverageCalculation':' + '.join(f'{fmt(weight)} x {fmt(rating["coverage"][part])}' for part,weight in rating['partWeights'].items())+f' = {rating["confidence"]:.2%} input coverage.',
            'notes':(['Source priority shared with Stock Fundamentals: FinEdge reported data, calculations from available FinEdge inputs, Upstox fallback, then N/A. Model fills remain explicitly labelled scoring assumptions.'] if meta.get('dashboardSources') else []) + ['All financial amounts and shares use crore units; EPS and prices use INR per share. Missing values are not zero.',
                     'Calendar period labels identify reporting periods. Filing availability and retrieval dates are recorded separately.',
                     'Scale = clamp((value - worst) / (best - worst) x 100, 0, 100). Lower-is-better metrics have best below worst.',
                     'Component denominator excludes N and L metrics, retains filled and loss-rule metrics. Missing pledge still reduces input coverage.',
                     'PEG is core for LIGHT/MFG; other groups require at least 6 actual good profit quarters, with growth capped at 40%. Loss/non-positive-growth rules retain their weight.',
                     'For non-financial groups, debt/equity below 0.1 excludes interest cover. BANK, NBFC and INSURANCE always score interest cover in Quality, replacing capital adequacy/solvency; missing inputs remain filled. Missing own valuation history substitutes an available positive industry median. Missing metrics use min(group median points, 50), except unknown pledge which is excluded.',
                     'Current non-positive profit scores zero for profit growth and profit CAGR. A good profit-streak quarter must be profitable; a short loss-making record blends with zero. Non-positive current operating margin scores zero for margin change.',
                     'Loss severity and group family may cap Fundamental first. If Fundamental or Quality is then below 35, Valuation is capped at 60. Both adjustments are applied before the final weighted mean.',
                     'Coverage below 80% or fewer than 6 comparable quarters: provisional; below 50%: unrated. Data-quality review flags are displayed separately from the model rating; unverified group classification prevents a valid rating.']}
