"""Can HOME write the report from its own records? Benchmark values are never inputs.

Each statement has a data contract. Existing figures, computable partial facts,
unlinked records, missing operational ledgers and new policy decisions differ.
"""
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from .evidence_bridge import match_key

REGIONS={'서울특별시','경기도','인천광역시'}
# A metric classification, not a policy-link reassignment or a briefing value.
THIRD_TOWN_DISTRICTS={('경기도',n) for n in ('남양주왕숙','남양주왕숙2','하남교산','고양창릉','부천대장')}|{('인천광역시','인천계양')}
THIRD_TOWN_DEFINITION_URL='https://www.xn--3-3u6ey6lv7rsa.kr/kor/CMS/Contents/Contents.do?mCode=MN181'
TYPES={
    'TARGET': {'M01','M02','M03','M06','M35','M36'},
    'ACTUAL': {'M04','M07','M08','M09','M10','M11','M14','M15','M16','M19','M30','M31'},
    'PLAN': {'M17','M18','M20','M21','M22'},
    'FORECAST': {'M05','M37'},
    'OPERATIONS': {'M12','M13','M23','M24','M25','M26'},
    'POLICY_FACT': {'M27','M28','M29'},
    'SERIES': {'M32','M33','M34'},
}
LABELS={'DERIVED_PARTIAL':'보유 데이터 부분 산출 가능','REFERENCE_ONLY':'보유 참조값 인용 가능',
    'INPUT_VERSION_GAP':'최신 목표·결정 판본 확인 필요','SOURCE_EVIDENCE_GAP':'대상 원천의 사건 증빙 보완 필요',
    'AGGREGATION_GAP':'자료 보유 · 연결·집계 보완 필요','INPUT_LEDGER_GAP':'업무 원장 확보 필요',
    'DEFINITION_GAP':'집계 정의·분류 확인 필요','POLICY_FACT_REQUIRED':'외부 정책 결정 입력 필요',
    'FORECAST_GAP':'사업 일정·전망 산식 보완 필요'}


def normalized(text):return re.sub(r'[^가-힣A-Z0-9]','',str(text or '').upper())


def area_matches(name,area):
    name,area=normalized(name),normalized(area)
    if area=='남양주왕숙':return area in name and '남양주왕숙2' not in name
    return area in name


