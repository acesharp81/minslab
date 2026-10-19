"""Recollect direct LH construction rows and preserve a separate gap audit."""
import json
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for,Mapping,IntegrityRound,Audit,upsert_revision
from backend.service import HomeService,today
from backend.sources import SOURCES
from backend.independent_metrics import freeze
from backend.construction_audit import permit_candidates
from backend.collection_repairs import save as repair

ACTOR='김민';REASON='공식 발표 후 도출된 보완 사항 적용'


def main():
    s=HomeService(engine_for(),'/app/data');out=s.data_dir/'remediation/construction-gap-20261017'
    out.mkdir(parents=True,exist_ok=True)
    def save(name,value):
        path=out/name
        if path.exists():raise ValueError('기존 점검 산출물 덮어쓰기 금지: '+name)
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')
    def mappings():
        with s.sessions() as db:
            return {r.project_id:[r.id,r.policy_id,r.program_id,r.status,r.revision_no] for r in db.scalars(select(Mapping))}
    before_mappings=mappings();save('mappings-before.json',before_mappings)
    with s.sessions() as db:
        before_rounds={r.id:r.digest for r in db.scalars(select(IntegrityRound))}
    save('rounds-before.json',before_rounds)
    before=freeze(s,ACTOR,'착공 물량 전달 오류 수정 전 확인');save('snapshot-before.json',before)
    collected=[]
    for source_id in ('lh_construction','lh_incheon_construction'):
        result=s.collect_one(next(x for x in SOURCES if x['id']==source_id))
        collected.append(dict(source_id=source_id,result=result))
        print(json.dumps(collected[-1],ensure_ascii=False),flush=True)
        if result['status']!='SUCCESS':raise ValueError('LH 원문 재수집 실패')
    save('collection.json',collected)
    after=freeze(s,ACTOR,REASON);save('snapshot-after.json',after)
    current=after['result'];instant=datetime.fromisoformat(after['context']['known_at'])
    permits=permit_candidates(s,instant,current['period_start'],current['period_end']);save('permit-audit.json',permits)
    assert before_mappings==mappings(),'정책 매칭 변경 감지'
    with s.sessions() as db:
        assert before_rounds=={r.id:r.digest for r in db.scalars(select(IntegrityRound))},'동결 성적표 변경 감지'
    def metric(snap):return next(m for m in snap['result']['metrics'] if m['metric_code']=='CONSTRUCTION_STARTED')
    events=[e for e in current['selected_events'] if e['event_type']=='CONSTRUCTION_STARTED']
    sources=[]
    for sid in ('lh_construction','lh_incheon_construction','building_hub','building_hub_incheon'):
        stats=s.latest_collection_stats(sid)
        sources.append(dict(source_id=sid,**{k:stats.get(k) for k in ('source_base_date','scope_total_dongs','scope_completed_dongs','scope_remaining_dongs')}))
    reference=json.loads((Path(__file__).resolve().parents[1]/'backend/data/official_benchmark_20261016.json').read_text())
    benchmark=next(r for r in reference['rows'] if r['id']=='M04')
    audit=dict(actor=ACTOR,reason=REASON,known_at=after['context']['known_at'],snapshot_id=after['id'],snapshot_digest=after['digest'],
        previous_snapshot_id=before['id'],previous_value=metric(before)['value'],current_value=metric(after)['value'],
        selected_events=events,period_start=current['period_start'],period_end=current['period_end'],
        source_coverage=sources,permit_candidates=permits,benchmark=benchmark,
        numeric_difference=benchmark['official_value']-metric(after)['value'] if metric(after)['value'] is not None else None,
        agreement_percent=None,publishable=False,
        cause='LH 건설공사 표의 같은 행에 착공일과 주택 공사규모(호)가 있으나, 물량을 착공 사건에 전달하지 않아 직접 원천도 물량 미확인으로 제외됨.',
        action='동일 행의 실제 착공일·물량·단위·공종을 별도 근거로 보존하고 단일 주택 범위만 집계. 전체·부분 범위 중복 제거. 일반 계획 총량은 대입하지 않음.',
        remaining='LH 원문 기준일은 7월 1일. 이후 착공, 민간·정비·신축매입 대상 전체 명부와 실제 착공 원천이 부족. 인허가 착공일 행의 0호는 공급 0이 아닌 물량 미확인. 지역별 수집 완료와 행위 유형·중복 검증 필요.',
        comparison_note='발표는 10월 둘째 주까지의 수도권 실적, 자체 집계는 확인된 등록 사업 부분 범위. 표시상 차이는 확정 누락량·정확도·동일 기간 일치율이 아님.',
        policy_mappings_unchanged=len(before_mappings),frozen_rounds_preserved=before_rounds)
    save('audit.json',audit)
    with s.sessions.begin() as db:
        row,_=upsert_revision(db,'construction_audit','integrity_audit','20261017',audit,'construction_gap')
        db.add(Audit(entity_id=row.entity_id,action='CONSTRUCTION_GAP_REVIEW',before={},after=dict(actor=ACTOR,reason=REASON,snapshot_id=after['id'],previous_value=audit['previous_value'],current_value=audit['current_value'])))
    result=repair(s,'lh-construction-quantity-20261017',dict(title='LH 원문 착공 물량의 사건 전달 누락 수정',actor=ACTOR,reason=REASON,
        repair_type='SCOPE_QUANTITY',status='APPLIED_REVIEW_PENDING',base_date=today().isoformat(),stages=['CONSTRUCTION'],
        source_ids=['lh_construction','lh_incheon_construction'],project_ids=sorted({e['project_id'] for e in events}),
        cause=audit['cause'],action=audit['action'],remaining=audit['remaining'],
        impact=f"확인된 등록 사업 착공 {audit['previous_value']} → {audit['current_value']}호. 수도권 전체 일치율 미산정.",
        related_keys=['construction_start_evidence','start_actual_date','quantity'],report_url='/poc/home/#data-integrity'))
    save('repair-history.json',result)
    print(json.dumps({k:audit[k] for k in ('previous_value','current_value','numeric_difference','snapshot_id','policy_mappings_unchanged')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
