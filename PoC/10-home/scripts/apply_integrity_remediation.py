"""Apply the authorized R01 repairs and persist evidence without changing approvals."""
import json
from pathlib import Path
import sys
from sqlalchemy import select

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for, Mapping, MetricSnapshot, IntegrityRound, CollectionJob, Revision, Audit, now
from backend.service import HomeService, today
from backend.independent_metrics import freeze, get_snapshot
from backend.reference_registry import reconcile as references
from backend.evidence_bridge import reconcile
from backend.stage_evidence import refresh
from backend.project_collection import refresh_links, collection_matrix
from backend.requirements_status import build_status
from backend.collection_repairs import save, quality_guide

ACTOR='김민'
REASON='공식 발표 후 도출된 보완 사항 적용'


def main():
    service=HomeService(engine_for(),'/app/data')
    folder=service.data_dir/'remediation/r01';folder.mkdir(parents=True,exist_ok=True)
    for table in (MetricSnapshot.__table__,IntegrityRound.__table__,CollectionJob.__table__):table.create(service.engine,checkfirst=True)
    with service.sessions() as db:
        approval_before={r.project_id:dict(status=r.status,revision_no=r.revision_no,policy_id=r.policy_id,program_id=r.program_id)
                         for r in db.scalars(select(Mapping).where(Mapping.status.in_(('CONFIRMED','RELEASED'))))}
    with service.sessions() as db:
        original=db.scalar(select(MetricSnapshot.id).where(MetricSnapshot.actor==ACTOR,MetricSnapshot.reason==REASON+' · 정비 전 자료 기준본').order_by(MetricSnapshot.known_at).limit(1))
    before=get_snapshot(service,original) if original else freeze(service,ACTOR,REASON+' · 정비 전 자료 기준본')
    result=dict(actor=ACTOR,reason=REASON,started_at=now().isoformat(),before_snapshot_id=before['id'])
    result['reference_registry']=references(service,ACTOR,REASON,promote=True)
    print(json.dumps(dict(step='reference_registry',result=result['reference_registry']),ensure_ascii=False),flush=True)
    result['stage_evidence']=refresh(service,refresh_candidates=True,actor=ACTOR,reason=REASON)
    result['collection_links']=refresh_links(service,actor=ACTOR,reason=REASON)
    links=reconcile(service,apply=True,actor=ACTOR,reason=REASON)
    result['evidence_bridges']={k:v for k,v in links.items() if k not in ('proposals','held')}
    after=freeze(service,ACTOR,REASON+' · 정비 후 자료 기준본')
    result.update(after_snapshot_id=after['id'],after_counts=after['result']['counts'])
    with service.sessions() as db:
        approval_after={r.project_id:dict(status=r.status,revision_no=r.revision_no,policy_id=r.policy_id,program_id=r.program_id)
                        for r in db.scalars(select(Mapping).where(Mapping.status.in_(('CONFIRMED','RELEASED'))))}
    if any(approval_after.get(key)!=value for key,value in approval_before.items()):raise RuntimeError('기존 확정·해제 매핑이 변경되어 검토 필요')
    result['protected_approvals']=dict(preserved=len(approval_before),changed=0)
    repair=save(service,'independent-integrity-r01',dict(title='독립 산출·실시간 추적 기반 1차 보완',
        actor=ACTOR,reason=REASON,round_id='HOME-INTEGRITY-R01',repair_type='OTHER',
        cause='공식 발표와 중간 대조 후 모집단 후보·자동 범위 연결·원천 통계 분리·인지시각 재현·연속 수집 처리 보완 필요 확인',
        action='정비·허가 원천 후보 등록, 해당 구획의 직접 사건 연결, 원천 통계와 독립 사건 집계 분리, 기준시각별 판본·사건 동결, 영속 수집 작업 및 재시도, 법정동 재방문, 회차별 성적표 관리 적용',
        remaining='수도권 전수 사업 분모, 계약·실입주 원천 사건, 장기간 지연 P95, 독립 정답 표본 확대와 담당자 재검토는 미완료',
        stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],status='APPLIED_REVIEW_PENDING',base_date=today().isoformat(),
        source_ids=['sh_inventory','lh_notice_detail','molit_renewal_inventory','building_hub'],
        project_ids=[],related_keys=['project','events','known_at','source_revision_id','collection_job'],
        report_url='/poc/home/#data-integrity',impact='실적을 추정으로 채우지 않고 근거가 확인된 등록 사업만 독립 집계',
        quality_checks=[dict(id='R01-independent-events',title='독립 사건 집계와 확정 판단 보존',kind='CONSISTENCY',layer='LINKAGE',result='PARTIAL',
            rule='원천 통계·공식 발표 총량·추정량을 직접 사건 집계에 넣지 않으며 기존 확정·해제를 변경하지 않음',
            evidence=f"정비 전 {before['id']}, 정비 후 {after['id']}, 기존 확정·해제 {len(approval_before)}건 보존",
            repair='정비·허가 후보와 구획별 근거 연결, 판본 해시 고정, 작업 단계별 재시도 적용',
            completion_criteria='전체 사업 분모와 실적 원천을 확보하고 장기간 운영 지연·정답 표본을 별도 검증',
            checked_at=today().isoformat(),checked_scope='현재 등록 사업 및 직접 사건 산출 경로')]))
    result['repair']=repair;result['finished_at']=now().isoformat()
    matrix=collection_matrix(service,policy_id='POL_2025_0907')
    (folder/'requirements-after.json').write_text(json.dumps(build_status(service,matrix),ensure_ascii=False,default=str))
    (folder/'quality-after.json').write_text(json.dumps(quality_guide(collection_matrix(service)),ensure_ascii=False,default=str))
    (folder/'snapshot-after.json').write_text(json.dumps(after,ensure_ascii=False,default=str))
    (folder/'remediation-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