def evaluate(benchmark,snapshot,projects,delivery,annual,inventory,reference_rows=()):
    known_at=snapshot['context']['known_at'];events=snapshot['result']['selected_events']
    projects_by_id={p['id']:p for p in projects}
    # A single UI programme label is not the metric's population definition.
    # Incheon records use a different UI programme but remain third-town sites.
    end_date=datetime.fromisoformat(known_at).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
    tagged_third_districts=set()
    for p in projects:
        if (p.get('mapping',{}).get('program_name') or p.get('program'))=='3기 신도시':
            key=match_key(p)
            if key:tagged_third_districts.add(key[:2])
    def is_third(project_id):
        p=projects_by_id.get(project_id,{})
        key=match_key(p)
        return bool(key and key[:2] in THIRD_TOWN_DISTRICTS)
    def event_subset(key,row):
        event_type='RECRUITMENT_PUBLISHED' if key in {'M16','M19'} else 'APPROVAL_GRANTED' if key=='M30' else 'CONSTRUCTION_STARTED'
        result=[e for e in events if e['event_type']==event_type and e.get('region') in REGIONS and '2026-01-01'<=e['event_date']<=end_date]
        if key.startswith('S'):return [e for e in result if area_matches(e['name'],row['name'])]
        if key=='M08':return [e for e in result if is_third(e['project_id'])]
        if key in {'M09','M15'}:return None  # These programme boundaries are not encoded in the existing taxonomy.
        if key in {'M07','M16','M19'}:
            result=[e for e in result if e.get('source_id','').startswith(('lh_','sh_','gh_','ih_'))]
        if key in {'M10','M11'}:result=[e for e in result if e.get('taxonomy',{}).get('acquisition_mode')=='NEW_PURCHASE_AGREEMENT']
        if key in {'M11','M30'}:result=[e for e in result if e['region']=='서울특별시']
        if key=='M14':result=[e for e in result if e.get('taxonomy',{}).get('acquisition_mode')=='REDEVELOPMENT']
        if key in {'M16','M19'}:
            result=[e for e in result if e['event_date']<='2026-09-30' and e.get('taxonomy',{}).get('supply_mode')==('SALE' if key=='M16' else 'RENT')]
        if key=='M30':result=[e for e in result if e['event_date']<='2026-08-31']
        return result
    raw_counts=Counter()
    for r in inventory:raw_counts[r['kind']]+=r['records']
    rows=[]
    for original in benchmark['rows']:
        key=original['id']
        kind=next((k for k,v in TYPES.items() if key in v),'ACTUAL' if original.get('stage')=='착공' else 'PLAN')
        r=dict(id=key,name=original['name'],kind=kind,official_period=original['official_period'],
            benchmark_value=original['official_value'],benchmark_unit=original['unit'],
            own_value=None,own_unit=original['unit'],event_ids=[],source_revision_ids=[],project_ids=[],
            status='SOURCE_EVIDENCE_GAP',scope_verified=False,comparable=False,numeric_gap=None,
            full_statement_reproducible=False,refresh_only_sufficient=False,
            input_period='2026년 발생 사건 · 현재 보유 원장',known_at=known_at,
            report_value_used_as_input=False,writeable_statement=None)
        if kind=='ACTUAL' and key!='M31':
            r.update(required='사업·블록 식별, 대상 분류, 실제 사건일, 해당 사건 세대수, 정정·취소 및 중복 관계',
                formula='대상·지역·발생기간 필터 → 동일 물리 구획 중복 제거 → 유효 사건 물량 합계',
                blocker='보유 사업 범위의 부분 산출은 가능하나 대상 전수·최신 사건 누락 여부는 미검증.',
                next_action='기존 원장과 사건을 먼저 연결·집계하고 미연결·미확보·기간 차이를 분리한다. 항목명과 같은 API를 찾지 않는다.')
            subset=event_subset(key,original)
            if subset is None:
                r.update(status='DEFINITION_GAP',blocker='도심 노후청사 등과 일반 민간의 분류 경계가 현재 원장에 확정돼 있지 않음. 전체 착공 합계를 대신 넣지 않음.')
            elif subset:
                r.update(status='DERIVED_PARTIAL',own_value=sum(e['quantity'] for e in subset),
                    event_ids=[e['event_id'] for e in subset],project_ids=sorted({e['project_id'] for e in subset}),
                    source_revision_ids=sorted({e['source_revision_id'] for e in subset}),
                    input_period=min(e['event_date'] for e in subset)+' ~ '+max(e['event_date'] for e in subset),
                    own_scope='현재 보유 원장에서 직접 증빙된 대상 부분집합')
                r['writeable_statement']=f"HOME 보유 원장에서 {original['name']} 관련 {len(subset)}개 사건, {r['own_value']:,}호를 확인했다. 전체 실적 확정값은 아니다."
            else:r.update(blocker='대상 자료·후보가 존재하더라도 인정 가능한 사건이 현재 집계에 연결되지 않음. 실제 실적 0으로 해석하지 않음.')
            if key in {'M14','M30','M15'}:r['available_raw_rows']={k:raw_counts[k] for k in ('permit','general_permit','renewal_roster','project')}
        elif key=='M31':
            cell=next((x['metrics']['착공'] for x in annual.get('rows',[]) if x['year']==2026 and x.get('region')=='서울특별시'),{})
            r.update(status='REFERENCE_ONLY' if cell.get('units') is not None else 'SOURCE_EVIDENCE_GAP',own_value=cell.get('units'),
                input_period=str(cell.get('through_period')),required='서울 월별 착공 시계열과 기간별 판본',
                formula='서울 2026년 1~8월 월별 착공 합계',own_scope='플랫폼에 저장된 공식 통계 참조값',
                blocker='보유 통계로 수치는 인용 가능. 사업 사건으로 독립 산출한 값과 구분하며 10월 최신값을 뜻하지 않음.',
                next_action='월별 원장의 동일 기간 재현과 사업 사건 합계 대조',writeable_statement='저장된 서울 착공 통계의 확인 기간과 값을 출처와 함께 제시할 수 있다.')
        elif kind=='TARGET':
            old=delivery.get('plan',{})
            value=old.get('target_units') if key=='M01' else next((v['units'] for v in old.get('annual',[]) if v['year']==2026),None) if key=='M03' else None
            r.update(status='REFERENCE_ONLY' if key=='M01' and value is not None else 'INPUT_VERSION_GAP',own_value=value,
                required='주체가 결정한 목표·기간·대상·단위·적용일과 변경 판본',formula='유효한 정책 목표 판본 선택; 실적 합계에서 목표를 추정하지 않음',
                own_scope='기존 9·7 목표 판본' if value is not None else None,
                blocker='새 통합 목표·제도 결정은 사업 실적으로 추론할 수 없음. 최신 결정이 원천 입력돼야 함.',
                next_action='이미 수집한 정책 원문·변경 결정의 필드 추출과 판본 연결 여부부터 확인')
        elif kind=='PLAN':
            stage='MOVE_IN' if key in {'M22','S14','S15','S16'} else 'SUPPLY'
            start,end=('2026-10-01','2027-12-31') if key=='M22' else ('2026-12-01','2026-12-31') if key=='S14' else ('2027-01-01','2027-12-31') if key in {'S15','S16'} else ('2026-10-01','2026-12-31')
            cohorts=delivery.get('portfolio_cohorts',[])
            if key.startswith('S'):cohorts=[c for c in cohorts if area_matches(c['name'],original['name'])]
            if key=='M18':cohorts=[c for c in cohorts if any(is_third(i) for i in [c['id']]+c.get('source_ids',[]))]
            plans=[dict(project_id=c['id'],name=c['name'],stage=stage,date=s['due_date'],units=s.get('units'),origin=s.get('origin'),managed=bool(s.get('managed_schedule')),evidence_url=s.get('evidence_url')) for c in cohorts for s in c.get('schedules',[]) if s['stage']==stage and start<=s['due_date']<=end]
            r.update(status='AGGREGATION_GAP' if plans else 'SOURCE_EVIDENCE_GAP',
                required='사업·블록별 모집/입주 예정일, 회차, 분양·임대 구분, 물량, 변경·취소 판본',
                formula='기간 내 최신 유효 계획 선택 → 실제 완료분/추가모집 중복 제거 → 사업·유형 합계',
                input_period=start+' ~ '+end,plan_candidates=plans,available_plan_rows=len(plans),
                blocker='계획 자료는 보유하지만 공공/분양/임대 경계·최신 판본·회차·부분 물량 검증 전에는 그대로 합산할 수 없음.' if plans else '해당 기간·사업의 저장 일정 연결 미확인. 모집계획·입주계획·실제 입주를 구분해야 함.',
                next_action='기존 계획·공고·일정 원장에서 해당 사업과 기간을 연결한 뒤 세대수 합계 검증')
        elif kind=='FORECAST':
            r.update(status='FORECAST_GAP',required='확정 실적, 잔여 사업별 일정·착공 준비 단계·장애·지연 이력',
                formula='확인 실적 + 잔여 사업의 시나리오별 예상 물량; 가정과 범위 명시',
                available_plan_rows=sum(s['stage']=='CONSTRUCTION' for c in delivery.get('portfolio_cohorts',[]) for s in c.get('schedules',[])),
                blocker='사업 일정은 있으나 전체 잔여 명부·실행 가능성 판단·구간 전망의 검증이 없음. 정부 전망 숫자 수집으로 대체할 수 없음.',
                next_action='보유 일정의 분기별 집중도부터 산출하고 지연·준비도에 근거한 자체 전망을 검증')
        elif kind=='OPERATIONS':
            required='매입약정 접수 사건·중복/취소·월별 물량 원장' if key in {'M12','M13'} else '제도개선 과제 식별자·완료 근거·적용일 원장' if key in {'M23','M24','M25'} else 'PF 관리 대상 사업장·지정 상태 원장'
            formula='(8월 접수량 / 4~7월 월평균 - 1) × 100' if key=='M13' else '전체 과제 - 완료 과제' if key=='M25' else '동일 정의·기간의 업무 기록 집계'
            r.update(status='INPUT_LEDGER_GAP',required=required,formula=formula,
                blocker='현재 확보·연계된 원장에서 이 업무의 원시 기록을 확인하지 못함. 인허가·주택수·모집공고로 대체할 수 없음.',
                next_action='해당 업무의 원시 기록 제공 경로와 기존 첨부의 정형화 가능성을 확인; 동명 지표 문서는 필수 조건이 아님')
        elif kind=='POLICY_FACT':
            r.update(status='POLICY_FACT_REQUIRED',required='기관 신설·운영 계획 또는 발표 일정에 대한 결정 사실',
                formula='최신 결정·시행 상태를 출처·적용일과 함께 서술',blocker='기관의 새 결정은 주택 사건 데이터만으로 도출할 수 없음. 공급 데이터 오류나 누락 호수로 채점하지 않음.',
                next_action='결정이 공개·제공되면 정책 사실 원장에 입력. 독립 공급실적 산출과 별도로 평가')
        else:
            r.update(status='DEFINITION_GAP' if key in {'M32','M33'} else 'INPUT_LEDGER_GAP',
                required='일반주택 유형별 당기·전년 동기간 월별 원장' if key in {'M32','M33'} else '주택 매매 소비심리 조사 원시 응답 또는 독립 생산기관 지수 시계열',
                formula='(당기 합계 / 전년 같은 기간 합계 - 1) × 100' if key in {'M32','M33'} else '같은 지역·조사 정의의 8월/9월 지수 비교',
                available_raw_rows={k:raw_counts[k] for k in ('permit','general_permit','statistic')},
                blocker='최근 6개월의 정확한 범위·일반주택 분류·전년 분모 연결이 필요.' if key in {'M32','M33'} else '매매가격지수와 소비심리지수는 다른 지표. 보유 가격 자료로 대체할 수 없음.',
                next_action='이미 보유한 통계·일반 인허가 필드를 먼저 대조하고 필요한 분류·기간 또는 조사 원천만 보완')
        if key.startswith('S'):
            refs=[x for x in reference_rows if area_matches(x.get('name',''),original['name'])]
            r['existing_reference_candidates']=[dict(id=x['id'],kind=x['kind'],name=x.get('name'),source_date=x.get('source_date'),evidence_url=x.get('evidence_url')) for x in refs]
            r['available_reference_rows']=len(refs)
            if refs:r['blocker']+=f' 이미 보유한 참고 자료 {len(refs)}행을 확인했다. 과거·추가모집·재고가 포함될 수 있어 이 행 수를 해당 사건 수나 물량으로 간주하지 않음.'
        r['with_latest_inputs']=('최신 결정·통계가 현재 스키마에 정상 반영되면 해당 판본의 인용 가능. 독립 실적 생성과 구분.' if r['status'] in {'REFERENCE_ONLY','INPUT_VERSION_GAP'} else
            '새 정책 결정 사실이 입력되면 서술 가능. 사업 데이터에서 예측할 대상이 아님.' if kind=='POLICY_FACT' else
            '동일 원천의 최신판만 받아서는 부족. 위 대상·분류·연결·원장·산식의 공백도 해결해야 함.')
        if key=='M21':r['formula']='같은 기간의 공공분양 모집 + 공공임대 모집; 사업·회차 중복 제거';r['dependencies']=['M17','M20']
        if key=='M13':r['dependencies']=['M12']
        if key=='M25':r['dependencies']=['M23','M24']
        r['status_label']=LABELS[r['status']];rows.append(r)
    third=next(r for r in rows if r['id']=='M08')
    third_events=[e for e in events if e['event_id'] in third['event_ids']]
    return dict(version='REPORT-REPRODUCIBILITY-1',question='우리 플랫폼의 보유 원천만으로 최신 공급 보고서를 작성할 수 있는가',
        known_at=known_at,snapshot_id=snapshot['id'],benchmark_used='작성할 주장·정의의 외부 시험 문제; 정답 숫자는 자체 산출 입력에 사용하지 않음',
        verdict='전체 보고서 작성은 아직 불가 · 근거와 범위를 명시한 부분 보고서 작성 가능',
        full_report_ready=False,limited_report_ready=any(r['writeable_statement'] for r in rows),
        reportability_score=None,score_note='53행은 상하위 합계·정책 결정·정성 주장까지 포함하여 단순 행 수 비율을 보고서 작성 점수로 환산하지 않음. 기존 63.1점은 기술 준비도이며 보고서 재현율이 아님.',
        latest_input_assumption='새 데이터가 도착해도 대상 분류·연결·중복·계획/실적·전망 산식이 없으면 보고서는 자동 완성되지 않음. 최신성 부족과 구조적 처리 부족을 분리.',
        preannouncement_capability='미검증: 이번 검증은 현재 보유 데이터 기준. 발표 전 인지시각 동결본 재현과 구분.',
        limitations=['저장된 정형 원장·현재 집계 경로·관련 참고 자료를 검증했으며 모든 첨부의 미정형 본문을 전수 재판독한 결과는 아님.',
            '미산출은 원천 부재나 0 실적의 확정이 아니다. 새 원천 수집 전에 보유 자료의 정형화·연결 공백을 확인해야 함.'],
        rows=rows,status_counts=dict(Counter(r['status'] for r in rows)),
        third_town=dict(value=third['own_value'],event_count=len(third['event_ids']),district_membership=sorted([list(k) for k in THIRD_TOWN_DISTRICTS]),
            membership_basis='3기 신도시의 지구 분류 정의와 HOME 지역·지구·블록 식별자를 대조. 프로그램 표시명만으로 범위를 제한하지 않음.',
            definition_url=THIRD_TOWN_DEFINITION_URL,existing_program_districts=sorted([list(k) for k in tagged_third_districts]),
            events=[dict(name=e['name'],event_date=e['event_date'],units=e['quantity'],source_id=e['source_id'],
                source_revision_id=e['source_revision_id'],evidence_url=e.get('evidence_url'),
                source_base_date=(projects_by_id.get(e['project_id'],{}).get('construction_start_evidence') or {}).get('source_base_date')) for e in third_events],
            caveat='부분 확인 실적이며 전체 3기 신도시 전수값은 미확정. 화면 누적 측정과 2026년 신규 착공은 별도 검증.'),
        screenshot_observation=dict(value=7527,source='사용자 첨부 화면',display_date='2026-09-01',
            status='SCOPE_NOT_REPRODUCED',note='당시 필터·사업 집합·판본을 재현하지 못했으므로 이 숫자의 정확/오류를 판정하지 않음. 누적 도달량과 당해 연도 착공은 정의가 다름.'),
        priority_actions=['보고서 지표의 대상·기간·단위·계획/실적 계약을 정의하고 기존 원장 조회에 연결',
            '누적 관리값을 당해 연도 직접 사건값과 분리하고 기존 원문의 사건·물량 전달 누락 점검',
            '확인된 미연결·분류 공백을 처리한 후 실제 미확보 원천만 추가 수집',
            '과거 판본과 최신성, 업무 원장 및 전망 모델의 공백을 별도 검증'])
