"""Manually collected publication text, pinned to its discovery revision.

Supplements neither approve a review nor create project/stage facts. Keeping a
separate revision prevents the hourly listing collector from erasing the text.
"""
from sqlalchemy import select
from .db import Revision, Audit, now, upsert_revision

KIND = 'publication_supplement'


def load(service, document_ids):
    if not document_ids:
        return {}
    with service.sessions() as db:
        return {r.payload['document_id']: r.payload for r in db.scalars(select(Revision).where(
            Revision.kind == KIND, Revision.superseded_at.is_(None),
            Revision.payload['document_id'].as_string().in_(document_ids)))}


def summary(payload, source_revision_no):
    return {k: v for k, v in payload.items() if k in (
        'source_revision_no', 'collected_at', 'summary', 'actor')} | {
        'stale': payload['source_revision_no'] != source_revision_no,
        'attachments': [{k: a[k] for k in ('name','url','sha256') if k in a}
                        for a in payload.get('attachments', [])]}


def save(service, document_id, source_revision_no, body_text, summary_text, attachments, actor, raw_sha256):
    from .publication_reviews import source_ids
    from .source_authority import public_url
    if not body_text.strip() or not summary_text.strip() or not actor.strip():
        raise ValueError('수집 본문·확인 내용·수집자를 기록하세요')
    if len(raw_sha256) != 64 or any(c not in '0123456789abcdef' for c in raw_sha256):
        raise ValueError('원문 SHA256을 기록하세요')
    for a in attachments:
        if not a.get('name') or not a.get('url') or public_url(a['url']) != a['url']:
            raise ValueError('첨부 공개 원문 주소를 확인하세요')
    with service.sessions.begin() as db:
        doc=db.scalar(select(Revision).where(Revision.entity_id == document_id,
            Revision.kind == 'document_evidence', Revision.source_id.in_(source_ids()),
            Revision.superseded_at.is_(None)).with_for_update())
        if not doc or doc.revision_no != source_revision_no:
            raise ValueError('수집 대상 판본이 변경됐습니다. 원문을 다시 확인하세요')
        payload=dict(document_id=document_id, source_revision_no=source_revision_no,
            body_text=body_text, summary=summary_text, attachments=attachments,
            actor=actor, raw_sha256=raw_sha256, collected_at=now().isoformat(),
            scope='수동 원문·첨부 수집 · 사업 연결·정책 귀속·실적 승인 아님')
        row,outcome=upsert_revision(db,KIND,'publication_manual',document_id,payload,'manual-publication-collection')
        db.add(Audit(entity_id=row.entity_id,action='PUBLICATION_MANUAL_COLLECTION',before={},after=payload))
        return dict(id=row.entity_id,revision_no=row.revision_no,outcome=outcome)


def usable(payload, source_revision_no, analysis=None):
    """A manual recovery may replace only an older extraction of the same revision."""
    from datetime import datetime
    if not payload or payload.get('source_revision_no') != source_revision_no or not payload.get('body_text'):
        return False
    analysis = analysis or {}
    if not analysis.get('collected_at'):
        return not analysis.get('body_text')
    try:
        return datetime.fromisoformat(payload['collected_at']) >= datetime.fromisoformat(analysis['collected_at'])
    except (KeyError, TypeError, ValueError):
        return False
