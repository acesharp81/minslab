"""Structural PNU validation and persisted project/permit parcel candidates.

A composed PNU is a source-derived identifier, not cadastral or project approval.
Read views never re-run matching; a refresh follows stored permit selections.
"""
import re
from collections import Counter, defaultdict
from sqlalchemy import select, tuple_, text
from .db import Revision, upsert_revision

KIND = 'project_parcel'
REASONS = {
    'PERMIT_LINK_MISSING': '사업에 연결된 주택인허가 원천 없음',
    'DETAIL_NOT_COLLECTED': '연결 허가의 대지위치 상세 수집 필요',
    'BLOCK_ADDRESS': '원천이 블록 주소 · 확정 지번 대조 필요',
    'LAND_TYPE_MISSING': '원천 산 여부 미확보',
    'LOT_MISSING': '원천 본번·부번 미확보',
    'LOT_INVALID': '0번지 또는 잘못된 본번·부번',
    'LEGAL_CODE_INVALID': '법정동 코드 형식 오류',
    'LEGAL_CODE_UNVERIFIED': '공식 법정동 코드 마스터 대조 필요',
    'CANDIDATE': 'PNU 구성 완료 · 사업/필지 동일성 검토 필요',
}


def compose(row):
    code = str(row.get('sigungu_code') or '') + str(row.get('bjdong_code') or '')
    if not re.fullmatch(r'[0-9]{10}', code) or code.startswith('00'):
        return None, 'LEGAL_CODE_INVALID'
    land = str(row.get('plat_gb_cd') if row.get('plat_gb_cd') is not None else '').strip()
    if land == '2': return None, 'BLOCK_ADDRESS'
    if land not in ('0', '1'): return None, 'LAND_TYPE_MISSING'
    bun, ji = (str(row.get(k) if row.get(k) is not None else '').strip() for k in ('bun', 'ji'))
    if not bun or not ji: return None, 'LOT_MISSING'
    if not all(re.fullmatch(r'[0-9]{1,4}', v) for v in (bun, ji)) or int(bun) == 0:
        return None, 'LOT_INVALID'
    return code + ('1' if land == '0' else '2') + bun.zfill(4) + ji.zfill(4), 'CANDIDATE'


def enrich_source(payload, raw):
    """Preserve HUB land classification; blank sub-lot never defaults to zero."""
    payload['plat_gb_cd'] = str(raw['platGbCd']).strip() if raw.get('platGbCd') is not None else None
    pnu, reason = compose(payload)
    payload.update(pnu=pnu, pnu_status=reason,
                   pnu_basis='HUB_COMPONENTS' if pnu else None)


def selected_permits(service, reference=None):
    links = [r for r in service.rows('stage_evidence', reference)
             if r.get('status') in ('REVIEW', 'CONFIRMED') and r.get('selected')]
    refs = {(r['selected'].get('source_entity_id'), r['selected'].get('source_revision_no')) for r in links}
    refs = {(eid, rev) for eid, rev in refs if eid and rev is not None}
    with service.sessions() as db:
        records = db.scalars(select(Revision).where(Revision.kind == 'permit',
            tuple_(Revision.entity_id, Revision.revision_no).in_(list(refs)))).all() if refs else []
    lookup = {(r.entity_id, r.revision_no): dict(r.payload, id=r.entity_id, revision_no=r.revision_no,
               source_id=r.source_id, batch_id=r.batch_id) for r in records}
    by_project = defaultdict(dict)
    for link in links:
        picked = link['selected']; key = (picked.get('source_entity_id'), picked.get('source_revision_no'))
        if key in lookup: by_project[link['project_id']][key] = lookup[key]
    return by_project


def target_dongs(service):
    return {str(p.get('sigungu_code') or '') + str(p.get('bjdong_code') or '')
            for ps in selected_permits(service).values() for p in ps.values()}


def reconcile(service):
    """Store all constituent parcels, preserving native permit IDs and source revisions."""
    linked = selected_permits(service)
    permits = {key: p for group in linked.values() for key, p in group.items()}
    native = {p['source_object_id'] for p in permits.values()}
    with service.sessions() as db:
        records = db.scalars(select(Revision).where(Revision.kind == 'permit_parcel',
            Revision.superseded_at.is_(None),
            Revision.payload['parent_permit_native_id'].as_string().in_(sorted(native)))).all() if native else []
    parcels = defaultdict(list)
    for r in records:
        parcels[r.payload['parent_permit_native_id']].append(dict(r.payload, id=r.entity_id,
            revision_no=r.revision_no, source_id=r.source_id))
    recovery = {(r['source_entity_id'], r['source_revision_no']): r for r in service.rows('parcel_evidence')}
    legal = {r['source_object_id'] for k in ('legal_dong','policy_legal_dong') for r in service.rows(k)}
    old = {r['project_id']: r for r in service.rows(KIND)}
    outcomes = Counter(); states = Counter()
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql': db.execute(text('SELECT pg_advisory_xact_lock(1019083)'))
        for project in service.projects():
            pid = project['id']; candidates = []; reasons = set(); source_refs = []
            for key, permit in linked.get(pid, {}).items():
                source_refs.append(dict(id=key[0], revision_no=key[1], native_id=permit['source_object_id']))
                derived = recovery.get(key)
                rows = [permit, *parcels[permit['source_object_id']]]
                if derived: rows.append(derived)
                for row in rows:
                    pnu, reason = compose(row)
                    if pnu and pnu[:10] not in legal: pnu, reason = None, 'LEGAL_CODE_UNVERIFIED'
                    if pnu:
                        candidates.append(dict(pnu=pnu, source_entity_id=row['id'], source_revision_no=row['revision_no'],
                            source_id=row.get('source_id'), permit_entity_id=key[0], permit_revision_no=key[1],
                            native_permit_id=permit['source_object_id'], representative=row.get('representative'),
                            basis='공식 법정동 코드·원천 산 여부·지번 구성; 동일 허가 PK',
                            evidence_url=row.get('evidence_url') or permit.get('evidence_url')))
                    else: reasons.add(reason)
                if not parcels[permit['source_object_id']]: reasons.add('DETAIL_NOT_COLLECTED')
            if not source_refs: reasons.add('PERMIT_LINK_MISSING')
            pnus = sorted({c['pnu'] for c in candidates})
            status = 'CANDIDATE' if pnus else 'MISSING'
            states[status] += 1
            payload = dict(project_id=pid, name=project['name'], region=project['region'], status=status,
                pnus=pnus, candidates=sorted(candidates, key=lambda c:(c['pnu'],c['source_entity_id'],c['source_revision_no'])),
                missing_reasons=sorted(reasons), permit_refs=sorted(source_refs,key=lambda r:(r['id'],r['revision_no'])),
                basis='저장된 인허가 선택을 따라 생성한 필지 후보 · 합필/분필·사업 귀속 확정 전',
                base_date=project['base_date'])
            # No officer decision is overwritten by automatic refresh.
            previous = old.get(pid)
            if previous and previous.get('reviewed'):
                outcomes['preserved'] += 1; continue
            _, result = upsert_revision(db,KIND,'parcel_identity',pid,payload,'parcel_refresh')
            outcomes[result] += 1
    return dict(states=dict(states), revisions=dict(outcomes))
