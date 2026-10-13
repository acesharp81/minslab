"""Idempotent review-only links from source objects to stable candidate projects."""
import hashlib
import re
from collections import defaultdict

from sqlalchemy import func, select

from .db import Audit, IdentityAlias, Plan, PlanEvent, PlanProjectLink, ProjectEvidence, ProjectIdentity, Revision, now


def normal(value, block=False):
    value = re.sub(r'[^가-힣A-Za-z0-9]', '', str(value or '')).lower()
    return value.removesuffix('bl') if block else value


def project_id(source_entity_id):
    return 'HPR_' + hashlib.sha256(('home:project:' + source_entity_id).encode()).hexdigest()[:24]


def grouping_key(payload):
    key = (payload.get('region'), normal(payload.get('district')),
           normal(payload.get('block'), block=True))
    return key if all(key) else None


def reconcile_identity_links(service):
    """Create 1:1 source anchors and unapproved LH schedule proposals only."""
    with service.sessions.begin() as session:
        projects = session.scalars(select(Revision).where(
            Revision.kind == 'project', Revision.superseded_at.is_(None))).all()
        forecasts = session.scalars(select(Revision).where(
            Revision.kind == 'lh_completion_plan', Revision.superseded_at.is_(None))).all()
        aliases = {alias.source_entity_id: alias for alias in session.scalars(select(IdentityAlias)).all()}
        evidence = {(item.project_id, item.revision_id) for item in session.scalars(select(ProjectEvidence)).all()}
        indexed = defaultdict(list)
        project_pids = {}
        anchors, proposals, ambiguous = 0, 0, 0
        for row in projects:
            existing = aliases.get(row.entity_id)
            pid = existing.project_id if existing else project_id(row.entity_id)
            project_pids[row.entity_id] = pid
            if session.get(ProjectIdentity, pid) is None:
                session.add(ProjectIdentity(id=pid, name=row.sample_name or row.payload.get('name') or '사업명 미확보',
                                            region=row.sample_region or row.payload.get('region') or '미확보',
                                            identity_status='REVIEW'))
                session.flush()
            if existing is None:
                alias = IdentityAlias(project_id=pid, source_entity_id=row.entity_id,
                    source_id=row.source_id, relation_status='REVIEW', match_rule='SOURCE_ANCHOR',
                    unit_comparison=None, basis='원천 사업후보 1:1 정체성 시작점 · 다른 원천과 동일 실사업 여부 미확정',
                    evidence_revision_id=row.id, evidence_url=row.payload.get('evidence_url') or '')
                session.add(alias)
                aliases[row.entity_id] = alias
                anchors += 1
            if (pid, row.id) not in evidence:
                session.add(ProjectEvidence(project_id=pid, revision_id=row.id, evidence_role='SOURCE_PROJECT'))
                evidence.add((pid, row.id))
            key = grouping_key(row.payload)
            if key:
                indexed[key].append(row)
        for row in forecasts:
            key = grouping_key(row.payload)
            matches = indexed.get(key, []) if key else []
            if len(matches) > 1:
                ambiguous += 1
            if row.entity_id in aliases:
                pid = aliases[row.entity_id].project_id
                if (pid, row.id) not in evidence:
                    session.add(ProjectEvidence(project_id=pid, revision_id=row.id,
                                                evidence_role='COMPLETION_FORECAST'))
                    evidence.add((pid, row.id))
                continue
            if len(matches) != 1:
                continue
            match = matches[0]
            pid = project_pids[match.entity_id]
            forecast_units = row.payload.get('planned_units')
            project_units = match.payload.get('planned_units')
            comparison = ('EQUAL' if forecast_units is not None and forecast_units == project_units
                          else 'DIFFERENT' if forecast_units is not None and project_units is not None
                          else 'UNKNOWN')
            alias = IdentityAlias(project_id=pid, source_entity_id=row.entity_id,
                source_id=row.source_id, relation_status='REVIEW',
                match_rule='REGION_DISTRICT_BLOCK', unit_comparison=comparison,
                basis='지역·지구·블록 정규화 단일 후보; LH 준공예정은 실제 준공·입주 아님. '
                      + ('계획 호수 차이 확인 필요' if comparison == 'DIFFERENT' else '담당자 동일 사업 확인 필요'),
                evidence_revision_id=row.id, evidence_url=row.payload.get('evidence_url') or '')
            session.add(alias)
            aliases[row.entity_id] = alias
            session.add(ProjectEvidence(project_id=pid, revision_id=row.id, evidence_role='COMPLETION_FORECAST'))
            evidence.add((pid, row.id))
            proposals += 1
        return dict(source_anchors_added=anchors, forecast_proposals_added=proposals,
                    ambiguous_forecasts=ambiguous, forecast_rows=len(forecasts),
                    approval_effect='NONE')


