from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfReader
from backend import premium_service, server
from backend.benchmark_resolution import reported_benchmarks, select_reported_benchmarks, merge_sector_values
from backend.premium_benchmarks import peer_benchmark
from backend.premium_presentation import build_report_review
from backend.premium_pdf import render_premium_pdf

ASOF = date(2026, 10, 23)


def test_reported_provider_priority_and_nonpositive_benchmark_rejection():
    native = [{'name':'P/E','industryValue':30}]
    secondary = [{'name':'P/E','sector_value':'25'}, {'name':'P/B','sector_value':'2.38'}, {'name':'EV/EBITDA','sector_value':'-12'}]
    observations = reported_benchmarks(native,secondary,'2026-10-24')
    values, details = select_reported_benchmarks(observations)
    assert values == {'industry_median_pe':30,'industry_median_pb':2.38}
    assert details['industry_median_pe']['provider']=='FinEdge'
    assert details['industry_median_pb']['scope']=='sector'
    assert details['industry_median_pb']['statementBasis']=='unspecified'
    assert len(observations)==4  # invalid values retained for disclosure


@pytest.mark.parametrize('value',[None,0,-12.64,'N/A',float('nan'),True])
def test_invalid_sector_pe_is_never_scored_as_an_industry_benchmark(value):
    obs = reported_benchmarks([], [{'name':'P/E','sector_value':value}], '2026-10-24')
    assert select_reported_benchmarks(obs)[0] == {}


def test_sector_values_merge_independently_without_replacing_company_values():
    primary=[{'name':'P/E','company_value':15.205,'sector_value':None}, {'name':'P/B','company_value':4.058,'sector_value':3}]
    before=deepcopy(primary)
    out=merge_sector_values(primary,[{'name':'P/E','company_value':14.87,'sector_value':-12.64},{'name':'P/B','sector_value':2.38}])
    assert out[0]['company_value']==15.205 and out[0]['sector_value']==-12.64
    assert out[0]['sector_source']=='Upstox'
    assert out[1]['sector_value']==3
    assert primary==before


def test_available_positive_peer_median_discloses_partial_per_metric_coverage():
    def get(path,params):
        s=path.rsplit('/',1)[-1]
        if not path.startswith('/daily-price-ratios/') or s=='G': return {}
        return {'price_ratios':[{'quote_date':'2026-10-23','pe':{'A':10,'B':20,'C':30,'D':40,'E':50,'F':0}[s], 'pb':None if s=='A' else 2}]}
    result, meta=peer_benchmark(get,{'peers':list('ABCDEFG')},'consolidated',ASOF,'MFG')
    assert result=={'industry_median_pe':30,'industry_median_pb':2}
    pe=meta['metrics']['industry_median_pe']
    pb=meta['metrics']['industry_median_pb']
    assert (pe['positiveCount'],pe['observedCount'],pe['universeCount'])==(5,6,7)
    assert (pb['positiveCount'],pb['observedCount'],pb['universeCount'])==(5,5,7)
    assert pe['partial'] and pb['partial']


def test_report_uses_provider_benchmark_before_peer_calculation_and_discloses_actual_inputs(monkeypatch):
    fixture=json.loads((Path(__file__).parent/'fixtures'/'premium_stock_audit_2026_10_18.json').read_text())['stocks'][0]
    raw=deepcopy(fixture['raw'])
    raw['benchmarkObservations']=reported_benchmarks([], [{'name':'P/E','sector_value':25},{'name':'P/B','sector_value':2.38},{'name':'EV/EBITDA','sector_value':8.77}], '2026-10-24')
    wanted=[]
    def peers(*args):
        wanted.extend(args[-1]);return {},{}
    monkeypatch.setattr('backend.premium_benchmarks.peer_benchmark',peers)
    report=premium_service.generate_report(None,fixture['symbol'],'Example','consolidated','a'*32,'2026-10-24T12:00:00+00:00',lambda *a:(raw,[],'consolidated',{}))
    assert wanted==[]
    assert report['inputs']['industry_median_pe']==25
    assert report['inputs']['industry_median_pb']==2.38
    assert any(r['label']=='Upstox sector P/E benchmark' for r in report['calculationTrace']['latest'])
    factors=[item for part in report['review']['parts'] for bucket in ('pros','cons','mixed') for item in part[bucket]]
    industry=next(item for item in factors if item['metric']=='PB_VS_INDUSTRY')
    assert industry['label']=='P/B vs sector'
    assert '2.38x' in industry['comparisonText'] and 'Upstox' in industry['comparisonText']
    assert 'statement basis' in ' '.join(report['review']['notes'])
    pages=PdfReader(BytesIO(render_premium_pdf(report))).pages
    text='\n'.join(p.extract_text() for p in pages)
    assert 'P/B vs sector' in text and 'Source: Upstox' in text


def test_negative_upstox_pe_falls_back_to_peer_pe_only(monkeypatch):
    fixture=json.loads((Path(__file__).parent/'fixtures'/'premium_stock_audit_2026_10_18.json').read_text())['stocks'][2]
    raw=deepcopy(fixture['raw'])
    raw['benchmarkObservations']=reported_benchmarks([], [{'name':'P/E','sector_value':-12.64},{'name':'P/B','sector_value':2.38}], '2026-10-24')
    def peers(*args):
        assert args[-1]==['pe']
        return {'industry_median_pe':30}, {'metrics':{'industry_median_pe':{'value':30,'provider':'FinEdge','scope':'industry','method':'available peer median','positiveCount':74,'observedCount':122,'universeCount':137}}}
    monkeypatch.setattr('backend.premium_benchmarks.peer_benchmark',peers)
    report=premium_service.generate_report(None,fixture['symbol'],'Example','consolidated','a'*32,'2026-10-24T12:00:00+00:00',lambda *a:(raw,[],'consolidated',{}))
    assert report['inputs']['industry_median_pe']==30 and report['inputs']['industry_median_pb']==2.38
    assert any('-12.64x' in n for n in report['review']['notes'])
    factors=[item for part in report['review']['parts'] for bucket in ('pros','cons','mixed') for item in part[bucket]]
    pe=next(item for item in factors if item['metric']=='PE_VS_INDUSTRY')
    assert '74 positive multiples' in pe['comparisonText'] and '122 of 137' in pe['comparisonText']


def test_unused_peer_metrics_do_not_trigger_calculation():
    def get(*args): raise AssertionError('provider should not be called')
    assert peer_benchmark(get,{'peers':list('ABCDE')},'consolidated',ASOF,'MFG',[])[0]=={}
