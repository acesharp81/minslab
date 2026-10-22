"""Bounded, read-only previews of current source records."""
from urllib.parse import urlsplit
from sqlalchemy import select, func
from .source_authority import public_url, authority, LABELS
from .db import Revision
from .sources import SOURCES
from scripts.export_json import credential_values, scrub


def source_preview(service, source_id):
    if source_id.startswith('document:'):
        return document_preview(service,source_id)
    if not any(s['id'] == source_id for s in SOURCES):
        raise KeyError(source_id)
    condition = (Revision.source_id == source_id, Revision.superseded_at.is_(None))
    with service.sessions() as session:
        total = session.scalar(select(func.count()).select_from(Revision).where(*condition))
        records = session.scalars(select(Revision).where(*condition)
            .order_by(Revision.recorded_at.desc(), Revision.entity_id).limit(50)).all()
        secrets = credential_values()
        items = [dict(id=r.entity_id, kind=r.kind, recorded_at=r.recorded_at.isoformat(),
                      revision_no=r.revision_no, data=scrub(r.payload, secrets)) for r in records]
    fields = sorted({key for item in items for key in item['data']})
    return dict(source_id=source_id, total=total, limit=50, items=items, fields=fields)


def document_preview(service, source_id):
    """Document publisher cards share the standard bounded, scrubbed preview contract."""
    parts=source_id.split(':',2)
    if len(parts)!=3 or parts[1] not in LABELS or not parts[2]:raise KeyError(source_id)
    expected_authority,expected_host=parts[1:]
    secrets=credential_values();total=0;items=[]
    with service.sessions() as session:
        query=select(Revision.entity_id,Revision.source_id,Revision.payload,Revision.recorded_at,Revision.revision_no).where(
            Revision.kind=='document_evidence',Revision.superseded_at.is_(None)).order_by(
                Revision.recorded_at.desc(),Revision.entity_id).execution_options(yield_per=64)
        for eid,sid,payload,recorded_at,revision_no in session.execute(query):
            url=public_url(payload.get('evidence_url') or payload.get('source_url'))
            if (authority(url,sid),urlsplit(url).hostname or '출처 미기재')!=(expected_authority,expected_host):continue
            total+=1
            if len(items)<50:items.append(dict(id=eid,kind='document_evidence',recorded_at=recorded_at.isoformat(),
                revision_no=revision_no,data=scrub(payload,secrets)))
    if not total:raise KeyError(source_id)
    return dict(source_id=source_id,total=total,limit=50,items=items,
                fields=sorted({key for item in items for key in item['data']}))


def collected_record(service, entity_id, revision_no=None):
    """Read one identified collected record; never substitute a source-wide sample."""
    allowed=[s['id'] for s in SOURCES]
    chain=[];seen=set()
    with service.sessions() as session:
        for _ in range(5):
            conditions=[Revision.entity_id==entity_id,Revision.source_id.in_(allowed)]
            conditions.append(Revision.revision_no==revision_no if revision_no is not None else Revision.superseded_at.is_(None))
            row=session.scalar(select(Revision).where(*conditions))
            if row is None or row.id in seen:raise KeyError(entity_id)
            seen.add(row.id)
            # Project metadata is derived from a pinned source record. Follow it,
            # instead of presenting the project overlay as an API response.
            ref=row.payload.get('source_reference_id') if row.kind=='project' else None
            if not ref:break
            chain.append(dict(id=row.entity_id,revision_no=row.revision_no))
            pinned=row.payload.get('source_reference_revision_id')
            if pinned:
                original=session.get(Revision,pinned)
                if original is None or original.entity_id!=ref:raise KeyError(ref)
                revision_no=original.revision_no
            else:revision_no=row.payload.get('source_reference_revision_no')
            entity_id=ref
        else:raise KeyError(entity_id)
        source=next(s for s in SOURCES if s['id']==row.source_id)
        from .source_authority import clean
        return dict(id=row.entity_id,kind=row.kind,source_id=row.source_id,source_name=source['name'],
                    revision_no=row.revision_no,recorded_at=row.recorded_at.isoformat(),
                    source_date=row.sample_source_date,base_date=row.sample_base_date,reference_chain=chain,
                    catalog_url=public_url(source.get('url')),data=clean(scrub(row.payload,credential_values())))



def project_collected_records(service, project_id, source_url):
    from .project_collection import collection_matrix
    matrix=collection_matrix(service,project_ids=(project_id,),include_link_history=False)
    if not matrix['items']:raise KeyError(project_id)
    refs={(project_id,None):['사업 원천']}
    for stage,cell in matrix['items'][0]['cells'].items():
        for r in cell.get('sources',[]):
            if r.get('source_entity_id') and (not source_url or public_url(r.get('evidence_url'))==source_url):
                refs.setdefault((r['source_entity_id'],r.get('source_revision_no')),[]).append(stage+' · '+r.get('kind',''))
    result=[];seen=set()
    for (eid,rev),contexts in refs.items():
        try:record=collected_record(service,eid,rev)
        except KeyError:continue
        urls={record['catalog_url'],public_url(record['data'].get('evidence_url')),public_url(record['data'].get('source_url'))}
        if source_url and source_url not in urls:continue
        key=(record['id'],record['revision_no'])
        if key in seen:continue
        seen.add(key);result.append(dict(record,contexts=contexts))
    return dict(project_id=project_id,items=result,notice='해당 사업에 연결된 수집 레코드입니다. 원천 필드 값과 관리·추정값은 구분합니다. 고정 판본이 있는 근거는 해당 판본을 표시합니다.')
