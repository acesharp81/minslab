"""Read-only project report input, using the policy ledger and dated evidence.

No identity inference, data repair or approval is performed by this projection.
All source alternatives and edit reasons remain available for a lazy appendix.
"""
from copy import deepcopy
from .read_scope import projection_reads
from .db import entity_id, Revision
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select

VERSION = 'HOME_PROJECT_BRIEF_V1_20261023'


def report_input(service, project_id, reference, ledger):
    from .project_collection import collection_matrix
    with projection_reads():
        matches = [c for c in ledger.get('portfolio_cohorts', [])
                   if project_id == c['id'] or project_id in c.get('source_ids', [])]
        if len(matches) > 1:
            raise ValueError('해당 기준일에 단일 대표사업으로 연결된 원장이 없습니다. 사업 식별·정책 귀속을 확인하세요.')
        cohort = deepcopy(matches[0]) if matches else None
        ids = (set(cohort.get('source_ids', [])) | {cohort['id']}) if cohort else {project_id}
        projects = [p for p in service.projects(as_of=reference) if p['id'] in ids]
        if not projects:raise ValueError('해당 기준일의 사업 원천 판본이 없습니다.')
        matrix = collection_matrix(service, as_of=reference, project_ids=tuple(sorted(ids)), include_link_history=False)
        if cohort is None:cohort = project_only_cohort(projects[0], matrix)
        refs = [dict(entity_id=p['id'], kind='project', source_id=p.get('source_id')) for p in projects]
        refs.extend(dict(entity_id=entity_id('project_profile','manual_project',p['id']), project_id=p['id'],
                         kind='project_profile') for p in projects)
        schedules = [r for r in service.rows('execution_schedule', reference) if r.get('project_id') in ids]
        refs.extend(dict(entity_id=s['id'],project_id=s.get('project_id'),kind='execution_schedule')
                    for s in schedules if s.get('id'))
        # Preserve all linked evidence, not only the source selected for aggregation.
        evidence = []
        for row in matrix.get('items', []):
            for stage, cell in row.get('cells', {}).items():
                evidence.extend(dict(r, report_stage=stage, report_project_id=row['id']) for r in cell.get('sources', []))
        linked_ids = {r.get('source_entity_id') for r in evidence if r.get('source_entity_id')} - ids
        refs.extend(dict(entity_id=eid,kind='linked_evidence') for eid in sorted(linked_ids))
        histories = revision_histories(service, refs, reference)
        mappings = [dict(project_id=p['id'], history=service.mapping_history(p['id'], reference)) for p in projects]
        locations = [r for r in service.rows('project_location', reference)
                     if r.get('project_id') in ids and r.get('status') != 'RELEASED']
        return dict(kind='project', scope=dict(project_id=cohort['id'], requested_project_id=project_id,
                    name=cohort['name'], as_of_date=reference.isoformat(), policy_id=ledger.get('policy_id')),
                    data=dict(cohort=cohort, projects=projects, evidence=evidence, histories=histories,
                              mapping_history=mappings, locations=locations, plan=ledger.get('plan', {}),
                              cells=matrix.get('items', []), schedules=schedules),
                    snapshot=dict(as_of_date=reference.isoformat(), formula_version=VERSION,
                                  knowledge_rule='기준일 한국시간 종료 이전 등록 판본·당시 매핑; 최신값 소급 대체 없음'))


def revision_histories(service, refs, reference):
    """One bounded query; do not repeat an entire collection manifest per revision.

    Revision IDs + original payload hashes are the reproducible references.
    Source URLs and values stay in the pinned input; raw files stay in the archive.
    """
    cutoff=datetime.combine(reference+timedelta(days=1),time.min,ZoneInfo('Asia/Seoul')).astimezone(timezone.utc)
    if service.known_at is not None:cutoff=min(cutoff,service.known_at.astimezone(timezone.utc))
    by_id={r['entity_id']:dict(r,revisions=[]) for r in refs}
    with service.sessions() as session:
        rows=session.scalars(select(Revision).where(Revision.entity_id.in_(by_id),Revision.recorded_at<cutoff)
                             .order_by(Revision.entity_id,Revision.revision_no.desc())).all()
        def utc(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        for r in rows:
            by_id[r.entity_id]['revisions'].append(dict(revision_no=r.revision_no,source_revision_id=r.id,
                source_id=r.source_id,batch_id=r.batch_id,recorded_at=utc(r.recorded_at).isoformat(),
                superseded_at=utc(r.superseded_at).isoformat() if r.superseded_at and utc(r.superseded_at)<cutoff else None,
                base_date=r.payload.get('base_date'),payload_hash=r.payload_hash,values=r.payload))
    return list(by_id.values())


def project_only_cohort(p, matrix):
    """Keep the selected project's existing editor values if absent from policy totals.

    Do not guess another representative ID or add this row to the policy ledger.
    """
    row=next((r for r in matrix.get('items',[]) if r['id']==p['id']),None)
    if row is None:raise ValueError('해당 기준일의 사업별 관리 원장이 없습니다.')
    events=[];schedules=[]
    for stage,cell in row.get('cells',{}).items():
        if stage=='POLICY':continue
        for kind,output in [('measurement',events),('target',schedules)]:
            for value in cell.get('management',{}).get(kind,[]):
                v=deepcopy(value);when=v.pop('date',None)
                if not when:continue
                v.update(stage=v.get('milestone') or stage,origin='MANUAL' if v.get('manual') else 'SOURCE')
                if kind=='measurement':v.update(event_date=when,status='ACTUAL')
                else:
                    v.update(due_date=when,managed_schedule=bool(v.get('manual')))
                    saved=p.get('managed_schedules',{}).get(v['stage'],{})
                    if saved.get('baseline'):v['baseline']=saved['baseline']
                output.append(v)
    meta=dict(supply_type=p.get('supply_type_assessment'),tenure=p.get('tenure'),mapping=p.get('mapping'),
              source_revisions=[{k:p.get(k) for k in ('id','source_id','source_revision_id','revision_no',
                  'source_payload_hash','recorded_at','last_collection_at','base_date','evidence_url')}])
    return dict({k:p.get(k) for k in ('id','name','block','region','municipality','developer','latitude','longitude','coordinate_basis','planned_units')},
                units=p.get('planned_units'),program_id=p.get('mapping',{}).get('program_id'),program=p.get('program'),
                source_ids=[p['id']],events=events,schedules=schedules,report_metadata=meta,
                ledger_scope='PROJECT_ONLY',ledger_note='정책 합산 원장과 대표 ID 연결 미확인. 선택 사업 관리값만 표시하며 정책 총량에 추가하지 않음.')
