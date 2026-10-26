from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path
from pypdf import PdfReader
import pytest
from backend.premium_data import adapt_inputs
from backend.premium_engine import score_company
from backend.premium_trace import build_calculation_trace
from backend.premium_pdf import render_premium_pdf
from backend import premium_service

DATA=json.loads((Path(__file__).parent/'fixtures'/'premium_stock_audit_2026_10_18.json').read_text())


def report_for(stock):
    d,g,profile,meta,warnings,trends=adapt_inputs(stock['raw'],stock['symbol'],date(2026,10,18),'consolidated')
    rating=score_company(d,g)
    return {'id':'b'*32,'company':{'symbol':stock['symbol'],'name':profile.get('name') or stock['symbol'],'industry':profile.get('industry')},
            'createdAt':'2026-10-18T04:30:00+00:00','statementType':'consolidated','rating':rating,'inputs':d,'inputMeta':meta,
            'warnings':warnings,'trends':trends,'benchmark':{},'sources':[],'inputHash':'f'*64,
            'calculationTrace':build_calculation_trace(d,rating,meta)}


@pytest.mark.parametrize('stock',DATA['stocks'],ids=lambda s:s['symbol'])
def test_trace_covers_every_used_metric_and_parameter_without_changing_score(stock):
    report=report_for(stock); trace=report['calculationTrace'];rating=report['rating']
    assert len(trace['quarterly'])==len(report['inputs']['sales_q'])
    assert len(trace['annual'])==len(report['inputs']['sales_y'])
    assert [r['metric'] for r in trace['metrics']]==[r['metric'] for r in rating['metrics']]
    assert trace['quarterly'][0]['sales']==report['inputs']['sales_q'][0]
    for actual,source in zip(trace['metrics'],rating['metrics']):
        for key in ('weight','share','worst','best','points','value'):assert actual[key]==source[key]
        assert actual['valueCalculation'] and actual['pointsCalculation']
    for part in trace['parts']:
        assert part['denominator']==sum(r['weight'] for r in rating['metrics'] if r['part']==part['part'] and r['status'] not in ('N','L'))
    if rating['status']=='NOT RATED':
        assert 'withheld' in trace['finalCalculation'].lower()
        assert all(part['score'] is None for part in trace['parts'])
    else:
        assert all(part['score']==rating['parts'][part['part']] for part in trace['parts'])
    before=deepcopy(rating)
    build_calculation_trace(report['inputs'],rating,report['inputMeta'])
    assert rating==before
    json.dumps(trace,allow_nan=False)


@pytest.mark.parametrize('stock',DATA['stocks'],ids=lambda s:s['symbol'])
def test_pdf_keeps_financial_history_and_category_review_without_technical_appendix(stock):
    report=report_for(stock)
    pages=PdfReader(BytesIO(render_premium_pdf(report))).pages
    content='\n'.join(page.extract_text() for page in pages)
    for term in ('Quarterly results','Annual results','Key financial ratios','Fundamental','Valuation','Quality','Risk','Pros','Cons','Input coverage'):
        assert term in content
    for term in ('Weight','weighted','Source audit','SHA-256','clamp(', '0-point threshold','Short-history blend','Model 3.', 'State A', 'Group-fill', 'Private admin'):
        assert term not in content
    assert len(pages) == 7
    assert report['inputHash'] not in content.replace('\n','')
    assert 'None' not in content


def test_generation_returns_the_trace_with_the_exact_rating_and_inputs(monkeypatch):
    stock=DATA['stocks'][0]
    monkeypatch.setattr(premium_service,'fetch_inputs',lambda *a:(stock['raw'],[]))
    monkeypatch.setattr('backend.premium_benchmarks.peer_benchmark',lambda *a:({},{}))
    result=premium_service.generate_report(lambda *a:None,stock['symbol'],'Test name','consolidated','c'*32,'2026-10-18T04:30:00+00:00')
    expected=build_calculation_trace(result['inputs'],result['rating'],result['inputMeta'])
    assert result['calculationTrace']==expected
