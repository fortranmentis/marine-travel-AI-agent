"""Allowlisted public transport clients. Credentials and request URLs stay server-side."""
from collections import OrderedDict
import copy
import datetime as dt
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

import httpx
from .config import load_env

load_env()

BASES = {
    'komsa':'https://apis.data.go.kr/B554035/oprt-schd-info-v2',
    'ship':'https://apis.data.go.kr/1613000/DmstcShipNvgInfo',
    'subway':'https://apis.data.go.kr/1613000/SubwayInfo',
    'stops':'https://apis.data.go.kr/1613000/BusSttnInfoInqireService',
    'bus_routes':'https://apis.data.go.kr/1613000/BusRouteInfoInqireService',
    'bus_positions':'https://apis.data.go.kr/1613000/BusLcInfoInqireService',
    'bus_arrivals':'https://apis.data.go.kr/1613000/ArvlInfoInqireService',
}
OPERATIONS = {
    'komsa':{'get-oprt-schd-info-v2'},
    'ship':{'GetPsnshipTrminlList','GetPortList','GetShipOpratInfoList','GetShipKndList'},
    'subway':{'GetKwrdFndSubwaySttnList','GetSubwaySttnExitAcctoBusRouteList','GetSubwaySttnAcctoSchdulList'},
    'stops':{'getCtyCodeList','getCrdntPrxmtSttnList','getSttnNoList'},
    'bus_routes':{'getCtyCodeList','getRouteNoList','getRouteInfoIem','getRouteAcctoThrghSttnList','getSttnAcctoRouteList'},
    'bus_positions':{'getCtyCodeList','getRouteAcctoBusLcList'},
    'bus_arrivals':{'getCtyCodeList','getSttnAcctoArvlPrearngeInfoList'},
}
SOURCES={'komsa':'15142302','ship':'15098523','subway':'15098554','stops':'15098534',
         'bus_routes':'15098529','bus_positions':'15098533','bus_arrivals':'15098530'}
_cache=OrderedDict();_lock=threading.RLock();KST=dt.timezone(dt.timedelta(hours=9))


@lru_cache(maxsize=2)
def _credentials(path,mtime):
    content=Path(path).read_text(encoding='utf-8-sig');result={}
    for block in re.split(r'\n\s*\n',content):
        endpoint=re.search(r'(?:End\s*Point|엔드포인트)\s*[:：]\s*(https?://\S+)',block,re.I)
        key=re.search(r'^\s*(?:인증키|키)\s*[:：]\s*(\S+)',block,re.M)
        if not endpoint or not key:continue
        base=endpoint[1].rstrip('/');parsed=urlsplit(base)
        if parsed.query or parsed.fragment or base not in BASES.values():continue
        service=next(k for k,v in BASES.items() if v==base)
        if service in result:raise ValueError('Duplicate transport credential entry')
        result[service]=unquote(key[1])
    return result


def credentials():
    path=os.environ.get('TRANSPORT_CREDENTIALS_FILE','')
    if not path:return {}
    try:return _credentials(path,Path(path).stat().st_mtime_ns)
    except (OSError,ValueError,UnicodeError):return {}


def availability():return {service:service in credentials() for service in BASES}


def decode(raw):
    try:obj=json.loads(raw)
    except (ValueError,TypeError):
        try:
            tree=ET.fromstring(raw)
            values={n.tag.split('}')[-1]:n.text for n in tree.iter()}
            code=values.get('returnReasonCode',values.get('resultCode','invalid_response'))
            return dict(code='unexpected_xml' if code in ('00','0','200') else code,rows=[],total=0)
        except ET.ParseError:return dict(code='invalid_response',rows=[],total=0)
    response=obj.get('response',obj);header=response.get('header') or {};body=response.get('body') or {}
    items=body.get('items') or {};rows=items.get('item',[]) if isinstance(items,dict) else items
    if isinstance(rows,dict):rows=[rows]
    if not isinstance(rows,list) or not all(isinstance(r,dict) for r in rows):raise ValueError('Invalid source rows')
    code=str(header.get('resultCode',''))
    if not re.fullmatch(r'[A-Za-z0-9_]{1,60}',code):code='invalid_response_code'
    total=body.get('totalCount')
    return dict(code=code,rows=rows,total=int(total) if total is not None and total!='' else len(rows))


def request(service,operation,params=None,*,ttl=300):
    if service not in BASES or operation not in OPERATIONS[service]:raise ValueError('Unsupported transport operation')
    params=params or {}
    if any(str(k).lower() in ('servicekey','apikey') for k in params):raise ValueError('Credential override rejected')
    source='https://www.data.go.kr/data/'+SOURCES[service]+'/openapi.do'
    key=credentials().get(service)
    if not key:return dict(status='not_configured',rows=[],count=0,source_url=source)
    identity=(service,operation,json.dumps(params,sort_keys=True,ensure_ascii=False))
    with _lock:
        now=time.monotonic()
        for old in [k for k,v in _cache.items() if v[0]<=now]:del _cache[old]
        if identity in _cache:return dict(copy.deepcopy(_cache[identity][1]),cached=True)
    result=dict(status='unavailable',rows=[],count=0,source_url=source,
                observed_at=dt.datetime.now(KST).isoformat(),cached=False)
    common=dict(serviceKey=key,pageNo=1,numOfRows=100)
    common.update({'dataType':'JSON'} if service=='komsa' else {'_type':'json'})
    try:
        with httpx.Client(timeout=15,trust_env=False) as client:
            response=client.get(BASES[service]+'/'+operation,params={**common,**params})
            if response.status_code!=200:result['result_code']='HTTP_'+str(response.status_code)
            else:
                value=decode(response.text);code=value['code'];result['result_code']=code
                if code in ('00','0','0000','200'):
                    result.update(status='available' if value['rows'] else 'no_data',rows=value['rows'],count=value['total'],
                                  truncated=value['total']>len(value['rows']))
                elif code=='153':result.update(status='no_data')
    except Exception:result['result_code']='connection_or_response_error'
    with _lock:
        _cache[identity]=(time.monotonic()+(ttl if result['status'] in ('available','no_data') else 60),copy.deepcopy(result))
        while len(_cache)>256:_cache.popitem(last=False)
    return result


def pages(service,operation,params=None,*,ttl=3600,limit=2000):
    values=[];expected=None;seen=set();last=None
    for page in range(1,22):
        result=request(service,operation,dict(params or {},pageNo=page),ttl=ttl);last=result
        if result['status'] not in ('available','no_data'):return result
        if expected is None:expected=result['count']
        if result['count']!=expected or expected>limit:return dict(result,status='incomplete',rows=[])
        for row in result['rows']:
            identity=json.dumps(row,sort_keys=True,ensure_ascii=False)
            if identity in seen:return dict(result,status='incomplete',rows=[])
            seen.add(identity);values.append(row)
        if len(values)==expected:return dict(result,rows=values,count=len(values),truncated=False)
        if not result['rows'] or len(values)>expected:break
    return dict(last or {},status='incomplete',rows=[])
