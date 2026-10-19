import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from backend.db import Base,Revision,upsert_revision,upsert_raw_revisions


@pytest.fixture
def engine():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def payload(n):
    return dict(name='사업'+str(n),units=n,source_date='2026-01-02',
                dates={'원천 허가일 (apprvDay)':'2025-12-01'})


def test_batch_and_single_writes_have_identical_history_and_noop_behavior(engine):
    with Session(engine) as s,s.begin():
        for method,source in [('single','a'),('batch','b')]:
            original=[('permit',str(i),payload(i)) for i in range(7)]
            revised=[('permit',str(i),payload(i+10 if i%2 else i)) for i in range(8)]
            write=lambda records,bid: ([upsert_revision(s,k,source,key,p,bid) for k,key,p in records]
                if method=='single' else list(upsert_raw_revisions(s,source,records,bid,chunk_size=3)))
            assert [o for _,o in write(original,'first')]==['new']*7
            outcomes=[o for _,o in write(revised,'second')]
            assert outcomes==['unchanged','changed','unchanged','changed','unchanged','changed','unchanged','new']
            assert all(o=='unchanged' for _,o in write(revised,'third'))
    with Session(engine) as s:
        rows=s.scalars(select(Revision)).all();byid={r.id:r for r in rows}
        def canonical(source):
            return sorted((r.payload['name'],r.revision_no,r.payload_hash,r.superseded_at is not None,
                           r.sample_event_day,byid[r.previous_id].payload_hash if r.previous_id else None)
                          for r in rows if r.source_id==source)
        assert canonical('a')==canonical('b')


def test_duplicate_keys_keep_sequential_history(engine):
    with Session(engine) as s,s.begin():
        result=list(upsert_raw_revisions(s,'source',[('register','same',payload(1)),
            ('register','same',payload(2)),('register','same',payload(2))],'batch'))
        assert [o for _,o in result]==['new','changed','unchanged']
        assert result[-1][0].revision_no==2
        assert result[-1][0].previous_id==result[0][0].id


def test_later_chunk_failure_rolls_back_prior_chunks_and_replacements(engine):
    with Session(engine) as s,s.begin():upsert_revision(s,'register','source','old',payload(1),'first')
    with pytest.raises(TypeError):
        with Session(engine) as s,s.begin():
            list(upsert_raw_revisions(s,'source',[('register','old',payload(2)),
                ('register','bad',dict(value=object()))],'broken',chunk_size=1))
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Revision))==1
        old=s.scalar(select(Revision));assert old.superseded_at is None and old.payload['units']==1


def test_project_side_effect_records_cannot_use_raw_batch(engine):
    with Session(engine) as s,pytest.raises(ValueError):
        list(upsert_raw_revisions(s,'source',[('project','one',payload(1))],'batch'))