def identity_summary(service, offset=0, limit=100):
    with service.sessions() as session:
        total = session.scalar(select(func.count()).select_from(ProjectIdentity)) or 0
        forecast_proposals = session.scalar(select(func.count()).select_from(IdentityAlias).where(
            IdentityAlias.match_rule == 'REGION_DISTRICT_BLOCK',
            IdentityAlias.relation_status == 'REVIEW')) or 0
        rows = session.scalars(select(ProjectIdentity).order_by(ProjectIdentity.region, ProjectIdentity.name,
                                                               ProjectIdentity.id).offset(offset).limit(limit)).all()
        ids = [row.id for row in rows]
        aliases = session.scalars(select(IdentityAlias).where(
            IdentityAlias.project_id.in_(ids)).order_by(IdentityAlias.source_id, IdentityAlias.source_entity_id)).all() if ids else []
        by_project = defaultdict(list)
        for alias in aliases:
            by_project[alias.project_id].append(dict(id=alias.id, source_id=alias.source_id,
                source_entity_id=alias.source_entity_id, status=alias.relation_status,
                match_rule=alias.match_rule, unit_comparison=alias.unit_comparison,
                basis=alias.basis, evidence_revision_id=alias.evidence_revision_id,
                evidence_url=alias.evidence_url))
        return dict(total=total, forecast_review_count=forecast_proposals,
                    offset=offset, limit=limit, items=[
            dict(id=row.id, name=row.name, region=row.region, identity_status=row.identity_status,
                 aliases=by_project[row.id]) for row in rows],
            notice='정체성·LH 일정 연결은 검토 후보입니다. 기존 정책 매핑과 공식 공급실적을 변경하지 않습니다.')



def plan_summary(service):
    with service.sessions() as session:
        plans = session.scalars(select(Plan).order_by(Plan.region, Plan.name)).all()
        events = session.scalars(select(PlanEvent).order_by(PlanEvent.notice_date, PlanEvent.notice_no)).all()
        links = session.scalars(select(PlanProjectLink)).all()
        by_plan_events, by_plan_links = defaultdict(list), defaultdict(list)
        for event in events:
            by_plan_events[event.plan_id].append(dict(id=event.id, event_type=event.event_type,
                notice_no=event.notice_no, notice_date=event.notice_date,
                evidence_url=event.evidence_url, evidence_sha256=event.evidence_sha256,
                source_revision_id=event.source_revision_id,
                verification_status=event.verification_status))
        for link in links:
            by_plan_links[link.plan_id].append(dict(project_id=link.project_id, status=link.status,
                basis=link.basis, evidence_url=link.evidence_url))
        return dict(total=len(plans), items=[dict(id=plan.id, name=plan.name, region=plan.region,
            plan_type=plan.plan_type, legal_status=plan.legal_status,
            events=by_plan_events[plan.id], project_links=by_plan_links[plan.id]) for plan in plans],
            notice='공식 변경 고시 파일럿만 확보한 상태입니다. 최초 지정·전체 변경 이력과 사업 귀속은 미확보/검토 필요.')


