from copy import deepcopy
from datetime import datetime, timezone, timedelta
from io import BytesIO
import jwt
import pytest
from pypdf import PdfReader
from backend import premium_service, premium_snapshot, server
from backend.tests.test_premium_reports import asgi_request, auth, sample_report, example


def test_inline_generation_and_pdf_survive_another_instance_without_jobs(monkeypatch, example):
    report=sample_report(example)
    monkeypatch.setattr(premium_service,'generate_report',lambda *a:deepcopy(report))
    monkeypatch.setattr(server,'_resolve_finedge_stock',lambda q:{'symbol':'TEST','name':'Test Ltd'})
    monkeypatch.setattr(server,'_premium_jobs',{})
    class NoDatabase:
        def __getattr__(self,name):pytest.fail('Current report generation must not access a database')
    monkeypatch.setattr(server,'db',NoDatabase())
    status,result=asgi_request(server.app,'POST','/api/premium-reports',{'query':'TEST','delivery':'inline'},auth())
    assert status==200 and result['state']=='ready' and result['snapshotReceipt']
    assert server._premium_jobs=={}
    receipt=result.pop('snapshotReceipt')
    # Simulate the PDF reaching a different, fresh function instance.
    monkeypatch.setattr(server,'_premium_jobs',{})
    monkeypatch.setattr(server,'_premium_pdf_tokens',{})
    status,body=asgi_request(server.app,'POST','/api/premium-reports/pdf',{'report':result,'receipt':receipt},auth())
    assert status==200 and body.startswith(b'%PDF')
    assert len(PdfReader(BytesIO(body)).pages)>1
    assert server._premium_jobs=={}


def test_stored_report_pdf_renders_from_the_reader_view_at_any_time(monkeypatch, example):
    report=sample_report(example)
    stored={k:v for k,v in report.items() if k not in('calculationTrace','inputs','inputHash')}
    stored['financialHistory']={k:(report.get('calculationTrace') or {}).get(k) or [] for k in('quarterly','annual','latest')}
    assert asgi_request(server.app,'POST','/api/premium-reports/pdf-stored',{'report':stored})[0]==401
    status,body=asgi_request(server.app,'POST','/api/premium-reports/pdf-stored',{'report':stored},auth())
    assert status==200 and body.startswith(b'%PDF')
    assert asgi_request(server.app,'POST','/api/premium-reports/pdf-stored',{'report':{'state':'ready'}},auth())[0]==400


def test_snapshot_rejects_changes_expiry_different_admin_and_wrong_token_purpose():
    secret='test-snapshot-secret-with-over-32-bytes'
    signed=premium_snapshot.issue({'id':'a'*32,'state':'ready','rating':{'final':50.0}},'admin',secret)
    receipt=signed.pop('snapshotReceipt')
    unchanged=deepcopy(signed);unchanged['rating']['final']=50
    assert premium_snapshot.verify(unchanged,receipt,'admin',secret)==unchanged
    changed=deepcopy(signed);changed['rating']['final']=100
    for candidate,token,subject in [(changed,receipt,'admin'),(signed,receipt,'other')]:
        with pytest.raises(Exception):premium_snapshot.verify(candidate,token,subject,secret)
    claims=jwt.decode(receipt,secret,algorithms=['HS256'],audience=premium_snapshot.AUDIENCE)
    claims['exp']=datetime.now(timezone.utc)-timedelta(seconds=5)
    with pytest.raises(jwt.ExpiredSignatureError):premium_snapshot.verify(signed,jwt.encode(claims,secret,algorithm='HS256'),'admin',secret)
    claims['exp']=datetime.now(timezone.utc)+timedelta(minutes=5);claims['aud']='some-other-purpose'
    with pytest.raises(jwt.InvalidAudienceError):premium_snapshot.verify(signed,jwt.encode(claims,secret,algorithm='HS256'),'admin',secret)


def test_inline_provider_failure_is_returned_to_the_same_request(monkeypatch):
    monkeypatch.setattr(server,'_resolve_finedge_stock',lambda q:{'symbol':'TEST','name':'Test'})
    def fail(*a):raise TimeoutError('private-provider-error')
    monkeypatch.setattr(premium_service,'generate_report',fail)
    status,result=asgi_request(server.app,'POST','/api/premium-reports',{'query':'TEST','delivery':'inline'},auth())
    assert status==502 and 'private-provider-error' not in str(result)


def test_snapshot_pdf_rejects_tampering_and_requires_auth(monkeypatch, example):
    report=sample_report(example)
    signed=premium_snapshot.issue(report,'admin@example.test',server.token_secret()); receipt=signed.pop('snapshotReceipt')
    signed['rating']['final']=100
    payload={'report':signed,'receipt':receipt}
    assert asgi_request(server.app,'POST','/api/premium-reports/pdf',payload)[0]==401
    assert asgi_request(server.app,'POST','/api/premium-reports/pdf',payload,auth())[0]==400
