"""Evidence-scoped policy references. Never writes membership or performance facts."""
import re
from urllib.parse import urlparse
from sqlalchemy import select
from .db import Revision, Mapping, Audit, upsert_revision

KIND = 'project_policy_relation'
SOURCE = 'policy_reference_review'
LABELS = {'A': '지구 연관 · 블록 귀속 확인 필요', 'B': '공공택지 정책수단 관련',
          'C': '정비사업 정책수단 관련', 'D': '개별 정책 귀속 근거 미확보'}


def evidence_context(project):
    url = project.get('evidence_url') or ''
    intro = urlparse(url).hostname in ('data.go.kr', 'www.data.go.kr') and '/openapi.do' in url
    return dict(source_object_id=project.get('source_object_id'),
                source_reference_id=project.get('source_reference_id'),
                source_reference_revision=project.get('source_reference_revision'),
                address=project.get('address'), district=project.get('district'), block=project.get('block'),
                source_start_plan_date=project.get('start_plan_date'),
                source_start_actual_date=project.get('start_actual_date'),
                evidence_status='PER_PROJECT_EVIDENCE_MISSING' if intro else 'SOURCE_REVIEW_REQUIRED',
                evidence_note=('사업별 공개 URL 미확보 · 원시 레코드 ID는 별도 대조' if intro else '원천자료 확인과 정책 귀속 승인은 별도'))


def validate_reference(payload):
    if payload.get('relation_type') != 'POLICY_REFERENCE':
        raise ValueError('관련성 참고 전용 기록입니다')
    if payload.get('category') not in LABELS or payload.get('relation_level') not in ('DISTRICT','BLOCK','PROJECT','THEMATIC'):
        raise ValueError('관련성 분류를 확인하세요')
    if payload.get('inclusion_in_97_supply_target') is not False or any(payload.get(k) is not None for k in ('credited_housing_units','credited_start_date','approved_by','approved_at')):
        raise ValueError('참고 관계로 정책 실적을 승인할 수 없습니다')
    if payload.get('relation_status') not in ('CANDIDATE','NO_EVIDENCE'):
        raise ValueError('대상 확정은 별도 귀속 심사가 필요합니다')
    if not re.fullmatch(r'[a-f0-9]{64}', payload.get('report_sha256','')) or not payload.get('actor') or not payload.get('reason'):
        raise ValueError('검토 원문 해시와 검토자·사유가 필요합니다')


def save_reference(service, payload):
    validate_reference(payload)
    if payload['policy_id'] not in {p['policy_id'] for p in service.mapping_policies()}:
        raise ValueError('실제 정책대장에 없는 정책입니다')
    pid=payload['project_id'];key=f"{pid}:{payload['policy_id']}:{payload['report_sha256']}"
    with service.sessions.begin() as db:
        project=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.kind=='project',Revision.superseded_at.is_(None)).with_for_update())
        mapping=db.scalar(select(Mapping).where(Mapping.project_id==pid).with_for_update())
        if project is None or mapping is None:raise KeyError(pid)
        if project.payload_hash!=payload['project_sha256'] or mapping.revision_no!=payload['mapping_revision_no']:
            raise ValueError('사업 또는 연결 판본이 변경되었습니다. 다시 대조하세요')
        record,change=upsert_revision(db,KIND,SOURCE,key,payload,'policy-reference-review')
        if change!='unchanged':
            db.add(Audit(entity_id=pid,action='POLICY_REFERENCE_REVIEW',before={},after=dict(payload,relation_id=record.entity_id)))
        return dict(id=record.entity_id,revision_no=record.revision_no,change=change)
