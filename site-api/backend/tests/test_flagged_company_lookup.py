import pytest
from fastapi import HTTPException
from backend import server
from backend.premium_classification import resolve_group


@pytest.fixture
def directory(monkeypatch):
    rows=[{'symbol':str(540000+i),'name':f'Mehul Test {i} Ltd'} for i in range(30)]
    rows += [{'symbol':'HINDUNILVR','name':'Hindustan Unilever Ltd','bseCode':'500696'},
             {'symbol':'ZEEL','name':'Zee Entertainment Enterprises Ltd'},
             {'symbol':'INDHOTEL','name':'The Indian Hotels Company Ltd'},
             {'symbol':'BSEL','name':'Bsel Algo Ltd'}, {'symbol':'BSE','name':'BSE Ltd'},
             {'symbol':'TMCV','name':'Tata Motors Ltd'}, {'symbol':'TMPV','name':'Tata Motors Passenger Vehicles Ltd'}]
    monkeypatch.setattr(server,'_finedge_all_symbols',lambda:rows)
    monkeypatch.setattr(server,'_stock_search_cache',{})
    return rows


@pytest.mark.parametrize('query,symbol',[('HUL','HINDUNILVR'),('500696','HINDUNILVR'),('ZEE 5','ZEEL'),('ZEE5','ZEEL'),('Taj Hotels','INDHOTEL'),('IHCL','INDHOTEL'),('Tata Motors','TMCV'),('BSE','BSE')])
def test_verified_aliases_and_exact_codes_resolve_correct_company(directory,query,symbol):
    assert server._search_finedge_stocks(query)[0]['symbol']==symbol
    assert server._resolve_finedge_stock(query)['symbol']==symbol


def test_exact_match_is_ranked_before_suggestion_limit(directory):
    directory.append({'symbol':'MEHUL','name':'Actual Requested Company Ltd'})
    assert server._search_finedge_stocks('MEHUL')[0]['symbol']=='MEHUL'
    assert server._resolve_finedge_stock('MEHUL')['symbol']=='MEHUL'


@pytest.mark.parametrize('query',['Tata','Mehul','EHUL'])
def test_ambiguous_or_incidental_substrings_do_not_generate_arbitrary_company(directory,query):
    with pytest.raises(HTTPException) as caught:server._resolve_finedge_stock(query)
    assert caught.value.status_code==422


def test_unknown_symbol_is_not_fabricated(directory):
    with pytest.raises(HTTPException) as caught:server._resolve_finedge_stock('NOTLISTED')
    assert caught.value.status_code==404


@pytest.mark.parametrize('profile,group',[
    ({'industry':'Agricultural, Commercial & Construction Vehicles','sector':'Automobiles'},'MFG'),
    ({'industry':'Auto Parts','sector':'Infrastructure'},'MFG'),
    ({'industry':'Construction & Infrastructure'},'UTILITY'),
    ({'industry':'Power Generation'},'UTILITY'),
    ({'industry':'Insurance','sector':'Vehicle Insurance'},'INSURANCE'),
    ({'industry':'Finance Company','sector':'Vehicle Finance'},'NBFC'),
    ({'industry':'Electrical Equipment','sector':'Capital Goods'},'MFG'),
])
def test_construction_vehicles_are_manufacturing_without_changing_other_groups(profile,group):
    assert resolve_group(profile)==(group,False)
