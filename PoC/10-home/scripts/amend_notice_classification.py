"""Repair report aggregation from existing notice facts, preserving R01 editions."""
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FOLDER = ROOT / 'data/remediation/notice-classification-20261017'
PREVIOUS = ROOT / 'data/remediation/report-reproducibility-20261017'
REASON = '공식 발표 후 도출된 보완 사항 적용 · 모집공고 사건의 분양·임대 분류 유실 수정'


def read(name):
    return json.loads((FOLDER / (name + '.json')).read_text())


def write(name, value):
    (FOLDER / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def capture():
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.data_integrity import get_round
    from backend.independent_metrics import freeze, get_snapshot
    from scripts.reassess_report_reproducibility import ROUND
    FOLDER.mkdir(parents=True, exist_ok=True)
    if (FOLDER / 'before.json').exists():
        raise ValueError('이미 보관된 수정 전 평가를 덮어쓰지 않습니다.')
    s = HomeService(engine_for(), ROOT / 'data')
    before = get_round(s, ROUND)
    write('before', before)
    (FOLDER / 'before.html').write_text(get_round(s, ROUND, html=True))
    old = get_snapshot(s, before['result']['snapshot_id'])
    write('snapshot-before', old)
    # Same knowledge cutoff isolates the algorithm repair from fresh collection.
    for name in ('projects', 'delivery', 'annual', 'inventory', 'reference-rows'):
        shutil.copyfile(PREVIOUS / (name + '.json'), FOLDER / (name + '.json'))
    recompute()


def recompute():
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.independent_metrics import freeze
    s = HomeService(engine_for(), ROOT / 'data')
    old = read('snapshot-before')
    new = freeze(s, '김민', REASON, known_at=datetime.fromisoformat(old['context']['known_at']),
                 **old['context']['filters'])
    write('snapshot', new)
    prior = {e['event_id']: e for e in old['result']['selected_events']}
    changes = [dict(event_id=e['event_id'], name=e['name'], quantity=e['quantity'],
                    event_date=e['event_date'], before=prior[e['event_id']]['taxonomy']['supply_mode'],
                    after=e['taxonomy']['supply_mode'], evidence=e.get('classification_evidence'),
                    evidence_url=e['evidence_url'])
               for e in new['result']['selected_events'] if e['event_id'] in prior
               and e['taxonomy']['supply_mode'] != prior[e['event_id']]['taxonomy']['supply_mode']]
    write('classification-changes', changes)
    excluded_ids = {e['event_id'] for e in new['result']['selected_events']}
    write('newly-excluded', [e for e in new['result']['exclusions'] if e['event_id'] in prior and e['event_id'] not in excluded_ids])
    print(json.dumps(dict(snapshot_id=new['id'], classification_changes=len(changes), newly_excluded=len(read('newly-excluded'))), ensure_ascii=False))


def build():
    import scripts.reassess_report_reproducibility as report
    report.FOLDER = FOLDER
    report.REASON = REASON
    report.build()
    current = read('round')
    prior = read('before')['result']['report_reproducibility']
    old_sale = next(r for r in prior['rows'] if r['id'] == 'M16')['own_value']
    sale = next(r for r in current['report_reproducibility']['rows'] if r['id'] == 'M16')
    note = (f'왕숙2 점검으로 확인한 집계 오류 수정: 공사·분양 사업 중복 제거 시 공고의 분양·임대 분류가 '
            f'유실되어 제외된 사건을 원문 판본 기준으로 복원했다. 같은 인지시각의 공공분양 부분 합계 '
            f'{old_sale:,}호 → {sale["own_value"]:,}호. 왕숙2 A-1 812호와 A-3 686호 포함. '
            '신규 수집이나 정책 재매핑에 따른 증가가 아니며 전체 실적 정확도 가점은 없음. '
            '분양전환 공공임대는 임대로 분류하고, 예전 파서 판본에서 회차 정보가 빠진 추가·잔여·예비입주자 공고는 신규 공급 합계에서 제외했다.')
    sale['blocker'] += ' ' + note
    sale['next_action'] = '복원된 분류의 원문 추적을 유지하고 모집공고·실제 계약 실적의 기준 및 전수 범위를 검증한다.'
    construction_note = ('왕숙2 A-1·A-3는 보유 LH 공사 원장의 착공일이 모두 2025-12-31이므로 '
                         '2026년 신규 착공 합계에서 제외한다. 2026-04-30 본청약 1,498호와 구분한다.')
    next(r for r in current['report_reproducibility']['rows'] if r['id'] == 'M08')['blocker'] += ' ' + construction_note
    current['diagnostics']['report_reproducibility'] = current['report_reproducibility']
    current['notice_classification_update'] = dict(comment=note, construction_note=construction_note,
        previous_value=old_sale, current_value=sale['own_value'], changes=read('classification-changes'),
        newly_excluded=read('newly-excluded'),
        known_at=current['report_reproducibility']['known_at'], baseline_comparison_preserved=True)
    html = (FOLDER / 'round.html').read_text()
    from html import escape
    for category in current['categories']:
        for item in category['items']:
            if item['id'] in ('C3', 'D1', 'J1', 'J4'):
                old_comment = item['change_comment']
                item['change_comment'] += ' ' + note
                item['reason'] = item['change_comment']
                html = html.replace(escape(old_comment), escape(item['change_comment']))
    begin = html.index('<section class="section box" id="report-reproducibility">')
    end = html.index('</section>', begin) + len('</section>')
    html = html[:begin] + report.report_section(current['report_reproducibility']) + html[end:]
    # Item comments are rendered in the standard report; add a visible amendment
    # note as well, while retaining the original technical-score calculation.
    html = html.replace('<main>', '<main><section class="section box"><h2>보완1 갱신 · 모집공고 분류 유실 수정</h2><p>'
                        + escape(note) + '</p><p>' + escape(construction_note) + '</p></section>', 1)
    begin = html.index('<script type="application/json" id="report-data">') + len('<script type="application/json" id="report-data">')
    end = html.index('</script>', begin)
    html = html[:begin] + json.dumps(current, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c') + html[end:]
    write('round', current)
    (FOLDER / 'round.html').write_text(html)
    write('assessment', current['report_reproducibility'])
    write('diagnostics', current['diagnostics'])
    print(note)


def publish():
    import scripts.reassess_report_reproducibility as report
    report.FOLDER = FOLDER
    report.REASON = REASON
    report.publish()


if __name__ == '__main__':
    globals()[sys.argv[1]]()
