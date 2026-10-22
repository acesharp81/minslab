"""Append-only assessment rounds. Scores, inputs and HTML are stored together."""
from datetime import datetime
from sqlalchemy import select, text
from .db import IntegrityRound, Audit, MetricSnapshot
from .service import as_utc
from .independent_metrics import digest

# Dedicated to assessment writes; 1019113 is held by the collection worker.
INTEGRITY_WRITE_LOCK = 1019114


def replace_consolidated_round(service, identity, result, html, actor, reason):
    """User-authorized replacement of obsolete R01/R02, preserving an archive.

    The deletion and new registration share one transaction. Any validation
    failure restores the former active list. R00 and its audit never change.
    """
    import json
    from sqlalchemy.orm import sessionmaker
    from .service import HomeService
    obsolete=('HOME-INTEGRITY-R01','HOME-INTEGRITY-R02')
    archive=service.data_dir/'remediation/retired-rounds-20261017'
    archive.mkdir(parents=True,exist_ok=True)
    with service.engine.begin() as connection:
        if service.engine.dialect.name=='postgresql':connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': INTEGRITY_WRITE_LOCK})
        elif service.engine.dialect.name=='sqlite':connection.exec_driver_sql('BEGIN')
        scoped=HomeService(service.engine,service.data_dir)
        scoped.sessions=sessionmaker(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
        with scoped.sessions.begin() as db:
            for key in obsolete:
                old=db.get(IntegrityRound,key)
                if old is None:continue
                if db.scalar(select(IntegrityRound.id).where(IntegrityRound.parent_id==key,IntegrityRound.id.not_in(obsolete))):
                    raise ValueError('교체 대상 외 후속 평가가 있어 성적표를 삭제할 수 없습니다')
                saved=dict(id=old.id,sequence=old.sequence,parent_id=old.parent_id,actor=old.actor,reason=old.reason,
                    snapshot_id=old.snapshot_id,score=old.score,digest=old.digest,result=old.result,report_html=old.report_html)
                path=archive/(old.id+'.json');body=json.dumps(saved,ensure_ascii=False,indent=2)+'\n'
                if path.exists() and path.read_text()!=body:raise ValueError('기존 성적표 보관본 불일치')
                path.write_text(body)
                db.add(Audit(entity_id=old.id,action='DATA_INTEGRITY_ROUND_REPLACED',before=dict(id=old.id,digest=old.digest,sequence=old.sequence),
                    after=dict(actor=actor,reason=reason,requested_change='기존 보완1·2 삭제 후 최초 평가 대비 통합 보완1로 재배치',
                        replacement_id=identity,archive=str(path.relative_to(service.data_dir)),archive_sha256=__import__('hashlib').sha256(body.encode()).hexdigest())))
                db.delete(old)
        return save_round(scoped,identity,1,result,html,actor,reason,snapshot_id=result.get('snapshot_id'),parent_id='HOME-INTEGRITY-R00')


def classification_metrics(cases):
    if any(type(c.get('label')) is not bool or type(c.get('prediction')) is not bool for c in cases):
        raise ValueError('정답과 예측은 검토된 참/거짓 값이어야 합니다')
    tp=sum(c['label'] and c['prediction'] for c in cases)
    fp=sum(not c['label'] and c['prediction'] for c in cases)
    fn=sum(c['label'] and not c['prediction'] for c in cases)
    tn=sum(not c['label'] and not c['prediction'] for c in cases)
    ratio=lambda n,d:100*n/d if d else None
    return dict(sample_size=len(cases),tp=tp,fp=fp,fn=fn,tn=tn,accuracy=ratio(tp+tn,len(cases)),
                precision=ratio(tp,tp+fp),recall=ratio(tp,tp+fn),f1=ratio(2*tp,2*tp+fp+fn),
                platform_accuracy=None,platform_accuracy_reason='전체 사건의 대표 정답 모집단 미구축 · 목적 표본의 자동 연결 분류 성능')


def amend_round(service, identity, expected_digest, result, html, actor, reason):
    """Explicitly requested same-round update; archive old content and validate atomically.

    Administrative use only. Normal save_round remains immutable. Baselines and
    rounds already referenced by later assessments cannot be amended here.
    """
    import json
    import hashlib
    from sqlalchemy.orm import sessionmaker
    from .service import HomeService
    with service.engine.begin() as connection:
        if service.engine.dialect.name=='postgresql':connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': INTEGRITY_WRITE_LOCK})
        elif service.engine.dialect.name=='sqlite':connection.exec_driver_sql('BEGIN')
        scoped=HomeService(service.engine,service.data_dir)
        scoped.sessions=sessionmaker(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
        with scoped.sessions.begin() as db:
            old=db.get(IntegrityRound,identity)
            if old is None or old.sequence==0:raise ValueError('기준 성적표는 수정할 수 없습니다')
            if old.digest!=expected_digest:raise ValueError('성적표가 변경되었습니다. 수정 전 판본을 다시 확인하세요')
            if db.scalar(select(IntegrityRound.id).where(IntegrityRound.parent_id==identity)):
                raise ValueError('후속 평가가 참조하는 성적표는 수정할 수 없습니다')
            saved=dict(id=old.id,sequence=old.sequence,parent_id=old.parent_id,actor=old.actor,reason=old.reason,
                snapshot_id=old.snapshot_id,score=old.score,digest=old.digest,result=old.result,report_html=old.report_html,
                created_at=as_utc(old.created_at).isoformat())
            body=json.dumps(saved,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
            folder=service.data_dir/'remediation/round-amendments';folder.mkdir(parents=True,exist_ok=True)
            path=folder/(old.digest+'.json')
            if path.exists() and path.read_text()!=body:raise ValueError('성적표 수정 전 보관본 불일치')
            path.write_text(body)
            sequence,parent_id=old.sequence,old.parent_id
            db.add(Audit(entity_id=identity,action='DATA_INTEGRITY_ROUND_AMENDED',
                before=dict(digest=old.digest,score=old.score),after=dict(actor=actor,reason=reason,
                    requested_change=f'새 회차 없이 기존 보완{old.sequence} 갱신',archive=str(path.relative_to(service.data_dir)),
                    archive_sha256=hashlib.sha256(body.encode()).hexdigest())))
            db.delete(old)
        save_round(scoped,identity,sequence,result,html,actor,reason,snapshot_id=result.get('snapshot_id'),parent_id=parent_id)
    return identity


def save_round(service, identity, sequence, result, html, actor, reason, snapshot_id=None, parent_id=None):
    if not actor.strip() or not reason.strip() or not html.startswith('<!doctype html>'):
        raise ValueError('담당자·사유와 완성된 HTML 성적표가 필요합니다')
    categories=result.get('categories',[])
    items=[i for c in categories for i in c['items']]
    if len(items)!=40 or len({i['id'] for i in items})!=40 or sum(i['weight'] for i in items)!=100:
        raise ValueError('기준과 같은 40개 평가항목·100점 배점이 필요합니다')
    if sequence and any(not i.get('change_comment') or 'previous_score' not in i for i in items):
        raise ValueError('후속 평가의 모든 항목에 이전 점수와 개선 코멘트가 필요합니다')
    if any(not isinstance(i['score'],(int,float)) or not 0<=i['score']<=i['weight'] for i in items):
        raise ValueError('취득 점수는 배점 이내여야 합니다')
    if abs(sum(i['score'] for i in items)-float(result.get('total_score',sum(i['score'] for i in items))))>0.000001:
        raise ValueError('합산 점수가 항목 점수와 다릅니다')
    checksum=digest(dict(result=result,html=html,actor=actor,reason=reason,snapshot_id=snapshot_id,parent_id=parent_id))
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': INTEGRITY_WRITE_LOCK})
        old=db.get(IntegrityRound,identity)
        if old:
            if old.digest!=checksum:raise ValueError('발행 성적표는 변경할 수 없습니다. 새 보완회차로 등록하세요')
            return identity
        if sequence and (parent_id is None or (parent:=db.get(IntegrityRound,parent_id)) is None or parent.sequence>=sequence):
            raise ValueError('이전 회차의 연결이 필요합니다')
        if sequence:
            previous={i['id']:i for c in parent.result['categories'] for i in c['items']}
            if any(i['id'] not in previous or i['weight']!=previous[i['id']]['weight'] or abs(i['previous_score']-previous[i['id']]['score'])>0.000001 for i in items):
                raise ValueError('이전 회차의 항목·배점·점수와 일치해야 합니다')
        if snapshot_id and db.get(MetricSnapshot,snapshot_id) is None:raise ValueError('산출 기준본이 없습니다')
        db.add(IntegrityRound(id=identity,sequence=sequence,parent_id=parent_id,actor=actor,reason=reason,
                             snapshot_id=snapshot_id,score=str(result['display_score']),result=result,report_html=html,digest=checksum))
        db.add(Audit(entity_id=identity,action='DATA_INTEGRITY_ROUND',before={},after=dict(actor=actor,reason=reason,
                     sequence=sequence,parent_id=parent_id,snapshot_id=snapshot_id,score=result['display_score'],digest=checksum)))
    return identity


def rounds(service):
    with service.sessions() as db:
        rows=db.execute(select(IntegrityRound.id,IntegrityRound.sequence,IntegrityRound.parent_id,IntegrityRound.created_at,
                             IntegrityRound.actor,IntegrityRound.reason,IntegrityRound.score,IntegrityRound.snapshot_id,IntegrityRound.digest)
                        .order_by(IntegrityRound.sequence.desc())).mappings().all()
        return dict(items=[dict(r,created_at=as_utc(r['created_at']).isoformat()) for r in rows],
                    note='회차별 점수·근거·코멘트를 발행 시점 그대로 보존합니다.')


def get_round(service, identity, html=False):
    with service.sessions() as db:
        row=db.get(IntegrityRound,identity)
        if row is None:raise ValueError('성적표가 없습니다')
        checksum=digest(dict(result=row.result,html=row.report_html,actor=row.actor,reason=row.reason,
                             snapshot_id=row.snapshot_id,parent_id=row.parent_id))
        if checksum!=row.digest or row.score!=str(row.result['display_score']):raise ValueError('성적표 무결성 검사 실패')
        if html:return row.report_html
        return dict(id=row.id,sequence=row.sequence,parent_id=row.parent_id,actor=row.actor,reason=row.reason,
                    snapshot_id=row.snapshot_id,created_at=as_utc(row.created_at).isoformat(),digest=row.digest,result=row.result)