def identity_review_queue(service, page=1, page_size=20):
    with service.sessions() as session:
        query = select(IdentityAlias).where(IdentityAlias.match_rule == 'REGION_DISTRICT_BLOCK')
        total = session.scalar(select(func.count()).select_from(IdentityAlias).where(
            IdentityAlias.match_rule == 'REGION_DISTRICT_BLOCK')) or 0
        aliases = session.scalars(query.order_by(IdentityAlias.relation_status.desc(),
            IdentityAlias.source_entity_id).offset((page - 1) * page_size).limit(page_size)).all()
        items = []
        for alias in aliases:
            target = session.get(ProjectIdentity, alias.project_id)
            source = session.scalar(select(Revision).where(
                Revision.entity_id == alias.source_entity_id, Revision.superseded_at.is_(None)))
            items.append(dict(id=alias.id, source_entity_id=alias.source_entity_id,
                source_name=source.sample_name if source else '원천 판본 미확보',
                source_units=(source.payload.get('planned_units') if source else None),
                project_id=alias.project_id, project_name=target.name if target else '사업 미연계',
                region=target.region if target else None, status=alias.relation_status,
                unit_comparison=alias.unit_comparison, basis=alias.basis,
                evidence_url=alias.evidence_url, reviewed_at=alias.reviewed_at))
        return dict(total=total, page=page, page_size=page_size, items=items,
            notice='지역·지구·블록 단일 일치 제안. 담당자 확정 전 공식 사업 동일성 아님.')


def identity_options(service):
    with service.sessions() as session:
        rows = session.scalars(select(ProjectIdentity).where(
            ProjectIdentity.identity_status != 'RELEASED').order_by(
                ProjectIdentity.region, ProjectIdentity.name, ProjectIdentity.id)).all()
        return dict(items=[dict(id=row.id, name=row.name, region=row.region) for row in rows])


def review_identity_alias(service, alias_id, *, project_id, expected_project_id,
                          expected_status, status, basis, evidence_url):
    if not evidence_url.startswith('https://'):
        raise ValueError('정체성 검토 근거는 HTTPS 공식 원문 URL이어야 합니다')
    with service.sessions.begin() as session:
        alias = session.scalar(select(IdentityAlias).where(
            IdentityAlias.id == alias_id).with_for_update())
        if alias is None:
            raise ValueError('정체성 검토 링크가 없습니다')
        if alias.project_id != expected_project_id or alias.relation_status != expected_status:
            return dict(conflict=True, project_id=alias.project_id, status=alias.relation_status)
        target = session.get(ProjectIdentity, project_id)
        if target is None:
            raise ValueError('선택한 실사업 정체성 후보가 없습니다')
        source = session.scalar(select(Revision).where(
            Revision.entity_id == alias.source_entity_id, Revision.superseded_at.is_(None)))
        if source is None or source.sample_region != target.region:
            raise ValueError('원천 자료와 선택 사업의 지역이 다릅니다')
        before = dict(project_id=alias.project_id, status=alias.relation_status,
                      basis=alias.basis, evidence_url=alias.evidence_url)
        if alias.project_id != project_id:
            revision_ids = session.scalars(select(Revision.id).where(
                Revision.entity_id == alias.source_entity_id)).all()
            existing = {row.revision_id for row in session.scalars(select(ProjectEvidence).where(
                ProjectEvidence.project_id == project_id)).all()}
            old_rows = session.scalars(select(ProjectEvidence).where(
                ProjectEvidence.project_id == alias.project_id,
                ProjectEvidence.revision_id.in_(revision_ids))).all()
            for row in old_rows:
                if row.revision_id in existing:
                    session.delete(row)
                else:
                    row.project_id = project_id
            previous_project_id = alias.project_id
            alias.project_id = project_id
            session.flush()
            remaining = session.scalar(select(func.count()).select_from(IdentityAlias).where(
                IdentityAlias.project_id == previous_project_id)) or 0
            if remaining == 0:
                old_project = session.get(ProjectIdentity, previous_project_id)
                if old_project:
                    old_project.identity_status = 'RELEASED'
            if target.identity_status == 'RELEASED':
                target.identity_status = 'REVIEW'
        alias.relation_status, alias.basis, alias.evidence_url, alias.reviewed_at = (
            status, basis, evidence_url, now())
        after = dict(project_id=alias.project_id, status=status, basis=basis, evidence_url=evidence_url)
        session.add(Audit(entity_id=alias.id, action='IDENTITY_REVIEW', before=before, after=after))
        return dict(id=alias.id, **after, conflict=False)
