"""Persist the iH website supplement and R02 assessment inputs."""
import json
from pathlib import Path
import sys
from sqlalchemy import select
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for, Batch, Mapping, now
from backend.service import HomeService,today
from backend.independent_metrics import freeze
from backend.stage_evidence import refresh
from backend.project_collection import refresh_links,collection_matrix
from backend.requirements_status import build_status
from backend.collection_repairs import save,quality_guide

ACTOR='김민';REASON='공식 발표 후 도출된 보완 사항 적용'


def main():
    s=HomeService(engine_for(),'/app/data');folder=s.data_dir/'remediation/r02';folder.mkdir(exist_ok=True)
    stage=refresh(s,refresh_candidates=True,actor=ACTOR,reason=REASON)
    links=refresh_links(s,actor=ACTOR,reason=REASON)
    from backend.evidence_bridge import reconcile
    bridge=reconcile(s,apply=True,actor=ACTOR,reason=REASON)
    snapshot=freeze(s,ACTOR,REASON+' · iH 공식 홈페이지 수집 보완 및 정책 범위 검수')
    projects=[p for p in s.rows('project') if p['source_id']=='ih_notice']
    documents=[d for d in s.rows('document_evidence') if d['source_id']=='ih_notice']
    assert projects and documents
    assert all(p['mapping']['policy_id']=='UNASSIGNED' for p in projects)
    registered=s.projects(policy_id='POL_2025_0907')
    assert not any(p.get('source_reference_id') or p.get('policy_candidate_only') for p in registered)
    original=json.loads((s.data_dir/'remediation/r01/selected-before.json').read_text())['approved_mappings']
    with s.sessions() as db:
        current={m.project_id:m for m in db.scalars(select(Mapping))}
        assert all(all(getattr(current[p['project_id']],key)==value for key,value in p.items()) for p in original)
        batch=db.scalar(select(Batch).where(Batch.source_id=='ih_notice',Batch.status=='SUCCESS').order_by(Batch.finished_at.desc()))
        stats=batch.stats;manifest=batch.manifest
    data=dict(verified_at=now().isoformat(),actor=ACTOR,reason=REASON,source_id='ih_notice',
        projects=len(projects),documents=len(documents),original_files=len(manifest),
        project_records=[dict(id=p['id'],name=p['name'],planned_units=p.get('planned_units'),policy_id=p['mapping']['policy_id'],
                              evidence_url=p['evidence_url'],source_revision_id=p['source_revision_id']) for p in projects],
        board_checkpoints=stats['board_checkpoints'],source_failures=stats.get('failures',[]),
        policy_records=len(registered),approved_mappings_preserved=len(original),approved_mappings_changed=0,
        snapshot_id=snapshot['id'],snapshot_counts=snapshot['result']['counts'],stage_evidence=stage,collection_links=links,
        bridge_changes={k:v for k,v in bridge.items() if k not in ('proposals','held')},
        api_status='HTTP_504_UNRESOLVED',api_address_check='공식 Swagger host와 path가 기존 주소와 일치. 504의 상세 원인은 미확정.',
        unverified='공고·사업 계획 확보와 신규 정책 실적·계약·실입주 확보를 구분. 정책 전체 모집단은 미확정.')
    save(s,'ih-website-and-policy-scope-r02',dict(title='iH 공식 홈페이지 수집 및 참고 후보 정책 범위 보완',
        actor=ACTOR,reason=REASON,round_id='HOME-INTEGRITY-R02',repair_type='COLLECTION_GAP',status='APPLIED_REVIEW_PENDING',
        base_date=today().isoformat(),stages=['BUSINESS','CONSTRUCTION','SUPPLY','MOVE_IN'],source_ids=['ih_notice','ih_supply','molit_renewal_inventory','building_hub'],
        project_ids=[],related_keys=['source_reference_id','policy_candidate_only','known_at','notice_round'],
        cause='iH API는 공식 주소와 일치하나 504로 실패. 공개 홈페이지 원천 경로가 없었고 참고 후보가 일반 프로그램의 정책 제안을 따라 분모에 포함되는 경로를 최종 검수에서 발견.',
        action=f"iH 주택 사업 {len(projects)}건·공고 {len(documents)}건 원문·첨부·판본 수집. 페이지 체크포인트·정정/추가/예비 분리 및 정책 귀속 전 후보의 분모 유입 방지 적용.",
        remaining='iH 과거 게시판 이어받기, HWP 추가 정형화·물량 구획·정정 계보 확인, API 504 원인 확인, 실제 계약·실입주 원천 확보 및 담당자 검토 필요.',
        impact='원천 확보를 확대하며 특정 정책 실적·신규 물량·실입주를 임의 생성하지 않음',report_url='/poc/home/#data-integrity',
        quality_checks=[dict(id='R02-ih-primary',title='iH 원천·정책 범위·기존 판단 보존',kind='CONSISTENCY',layer='LINKAGE',result='PARTIAL',
            rule='공고·계획·예비자 수를 실적과 분리. 정책 미귀속 후보는 정책별 실적 분모에 포함하지 않음.',
            evidence=f"iH 사업 {len(projects)}건/문서 {len(documents)}건, 기존 확정·해제 {len(original)}건 보존, 정책 자료 분모 {len(registered)}건",
            repair='공식 웹 목록·상세·첨부 수집 및 후보 정책 귀속 차단, 원문 판본·기준본 고정',
            completion_criteria='과거 페이지·수량·정정 계보·실제 사건 원천까지 추가 대조',checked_at=today().isoformat(),checked_scope='iH 공개 주택 자료와 등록된 정책 관리 사업')]))
    matrix=collection_matrix(s,policy_id='POL_2025_0907')
    for name,value in [('verification.json',data),('requirements-after.json',build_status(s,matrix)),
                       ('quality-after.json',quality_guide(collection_matrix(s))),('snapshot-after.json',snapshot),
                       ('sources-after.json',dict(items=s.sources())),('ih-raw-manifest.json',manifest)]:
        (folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps({k:data[k] for k in ('projects','documents','policy_records','approved_mappings_preserved','snapshot_id','snapshot_counts','source_failures')},ensure_ascii=False))


if __name__=='__main__':main()
