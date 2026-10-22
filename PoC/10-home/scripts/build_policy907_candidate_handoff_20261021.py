"""Read-only external review ledger; potential identity is not policy evidence."""
import csv
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
from backend.evidence_bridge import match_key

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/analysis/policy907-full-verification-20261021'
OUT=ROOT/'docs/analysis/policy907_candidate_handoff_20261021'
POLICY='POL_2025_0907'


def read(name):return json.loads((BASE/(name+'.json')).read_text())
def writecsv(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
def compact(v):return re.sub(r'[^가-힣A-Z0-9]','',str(v or '').upper()).replace('블록','').replace('BL','')
def dates(p,stage):
    ds={f['date'] for f in (p.get('facts') or []) if f.get('stage')==stage and f.get('kind')=='ACTUAL' and f.get('date') and f.get('milestone')!='COMPLETION'}
    if stage=='CONSTRUCTION' and p.get('start_actual_date'):ds.add(p['start_actual_date'])
    return sorted(ds)
def md(v):return str(v or '—').replace('|',' / ').replace('\n',' ')


def main():
    OUT.mkdir(exist_ok=True)
    snapshot=read('snapshot');projects=read('projects');model=read('model');cohorts=model['portfolio_cohorts']
    raw={r['entity_id']:r['payload'] for r in read('raw_projects')}
    current={p['id']:p for p in projects if p['mapping']['policy_id']==POLICY and p['mapping']['status']=='CONFIRMED'}
    membership={pid:c for c in cohorts for pid in c['source_ids']}
    keys=defaultdict(list);names=defaultdict(list)
    for p in current.values():
        key=match_key(p)
        if key:keys[key].append(p)
        names[(p['region'],compact(p['name']))].append(p)
    primary=[];other=[];released=[]
    for p in projects:
        mapping=p['mapping'];pid=p['id'];r=raw[pid]
        if mapping['policy_id']==POLICY and mapping['status']!='RELEASED':continue
        key=match_key(p);same=keys.get(key,[]) if key else []
        named=names.get((p['region'],compact(p['name'])),[])
        related=list({q['id']:q for q in same+named}.values())
        compatible=[q for q in related if p.get('planned_units')==q.get('planned_units') and q['id'] in membership]
        confirmed_cohorts={membership[q['id']]['id'] for q in compatible}
        exact_key=bool(same and compatible and len(confirmed_cohorts)==1)
        source=p['source_id'];start=dates(r,'CONSTRUCTION')
        old=bool(start and max(start)<'2026-01-01')
        if exact_key:
            group='A_기존현장_원천보강';possibility='동일 현장 가능성 높음 · 신규 정책물량 추가 대상 아님'
            why='기존 9·7 확정 원천과 시도·지구·블록 및 호수가 같음. 정책 추가보다 동일 사업 원천 보강 검토'
            missing='사업 고유번호·블록·주소 및 공급유형 일치 확인; 기존 관리사업에 원천으로 연결'
            risk='기존 호수에 다시 더하면 중복. 해당 관리사업의 최대 실적·단일 호수만 유지'
            delta='0호(동일 현장·동일 공급범위 확정 조건)'
        elif source=='lh_progress':
            group='B_LH_블록확인';possibility='검증 우선 · 사업 실재 확인, 9·7 귀속 미확인'
            why='LH 공식 공정자료에 개별 블록·호수가 존재. 공공 프로그램 일반명만으로 9·7 연결을 확정하지 않음'
            missing='9·7 후속 사업명부·사업시행/직접시행 전환 문서와 정확한 블록·공급유형·기존 계약 포함관계'
            risk='공정자료 전체규모와 분양/임대의 선택범위·복수현장 계약 중복을 대조해야 함'
            delta='미산출 · 독립 주택범위 확정 전 가산 금지'
        elif source=='seoul_cleanup':
            group='C_서울정비_정책근거대기';possibility='조건부 · 정비사업 존재와 정책 귀속은 별개'
            why='서울 공식 정비사업 명부·추진경과 확보. 과거에 사업유형만으로 연결했던 정책 귀속은 철회·보류'
            missing='9·7 후속 인센티브·특례·공공참여 또는 정책 산입 대상이라는 사업별 명시 자료; 착공은 실제 사건 원장'
            risk='전체 계획세대수와 올해 착공량은 다름. 공개 사례 중계본동·흑석11·신림2에 다른 구역을 합산하지 않음'
            delta='미산출 · 정책 귀속·시점·중복 검증 후만 산정'
        elif source=='building_general_permit':
            group='D_일반주택_근거약함';possibility='낮음 · 허가/실착공 확인만으로 9·7 개별사업이라 할 수 없음'
            why='건축HUB 공식 인허가 관리번호와 실제 사건 자료는 있으나 9·7 대상 명시가 없음'
            missing='주소·건축인허가 관리번호와 연결되는 신축매입 약정·공공지원임대·정책지원 선정 원문 등'
            risk='기타 일반·민간 47,000호라는 총량에 들어갈 가능성과 9·7 개별사업 매핑 확정은 구분. 계획호수를 일괄 가산하지 않음'
            delta='미산출 · 일반주택 총량에 역산하여 채우기 금지'
        else:
            group='E_다른정책_관계확인';possibility='9·7 근거 약함 · 다른 정책 원문 또는 기관 사업목록만 확인'
            why='현재 다른 정책에 임시 연결된 기록. 1·29 또는 8·13 명시가 9·7 귀속의 증거가 되지는 않음'
            missing='기존 정책과 9·7의 승계·중복 산입 관계 및 해당 사업 포함을 명시한 자료'
            risk='정책 간 중복·기간·대상 변경을 확인하기 전 9·7로 옮기거나 더하지 않음'
            delta='미산출 · 정책 간 동일사업 대응표 필요'
        if p['id'] in ('PRO_42f49eac956e19c57750cff4','PRO_6cd92fc3a8e9e13eb4faddfd'):
            why+='; 새로 추출한 LH 모집공고 원일자2021-09-16·입주예정2023-12. 이미 정책 확정된 복수현장 계약과 범위 검증 필요'
            risk+='; 2021 공고를 2026년 신규 공급 또는 착공실적으로 전환하면 안 됨'
        label='2026년 연간 착공 비교 불가(이전 연도 실제 착공)' if old else '같은 사건·물량·기준일의 증빙 확보 전 미검증'
        row=dict(후보ID=pid,구분=group,검토가능성=possibility,사업명=p['name'],시도=p['region'],
            주소=p.get('address'),지구=p.get('district'),블록=p.get('block'),원천규모_호=r.get('planned_units'),관리규모_호=p.get('planned_units'),
            규모추정여부=bool(p.get('manual_fields',{}).get('planned_units',{}).get('inferred')),
            규모해석='원천 직접 기재값과 관리 채택값 분리. 관리값은 추정 여부 참조. 당해 착공실적 아님',공급형태=p.get('tenure') or '미확인',
            현재정책ID=mapping['policy_id'],현재연결상태=mapping['status'],원천ID=source,
            후보로본근거=why,미연결사유=mapping.get('basis'),확보된자료='공식 사업 원천 있음 · 9·7 개별 귀속 증빙 미확정',
            출처URL=p.get('evidence_url'),원천판본=p.get('revision_no'),원천기준일=p.get('base_date'),
            최초수집일_아님_현재판본기록시각=p.get('recorded_at'),사업화원천사건일='|'.join(dates(r,'BUSINESS')),
            인허가원천사건일='|'.join(dates(r,'APPROVAL')),착공원천사건일='|'.join(start),
            기존9_7원천ID='|'.join(q['id'] for q in related),기존9_7관리사업ID='|'.join(sorted(confirmed_cohorts)),
            공개항목대조시주의=risk,당해착공비교판정=label,
            정책연결시추가호수=delta,현재추가반영호수=0,
            외부에서필요한증빙=missing,외부검증결과='',외부근거URL='',외부문서발행일='',
            외부문서페이지_문구='',외부확인공급유형='',외부확인대상호수='',외부확인실제착공일='',
            외부확인정부발표항목ID='',중복검증결과='',최종처리='유보 · 자동 가산 금지')
        if mapping['status']=='RELEASED':released.append(row)
        elif mapping['policy_id']=='UNASSIGNED':primary.append(row)
        else:other.append(row)
    primary.sort(key=lambda r:(r['구분'],r['시도'],r['사업명']))
    other.sort(key=lambda r:(r['구분'],r['현재정책ID'],r['사업명']))
    assert len(primary)==99 and len(other)==114 and len(released)==8
    writecsv('policy_unassigned_99.csv',primary);writecsv('other_policy_114.csv',other);writecsv('released_8_do_not_readmit.csv',released)
    investigations=[dict(조사대상='수원당수2 A2',현재사업ID='미등록',원천규모_호=664,검토가능성='중간 · 입찰 사업 규모 확보, 9·7 귀속·실착공 미확인',
        확보자료='비드프로 입찰 재게시 · 입찰번호R26BK01586143-000 / 관리R26DC00223010 / 통합공공임대664호',
        출처URL='https://www.bidpro.co.kr/n0_ipchal/konggo/sisul/konggo_view.asp?num=3798992',
        필요한증빙='조달청/LH 입찰 원문과 정책 후속 프로그램 포함 문서, 블록별 실제 착공일·주택호수',
        대조제약='정부 당수2 3,400호에 자동 산입 금지. 기존5블록3,553호 및 3블록2,309호와 블록별 중복·산입기간 대조',
        현재추가반영호수=0,확인후추가량='미산출'),
        dict(조사대상='마곡 도전숙(DS13)',현재사업ID='원천 AGE_4caa36314cede89a40bcee76 / 정책 사업 미등록',원천규모_호=201,
        검토가능성='중간 · 공식 모집 근거 있음, 9·7 연결 및 정부 마곡200호의 블록 특정 미확인',
        확보자료='강서구 최초 모집2026-05-04 · 서울청년몽땅정보통 · 원천 입주계획201호',
        출처URL='https://www.gangseo.seoul.kr/gs040301/view?curPage=1&mgtNo=66875&srchKey=&srchPage=&srchText= | https://youth.seoul.go.kr/infoData/sprtInfo/view.do?key=2309130006&sprtInfoId=69810',
        필요한증빙='9·7 후속 임대 프로그램 산입 명부 또는 기관 설명, 최초 금회모집호수·재공고 중복, 마곡17 임대196호와 별개임을 확인',
        대조제약='201→약200은 수량 대응만 가능. 정부 마곡200호를 DS13이라고 단정하지 않음. 모집을 착공/입주완료로 전환 금지',
        현재추가반영호수=0,확인후추가량='미산출')]
    writecsv('additional_research_candidates_2.csv',investigations)
    manifest=dict(snapshot=snapshot,policy_unassigned=len(primary),by_source=dict(Counter(r['원천ID'] for r in primary)),
        other_policy_records=len(other),released_excluded=len(released),research_candidates=2,
        current_new_policy_mappings=0,current_added_units=0,
        guarantee='확인 전 양립 여부를 보장할 수 없음. G1~G5를 모두 통과한 범위만 반영',
        known_identity_only=sum(r['구분'].startswith('A_') for r in primary))
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    lines=['# the주택 · 9·7 정책 미연결 후보 외부 검증 인계서','',
        f"기준: {snapshot['snapshot_at']} (DB 읽기 전용 스냅샷). 후보 정리 과정의 정책 연결·수량 변경은 0건입니다.",'',
        '후보는 **9·7 귀속 근거가 아직 부족한 조사 대상**입니다. 사업의 존재·호수·착공에 관한 공식 자료가 이미 있는 경우도 많습니다. 공식 원천이 있다는 사실과 그 사업이 9·7 정책에 포함된다는 사실을 구분했습니다.',
        '가능성은 검증 우선순위에 관한 정성 판단입니다. 근거 없는 확률을 부여하지 않았습니다. **외부 증빙을 받기 전에는 공식 발표와 어긋나지 않는다고 보장할 수 없습니다. 아래 G1~G5를 모두 통과한 부분만 연결·집계하도록 조건을 정했습니다.**','',
        '## 1. 검증 대상 범위','',
        '| 구분 | 원천 기록 수 | 해석 |','|---|---:|---|',
        '| 정책 미귀속 | 99 | LH 공정7 · 서울정비41 · 일반인허가51 |',
        '| 다른 정책 임시 분류 | 114 | 1·29원문47 · 도시정책원문51 · SH명부16; 별도 부록 |',
        '| 추가 조사 후보 | 2 | 당수2 A2, 마곡 도전숙; 위99개와 별도 |',
        '| 해제 원천 | 8 | 중복·해제 사유 확인 전 재편입 금지; 별도 파일 |','',
        '**99는 독립 현장99개나 누락 사업99개가 아닙니다.** 같은 현장의 다른 원천, 전체 단지와 분양·임대의 부분 범위가 포함될 수 있어 호수를 합산하지 않습니다.',
        '현재 9·7 확정 원천231개와 관리단위176개는 이 목록의 신규 후보와 구분합니다. 이미 정책 연결됐지만 복합계약 등의 이유로 관리 총계에서 제외된 원천11개도 신규 미연결 사업으로 다시 더하지 않습니다.','',
        '## 2. 외부에서 먼저 확인할 LH 7개 원천','',
        '| 사업 | 원천 규모 | 가능성·근거 | 추가로 받아야 할 증빙 | 집계 제약 |','|---|---:|---|---|---|']
    for r in primary:
        if r['원천ID']=='lh_progress':lines.append('| '+' | '.join(md(x) for x in [r['사업명'],r['원천규모_호'],r['후보로본근거'],r['외부에서필요한증빙'],r['공개항목대조시주의']])+ ' |')
    lines+=['','검단 AA13-1·AA13-2는 새 파서로 각각702·964호를 분리했지만 원 모집공고일은2021-09-16, 입주예정은2023-12입니다. **9·7 정책 연결의 별도 근거가 확인되더라도 2026년 신규 공급으로 계산하면 안 됩니다.** 과거 착공사업이 9·7 정책 누적에 포함되는지와 2026년 당해 착공인지도 별개로 검증합니다.','',
        '## 3. 별도 추가 조사 2건','']
    for r in investigations:
        lines += [f"### {r['조사대상']} · {r['원천규모_호']:,}호",'',r['검토가능성']+'. '+r['확보자료'], '',
            '- 필요한 자료: '+r['필요한증빙'], '- 발표 대조 제약: '+r['대조제약'], '- 출처: '+r['출처URL'],'']
    lines+=['## 4. 공식 발표와 세부 조회를 어긋나게 하지 않는 반영 조건','',
        '| 관문 | 통과 조건 | 미충족 시 처리 |','|---|---|---|',
        '| G1 정책 귀속 | 사업명·사업ID·블록을 명시한9·7 후속 문서 또는 출처와 발언 주체가 분명한 담당기관 설명 | 정책 후보 유지. 공공·LH·정비라는 이유만으로 연결하지 않음 |',
        '| G2 사업·물량 범위 | 주소·지구·블록·주택유형·전체/금회·호수 구성 일치 | 원천만 저장. 다른 블록·오피스텔·예비자·전체 계약 혼합 금지 |',
        '| G3 사건과 시점 | 실제 착공·준공·모집·입주와 계획을 분리, 실제 사건일·관측상한·공표일 구분 | 정책 연결 가능 여부와 단계 실적 산입을 분리. 과거 착공을2026실적으로 전환 금지 |',
        '| G4 발표 모집단 | 해당 공개 항목의 기관·지역·기간·공급형태·블록에 포함되는지 확인 | 정책에 연결돼도 발표의 특정 항목에는 미산입. 미언급 사업 별도 |',
        '| G5 중복·정합성 | 기존 원천·관리사업과 통합하고 계층별 화면·사업별 조회·CSV가 같은 채택량을 사용 | 독립 호수 가산 보류. 원천을 더 연결해도 동일 물량은1회 |','',
        '수량이 약2,300호와2,342호처럼 반올림으로 양립해도 G2~G4를 대신하지 못합니다. 정확한 계획표의498호와548호는 단순 반올림으로 같다고 하지 않습니다. 정부4분기32항목에 없는 새 사업을 기존32항목의 분모에 임의로 넣지 않습니다.',
        '기존에 문서상 충돌이 있는 사업은 새 자료의 발행일·변경효력일·대상범위를 함께 보존합니다. 값의 차이를 없애려고 기존 원문을 덮어쓰지 않습니다.','',
        '## 5. 서울 정비사업41개 · 후보별 목록','',
        '다음은 공식 사업명부의 실제 사업입니다. 명부와 추진경과는 존재하지만9·7 개별 귀속 증빙이 없으므로 조건부 후보입니다. **기재된 규모는 전체 사업 계획량이며 정부의 당해 착공실적이 아닙니다.**','',
        '| 후보ID | 사업명 | 규모(호) | 원천 착공일 | 외부 확인 핵심 |','|---|---|---:|---|---|']
    for r in primary:
        if r['원천ID']=='seoul_cleanup':lines.append('| '+' | '.join(md(r[k]) for k in ['후보ID','사업명','원천규모_호','착공원천사건일','외부에서필요한증빙'])+' |')
    lines+=['','## 6. 일반 건축인허가51개 · 후보별 목록','',
        '해당 주소의 실제 인허가·착공이 확인돼도 정책 귀속은 확인되지 않습니다. 신축매입 약정이나 정책지원 선정 등 직접 증빙을 확보할 수 있는 사례부터 조사하는 편이 효율적입니다.','',
        '| 후보ID | 사업명 | 규모(호) | 원천 착공일 | 주소 |','|---|---|---:|---|---|']
    for r in primary:
        if r['원천ID']=='building_general_permit':lines.append('| '+' | '.join(md(r[k]) for k in ['후보ID','사업명','원천규모_호','착공원천사건일','주소'])+' |')
    lines+=['','## 7. 전달 파일과 외부 검증 결과 기입 방법','',
        '- [정책 미귀속99개 상세CSV](policy907_candidate_handoff_20261021/policy_unassigned_99.csv): 원천URL·판본·사건일·기존사업대응·제약·검증결과 입력란.',
        '- [다른 정책114개 상세CSV](policy907_candidate_handoff_20261021/other_policy_114.csv): 9·7과의 관계를 별도로 확인할 부록.',
        '- [추가 조사2개](policy907_candidate_handoff_20261021/additional_research_candidates_2.csv).',
        '- [해제8개 — 재편입 금지 대상](policy907_candidate_handoff_20261021/released_8_do_not_readmit.csv).','',
        '각 후보ID에 원문URL, 발행일, 페이지·문구, 정확한 사업명·주소·블록, 공급유형, 전체/금회 호수, 실제 착공일 또는 계획임을 채워주시면 됩니다. AI 답변이나 검색요약만 있는 경우는 원문을 추가로 확보해야 합니다.',
        '공식 자료는 G1~G5 확인 후 자동 매핑하고, 신뢰할 수 있는 비공식 자료는 **담당자 확인 - 비공식 자료: 출처URL**로 연결합니다. 사업 자체의 정책 연결과 실적 증빙 연결을 각각 기록하며, 증빙이 계획이면 실적으로 전환하지 않습니다.','']
    report=ROOT/'docs/analysis/THE_JUTAEK_907_UNLINKED_CANDIDATES_20261021.md';report.write_text('\n'.join(lines))
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
