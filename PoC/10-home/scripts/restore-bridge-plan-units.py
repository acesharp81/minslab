"""Restore dropped plan quantities using only the exact revision already linked.

Dry run by default. Does not rematch, change scope, confirm a link, or infer actuals.
"""
import sys
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,text
from backend.db import Revision,Audit,upsert_revision,engine_for
from backend.service import HomeService
from backend.evidence_bridge import facts,KIND
from backend.api_samples import today

def restore(service,apply=False):
    changes=[]
    with service.sessions.begin() as db:
        if apply and service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019081)'))
        bridges=list(db.scalars(select(Revision).where(Revision.kind==KIND,Revision.superseded_at.is_(None))))
        for old in bridges:
            payload=old.payload
            if payload.get('status')=='RELEASED':continue
            legacy=payload.get('relation_type') is None and payload.get('matching_version')=='district-block-units-v1'
            if payload.get('relation_type')!='SAME_SCOPE' and not legacy:continue
            source=db.scalar(select(Revision).where(Revision.entity_id==payload['source_entity_id'],Revision.revision_no==payload['source_revision_no']))
            if source is None:continue
            if legacy:
                target=db.scalar(select(Revision).where(Revision.entity_id==payload['project_id'],Revision.superseded_at.is_(None)))
                if target is None or source.payload.get('planned_units')!=payload.get('units') or target.payload.get('planned_units')!=payload.get('units'):continue
            generated=facts(dict(source.payload,source_id=source.source_id),today())
            updated=deepcopy(payload);count=0
            for f in updated.get('facts',[]):
                if f.get('kind')!='PLAN' or f.get('units') is not None or f.get('scope_partial') or f.get('scope_proof_entity_id'):continue
                values={g['units'] for g in generated if all(g.get(k)==f.get(k) for k in ('stage','kind','milestone','date'))
                        and type(g.get('units')) is int and 0<=g['units']<=payload.get('units',0) and not g.get('scope_partial')}
                if len(values)!=1:continue
                f['units']=values.pop();count+=1
            if not count:continue
            key=payload['project_id']+':'+payload['source_entity_id']
            changes.append(dict(project_id=payload['project_id'],bridge_id=old.entity_id,facts=count))
            if apply:
                row,_=upsert_revision(db,KIND,'cross_source',key,updated,'restore-plan-units-20261014')
                db.add(Audit(entity_id=row.entity_id,action='BRIDGE_PLAN_UNITS_RESTORE',before=payload,after=updated))
    return dict(applied=apply,links=len(changes),projects=len({r['project_id'] for r in changes}),facts=sum(r['facts'] for r in changes),changes=changes)

if __name__=='__main__':
    import json
    print(json.dumps(restore(HomeService(engine_for()),'--apply' in sys.argv),ensure_ascii=False))
