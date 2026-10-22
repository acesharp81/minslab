"""Render the external-candidate decisions and independent before/after checks."""
import csv
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/analysis/candidate_external_review_20261021'
OLD=ROOT/'docs/analysis/policy907-full-verification-20261021'
INPUT=ROOT/'docs/analysis/policy907_candidate_handoff_20261021'
AFTER=OUT/'after'
SONG='PRO_b2a3fc2ab9bda6c7ffaa3b0e'
YEON='PRO_0abce10856b8c6218fa0d63e'
SAME={'PRO_4b859c7f4b18222558932b97':'PRO_9a256c5d211050be9f0814ff',
      'PRO_4e534476d1d747285e612f85':'PRO_1c2a1be12daff06cef52f8c6',
      'PRO_a9e2bffb100945377e90ef33':'PRO_85998117430f9302232be12d'}


def read(path):return json.loads(path.read_text())
def dump(path,v):path.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def csvread(path):return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
def csvwrite(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})


def main():
    after=read(AFTER/'model.json');before=read(OUT/'snapshot/model.json')
    projects={p['id']:p for p in read(AFTER/'projects.json')}
    prior={p['id']:p for p in read(OUT/'snapshot/projects.json')}
    raw={p['entity_id']:p['payload'] for p in read(AFTER/'raw_projects.json')}
    result=read(OUT/'applied.json');cs={c['id']:c for c in after['portfolio_cohorts']}
    cases=[]
    for r in csvread(INPUT/'policy_unassigned_99.csv'):
        pid=r['후보ID'];p=projects[pid];old=prior[pid];source=raw[pid]
        code='POLICY_HELD';decision='9·7 귀속 보완자료 미확보 · 후보 유지';delta=0;master=None
        why='사업유형·허가·공사 또는 모집 사실만으로9·7 개별귀속 확정 불가'
        if pid in SAME:
            code='EXISTING_SITE_EVIDENCE_ONLY';decision='기존 관리사업에 공식 원천 연결 · 중복 추가 금지';master=SAME[pid]
            why='LH 지구코드·블록·호수 및 정식 사업명 대응. 기존 관리사업 물량에 이미 포함'
        if pid==SONG:
            code='EXISTING_APPROVED_SITE_RECOVERED';decision='기존 승인현장의 관리집계 복원 · 신규독립정책 귀속 아님';delta=1198;master=pid
            why='기존 승인 공사원천은 숫자블록으로 관리집계 제외. LH 지구102283·블록01의 단일 건축1198호를 한 번 복원'
        if pid==YEON:
            decision='공식82호·인가일 보정 및 비공식 사업실적 연결 · 정책귀속 유보'
            why='167호는 동종사업 중앙값 관리추정. 공식2025-118호는82호(분양65+임대17). LH참여형이라는 사실만으로후속공모 선정 확정 불가'
        qty=old.get('manual_fields',{}).get('planned_units',{})
        cases.append(dict(후보ID=pid,사업명=p['name'],원천ID=p['source_id'],기존전달규모_호=old.get('planned_units'),
            기존규모구분='담당자 추정' if qty.get('inferred') else '수집 원천 또는 원천채택',
            원천직접기재규모_호=source.get('planned_units'),현재관리규모_호=p.get('planned_units'),
            현재규모구분='담당자 추정' if p.get('manual_fields',{}).get('planned_units',{}).get('inferred') else
                '공식 변경인가 확인' if pid==YEON else '수집 원천 또는 원천채택',
            G1_정책귀속='기존 동일현장 정책승인 승계' if pid==SONG else '기존 승인사업 원천보강' if pid in SAME else '개별 귀속 미확인',
            G2_사업범위='공식 지구·블록·호수 확인' if pid in SAME or pid==SONG else '대표지번·공식82호 확인' if pid==YEON else '원천 사업 존재; 별도 정책 산입범위 미확정',
            G3_시점='공식 착공2024-07-10;2026연간착공0호' if pid==SONG else '원천 보강만으로실적 생성 안 함',
            G4_공식항목='R002 정책누적참고량만변경;정부연간실적·32계획표 미산입' if pid==SONG else '공식 비교표의 기존 대상·기간 유지',
            G5_중복='한 번만집계 · 기존 공사원천과 재합산 금지' if pid==SONG else '기존사업 물량 유지;독립가산 금지' if pid in SAME else '귀속확정 전추가금지',
            판정코드=code,최종처리=decision,사유=why,기존관리사업ID=master,이번정책누적추가호수=delta,
            이번2026연간착공추가호수=0,현재정책ID=p['mapping']['policy_id'],현재매핑상태=p['mapping']['status'],
            출처URL=p['evidence_url'],추가근거URL='https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=614277 | https://samhyundnc.co.kr/works/yeonnam-244-16-lh' if pid==YEON else
                'https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14' if pid==SONG else '',
            독립웹검증범위='새 공개자료 직접 재확인' if pid in SAME or pid in [SONG,YEON,'PRO_f3dcde6035029d54a848ef8d'] else
                '제공 외부검토 및 DB 전수 대조;개별 웹전수 검증 아님'))
    assert len(cases)==99
    assert Counter(r['판정코드'] for r in cases)=={'POLICY_HELD':95,'EXISTING_SITE_EVIDENCE_ONLY':3,'EXISTING_APPROVED_SITE_RECOVERED':1}
    assert sum(r['이번정책누적추가호수'] for r in cases)==1198
    csvwrite(OUT/'candidate_99_review_results.csv',cases)
    research=csvread(INPUT/'additional_research_candidates_2.csv')
    for r in research:
        r.update(이번최종처리='정책귀속 유보',이번추가호수=0,
            추가사유='LH9.25후속8개블록 공모표는당수2 A1·A3·B1이며A2포함표가아님;입찰664호는실착공아님' if '당수' in r['조사대상'] else
                'DS13 201호 공식모집은확인. R066서울마곡200호가DS13인지,마곡17임대196호인지미특정')
    csvwrite(OUT/'additional_2_review_results.csv',research)
    comparison_old={r['지표ID']:r for r in read(OLD/'official_185_comparison.json')}
    comparison_new={r['지표ID']:r for r in read(AFTER/'official_185_comparison.json')}
    comparison=[]
    for key,old in comparison_old.items():
        new=comparison_new[key]
        assert all(old.get(f)==new.get(f) for f in ['HOME_동일범위비교값','판정','수량표현부합','HOME_참고값'])
        comparison.append(dict(지표ID=key,공식항목=old['지표'],지역사업=old['지역·사업지'],공식수치=old['공식 기준수치'],
            이전동일범위HOME값=old['HOME_동일범위비교값'],이후동일범위HOME값=new['HOME_동일범위비교값'],
            이전정책부분참고량=old['HOME_정책사업부분값'],이후정책부분참고량=new['HOME_정책사업부분값'],
            이전판정=old['판정'],이후판정=new['판정'],모순추가여부=False,
            비고='정책 누적 직접등록 참고량만1198증가. 정부 올해실적과범위다름 유지' if key=='R002' else '비교값·판정 유지'))
    assert [r['지표ID'] for r in comparison if r['이전정책부분참고량']!=r['이후정책부분참고량']]==['R002']
    csvwrite(OUT/'official_185_before_after.csv',comparison)
    q4=csvread(ROOT/'docs/analysis/external_diagnostic_review_20261021/comparison_32.csv')
    for r in q4:
        ids=r['home_cohort_id'].split('|');oldval=int(r['home_quantity'])
        assert sum(cs[i]['units'] for i in ids)==oldval,(r['official_metric_id'],ids,oldval)
        r['previous_home_quantity']=oldval;r['current_home_quantity']=oldval;r['current_snapshot_at']=read(AFTER/'snapshot.json')['snapshot_at'];r['new_contradiction']=False
    csvwrite(OUT/'official_32_before_after.csv',q4)
    before_cs={c['id']:c for c in before['portfolio_cohorts']}
    assert all(cs[k]==v for k,v in before_cs.items())
    assert set(cs)-set(before_cs)=={SONG}
    assert projects[YEON]['planned_units']==82 and projects[YEON]['mapping']['policy_id']=='UNASSIGNED'
    assert projects[SONG]['mapping']['status']=='CONFIRMED'
    estimated=Counter(prior[r['후보ID']]['source_id'] for r in cases if r['기존규모구분']=='담당자 추정')
    summary=dict(snapshot_before=read(OUT/'snapshot/snapshot.json'),snapshot_after=read(AFTER/'snapshot.json'),
        primary_rows=99,decisions=dict(Counter(r['판정코드'] for r in cases)),separate_research_held=2,
        other_policy_preserved=114,released_preserved=8,new_independent_policy_admissions=0,
        existing_approved_site_recovered=1,existing_sites_source_only=3,prior_candidate_estimate_rows=dict(estimated),
        before=result['before'],after=result['after'],official_185_equivalent_values_preserved=True,
        official_185_statuses_preserved=True,official_32_equivalent_values_preserved=True,
        government_2026_actual_increment=0,raw_source_projects_preserved=True,existing_cohorts_preserved=True,
        unofficial_evidence_label='담당자 검토 - 비공식 자료: 삼현디앤씨 사업실적',
        confidence_limit='정책 후보의개별웹전수나정부비공개명부를 검증한것이 아님. 귀속근거미확보는부적격확정아님')
    dump(OUT/'verification.json',summary)
    template=ROOT/'scripts/templates/candidate_external_review_20261021.md'
    (ROOT/'docs/analysis/THE_JUTAEK_EXTERNAL_CANDIDATE_REVIEW_20261021.md').write_text(template.read_text())
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
