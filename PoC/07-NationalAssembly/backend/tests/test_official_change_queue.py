import os
import uuid
from datetime import datetime, timedelta, timezone
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from app.db.official_change_report_repository import OfficialChangeReportRepository


def test_old_missing_report_is_not_starved_by_twenty_completed_reports():
    dsn=os.environ.get('SHARED_TEST_DATABASE_URL')
    if not dsn: pytest.skip('Isolated PostgreSQL connection required')
    dsn=dsn.replace('postgresql+psycopg://','postgresql://')
    name='test_official_queue_'+uuid.uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        with psycopg.connect(dsn,options=f'-c search_path={name},public') as c:
            c.execute('CREATE TABLE live_broadcasts(id uuid,title text)')
            c.execute('CREATE TABLE meeting_briefs(id uuid,brief jsonb,generated_at timestamptz)')
            c.execute('CREATE TABLE meeting_official_integrations(id uuid,broadcast_id uuid,meeting_brief_id uuid,integrated_brief jsonb,changes jsonb,speaker_stats jsonb,status text,usage_metadata jsonb,generated_at timestamptz)')
            c.execute('CREATE TABLE meeting_official_change_reports(LIKE public.meeting_official_change_reports INCLUDING ALL)')
            now=datetime.now(timezone.utc); repo=OfficialChangeReportRepository(c); ids=[]
            for n in range(25):
                bid,mid,iid=uuid.uuid4(),uuid.uuid4(),uuid.uuid4();ids.append(iid);title=f'회의 {n}'
                c.execute('INSERT INTO live_broadcasts VALUES(%s,%s)',(bid,title))
                c.execute("INSERT INTO meeting_briefs VALUES(%s,'{}',%s)",(mid,now-timedelta(days=n)))
                c.execute("INSERT INTO meeting_official_integrations VALUES(%s,%s,%s,'{}','[]','{}','READY','{}',%s)",(iid,bid,mid,now-timedelta(hours=1)))
                if n<24:
                    _,snapshot,digest=repo._snapshot((iid,title,{}, {},[],{}))
                    c.execute("INSERT INTO meeting_official_change_reports(id,integration_id,input_hash,input_snapshot,status,provider,model,prompt_version,updated_at) VALUES(%s,%s,%s,%s,'READY','openai','fixture','v1',%s)",(uuid.uuid4(),iid,digest,Jsonb(snapshot),now))
            assert repo.sync_pending(provider='openai',model='fixture',prompt_version='v1',limit=20)==1
            assert c.execute('SELECT status FROM meeting_official_change_reports WHERE integration_id=%s',(ids[-1],)).fetchone()[0]=='PENDING'
            assert repo.sync_pending(provider='openai',model='fixture',prompt_version='v1',limit=20)==0
            # A semantically unchanged integration refresh is acknowledged once.
            c.execute("UPDATE meeting_official_change_reports SET updated_at=%s WHERE integration_id=%s",(now-timedelta(hours=2),ids[0]))
            assert repo.sync_pending(provider='openai',model='fixture',prompt_version='v1',limit=20)==0
            assert c.execute('SELECT status,updated_at>%s FROM meeting_official_change_reports WHERE integration_id=%s',(now-timedelta(hours=1),ids[0])).fetchone()==('READY',True)
    finally:
        with psycopg.connect(dsn,autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
