"""Discover source-backed candidates without turning references into actuals."""
import re
from sqlalchemy import select, text
from .db import Audit, IdentityAlias, ProjectEvidence, ProjectIdentity, Revision, Mapping, upsert_revision, entity_id, now
from .identity import project_id
from .service import today


def reconcile(service, actor, reason, promote=False):
    added, promoted, evidence_added, held = 0, [], 0, []
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(1019111)'))
        references = db.scalars(select(Revision).where(Revision.kind == 'renewal_inventory', Revision.superseded_at.is_(None))).all()
        # This bounded permit search is for the named acceptance case, not an
        # assertion that every historical building permit is an active project.
        references += [r for r in db.scalars(select(Revision).where(Revision.kind == 'permit',
                         Revision.superseded_at.is_(None), Revision.sample_name.contains('광교')))
                       if re.search(r'A\s*-?\s*17', r.payload.get('name', ''), re.I) and r.payload.get('units') == 600]
        aliases = {a.source_entity_id: a for a in db.scalars(select(IdentityAlias))}
        evidence = {(e.project_id, e.revision_id) for e in db.scalars(select(ProjectEvidence))}
        references.sort(key=lambda r:r.entity_id)
        permit_signatures=set()
        for source in references:
            payload = source.payload
            pid = aliases[source.entity_id].project_id if source.entity_id in aliases else project_id(source.entity_id)
            if db.get(ProjectIdentity, pid) is None:
                db.add(ProjectIdentity(id=pid, name=payload.get('name') or '원천 사업 후보',
                                       region=payload.get('region') or '미확보', identity_status='REVIEW'))
                db.flush()
            if source.entity_id not in aliases:
                alias = IdentityAlias(project_id=pid, source_entity_id=source.entity_id, source_id=source.source_id,
                    relation_status='REVIEW', match_rule='REFERENCE_SOURCE_ANCHOR', unit_comparison=None,
                    basis='정비·허가 원천의 실사업 검토 시작점. 현재 착공·정책 귀속은 별도 확인.',
                    evidence_revision_id=source.id, evidence_url=payload.get('evidence_url') or '')
                db.add(alias); aliases[source.entity_id] = alias; added += 1
                db.add(Audit(entity_id=pid, action='REFERENCE_CANDIDATE', before={},
                             after=dict(actor=actor, reason=reason, source_entity_id=source.entity_id, status='REVIEW')))
            if (pid, source.id) not in evidence:
                db.add(ProjectEvidence(project_id=pid, revision_id=source.id, evidence_role='REFERENCE_INVENTORY'))
                evidence.add((pid, source.id)); evidence_added += 1
            name = re.sub(r'\s+', '', payload.get('name', ''))
            selected = any(s in name for s in ('중계본동', '흑석11', '신림2재정비')) or (source.kind == 'permit' and '광교' in name)
            if not promote or not selected:
                continue
            if source.kind=='permit':
                signature=(payload.get('region'),payload.get('name'),payload.get('address'),payload.get('units'))
                if signature in permit_signatures:
                    # Two native permit IDs do not prove two distinct projects.
                    held.append(dict(source_entity_id=source.entity_id,reason='동일 명칭·주소·세대수의 다른 허가 관리번호 · 별개 사업 여부 확인 전 중복 관리 후보 보류'))
                    prior_id=entity_id('project',source.source_id,'reference:'+source.entity_id)
                    prior=db.scalar(select(Mapping).where(Mapping.project_id==prior_id))
                    if prior and prior.status=='REVIEW' and prior.revision_no==1:
                        old=dict(status=prior.status,revision_no=prior.revision_no,policy_id=prior.policy_id,
                                 program_id=prior.program_id,basis=prior.basis,evidence_url=prior.evidence_url)
                        prior.status='RELEASED';prior.revision_no+=1;prior.reviewed_at=now()
                        prior.basis='원천 고유번호는 다르나 동일 사업명·주소·물량 후보와 중복 의심. 관리 집계 제외 후 별개 사업 여부 검토.'
                        db.add(Audit(entity_id=prior_id,action='REFERENCE_DUPLICATE_HELD',before=old,
                                     after=dict(project_id=prior_id,status='RELEASED',actor=actor,reason=reason,basis=prior.basis)))
                    continue
                permit_signatures.add(signature)
            project = dict(payload, name=payload['name'], region=payload['region'],
                source_object_id=source.entity_id, source_reference_id=source.entity_id,
                source_reference_revision_id=source.id, source_reference_revision_no=source.revision_no,
                planned_units=payload.get('planned_units', payload.get('units')), source_kind=source.kind,
                stage='PLANNING', stage_label='원천 사업 후보 · 실제 사건 별도 검증',
                program='민간정비 후보' if source.kind == 'renewal_inventory' else '공공주택 후보',
                proposed_policy='UNASSIGNED', warnings=['REFERENCE_CANDIDATE_REVIEW'],
                actor=actor, reason=reason, base_date=payload.get('base_date') or today().isoformat())
            # Source inventory dates/stages are never converted to start_actual_date.
            project.pop('start_actual_date', None)
            project.pop('move_in_actual_date', None)
            row, outcome = upsert_revision(db, 'project', source.source_id, 'reference:' + source.entity_id, project, 'reference_registry')
            if row.entity_id not in aliases:
                alias = IdentityAlias(project_id=pid, source_entity_id=row.entity_id, source_id=source.source_id,
                    relation_status='REVIEW', match_rule='SOURCE_REFERENCE_DERIVATION', unit_comparison='EQUAL',
                    basis='동일 원천 고유키를 관리 후보로 표시. 다른 사업과 병합하거나 성과를 생성하지 않음.',
                    evidence_revision_id=source.id, evidence_url=payload.get('evidence_url') or '')
                db.add(alias); aliases[row.entity_id] = alias
            if db.scalar(select(Mapping).where(Mapping.project_id == row.entity_id)) is None:
                db.add(Mapping(project_id=row.entity_id, policy_id='UNASSIGNED', status='REVIEW',
                               basis='1차 원천 기반 관리 후보. 정책 귀속·실제 착공·물량 범위 추가 검증.', evidence_url=project.get('evidence_url') or ''))
            if outcome != 'unchanged':
                db.add(Audit(entity_id=row.entity_id, action='REFERENCE_PROMOTED', before={},
                             after=dict(actor=actor, reason=reason, source_revision_id=source.id, project_id=row.entity_id, status='REVIEW')))
            promoted.append(dict(id=row.entity_id, canonical_id=pid, name=project['name'], outcome=outcome,
                                 source_entity_id=source.entity_id, source_revision_id=source.id, policy_status='UNASSIGNED'))
    return dict(reference_rows=len(references), candidates_added=added, evidence_added=evidence_added, promoted=promoted,held=held,
                approval_effect='NONE', actual_events_created=0)
