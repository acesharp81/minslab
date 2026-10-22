"""Export the 223-row handoff review and verify its applied, non-additive scope."""
import csv
import hashlib
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/analysis/colleague_candidate_review_20261022'
INPUT=ROOT/'docs/analysis/policy907_candidate_handoff_20261021'


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def main():
    verified=json.loads((OUT/'verified_sources.json').read_text())
    applied=json.loads((OUT/'applied.json').read_text())
    assert applied['verified'] and len(applied['receipts'])==193
    evidence={r['project_id']:r for r in verified['projects']}
    mappings=json.loads((OUT/'current_mappings.json').read_text())
    previous={r['후보ID']:r for r in read_csv(ROOT/'docs/analysis/candidate_external_review_20261021/candidate_99_review_results.csv')}
    result=[]
    for filename in ('policy_unassigned_99.csv','other_policy_114.csv','released_8_do_not_readmit.csv','additional_research_candidates_2.csv'):
        for r in read_csv(INPUT/filename):
            pid=r.get('후보ID') or r.get('현재사업ID') or ''
            name=r.get('사업명') or r.get('조사대상')
            e=evidence.get(pid);old=previous.get(pid)
            source_url=r.get('출처URL','');page='';event='';units=r.get('원천규모_호','');primary=r.get('현재정책ID','')
            if e:
                decision='OFFICIAL_FOLLOWUP_EVIDENCE_LINKED'
                reason='기존 정책 연결 보존; 공식 후속관계·개별 사업 근거 연결. 9·7 원 목표 산입량은 미확정.'
                source_url=e['official_url'];page=e['source_page'];units=e['planned_units']
                event=json.dumps(e['event'],ensure_ascii=False) if e['event'] else ''
            elif old:
                decision=old['판정코드'];reason=old['사유'];primary=old['현재정책ID'];units=old['현재관리규모_호']
                if decision=='EXISTING_APPROVED_SITE_RECOVERED':reason='이전 검토에서 송림4 1,198호 누적 복원 완료. 이번 재추가 없음. '+reason
                elif decision=='EXISTING_SITE_EVIDENCE_ONLY':reason='이전 검토에서 기존 사업 원천 연결 완료. 이번 중복 연결·호수 가산 없음. '+reason
            elif filename=='released_8_do_not_readmit.csv':
                decision='RELEASE_PRESERVED';reason='중복·해제 사유를 해소하는 새로운 근거 없음.'
            else:
                decision='ATTRIBUTION_HELD';reason='기존 원천·명부 또는 사업 존재 확인과 9·7 귀속·물량 산입은 별개. 이번에 그 차이를 해소하는 개별 증빙 미확보.'
            result.append(dict(candidate_id=pid,project_name=name,input_file=filename,current_primary_policy=mappings.get(pid,{}).get('policy_id',primary),
                current_mapping_status=mappings.get(pid,{}).get('status',''),
                decision=decision,reason=reason,management_or_source_units=units,quantity_note='규모·계획·추정 구분은 원천 및 이전 검토 참조; 모든 행 합산 금지',
                new_policy907_units_this_review=0,new_construction_units_this_review=0,official_url=source_url,source_page=page,
                official_administrative_event=event,reviewed_at='2026-10-22',
                evidence_review_scope='공식 원문 재검증 및 추가 연결' if e else '첨부와 이전 검토 대조; 이번 개별 사업 신규 인터넷 검증은 하지 않음'))
    assert len(result)==223
    with (OUT/'candidate_223_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
    before=json.loads((ROOT/'docs/analysis/cumulative_forecast_review_20261022/after.json').read_text())
    after=json.loads((OUT/'after.json').read_text())
    def normalize(v):
        if isinstance(v,dict):return {k:normalize(x) for k,x in v.items()}
        if isinstance(v,list):return sorted((normalize(x) for x in v),key=lambda x:json.dumps(x,sort_keys=True))
        return v
    for key in ('portfolio_cohorts','portfolio_comparisons','official_alignment','regional_start_months'):
        assert normalize(before[key])==normalize(after[key]),key
    totals={k:dict(current=(m['tracking']['actual_points'] or [{}])[-1].get('units'),
             year_end=next((p['units'] for p in reversed(m['tracking']['forecast_points']) if p['date']<='2026-12-31'),None))
            for k,m in after['portfolio_comparisons']['policy']['metrics'].items()}
    checks=dict(input_candidates=223,dispositions=dict(Counter(r['decision'] for r in result)),
                applied_revisions=len(applied['receipts']),policy907_projects=len(after['portfolio_cohorts']),
                policy907_quantities_unchanged=True,official_comparison_unchanged=True,totals=totals,
                original_scope_note='전체 223개에 새 인터넷 전수조사를 수행했다는 뜻이 아님. 새 검증 대상은 공식 원문 63개 및 정책 간 관계.')
    (OUT/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    files=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted((OUT/'sources').iterdir())]
    (OUT/'source_manifest.json').write_text(json.dumps(files,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(checks,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
