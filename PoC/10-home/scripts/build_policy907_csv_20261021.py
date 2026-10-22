"""Lossless linked-project CSVs with supply form, provenance and counting scope."""
import csv
import json
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit
from scripts.export_policy907_verification_20261021 import csvwrite, dump, FOLDER

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/analysis' / FOLDER
STAGES = dict(POLICY='정책', BUSINESS='사업화', APPROVAL='인허가', CONSTRUCTION='착공',
              COMPLETION='준공', SUPPLY='공급·모집', MOVE_IN='입주')
PROGRAMS={}


def read(name):
    return json.loads((OUT / (name + '.json')).read_text())


def source_class(value):
    text = json.dumps(value, ensure_ascii=False)
    if value.get('inferred') or value.get('input_rule', '').startswith(('OFFICER_CURRENT_ESTIMATE', 'PREDECESSOR_', 'OFFICER_AVERAGE')):
        return '담당자 추정'
    host=urlsplit(value.get('evidence_url') or '').hostname or ''
    news=any(host==h or host.endswith('.'+h) for h in ['etoday.co.kr','yna.co.kr','richgo.ai','thebell.co.kr','dnews.co.kr','donga.com','joongang.co.kr'])
    if '비공식' in text or value.get('source_type') == 'NON_OFFICIAL' or value.get('checked_source_type') == 'NON_OFFICIAL' or news:
        return '담당자 확인 - 비공식 자료: 출처 컬럼 참조'
    if '자동 매핑' in text and (value.get('source_type')=='OFFICIAL' or '공식' in text):
        return '공식 자료 자동 매핑'
    if value.get('input_rule') == 'OFFICER_VERIFIED_SOURCE':
        return '담당자 확인 - 공식 자료: 출처 컬럼 참조'
    return '공식 원천·연결 근거' if value.get('source_id') not in ('officer', None) else '담당자 입력·근거 확인 필요'


def base(project, cohort=None):
    mapping = project.get('mapping', {})
    program=PROGRAMS.get(mapping.get('program_id'),{})
    assessment = project.get('supply_type_assessment', {})
    return dict(기준일='2026-10-21', 정책ID=mapping.get('policy_id'), 정책='주택공급 확대방안(9·7)',
        정책발표일='2025-09-07',정책전체목표호수=1350000,정책목표주의='정책 전체 목표; 사업별 합산 금지',
        프로그램ID=mapping.get('program_id'), 프로그램=mapping.get('program_name') or project.get('program'),
        프로그램매핑상태=program.get('status'),프로그램정책연결근거=program.get('basis'),프로그램정책연결출처=program.get('evidence_url'),
        사업ID=project['id'], 관리사업ID=(cohort or {}).get('id'), 사업명=project['name'], 시도=project.get('region'),
        시군구=project.get('municipality'), 지구=project.get('district'), 블록=project.get('block'),
        공급형태=project.get('tenure') or '미확인', 공급유형코드=assessment.get('code', 'UNKNOWN'),
        공급유형=assessment.get('label', '미확인'), 공급유형확인상태=assessment.get('status'),
        공급유형판단근거=assessment.get('basis'), 공급유형출처=assessment.get('evidence_url'),
        공공여부=project.get('public_status') or ('공공' if assessment.get('code')=='PUBLIC' else
            '민간' if assessment.get('code') in ['PRIVATE_RENEWAL','OTHER_PRIVATE','PUBLIC_SUPPORTED_RENT'] else
            '공공·민간 혼합' if assessment.get('code')=='MIXED' else '미분류'), 계획총호수=project.get('planned_units'),
        매핑상태=mapping.get('status'), 매핑근거=mapping.get('basis'), 매핑출처=mapping.get('evidence_url'),
        원천ID=project.get('source_id'), 원천판본=project.get('revision_no'), 원천기준일=project.get('source_date') or project.get('base_date'),
        원천등록일=project.get('recorded_at'), 원천URL=project.get('evidence_url'))


