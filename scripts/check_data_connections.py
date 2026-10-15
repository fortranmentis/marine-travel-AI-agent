"""Check supplied public API credentials without printing keys or request URLs.

The credential document is parsed as data, never executed. Standard library only.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def get(url, params=None):
    if params:
        url += '?' + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode('utf-8-sig')
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'HTTP {error.code}') from None
    except Exception as error:
        # Exception text can contain the service key embedded in a URL.
        raise RuntimeError(type(error).__name__) from None


def load_credentials(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    blocks = re.split(r'\n\s*\n', text)
    result = []
    for block in blocks:
        endpoint = re.search(r'엔드포인트\s*:\s*(https?://\S+)', block)
        key = re.search(r'^키\s*:\s*(\S+)', block, re.M)
        if not endpoint or not key:
            continue
        parsed = urllib.parse.urlsplit(endpoint[1])
        if parsed.scheme != 'https' or parsed.hostname != 'apis.data.go.kr' or parsed.query:
            raise ValueError('Credential endpoint is not an approved public API base URL')
        result.append(dict(name=block.strip().splitlines()[0],
                           endpoint=endpoint[1].rstrip('/'),
                           key=urllib.parse.unquote(key[1])))
    if not result:
        raise ValueError('No credential entries parsed')
    return result


def summarize(raw):
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        root = ET.fromstring(raw)
        values = {node.tag.split('}')[-1]: node.text for node in root.iter()
                  if node.tag.split('}')[-1] in ('resultCode', 'resultMsg', 'returnReasonCode', 'returnAuthMsg')}
        return dict(status='xml_response', **values), []
    response = obj.get('response', obj)
    header = response.get('header', {})
    body = response.get('body') or {}
    items = body.get('items') or {}
    rows = items.get('item', []) if isinstance(items, dict) else items
    if isinstance(rows, dict):
        rows = [rows]
    code = str(header.get('resultCode', ''))
    status = 'ok' if code in ('0', '00', '0000') else 'api_error'
    if status == 'ok' and not rows:
        status = 'no_data'
    return dict(status=status, result_code=code, total_count=body.get('totalCount'),
                returned_count=len(rows), fields=sorted(rows[0]) if rows else []), rows


def marine_schema(page_id):
    source = f'https://www.data.go.kr/data/{page_id}/openapi.do'
    html = get(source)
    match = re.search(r'const swaggerJson\s*=\s*`(.*?)`;', html, re.S)
    if not match:
        raise ValueError('Official API schema not found')
    # Decode the escapes used by a JavaScript template literal without evaluating it.
    literal = match[1].replace('\\\\', '\\').replace('\\`', '`').replace('\\$', '$')
    schema = json.loads(literal)
    return schema, source


def probe(entry, schemas, date):
    common = dict(serviceKey=entry['key'], pageNo=1, numOfRows=10)
    base = entry['endpoint']
    report = dict(service=entry['name'], endpoint=base)
    try:
        if base.endswith('/KorService2'):
            params = dict(common, MobileOS='ETC', MobileApp='IncheonFamilyTravel', _type='json')
            codes_summary, codes = summarize(get(base + '/areaCode2', params))
            incheon = next((row for row in codes if row.get('name') == '인천'), None)
            if not incheon:
                raise ValueError('Incheon area code not returned')
            summary, rows = summarize(get(base + '/areaBasedList2', dict(params, areaCode=incheon['code'])))
            report.update(summary, incheon_area_code=incheon['code'],
                          sample_places=[row.get('title') for row in rows])
        elif base.endswith('/PhotoGalleryService1'):
            params = dict(common, MobileOS='ETC', MobileApp='IncheonFamilyTravel',
                          _type='json', keyword='인천')
            summary, _ = summarize(get(base + '/gallerySearchList1', params))
            report.update(summary)
        elif base.endswith('/VilageFcstInfoService_2.0'):
            # A representative grid for an API connection check, not a travel-site assignment.
            summary, _ = summarize(get(base + '/getVilageFcst', dict(
                common, dataType='JSON', base_date=date, base_time='0200', nx=55, ny=124)))
            report.update(summary, probe_grid=dict(nx=55, ny=124), base_date=date, base_time='0200')
        else:
            found = next(((schema, source) for schema, source in schemas
                          if 'https://' + schema['host'].rstrip('/') in (base, base + '2')), None)
            if not found:
                report['status'] = 'schema_not_found'
                return report
            schema, source = found
            official_base = 'https://' + schema['host'].rstrip('/')
            if official_base != base:
                report['supplied_endpoint'] = base
                base = official_base
                report['endpoint'] = base
            operation, spec = next(iter(schema['paths'].items()))
            merged = {p['name']: p for p in spec.get('parameters', [])}
            merged.update({p['name']: p for p in spec['get'].get('parameters', [])})
            parameters = list(merged.values())
            names = [p['name'] for p in parameters]
            params = {k: v for k, v in common.items() if k in names}
            for p in parameters:
                name = p['name']
                if name in params:
                    continue
                if name.lower() in ('type', 'datatype', '_type'):
                    params[name] = 'json'
                elif name.lower() in ('reqdate', 'date', 'basedate', 'basedt', 'searchdate'):
                    params[name] = date
                elif name == 'gubun' and '갯바위/선상' in p.get('description', ''):
                    params[name] = '갯바위'
                elif p.get('required'):
                    report.update(status='required_parameter_unmapped', parameter=name, schema_source=source)
                    return report
            report.update(operation=operation, parameters=names, schema_source=source)
            summary, rows = summarize(get(base + operation, params))
            report.update(summary, operation=operation, parameters=names, schema_source=source)
            # Record only public place/time metadata, never the credential or request URL.
            report['sample_metadata'] = [
                {k: v for k, v in row.items() if any(s in k.lower() for s in ('nm', 'date', 'ymd', 'lat', 'lon'))}
                for row in rows[:3]
            ]
    except Exception as error:
        report.update(status='error', error_type=type(error).__name__)
        if isinstance(error, RuntimeError):
            report['transport_error'] = str(error)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--date', default=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y%m%d'))
    parser.add_argument('--output', default='reports/data_connections.json')
    args = parser.parse_args()
    dt.datetime.strptime(args.date, '%Y%m%d')
    entries = load_credentials(args.credentials)
    schemas = []
    schema_errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(marine_schema, page): page for page in range(15142484, 15142492)}
        for future, page in futures.items():
            try:
                schemas.append(future.result())
            except Exception as error:
                schema_errors.append(dict(page=page, error_type=type(error).__name__))
    results = [probe(entry, schemas, args.date) for entry in entries]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(checked_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        probe_date=args.date, schema_errors=schema_errors, services=results), ensure_ascii=False, indent=2), encoding='utf-8')
    for result in results:
        print(json.dumps({k: result[k] for k in ('service', 'status', 'result_code', 'total_count', 'error_type', 'parameter') if k in result}, ensure_ascii=False))
    print(f'Report: {output.resolve()}')
    return 0 if all(row['status'] in ('ok', 'no_data') for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
