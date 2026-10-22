"""Reproducible V01–V16 and Q4-32 reconciliation against one HOME snapshot."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/analysis/policy907-full-verification-20261021'
OUT = ROOT / 'docs/analysis/external_diagnostic_review_20261021'
FIELDS = ('check_id official_metric_id official_release_date official_value official_precision official_scope '
          'home_project_id home_cohort_id home_quantity home_quantity_scope home_event_type home_event_date '
          'home_date_basis source_url source_revision comparison_status discrepancy_reason source_document_page review_decision').split()


def read(name):
    return json.loads((BASE / (name + '.json')).read_text())


def csvread(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        return list(csv.DictReader(file))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def csvwrite(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (list, dict)) else v
                for k, v in row.items()})


def main():
    OUT.mkdir(exist_ok=True)
    snapshot = read('snapshot'); projects = {p['id']: p for p in read('projects')}
    model = read('model'); cohorts = model['portfolio_cohorts']; cs = {c['id']: c for c in cohorts}
    membership = {pid: c for c in cohorts for pid in c['source_ids']}
    support = {r['id']: r for r in read('supporting_rows')}
    comparisons = read('official_185_comparison'); rs = {r['지표ID']: r for r in comparisons}
    def versions(ids):
        return dict(snapshot_at=snapshot['snapshot_at'], projects=[dict(id=pid,
            revision=projects[pid]['revision_no'], revision_id=projects[pid].get('source_revision_id'),
            sha256=projects[pid].get('source_payload_hash'), mapping_revision=projects[pid]['mapping']['revision_no'])
            for pid in ids if pid in projects])
    def row(key, ids, quantity, scope, status, reason, decision, **extra):
        official = [rs[i] for i in ids]
        value = {k: None for k in FIELDS}
        pids = extra.pop('project_ids', list(dict.fromkeys(pid for r in official for pid in r['HOME_근거ID'].split('|') if pid in projects)))
        value.update(check_id=key, official_metric_id='|'.join(ids),
            official_release_date='|'.join(sorted({r['발표일'] for r in official})),
            official_value=[r['공식 기준수치'] for r in official] if len(official)>1 else official[0]['공식 기준수치'] if official else None,
            official_precision='|'.join(sorted({r['수치 정밀도'] for r in official})), official_scope=scope,
            home_project_id='|'.join(pids), home_cohort_id='|'.join(sorted({membership[p]['id'] for p in pids if p in membership})),
            home_quantity=quantity, home_quantity_scope=extra.pop('quantity_scope',scope),
            source_url='|'.join(sorted({r['HOME_출처'] or r['출처 공식 URL'] for r in official})),
            source_revision=versions(pids), comparison_status=status, discrepancy_reason=reason,
            source_document_page='|'.join(sorted({r['원문 내 위치'] for r in official})), review_decision=decision,
            snapshot_at=snapshot['snapshot_at'])
        value.update(extra)
        return value

    # Official 32 rows, 31 disjoint management cohorts. Never allocate the
    # combined A1/A3 capacity to either block without a verified breakdown.
    prior = csvread(ROOT / 'docs/analysis/gpt_report_20261020/comparison_32.csv')
    q4 = []; groups = {}
    for old in prior:
        old['official_evidence_url']=old['official_evidence_url'].split('#')[0]+'#page=6'
        pid = old['project_id']; p = projects[pid]; c = membership[pid]
        assert p['mapping']['status']=='CONFIRMED' and p['mapping']['policy_id']=='POL_2025_0907'
        official = int(old['official_units']); group = groups.setdefault(c['id'], dict(official=0, home=c['units'], rows=[]))
        group['official'] += official; group['rows'].append(int(old['number']))
        source_plans = [s for s in c['schedules'] if s['stage']=='SUPPLY']
        actual = [e for e in c['events'] if e['stage']=='SUPPLY' and e.get('event_date','9999')<='2026-10-21']
        confirmed_notices = []
        for r in support.values():
            if r.get('project_id') not in c['source_ids'] or r.get('status')!='CONFIRMED': continue
            for f in r.get('facts',[]):
                if f.get('stage')=='SUPPLY' and f.get('kind')=='ACTUAL' and not f.get('scope_partial'):
                    confirmed_notices.append(dict(source_id=r.get('source_entity_id'),date=f.get('date'),units=f.get('units'),
                        url=r.get('evidence_url'),source_type=r.get('checked_source_type') or f.get('source_type'),
                        revision=r.get('source_revision_no'),label=r.get('review_label') or r.get('source_name')))
        v={k:None for k in FIELDS}
        v.update(check_id='V06',official_metric_id='Q4-'+str(old['number']).zfill(2),
            official_release_date='2026-10-16',official_value=official,official_precision='정확한 계획호수',
            official_scope='수도권 2026년4분기 '+old['type']+' 공급계획 첨부 명세',
            home_project_id=pid,home_cohort_id=c['id'],home_quantity=c['units'],
            home_quantity_scope='관리사업 전체 계획규모; 금회 공고·공급 완료량 아님',
            home_event_type='PLAN',home_event_date=sorted({s['due_date'] for s in source_plans if s.get('due_date')}),
            home_date_basis='SOURCE_PLAN_AND_OFFICER_SCHEDULE_SEPARATED',
            source_url='|'.join(sorted({p['evidence_url'],old['official_evidence_url']})),
            source_revision=versions(c['source_ids']),comparison_status='EXACT' if c['units']==official and old['match_kind']!='COMBINED' else 'SCOPE_DIFFERENT',
            discrepancy_reason=('정부780은아파트726+오피스텔54구성. HOME주택집계726, 별도오피스텔54보존' if pid=='PRO_e05c4608f73fa5151e560558' else
                '정부498과국토부2026-501호·공식배포기관추천안내548이상이. 원인·제외범위미확정' if pid=='PRO_69217405e9523695488434c1' else
                '정부382와10.13지자체배포LH기관추천안내387이상이. 원인·변경관계미확정' if pid=='PRO_9f9031c8f3a9ef0626b95757' else old['reason']),source_document_page='PDF p6',
            review_decision='기존 승인값 유지; 계획 수량 대응과 실제 공급·일정 검증은 별도',
            official_name=old['official_name'],supply_form=p.get('tenure'),supply_type=p.get('supply_type_assessment',{}).get('label'),
            count_once_units=c['units'] if int(old['count_once_units']) else 0,
            source_plans=source_plans,registered_supply_events=actual,confirmed_recruitment_notices=confirmed_notices,
            government_appendix_url=old['official_evidence_url'],snapshot_at=snapshot['snapshot_at'],
            ancillary_officetel_rooms=54 if pid=='PRO_e05c4608f73fa5151e560558' else 0,
            government_scope_reconstruction_value=780 if pid=='PRO_e05c4608f73fa5151e560558' else c['units'])
        q4.append(v)
    for v in q4:
        g=groups[v['home_cohort_id']]
        v.update(group_official_units=g['official'],group_home_units=g['home'],
            group_difference=g['home']-g['official'],group_rows=g['rows'])
    assert len(q4)==32 and len(groups)==31
    assert sum(r['official_value'] for r in q4)==14731
    assert sum(r['count_once_units'] for r in q4)==14753
    differences=[dict(cohort_id=k,**v,difference=v['home']-v['official'],
        causal_status='HOUSING_VS_OFFICETEL_SCOPE_CONFIRMED' if k=='PRO_e05c4608f73fa5151e560558' else
            'OFFICIAL_SOURCE_CONFLICT_CAUSE_UNVERIFIED' if k in ('PRO_69217405e9523695488434c1','PRO_9f9031c8f3a9ef0626b95757') else 'UNVERIFIED',
        reason='LH아파트726호+오피스텔54실=정부780; 주택집계에서오피스텔분리' if k=='PRO_e05c4608f73fa5151e560558' else
            '공식 발표계획과 원천 사업규모 차이 확인; 변경·제외의 인과는 미입증')
        for k,v in groups.items() if v['home']!=v['official']]
    assert sorted(r['difference'] for r in differences)==[-54,-1,5,22,50]
    csvwrite(OUT/'comparison_32.csv',q4);csvwrite(OUT/'comparison_32_differences.csv',differences)

    stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN']
    def amount(c,ss,condition=lambda e: True):
        return min(c['units'],max([e.get('units') or 0 for e in c['events'] if e['stage'] in ss and
            e.get('status','ACTUAL')=='ACTUAL' and e.get('event_date','9999')<='2026-10-21' and condition(e)]+[0]))
    starts=[]
    for c in cohorts:
        direct=amount(c,['CONSTRUCTION']);reached=amount(c,stages[2:])
        if not reached:continue
        starts.append(dict(project_id=c['id'],name=c['name'],direct_registered_units=direct,
            construction_reached_units=reached,inferred_predecessor_units=reached-direct,
            inferred_flag_amount=amount(c,['CONSTRUCTION'],lambda e:e.get('inferred') is True),
            non_inferred_flag_amount=amount(c,['CONSTRUCTION'],lambda e:e.get('inferred') is False),
            flag_missing_amount=amount(c,['CONSTRUCTION'],lambda e:'inferred' not in e),
            warning='플래그별 값은 근거가 중첩될 수 있어 재합산 금지; 직접 등록량은 공식 실착공 확정량과 다름',
            events=[e for e in c['events'] if e['stage']=='CONSTRUCTION'],source_revision=versions(c['source_ids'])))
    csvwrite(OUT/'construction_provenance.csv',starts)
    reached=sum(r['construction_reached_units'] for r in starts);direct=sum(r['direct_registered_units'] for r in starts)
    inferred=[r for r in starts if r['inferred_predecessor_units']]
    assert len(inferred)==5 and reached-direct==1343
    csvwrite(OUT/'construction_predecessor_5.csv',inferred)

    # Preserve exclusions as exclusions, with their actual related cohorts.
    excluded=[]
    for pid in read('csv_export_summary')['mapped_sources_without_cohort']:
        p=projects[pid];multi='MULTI_SITE_CONTRACT' in p.get('warnings',[])
        district=re.sub(r'\s','',p.get('district') or '')
        related=[c for c in cohorts if district and district in re.sub(r'\s','',c['name'])]
        excluded.append(dict(project_id=pid,name=p['name'],units=p['planned_units'],
            excluded_reason='MULTI_SITE_CONTRACT' if multi else 'WHOLE_COMPLEX_VS_SELECTED_COHORT_OR_IDENTITY_REVIEW',
            evidence_url=p['evidence_url'],warnings=p.get('warnings',[]),
            related_cohort_ids=[c['id'] for c in related],related_quantities=[c['units'] for c in related],
            relation_status='관련 지구 관리범위 참고; 단위별 독립 합산 가능성 미확정',
            decision='미연결 신규사업으로 재가산 금지; 복합계약·유형분리 사유 보존',source_revision=versions([pid])))
    assert len(excluded)==11;csvwrite(OUT/'excluded_sources_11.csv',excluded)
    scopes=csvread(BASE/'data_scope_issues.csv')
    csvwrite(OUT/'scope_differences_current.csv',[dict(r,source_revision=versions(cs[r['관리사업ID']]['source_ids']),
        interpretation='수량 범위 차이 경보. 중복·오류 확정이 아니며 승인 상한 유지') for r in scopes])

    inventory=csvread(BASE/'policy907_management_projects.csv')
    unknown_form=sum(r['공급형태']=='미확인' for r in inventory)
    unresolved=sum(r['공급유형확인상태']=='UNRESOLVED' for r in inventory)
    new_id='PRO_aee63666787f1bcd4a6fcece'
    checks=[
        row('V01',['R029'],3553,'정부 당수2 착공3,400호','UNVERIFIED',
            '기존5블록은 계획 합계. A2 664호 입찰 재게시 추가 확보했으나 입찰·계약은 실제 착공 아님',
            'LH 지구정보·비공식 입찰규모 저장; 정부 산입블록과 실제 사건은 유보',home_event_type='PLAN'),
        row('V02',['R030'],1160,'부천역곡 정부 약1,200호 착공 사례','EVENT_DATE_PENDING',
            'A1통합공공임대1,160호 공식 규모와 동원건설 진행중 확인. A2분양976호와 독립. 정부 마감시점 산입은 미확정',
            '사용자 지시 담당자 정책관리 채택; 공식 수량·비공식 상태 출처 명시. 실제 착공일은 입력하지 않음',
            project_ids=[new_id],home_event_type='OBSERVED_CONSTRUCTION',home_event_date='2026-10-21',home_date_basis='OBSERVED_BY'),
        row('V03',['R031'],None,'서울 노후청사 복합개발 착공417호','UNVERIFIED',
            '발표는417호 총량만 명시. 조사 원문에서 동일 사업·구성 명세 미확보. 명부 비공개라고 단정할 증거도 없음',
            '사업명 추정·숫자 맞추기 금지; 정부 산입사업 명세 필요'),
        row('V04',['R051'],14451,'2026년1~3분기 공공분양 모집실적','UNVERIFIED',
            '24개 후보 공고 부분합.349호는 산술 간격이며 실제 누락량으로 확정할 수 없음',
            '정부 기관별 포함공고 명세·사전/본·정정 기준 필요'),
        row('V05',['R059'],4461,'2026년1~3분기 공공임대 모집실적','SCOPE_DIFFERENT',
            '외부 진단4,260호는 이전 판본. 직전 마곡도전숙201호 추가로18개 범위4,461호',
            '정부14,700호와 동일 모집단 전량이 아님. 기관별 미대사 구분 유지',home_event_type='RECRUITMENT_NOTICE_PARTIAL'),
        row('V06',[],14753,'정부4분기 공급32항목14,731호','SCOPE_DIFFERENT',
            '주택만14,753호,정부혼합범위재구성14,807(오피스텔54포함). 주택차이+22와 동일혼합범위차이+76을 구분. 상쇄를 정확도 개선으로 보지 않음',
            '최신 snapshot·원천revision·계획/실제·공급형태·합본1회 집계를 동일CSV에 통합',
            official_value=14731,official_release_date='2026-10-16',official_metric_id='Q4-01~Q4-32',
            project_ids=list(dict.fromkeys(r['home_project_id'] for r in q4)),home_event_type='PLAN'),
        row('V07',['R111','R112','R113','R114'],6123,'서울 정비사업 인허가19,447·착공12,211호','SCOPE_DIFFERENT',
            '3개 개별 정비사업3,178+1,515+1,430=6,123은 전체12,211의 전량 명부가 아님',
            '정비사업 전체 명세·같은 시점 분모 미확보. 부분사업으로 전체를 검증했다고 주장하지 않음'),
        row('V08',['R085','R087','R090','R092','R095','R097'],
            {i:rs[i]['HOME_동일범위비교값'] for i in ['R085','R087','R090','R092','R095','R097']},
            '서울1~7월 과거3년 인허가 평균·증감률','UNVERIFIED',
            '확보 PDF 판본으로 평균21,273/18,629/2,644; 발표20,948/18,395/2,553과 차이. 개정 원인 미입증',
            '원표 판본·평균 산식 미확정 유지. 공표판본 차이로 자동 판정하지 않음'),
        row('V09',['R099','R100','R101','R102','R104','R105','R107','R108','R109','R110'],
            dict(prior_seoul_2025_jan_jul=13508,current_api=13631),
            '서울1~7월 착공 및 파생 증감·평균','SOURCE_VERSION_DIFFERENCE',
            '당시 PDF13,508과 현재API13,631로 판본차이 직접 재현.2026값19,507은 동일. 개정 발생일·행정사유는 별도 미확보',
            '과거PDF·현행API를 나란히 보존; 파생10항목을 독립10건 정확도 검증으로 세지 않음'),
        row('V10',['R025'],dict(management=2188,whole_candidate=2342,A17_rental=154),
            '계양 정부 착공 약2,300호','SCOPE_DIFFERENT',
            'LH공식 A17전체463=분양309+향후행복154 구성은 해소. 정부4개블록 산입명세는 미확정',
            '임대154를 현재 모집실적으로 가산하지 않음. 전체후보2,342의 수량표현과 실적 범위 구분'),
        row('V11',['R026','R027','R028'],dict(gyosan=1115,wangsuk2=1063,daejang=574),
            '하남교산·왕숙2·대장 공개 착공 사례','EVENT_DATE_PENDING',
            '물량은개략량 양립. 교산A2원천2024년, 왕숙2계약1,082와주택1,063은19호범위차이, 정부산입미확정',
            '기존 공식·담당자 비공식 확인 유지; 날짜·정부 산입을 숫자 유사성으로 확정하지 않음'),
        row('V12',['R064'],dict(whole_rental=822,current_offer=406,excluded=416),
            '금토 정부 임대 모집 약800호','SCOPE_DIFFERENT',
            '822는단지임대전체.219+187=406은금회.416은순환411+어린이집5. 정부의순환용산입규칙미확정',
            '공식PDF보정 유지. 전체규모가맞는다는이유로금회모집416호추가금지'),
        row('V13',[],dict(rows=len(scopes),cohorts=len({r['관리사업ID'] for r in scopes})),'전체/부분 차이 경보','SCOPE_DIFFERENT',
            '원천 범위 차이를 여러단계로 보여준 행 수. 확정 오류 건수로 해석하지 않음',
            '원천범위·관리상한·revision을CSV로보존; 승인값변경없음'),
        row('V14',[],dict(managed=len(inventory),unknown_form=unknown_form,unresolved_government_type=unresolved),
            '전체 관리사업의 공급형태·정부형 분류','UNVERIFIED',
            '세부공급형태 미확인과 정부형공급유형 미확정은 별도 필드. 공사원천에임대세부형이없을수있음',
            '출처가확인된유형만기입; 전량확정주장금지'),
        row('V15',[],dict(construction_reached=reached,direct_registered=direct,inferred_predecessor=reached-direct),
            '정책관리 착공단계 도달량과 직접 등록량','SCOPE_DIFFERENT',
            '외부 진단의78,541은당시직접등록량이지전량공식실착공확정량아님. 신규A1 1,160은비공식진행상태확인',
            '직접등록·선행단계도달추정·원천확인등급을분리. 5개추정1,343호명세보존'),
        row('V16',[],11,'연결원천과 관리단위 사이 제외대상','SCOPE_DIFFERENT',
            '복수현장계약 및 전체단지/선택유형범위가 관리코호트와 다름. 11개를 신규사업11개로 가산불가',
            '제외사유·관련관리ID·원천revision 보존; 동일성추가확인전승인총계유지'),
    ]
    assert len(checks)==16 and len({r['check_id'] for r in checks})==16
    assert all(set(FIELDS)<=set(r) for r in checks+q4)
    csvwrite(OUT/'diagnostic_V01_V16.csv',checks)
    write(OUT/'diagnostic_V01_V16.json',checks)
    combined=[dict(r,snapshot_at=snapshot['snapshot_at'],official_release_layer='2026-10-16' if r['발표일']=='2026-10-16' else 'OTHER_RELEASE',
        home_source_revisions=versions(r['HOME_근거ID'].split('|'))) for r in comparisons]
    csvwrite(OUT/'official_185_versioned.csv',combined)
    summary=dict(snapshot=snapshot,checks=16,check_status_counts=dict(Counter(r['comparison_status'] for r in checks)),
        q4_rows=32,q4_unique_cohorts=31,q4_official=14731,q4_home_capacity=14753,q4_difference=22,
        q4_mixed_scope_reconstruction=14807,q4_mixed_scope_difference=76,ancillary_officetel_rooms=54,
        q4_difference_causes_confirmed=False,official_indicators=185,
        release_october_16=sum(r['발표일']=='2026-10-16' for r in comparisons),
        release_other=sum(r['발표일']!='2026-10-16' for r in comparisons),
        source_projects=read('csv_export_summary')['source_projects'],management_cohorts=len(cohorts),
        capacity=sum(c['units'] for c in cohorts),construction_reached=reached,construction_direct_registered=direct,
        construction_predecessor_inferred=reached-direct,supply=sum(amount(c,['SUPPLY']) for c in cohorts),
        unknown_supply_form=unknown_form,unresolved_supply_type=unresolved,
        exact_start_date_for_new_A1=None,official_case_inclusion_for_A1=False,
        existing_approved_values_preserved=False,raw_sources_preserved=True,
        approved_correction='병점주택726/오피스텔54분리 및공식착공2025-12-31 726호채택; 공식모집·입주계획우선보정',new_policy_project_id=new_id)
    assert summary['release_october_16']==67 and summary['release_other']==118
    assert (summary['source_projects'],summary['management_cohorts'],summary['capacity'])==(231,176,152377)
    assert (reached,direct,summary['supply'])==(81770,80427,58125)
    write(OUT/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