def main():
    projects = read('policy_linked_projects')
    PROGRAMS.update({r['id']:r for r in read('programs')})
    model = read('model')
    cohorts = model['portfolio_cohorts']
    matrix = {r['id']: r for r in read('matrix')['items']}
    supporting = read('supporting_rows')
    profiles = {r['project_id']: r for r in supporting if r.get('source_id') == 'manual_project' and 'progress' in r}
    membership = {}
    for c in cohorts:
        for pid in c['source_ids']:
            assert pid not in membership
            membership[pid] = c
    source_rows, facts, flags = [], [], []
    for project in projects:
        pid = project['id']
        c = membership.get(pid)
        row = base(project, c)
        row.update(관리집계포함=bool(c), 관리집계채택호수=c.get('units') if c else None,
            관리집계대표원천=(c or {}).get('id') == pid,
            원천별호수합산금지='동일 현장 복수 원천 포함. 총계는 management_projects.csv의 관리사업 단위로 계산')
        profile = profiles.get(pid, {})
        for stage, label in STAGES.items():
            cell = matrix[pid]['cells']['CONSTRUCTION' if stage == 'COMPLETION' else stage]
            evidence = [e for e in cell['sources'] if (e.get('milestone') == 'COMPLETION' if stage == 'COMPLETION'
                else e.get('milestone') != 'COMPLETION' if stage == 'CONSTRUCTION' else True)]
            actual = profile.get('progress', {}).get(stage)
            if not actual:
                selected = [e for e in evidence if e.get('kind') == 'ACTUAL' and e.get('date') and not e.get('scope_partial') and e.get('pct') is None]
                dates = {e['date'] for e in selected if e.get('date_basis') != 'OBSERVED_BY'}
                actual = selected[0] if len(dates) == 1 else {}
            plan = project.get('managed_schedules', {}).get(stage, {})
            actual_date = actual.get('event_date') or actual.get('date')
            row.update({label+'_측정일': actual_date, label+'_측정호수': actual.get('units'),
                label+'_측정구분': source_class(actual) if actual else '미확보',
                label+'_측정일기준': actual.get('date_basis') or ('ESTIMATED' if actual.get('inferred') else 'EVENT_OR_UNSPECIFIED'),
                label+'_측정근거': actual.get('input_basis') or actual.get('basis') or actual.get('reason'),
                label+'_측정출처': actual.get('evidence_url') or actual.get('source_anchor', {}).get('evidence_url'),
                label+'_계획일': plan.get('due_date'), label+'_계획호수': plan.get('units'),
                label+'_계획정밀도': plan.get('source_precision') or plan.get('date_precision') or plan.get('precision'),
                label+'_계획원문표기': plan.get('source_date_label'), label+'_계획추정여부': plan.get('inferred'),
                label+'_계획근거': plan.get('input_basis') or plan.get('basis'), label+'_계획출처': plan.get('evidence_url'),
                label+'_근거수': len(evidence), label+'_확인상태': cell.get('status')})
            for index, item in enumerate(evidence):
                fact = {k: row[k] for k in ['사업ID', '관리사업ID', '사업명', '프로그램ID', '프로그램']}
                fact['공급형태'] = row['공급형태']
                fact.update(공급유형=row['공급유형'], 단계=stage, 단계명=label, 근거순번=index+1,
                    자료구분=item.get('kind'), 날짜=item.get('date'), 날짜원문=item.get('date_label'),
                    날짜기준=item.get('date_basis'), 호수=item.get('units'), 부분범위=item.get('scope_partial'),
                    담당자추정=item.get('inferred'), 확인구분=source_class(item), 원천ID=item.get('source_id'),
                    원천객체ID=item.get('source_entity_id'), 원천판본=item.get('source_revision_no'),
                    출처URL=item.get('evidence_url'), 근거=item.get('basis'), 원천전체JSON=item)
                facts.append(fact)
        source_rows.append(row)
    csvwrite(OUT/'policy907_all_source_projects.csv', source_rows)
    csvwrite(OUT/'policy907_all_stage_evidence.csv', facts)
    ps = {p['id']: p for p in projects}
    managed, events, schedules = [], [], []
    for c in cohorts:
        row = base(ps[c['id']], c)
        forms={ps[pid].get('tenure') or '미확인' for pid in c['source_ids']}
        known_forms={f for f in forms if '확인' not in f and f.strip() not in ['','-','—']}
        row.update(계획총호수=c['units'], 원천사업ID목록='|'.join(c['source_ids']), 원천기록수=len(c['source_ids']),
            공급형태=' | '.join(sorted(known_forms)) if known_forms else '미확인',공급형태_원천값목록=' | '.join(sorted(forms)),
            원천기록합산금지='관리사업별 한 번만 계산. 세부 근거 행 재합산 금지')
        for stage, label in STAGES.items():
            es = [e for e in c['events'] if e['stage'] == stage and e.get('status', 'ACTUAL') == 'ACTUAL' and e.get('event_date') and e['event_date'] <= '2026-10-21']
            ts = [s for s in c['schedules'] if s['stage'] == stage]
            raw_max = max((e.get('units') or 0 for e in es), default=0)
            row.update({label+'_측정날짜목록':'|'.join(sorted({e['event_date'] for e in es})),
                label+'_측정원천최대호수':raw_max if es else None, label+'_집계채택호수':min(c['units'],raw_max) if es else None,
                label+'_추정포함':any(e.get('inferred') for e in es) if es else None,
                label+'_계획날짜목록':'|'.join(sorted({s['due_date'] for s in ts if s.get('due_date')})),
                label+'_계획원천최대호수':max((s.get('units') or 0 for s in ts),default=None),
                label+'_출처목록':'|'.join(sorted({e['evidence_url'] for e in es+ts if e.get('evidence_url')}))})
            if raw_max > c['units']:
                flags.append(dict(관리사업ID=c['id'],사업명=c['name'],단계=stage,문제구분='전체·부분 호수 차이',
                    관리범위호수=c['units'],원천최대호수=raw_max,
                    처리='현행 집계 상한은 보존하고 원천 전체량을 별도 공개. 전체 단지·복수 현장·공급유형 구성 추가 확인 필요'))
            for kind, records in [('ACTUAL',es),('PLAN',ts)]:
                for index,item in enumerate(records):
                    target=events if kind=='ACTUAL' else schedules
                    target.append(dict(관리사업ID=c['id'],사업명=c['name'],공급형태=row['공급형태'],공급유형=row['공급유형'],
                        단계=stage,단계명=label,자료구분=kind,순번=index+1,날짜=item.get('event_date') or item.get('due_date'),
                        날짜정밀도=item.get('precision'),날짜기준=item.get('date_basis'),호수=item.get('units'),
                        집계상한호수=c['units'],확인구분=source_class(item),출처URL=item.get('evidence_url'),원천전체JSON=item))
        managed.append(row)
    csvwrite(OUT/'policy907_management_projects.csv',managed)
    csvwrite(OUT/'policy907_management_events.csv',events)
    csvwrite(OUT/'policy907_management_plans.csv',schedules)
    csvwrite(OUT/'data_scope_issues.csv',flags)
    programs = [r for r in read('programs') if r['policy_id']=='POL_2025_0907' and r['status']!='RELEASED']
    csvwrite(OUT/'policy907_programs.csv',[dict(r,linked_source_projects=sum(p['mapping'].get('program_id')==r['id'] for p in projects),
        management_projects=sum(c.get('program_id')==r['id'] for c in cohorts)) for r in programs])
    csvwrite(OUT/'policy907_policy_and_program_targets.csv',[
        dict(scope='POLICY',id=model['policy_id'],name='9·7 정책',year='',units=model['target_units'],evidence_url=model['plan']['evidence_url'])]+[
        dict(scope='POLICY_ANNUAL',id=model['policy_id'],name='9·7 정책 연차 목표',year=r['year'],units=r['units'],evidence_url=model['plan']['evidence_url']) for r in model['plan']['annual']]+[
        dict(scope='PROGRAM_TARGET',id=p['id'],name=p['name'],year=r['year'],units=r['units'],evidence_url=model['plan']['evidence_url']) for p in model['plan']['programs'] for r in p['annual']])
    snapshot=read('snapshot')
    assert len(source_rows)==snapshot['linked_source_projects']
    assert len(managed)==snapshot['management_cohorts']
    dump(OUT/'csv_export_summary.json',dict(source_projects=len(source_rows),management_projects=len(managed),
        management_capacity=sum(c['units'] for c in cohorts),stage_evidence_rows=len(facts),events=len(events),plans=len(schedules),
        supply_forms=dict(Counter(p.get('tenure') or '미확인' for p in projects)),scope_issue_rows=len(flags),
        mapped_sources_without_cohort=[p['id'] for p in projects if p['id'] not in membership]))
    print((OUT/'csv_export_summary.json').read_text())


if __name__=='__main__':
    main()
