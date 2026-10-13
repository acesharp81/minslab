"""Create a shareable, self-contained HOME architecture and acquisition snapshot.

Only public read APIs are used; API keys, raw records and personal data are excluded.
"""
import argparse
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.request import urlopen
import json
from zoneinfo import ZoneInfo

BASE = 'http://127.0.0.1:18100/poc/home/api'
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / 'docs' / 'HOME_ARCHITECTURE_AND_COLLECTION_20261010.html'


def fetch(base, name):
    with urlopen(base.rstrip('/') + '/' + name, timeout=30) as response:
        return json.load(response)


def e(value):
    return escape('—' if value is None else str(value), quote=True)


def n(value):
    return f'{value:,}' if isinstance(value, int) else '미확보'


def row(*cells):
    return '<tr>' + ''.join('<td>' + cell + '</td>' for cell in cells) + '</tr>'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default=BASE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    validation = fetch(args.base_url, 'validation')
    sources = fetch(args.base_url, 'sources')['items']
    coverage = fetch(args.base_url, 'coverage')['items']
    mappings = fetch(args.base_url, 'mappings')
    policies = fetch(args.base_url, 'policy-monitor')
    plans = fetch(args.base_url, 'plans')
    identities = fetch(args.base_url, 'identities')
    review_total = fetch(args.base_url, 'identity-reviews?page_size=100&page=1')['total']
    reviews = []
    for page in range(1, (review_total + 99) // 100 + 1):
        reviews.extend(fetch(args.base_url, f'identity-reviews?page_size=100&page={page}')['items'])
    completion_source = next((item for item in sources if item['id'] == 'lh_completion_plan'), {})
    completion_records = completion_source.get('record_count') or 0
    unit_conflicts = sum(item.get('unit_comparison') == 'DIFFERENT' for item in reviews)
    gaps = validation['data_gaps']
    projects = gaps['projects']
    snapshot = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M KST')
    completed_sources = sum(source['status'] == 'SUCCESS' for source in sources)
    configured = [source for source in sources if source.get('key_env')]
    missing_keys = [source['id'] for source in configured if source.get('key_configured') is not True]
    source_rows = []
    for source in sorted(sources, key=lambda item: (item.get('org') or '', item['id'])):
        status = source.get('status') or '미확보'
        badge = '<span class="badge '+('ok' if status == 'SUCCESS' else 'doing' if status == 'RUNNING' else 'warn')+'">'+e(status)+'</span>'
        url = source.get('url')
        link = '<a href="'+e(url)+'" target="_blank" rel="noopener noreferrer">원천 ↗</a>' if url and str(url).startswith('https://') else '미연계'
        source_rows.append(row('<code>'+e(source['id'])+'</code>',e(source.get('org') or '—'),e(source.get('collection_mode') or '—'),badge,n(source.get('record_count')),e((source.get('last_success') or '')[:10] or '—'),link))
    year_rows = []
    for item in gaps['rows']:
        missing = [str(cell['year']) for cell in item.get('cells', []) if cell['status'] not in ('ACQUIRED','CONFIRMED_ZERO')]
        seen = item.get('observed_years') or []
        period = str(min(seen))+'–'+str(max(seen)) if seen else '미확보'
        year_rows.append(row(e(item['label']),e(item['region']),e(period),'<span class="'+('alert' if missing else 'muted')+'">'+e(', '.join(missing) if missing else '표시 범위 내 없음')+'</span>',e(item.get('collection_status') or '—')))
    scope_rows = []
    scope_labels={'building_hub':'주택 인허가 기본','building_register':'주거용 건축물대장','building_hub_details':'인허가 동·필지 상세'}
    for item in gaps['scope']:
        pct=100*item['completed']/item['total'] if item['total'] else 0
        scope_rows.append(row(e(scope_labels.get(item['source_id'],item['source_id'])),n(item['completed'])+' / '+n(item['total']),f'{pct:.1f}%',n(item['remaining'])+'개',e(item['status'])))
    not_started_rows = [row(e(item['label']),e(item['scope']),'<span class="badge warn">'+e(item['status'])+'</span>',e(item['next_action'])) for item in gaps['not_started']]
    status_note = '필요 키 '+str(len(configured))+'개 원천 모두 설정됨' if not missing_keys else '키 설정 미확인: '+', '.join(missing_keys)
    template = Path(__file__).parent / 'templates' / 'home_architecture.html'
    content = template.read_text(encoding='utf-8')
    substitutions = {
        '__SNAPSHOT__': snapshot,
        '__POLICIES__': n(len(policies['items'])),
        '__PROGRAMS__': n(len(mappings['programs'])),
        '__PROJECTS__': n(projects['total']),
        '__PLANNED__': n(projects['planned_units_acquired']),
        '__PROGRESS__': n(projects['progress_acquired']),
        '__SCHEDULE__': n(projects['schedule_acquired']),
        '__OCCUPANCY__': n(projects['move_in_start_acquired']),
        '__REVIEW__': n(policies['review_count']),
        '__LH_COMPLETION__': n(completion_records),
        '__LH_REVIEW__': n(review_total),
        '__LH_CONFLICT__': n(unit_conflicts),
        '__LH_UNLINKED__': n(max(0, completion_records - review_total)),
        '__PLANS__': n(plans['total']),
        '__SOURCES__': n(len(sources)),
        '__SOURCE_SUCCESS__': n(completed_sources),
        '__PLANNED_MISSING__': n(projects['total']-projects['planned_units_acquired']),
        '__SCHEDULE_MISSING__': n(projects['total']-projects['schedule_acquired']),
        '__PROGRESS_MISSING__': n(projects['total']-projects['progress_acquired']),
        '__SOURCE_ROWS__': '\n'.join(source_rows),
        '__YEAR_ROWS__': '\n'.join(year_rows),
        '__YEAR_ROW_COUNT__': n(len(year_rows)),
        '__SCOPE_ROWS__': '\n'.join(scope_rows),
        '__NOT_STARTED_ROWS__': '\n'.join(not_started_rows),
        '__KEY_STATUS__': e(status_note),
    }
    for token, value in substitutions.items():
        content = content.replace(token, value)
    assert '__' not in content, 'Unresolved template token'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding='utf-8')
    print(args.output)
    print('snapshot', snapshot, 'sources', len(sources), 'coverage', len(coverage), 'gaps', len(gaps['not_started']))


if __name__ == '__main__':
    main()
