import hashlib
from sqlalchemy import create_engine
from backend.db import Base,Mapping,upsert_revision
from backend.service import HomeService
from scripts import confirm_nonofficial_start_evidence_20261020 as review


def test_confirmed_nonofficial_sources_are_admitted_once_with_observation_bounds(tmp_path,monkeypatch):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine,tmp_path)
    folder=tmp_path/'named-start-deep-20261020/sources';folder.mkdir(parents=True)
    body=b'<p> '+ '상반기 착공 A9 574 A16 A18 1216 A6 A7 1063'.encode() +b'</p>'
    (folder/'etoday-20260812.html').write_bytes(body);monkeypatch.setattr(review,'ARTICLE_SHA',hashlib.sha256(body).hexdigest())
    with service.sessions.begin() as db:
        for group in review.HELD[:3]:
            for pid,(block,units) in zip(group['project_ids'],group['blocks']):
                r,_=upsert_revision(db,'project','test',pid,dict(name=group['name']+block,planned_units=units,base_date='2026-10-20'),'test');db.flush();r.entity_id=pid
                db.add(Mapping(project_id=pid,policy_id='POL_2025_0907',status='CONFIRMED',revision_no=1,basis='approved',evidence_url='https://test'))
            key='named-start-deep-20261020:held:'+group['name']
            upsert_revision(db,'document_evidence','officer',key,dict(name=group['name'],base_date='2026-10-20',facts=[],review_decision='HOLD_OFFICIAL_ACTUAL_SOURCE'),'test')
    first=review.apply(service);second=review.apply(service)
    assert sum(r['units'] for r in first['results'])==2853 and len(first['results'])==5
    assert first['protected_before']==first['protected_after']
    assert all(r['outcome']=='unchanged' for r in second['results'])
    links=service.rows('evidence_bridge');assert len(links)==5
    for link in links:
        assert link['status']=='CONFIRMED' and link['reviewed']
        assert link['review_label'].startswith('담당자 확인 완료 - 비공식 자료:')
        f=link['facts'][0];assert f['date_basis']=='OBSERVED_BY' and f['source_event_date'] is None
        assert f['date']=='2026-06-30' and f['event_period_start']=='2026-01-01'
    docs=service.rows('document_evidence')
    assert all(r['actual_admission_status']=='APPLIED' and not r['official_actual_verified'] for r in docs)
