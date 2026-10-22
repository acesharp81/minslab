"""Full policy-linked CSV snapshot and workbook verification, without silent rounding.

capture: run inside HOME image. workbook: standard-library OOXML extraction.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FOLDER = 'policy907-full-verification-20261021'
POLICY = 'POL_2025_0907'


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def csvwrite(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v
                for k, v in row.items() if k in fields})


def workbook():
    path = ROOT / 'docs/analysis/housing_supply_97_official_verification_20261021.xlsx'
    out = ROOT / 'docs/analysis' / FOLDER
    out.mkdir(exist_ok=True)
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    result = {}
    with zipfile.ZipFile(path) as archive:
        strings = [''.join(t.itertext()) for t in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', ns)] if 'xl/sharedStrings.xml' in archive.namelist() else []
        relations = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(archive.read('xl/workbook.xml')).findall('m:sheets/m:sheet', ns):
            target = relations[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            rows = []
            for raw in ET.fromstring(archive.read(target)).findall('.//m:sheetData/m:row', ns):
                cells = {}
                for cell in raw.findall('m:c', ns):
                    value = cell.find('m:v', ns)
                    inline = cell.find('m:is', ns)
                    value = value.text if value is not None else ''.join(inline.itertext()) if inline is not None else ''
                    if cell.get('t') == 's':
                        value = strings[int(value)]
                    cells[''.join(filter(str.isalpha, cell.get('r')))] = value or ''
                rows.append(cells)
            headers = rows[0]
            result[sheet.get('name')] = [{headers.get(k, k): v for k, v in row.items()} for row in rows[1:]]
    assert len(result['공식수치_대조입력']) == 185
    dump(out / 'workbook_extracted.json', result)
    dump(out / 'input_manifest.json', dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        parsed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), indicators=185, issues=18, sources=17))
    for name in ['공식수치_대조입력', '공식출처목록', '교차검증_쟁점']:
        csvwrite(out / (name + '.csv'), result[name])
    print(json.dumps({k: len(v) for k, v in result.items()}, ensure_ascii=False))


def capture():
    from sqlalchemy import select, text
    from sqlalchemy.orm import sessionmaker
    from backend.db import Revision, Mapping, ProgramMapping, engine_for
    from backend.service import HomeService
    from backend.read_scope import projection_reads
    from backend.policy_delivery import build_delivery
    from backend.project_collection import collection_matrix
    from scripts.export_json import scrub, credential_values
    folder = Path('/app/data') / FOLDER
    folder.mkdir(exist_ok=True)
    engine = engine_for()
    secrets = credential_values()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            timestamp = conn.scalar(text('SELECT CURRENT_TIMESTAMP'))
            service = HomeService(engine, '/app/data')
            service.sessions = sessionmaker(bind=conn, expire_on_commit=False)
            with projection_reads():
                projects = service.projects()
                linked = [p for p in projects if p['mapping']['policy_id'] == POLICY and p['mapping']['status'] != 'RELEASED']
                model = build_delivery(service, date(2026, 10, 21), include_portfolio_comparisons=False)
                matrix = collection_matrix(service, policy_id=POLICY, include_link_history=False)
                kinds = ['policy', 'project_profile', 'execution_schedule', 'stage_evidence', 'collection_link',
                    'evidence_bridge', 'document_evidence', 'statistic', 'statistic_reference', 'housing_type_stat',
                    'delivery_setting', 'collection_research', 'agency_plan', 'lh_movein_plan', 'plan_notice',
                    'project_location', 'lh_notice', 'notice']
                rows = []
                for kind in kinds:
                    rows.extend(service.rows(kind))
                mappings = [dict(r._mapping) for r in conn.execute(select(Mapping.__table__))]
                programs = [dict(r._mapping) for r in conn.execute(select(ProgramMapping.__table__))]
                raw_projects = [dict(r._mapping) for r in conn.execute(select(Revision.__table__).where(
                    Revision.kind == 'project', Revision.superseded_at.is_(None)))]
            for name, data in [('projects', projects), ('policy_linked_projects', linked), ('model', model),
                ('matrix', matrix), ('supporting_rows', rows), ('mappings', mappings), ('programs', programs), ('raw_projects', raw_projects)]:
                dump(folder / (name + '.json'), scrub(data, secrets))
            dump(folder / 'snapshot.json', dict(snapshot_at=str(timestamp), client_as_of='2026-10-21',
                transaction='PostgreSQL REPEATABLE READ READ ONLY', projects=len(projects), linked_source_projects=len(linked),
                management_cohorts=len(model['portfolio_cohorts']), matrix_rows=len(matrix['items']), supporting_rows=len(rows)))
    print((folder / 'snapshot.json').read_text())


def official():
    import requests
    import subprocess
    from bs4 import BeautifulSoup
    from concurrent.futures import ThreadPoolExecutor
    folder = ROOT / 'docs/analysis' / FOLDER
    sources = json.loads((folder / 'workbook_extracted.json').read_text())['공식출처목록']
    def fetch(source):
        key, url = source['자료ID'], source['공식 URL']
        result = dict(source_id=key, url=url, collected_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
        try:
            response = requests.get(url, timeout=25)
            response.raise_for_status()
            raw = response.content
            extension = '.pdf' if raw.startswith(b'%PDF') else '.html'
            path = folder / (key + extension)
            path.write_bytes(raw)
            if extension == '.pdf':
                text = subprocess.run(['pdftotext', '-layout', str(path), '-'], check=True, capture_output=True, text=True).stdout
                links = []
            else:
                response.encoding = response.apparent_encoding
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text('\n', strip=True)
                links = [dict(text=a.get_text(' ', strip=True), href=a['href']) for a in soup.select('a[href]')
                    if any(w in str(a).lower() for w in ['download', 'getfile', 'attach', '.pdf', '.hwp'])]
            (folder / (key + '.txt')).write_text(text)
            dump(folder / (key + '_links.json'), links)
            result.update(status=response.status_code, file=path.name, sha256=hashlib.sha256(raw).hexdigest(),
                bytes=len(raw), content_verified=False, note='HTTP 성공과 본문·지표 확인은 별개; 항목별 결과 참조')
        except Exception as error:
            result.update(error=type(error).__name__)
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, sources))
    dump(folder / 'official_capture_manifest.json', rows)
    print(json.dumps(rows, ensure_ascii=False))


def type_months(history=False):
    import os
    import urllib.request
    import urllib.parse
    folder = Path('/app/data') / FOLDER
    rows = []
    periods=[(year,1,2) for year in [2025,2026]] if not history else [(year,start,min(start+1,7)) for year in [2023,2024] for start in [1,3,5,7]]
    for year,start,end in periods:
        params = dict(key=os.environ['POC10_MOLIT_STAT_API_KEY'], form_id='5387', style_num='1',
            start_dt=f'{year}{start:02d}', end_dt=f'{year}{end:02d}')
        url = 'https://stat.molit.go.kr/portal/openapi/service/rest/getList.do'
        with urllib.request.urlopen(url+'?'+urllib.parse.urlencode(params), timeout=30) as response:
            data = json.load(response)
        assert data['result_status']['status_code'] == 'INFO-000'
        assert data['result_data']['unitName'] == '호'
        data = {k: v for k, v in data.items() if k.lower() not in ['cert_id', 'key', 'apikey']}
        selected = [r for r in data['result_data']['formList'] if r['구  분'] == '서울']
        assert len(selected) == 8*(end-start+1)
        rows.extend(selected)
        dump(folder / (f'5387_{year}{start:02d}{end:02d}.json'), data)
    dump(folder / ('typed_starts_history.json' if history else 'typed_starts_jan_feb.json'), rows)
    print(json.dumps(dict(rows=len(rows), periods=sorted({r['date'] for r in rows}))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['workbook', 'capture', 'official', 'type-months','type-history'])
    args = parser.parse_args()
    {'workbook': workbook, 'capture': capture, 'official': official, 'type-months': type_months,'type-history':lambda:type_months(True)}[args.action]()
