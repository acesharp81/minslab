import copy
import json
import sqlite3
from app.storage import Store,history_projection


def job(jid='j',created='2026-11-01T00:00:00+00:00'):
    return dict(id=jid,created_at=created,state='COMPLETED',demo=False,metadata={'title':'검수 이력'},runs=[
        dict(id='old',created_at=created,options={'mode':'live','vision_model':'gpt-5.4','analysis_model':'gpt-5.4-mini'},scope='FULL_IMAGE',observation={'objects':[{'id':'o'}]},results=[{'status':'PASS'}],reviews=[]),
        dict(id='latest',created_at=created,options={'mode':'live','vision_model':'gpt-6.1-sol','analysis_model':'gpt-5.4-mini'},results=[{'status':'ERROR'}],reviews=[{'reason':'보류'}])])


def test_legacy_migration_projects_once_without_altering_original_history(tmp_path):
    path=tmp_path/'old.sqlite3';original=job()
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,created TEXT NOT NULL,body TEXT NOT NULL)')
        c.execute('INSERT INTO jobs VALUES(?,?,?)',(original['id'],original['created_at'],json.dumps(original)))
    store=Store(path)
    assert store.get('j')==original
    assert store.summaries()[0]['run_count']==2
    assert store.versions('j')[0]['reusable_observation'] and not store.versions('j')[1]['reusable_observation']
    with store.connect() as c:
        plan=' '.join(str(tuple(row)) for row in c.execute('EXPLAIN QUERY PLAN SELECT summary FROM job_history ORDER BY created DESC,id DESC LIMIT 100'))
        assert 'job_history_created_idx' in plan and 'TEMP B-TREE' not in plan
        assert c.execute('SELECT count(*) FROM job_history_dirty').fetchone()[0]==0


def test_summaries_do_not_read_large_job_bodies_and_preserve_order(tmp_path):
    store=Store(tmp_path/'db');a=job('a');a['runs'][0]['reference_snapshot']=[{'content':'large '*10000}]
    store.save(a);store.save(job('b','2026-11-02T00:00:00+00:00'))
    traces=[];connect=store.connect
    from contextlib import contextmanager
    @contextmanager
    def watched():
        with connect() as c:
            c.set_trace_callback(traces.append);yield c
    store.connect=watched
    rows=store.summaries();assert [r['id'] for r in rows]==['b','a']
    assert len(json.dumps(rows))<1000 and not any('SELECT body' in s or 'SELECT j.body' in s for s in traces)


def test_save_and_direct_sql_writers_refresh_state_versions_and_delete(tmp_path):
    store=Store(tmp_path/'db');j=job();store.save(j)
    j['state']='RUNNING';store.save(j);assert store.active_count()==1 and store.active_jobs()[0]['id']=='j'
    j['state']='COMPLETED';j['metadata']['title']='원시 SQL 수정';j['runs'].append({**j['runs'][0],'id':'third'})
    with store.connect() as c:c.execute('UPDATE jobs SET body=? WHERE id=?',(json.dumps(j),'j'))
    assert store.summaries()[0]['metadata']['title']=='원시 SQL 수정'
    assert len(store.versions('j'))==3 and store.active_count()==0
    with store.connect() as c:c.execute('DELETE FROM jobs WHERE id=?',('j',))
    assert store.summaries()==[] and store.versions('j') is None and not store.exists('j')


def test_latest_and_explicit_version_views_preserve_full_export_data(tmp_path):
    store=Store(tmp_path/'db');j=job();store.save(j)
    latest=store.view('j');assert len(latest['runs'])==1 and latest['runs'][0]['id']=='latest'
    assert latest['run_count']==2 and latest['previous_reusable_run']['id']=='old'
    old=store.view('j','old');assert old['runs']==[j['runs'][0]]
    assert store.get('j')==j and store.view('j','missing') is None and store.view('unknown') is None
    j['runs']=[];store.save(j);assert store.view('j')['runs']==[] and store.versions('j')==[]


def test_history_reuse_eligibility_matches_legacy_and_crop_contract():
    j=job();legacy=copy.deepcopy(j['runs'][0]);legacy.pop('observation');legacy['results']=[{'status':'REVIEW','observation':'저장 관찰','model':'gpt-5.4'}]
    j['runs']=[legacy];assert history_projection(j)[1][0]['reusable_observation']
    legacy['scope']='CROP';assert not history_projection(j)[1][0]['reusable_observation']
