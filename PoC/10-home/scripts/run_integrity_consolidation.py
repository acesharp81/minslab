"""Authorized collection, reviewed corrections and frozen consolidated inputs."""
import argparse
import json
from pathlib import Path
import sys
from sqlalchemy import select,func
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for,Revision,IdentityAlias,ProjectIdentity,Mapping
from backend.service import HomeService,today
from backend.sources import SOURCES

ACTOR='김민';REASON='공식 발표 후 도출된 보완 사항 적용'
ROUND='HOME-INTEGRITY-R01-CONSOLIDATED-20261017'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--collect',action='store_true');parser.add_argument('--correct',action='store_true');parser.add_argument('--assess',action='store_true')
    args=parser.parse_args();s=HomeService(engine_for(),'/app/data');out=s.data_dir/'remediation/r03';out.mkdir(parents=True,exist_ok=True)
    def save(name,value):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')
    if args.collect:
        results=[]
        for source_id in ('ih_housing_inventory','seoul_cleanup','ih_notice'):
            source=next(x for x in SOURCES if x['id']==source_id)
            for iteration in range(18 if source_id=='ih_notice' else 1):
                result=s.collect_one(source);results.append(dict(source_id=source_id,iteration=iteration+1,result=result));save('collection-execution.json',results)
                stats=s.latest_collection_stats(source_id)
                print(json.dumps(dict(source_id=source_id,iteration=iteration+1,status=result['status'],fetched=stats.get('fetched'),
                    documents=stats.get('documents'),roster_rows=stats.get('roster_rows'),complexes=stats.get('complexes'),
                    board_checkpoints=stats.get('board_checkpoints'),failures=len(stats.get('failures',[]))),ensure_ascii=False),flush=True)
                if result['status']!='SUCCESS':break
                if source_id!='ih_notice' or all(c['complete_window'] for c in stats['board_checkpoints'].values()):break
        save('sources-after-collection.json',dict(items=s.sources()))
    if args.correct:
        from backend.matching_corrections import propose,apply,REASON as CORRECTION_REASON
        from backend.collection_repairs import save as repair
        projects=s.rows('project');bridges=s.rows('evidence_bridge');stages=s.rows('stage_evidence')
        ids={b['source_entity_id'] for b in bridges}|{r['selected']['source_entity_id'] for r in stages if r.get('selected')}
        with s.sessions() as db:
            sources={r.entity_id:dict(r.payload,id=r.entity_id,source_id=r.source_id) for r in db.scalars(select(Revision).where(Revision.entity_id.in_(ids),Revision.superseded_at.is_(None)))}
        changes=propose(projects,bridges,stages,sources)
        if changes:
            save('matching-correction-plan.json',changes)
            result=apply(s,changes,ACTOR);names={p['id']:p['name'] for p in projects}
            for row in result['items']:row['name']=names[row['project_id']]
            save('matching-corrections.json',result)
            repair(s,'reviewed-matching-scope-correction-20261017',dict(title='담당자 확인 전체·부분 매칭 오류 정정',actor=ACTOR,reason=CORRECTION_REASON,round_id=ROUND,
                repair_type='SCOPE_QUANTITY',status='APPLIED',base_date=today().isoformat(),stages=['APPROVAL','SUPPLY','CONSTRUCTION','MOVE_IN'],
                source_ids=['building_hub','official_document'],project_ids=sorted({r['project_id'] for r in result['items']}),
                cause='확정된 자동매칭에서 전체 승인 물량이 부분 사업에 적용되고, 직접 사건의 부분 범위 관계가 동일 범위로 저장됨.',
                action=f"{result['count']}건을 원문·기존 판본에 대조하여 관계와 물량 귀속 정정. 사업 동일성과 원문 사건일은 유지.",
                remaining='부분 사업의 승인 물량은 배분 직접 근거 확보 전 미확정. 수도권 모집단·실제 계약·입주 확보는 별도 과제.',
                related_keys=['source_revision_no','selected.units','relation_type','source_total_units','correction_explanation']))
            print('CORRECTIONS',result['count'],flush=True)
        else:print('CORRECTIONS no additional confirmed scope errors',flush=True)
    if args.assess:
        from backend.independent_metrics import freeze
        from backend.policy_delivery import build_delivery
        from backend.annual_supply import annual_supply
        from backend.integrity_diagnostics import evaluate
        from backend.project_collection import collection_matrix
        from backend.requirements_status import build_status
        snapshot=freeze(s,ACTOR,REASON);save('snapshot-after.json',snapshot)
        # Query all diagnostic inputs at the same knowledge cutoff as the event snapshot.
        from datetime import datetime
        scoped=HomeService(s.engine,s.data_dir,known_at=datetime.fromisoformat(snapshot['context']['known_at']))
        delivery=build_delivery(scoped,today(),include_portfolio_comparisons=False);save('delivery-after.json',delivery)
        annual=annual_supply(scoped,'서울특별시',2026);save('annual-after.json',annual)
        with s.sessions() as db:
            counts=[dict(kind=k,source_id=sid,region=region,records=n) for k,sid,region,n in db.execute(select(Revision.kind,Revision.source_id,Revision.sample_region,func.count()).where(Revision.superseded_at.is_(None),Revision.kind.in_(('project','renewal_inventory','renewal_roster','housing_inventory','permit'))).group_by(Revision.kind,Revision.source_id,Revision.sample_region))]
            identity_counts=dict(source_aliases=db.scalar(select(func.count()).select_from(IdentityAlias)),identity_anchors=db.scalar(select(func.count()).select_from(ProjectIdentity)))
            baseline=json.loads((out.parent/'r01/selected-before.json').read_text())['approved_mappings']
            current={m.project_id:dict(id=m.id,project_id=m.project_id,policy_id=m.policy_id,program_id=m.program_id,status=m.status,revision_no=m.revision_no) for m in db.scalars(select(Mapping))}
            assert all(current.get(r['project_id'])==r for r in baseline),'기존 정책 귀속 변경 감지'
        diagnostic=evaluate(snapshot,scoped.rows('project'),delivery,annual,counts,identity_counts,s.latest_collection_stats('ih_notice'))
        save('diagnostics.json',diagnostic)
        requirements=build_status(s,collection_matrix(s,policy_id='POL_2025_0907'));save('requirements-after.json',requirements)
        save('sources-after.json',dict(items=s.sources()))
        save('verification.json',dict(actor=ACTOR,reason=REASON,round_id=ROUND,snapshot_id=snapshot['id'],snapshot_counts=snapshot['result']['counts'],
            original_policy_mappings_preserved=len(baseline),original_policy_mappings_changed=0,agreement_percent=diagnostic['agreement']['overall_confirmed_percent'],
            current_benchmark_rows=len(diagnostic['agreement']['rows']),independent_actual_matches=diagnostic['agreement']['independent_actual_matches']))
        print('ASSESSMENT',snapshot['result']['counts'],'agreement',diagnostic['agreement']['overall_confirmed_percent'],flush=True)


if __name__=='__main__':main()
