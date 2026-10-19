import copy
from datetime import date
import pytest
from sqlalchemy import create_engine, select, func
from backend.db import Base, Revision, Mapping, ProgramMapping, upsert_revision
from backend.service import HomeService
from backend.lh_policy_followup import SITES, REVIEWED_UNITS, POLICY, parse_tender, physical_key, admit_reviewed
from backend.roadmap import source_events


def pages():
    parts=['2025.10.30. 주택공급 확대방안(25.9.7) LH직접시행']
    for i,(s,units) in enumerate(zip(SITES,REVIEWED_UNITS)):
        parts.append(f'\n {i+1}. {s[0]} {s[1][0]}-{s[1][1:]}BL\n 규모/건설호수\n{units}호\n * (사업추진일정) 주택건설공사 착공(`26년 06월 예정)\n')
    return ['\n'.join(parts)]


def test_parse_plan_not_actual_and_reject_missing_scope():
    rows=parse_tender(pages())
    assert len(rows)==8 and sum(r['units'] for r in rows)==5162
    assert all(r['facts'][0]['kind']=='PLAN' and r['facts'][0]['date']=='2026-06' for r in rows)
    with pytest.raises(ValueError):parse_tender([pages()[0].replace('8. 수원당수2 A-3BL','8. 수원당수 A-3BL')])
    with pytest.raises(ValueError):parse_tender([pages()[0].replace('25.9.7','25.1.10')])
    with pytest.raises(ValueError):parse_tender([pages()[0].replace('06월 예정','07월 예정',1)])


def test_quantity_components_and_native_block():
    good=pages()[0].replace('510호','426호 84호 510호',1)
    assert parse_tender([good])[0]['units']==510
    with pytest.raises(ValueError):parse_tender([good.replace('426호','425호',1)])
    assert physical_key(dict(region='인천광역시',district='인천검단',block='AA13-2',name='AA13-1BL 및 AA13-2BL 공사'))==('인천광역시','인천검단','AA13-2')
    assert physical_key(dict(region='경기도',district='수원당수2',block='A1',name='수원당수2 A1'))!=physical_key(dict(region='경기도',district='수원당수',block='A1',name='수원당수 A1'))


@pytest.fixture
def service(tmp_path):
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    s=HomeService(engine,tmp_path)
    with s.sessions.begin() as db:
        for i,name in enumerate(['LH 직접시행 전환·토지이용 효율화']):
            db.add(ProgramMapping(id='PG'+str(i),name=name,seed_policy_id=POLICY,policy_id=POLICY,status='CONFIRMED',basis='test',evidence_url='https://www.lh.or.kr'))
        for row in parse_tender(pages()):
            row['original_sha256']='a'*64
            upsert_revision(db,'agency_plan','lh_policy_followup',row['source_object_id'],row,'test')
    return s


def test_admission_atomic_and_idempotent(service):
    assert all(p['result']=='proposed' for p in admit_reviewed(service)['projects'])
    with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Mapping))==0
    result=admit_reviewed(service,True)
    assert len(result['projects'])==8 and all(p['result']=='added' for p in result['projects'])
    assert all(p['program']=='LH 직접시행 전환·토지이용 효율화' for p in result['projects'])
    assert all(p['result']=='existing_preserved' for p in admit_reviewed(service,True)['projects'])
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Mapping))==8
        projects=db.scalars(select(Revision).where(Revision.kind=='project')).all()
        assert all(not p.payload.get('start_actual_date') for p in projects)
        events=source_events(dict(projects[0].payload,source_id='lh_policy_followup'),date(2026,10,19))
        assert len(events)==1 and events[0]['due_date']=='2026-06-30' and not events[0]['actual_verified']


def test_collision_preflight_leaves_no_partial_writes(service):
    with service.sessions.begin() as db:
        upsert_revision(db,'project','other','existing',dict(name='수원당수2 A3',region='경기도',district='수원당수2',block='A3',base_date='2026-01-01'), 'test')
    with pytest.raises(ValueError):admit_reviewed(service,True)
    with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Mapping))==0


def test_changed_source_requires_new_review(service):
    with service.sessions.begin() as db:
        r=db.scalars(select(Revision).where(Revision.kind=='agency_plan')).first()
        payload=copy.deepcopy(r.payload);payload['units']+=1
        upsert_revision(db,'agency_plan','lh_policy_followup',payload['source_object_id'],payload,'changed')
    with pytest.raises(ValueError):admit_reviewed(service,True)
    with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Mapping))==0
