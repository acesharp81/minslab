"""Record the unreconciled official Wangsuk2 claim in the existing R01."""
from copy import deepcopy
from datetime import datetime
from html import escape
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FOLDER = ROOT / 'data/remediation/wangsuk2-official-review-20261017'
ROUND = 'HOME-INTEGRITY-R01-CONSOLIDATED-20261017'
REASON = '공식 발표 후 도출된 보완 사항 적용 · 왕숙2 공식 착공 성과 포함 및 미재현 사유 기록'


def read(name):
    return json.loads((FOLDER / (name + '.json')).read_text())


def write(name, value):
    (FOLDER / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def capture():
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.data_integrity import get_round
    FOLDER.mkdir(parents=True, exist_ok=True)
    if (FOLDER / 'before.json').exists():
        raise ValueError('수정 전 보관본이 이미 있습니다.')
    s = HomeService(engine_for(), ROOT / 'data')
    write('before', get_round(s, ROUND))
    (FOLDER / 'before.html').write_text(get_round(s, ROUND, html=True))


def build():
    from scripts.reassess_report_reproducibility import report_section
    from scripts.build_consolidated_integrity import details
    current = deepcopy(read('before')['result'])
    text = (FOLDER / 'briefing_official.txt').read_text()
    assert '하남 교산과 남양주 왕숙2에서 각각 1,100호' in text
    report = current['report_reproducibility']
    official = next(r for r in current['agreement']['rows'] if r['id'] == 'S04')
    assert official['official_value'] == 1100 and official['stage'] == '착공'
    statement = ('공식 성과 보고서에는 남양주왕숙2가 2026년 10월 둘째 주까지의 착공 실적 1,100호로 포함돼 있다. '
                 '이는 본청약 A-1 812호·A-3 686호(합계 1,498호)와 다른 사건·물량이다. '
                 '우리 보유 LH 원장의 두 블록 착공일은 2025-12-31이지만, 공식 1,100호의 구성 블록과 '
                 '같은 대상인지 확인되지 않았다. 따라서 과거 착공일만으로 공식 성과의 제외가 정당하다고 '
                 '결론 내릴 수 없으며, 공식 발표의 왕숙2 착공 성과를 자체 원장으로 아직 재현하지 못한 공백으로 기록한다.')
    action = ('공식 착공 1,100호의 구성 블록·물량·실적 인정일을 원천별로 확인하고, 보유 LH 공사 원장 '
              '(2026-07-01 기준)의 이후 판본 및 건축 인허가 실제착공 사건과 대조한다. '
              '공사 계약상 착공일과 보고 실적 인정일, 블록 차이·누락·정정 가능성을 확인한 뒤 판정한다. '
              '공식 수치를 자체 사건으로 입력하거나 본청약 1,498호로 대체하지 않는다.')
    projects = json.loads((ROOT / 'data/remediation/report-reproducibility-20261017/projects.json').read_text())
    blocks = [dict(project_id=p['id'], name=p['name'], block=p.get('block'),
                   units=p['construction_start_evidence']['units'],
                   event_date=p['construction_start_evidence']['event_date'],
                   source_base_date=p['construction_start_evidence']['source_base_date'],
                   evidence_url=p['evidence_url'])
              for p in projects if '왕숙2' in p['name'] and p.get('construction_start_evidence')]
    assert len(blocks) == 2 and sum(p['units'] for p in blocks) == 1498
    assert all(p['event_date'] == '2025-12-31' for p in blocks)
    case = dict(id='WANGSUK2-OFFICIAL-START-REVIEW-20261017', status='UNRESOLVED',
                official_included=True, official_value=1100, official_period=official['official_period'],
                official_event_type='CONSTRUCTION_STARTED', official_url=official['official_url'],
                official_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                own_construction_value=None, numeric_gap=None, comparable=False,
                official_block_membership_verified=False, prior_period_block_evidence=blocks,
                recruitment_value=1498, recruitment_date='2026-04-30',
                related_claims=['S04', 'M08', 'M16'],
                parent_scope='공식 3기 신도시 착공 7,300호의 구성 언급. 별도 가산하지 않음.',
                statement=statement, next_action=action, benchmark_used_as_event=False,
                previous_conclusion_correction='A-1·A-3의 전년도 착공 제외와 왕숙2 공식 성과 재현 여부는 별개다.')
    current['official_report_reviews'] = [case]
    for key in ('S04', 'M08'):
        row = next(r for r in report['rows'] if r['id'] == key)
        row.update(official_included=True, reconciliation_case_id=case['id'])
        row['blocker'] += ' ' + statement
        row['next_action'] = action
        if key == 'S04':
            row.update(status='OFFICIAL_SCOPE_RECONCILIATION_PENDING',
                       status_label='공식 착공 성과 포함 · 구성 블록·기간 대조 미완료',
                       own_value=None, numeric_gap=None, comparable=False, full_statement_reproducible=False)
    report['third_town']['caveat'] += ' 공식 보고서의 왕숙2 착공 1,100호는 구성 블록·실적 인정일 대조가 남아 있으며, 본청약 1,498호와 구분해 미재현 항목으로 기록했다.'
    report['status_counts'] = dict(__import__('collections').Counter(r['status'] for r in report['rows']))
    report['official_report_reviews'] = [case]
    report['priority_actions'].insert(0, action)
    current['diagnostics']['report_reproducibility'] = report
    for agreement in (current['agreement'], current['diagnostics']['agreement']):
        row = next(r for r in agreement['rows'] if r['id'] == 'S04')
        row.update(status='OFFICIAL_SCOPE_RECONCILIATION_PENDING', explanation=statement,
                   next_action=action, official_included=True, reconciliation_case_id=case['id'],
                   numeric_gap=None, actual_value=None, eligible=False, independent_match=False, state='pending')
        next(r for r in agreement['rows'] if r['id'] == 'M08')['explanation'] += ' ' + statement
    current['notice_classification_update']['construction_note'] += ' ' + statement
    html = (FOLDER / 'before.html').read_text()
    for category in current['categories']:
        for item in category['items']:
            if item['id'] in ('C3', 'D1', 'E1', 'J1', 'J4'):
                old = item['change_comment']
                item['change_comment'] += ' 공식 성과 포함 재검증: ' + statement
                item['reason'] = item['change_comment']
                html = html.replace(escape(old), escape(item['change_comment']))
    begin = html.index('<section class="section box" id="report-reproducibility">')
    end = html.index('</section>', begin) + len('</section>')
    html = html[:begin] + report_section(report) + html[end:]
    marker = '<section class="section box"><h2>53개 발표 항목 최신 재대조</h2>'
    begin = html.index(marker); end = html.index('</section>', begin) + len('</section>')
    replacement = details(current); start = replacement.index(marker)
    html = html[:begin] + replacement[start:replacement.index('</section>', start) + len('</section>')] + html[end:]
    html = html.replace('<main>', '<main><section class="section box" id="wangsuk2-official-review"><h2>왕숙2 · 공식 착공 성과 포함 및 자체 원장 미재현</h2><p>'
                        + escape(statement) + '</p><p>' + escape(action) + '</p></section>', 1)
    current.update(reason=REASON, assessed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
    begin = html.index('<script type="application/json" id="report-data">') + len('<script type="application/json" id="report-data">')
    end = html.index('</script>', begin)
    html = html[:begin] + json.dumps(current, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c') + html[end:]
    write('review', case); write('round', current)
    (FOLDER / 'round.html').write_text(html)


def publish():
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.data_integrity import amend_round
    print(amend_round(HomeService(engine_for(), ROOT / 'data'), ROUND, read('before')['digest'],
                      read('round'), (FOLDER / 'round.html').read_text(), '김민', REASON))


if __name__ == '__main__':
    globals()[sys.argv[1]]()
