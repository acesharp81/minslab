from datetime import date,datetime,timezone
import hashlib,json
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine,select,func
from backend import publication_watch as watch
from backend.sources import SOURCES
from backend.db import Base,Revision,CollectionJob,upsert_revision
from backend.service import HomeService
from backend.collection_jobs import enqueue,run_next
from backend.source_operations import operations

ROOT=Path(__file__).parent/'fixtures/publication_watch'
SOURCES_BY_ID={s['id']:s for s in SOURCES}

@pytest.mark.parametrize('sid,file', [('lh_press_watch','lh.html'),('ih_press_watch','ih.html'),('seoul_press_watch','seoul.xml'),('newsis_housing_watch','newsis.xml')])
def test_live_listing_samples_are_candidates_only(sid,file):
    class Fetcher:
        def get(self,url,*args):return (ROOT/('newsis-met.xml' if url.endswith('met.xml') else file)).read_bytes()
    with patch.object(watch,'today',return_value=date(2026,10,26)):
        records,stats=watch.collect(SOURCES_BY_ID[sid],Fetcher())
    assert records and stats['provided']>=len(records)
    assert not stats['complete_population'] and stats['actual_events_created']==0
    assert all(p['facts']==[] and p['units'] is None and p['status']=='REVIEW' for _,_,p in records)
    assert all('content_text' not in p and 'original_file' not in p for _,_,p in records)
    assert all(p['authority']==('NONOFFICIAL' if sid.startswith('newsis') else 'OFFICIAL') for _,_,p in records)
    assert len({key for _,key,_ in records})==len(records)


def test_missing_date_untrusted_link_and_blocked_page_fail():
    source=SOURCES_BY_ID['newsis_housing_watch']
    for body in [b'<html>blocked</html>',b'<!DOCTYPE rss><rss><channel/></rss>',
                 b'<rss><channel><item><title>x</title><link>https://attacker.test/</link><pubDate>2026-10-26</pubDate></item></channel></rss>',
                 b'<rss><channel><item><title>x</title><link>https://newsis.com/1</link></item></channel></rss>']:
        with pytest.raises(ValueError):watch.rss_rows(body,source)
    assert not watch.housing_title('한국토지주택공사(LH), 금융 협약 체결')
    assert watch.housing_title('한국토지주택공사(LH), 시흥거모 공공분양주택 공급')


@pytest.mark.parametrize('source_id', ['newsis_housing_watch', 'sh_notice_watch', 'molit_press_watch', 'opm_press_watch'])
def test_discovery_job_never_enters_link_or_snapshot(source_id):
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e)
    try:
        jid=enqueue(s,source_id,force=True)
        with patch.object(s,'collect_one',return_value={'status':'SUCCESS'}):
            result=run_next(s,'LATEST')
        assert result['status']=='SUCCESS' and result['next_stage'] is None
        with s.sessions() as db:
            job=db.get(CollectionJob,jid)
            assert set(job.result)=={'COLLECT'} and job.status=='SUCCESS'
    finally:e.dispose()


def test_lh_dynamic_html_does_not_create_fake_fact_revisions():
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e)
    original=dict(source_object_id='test',original_file='raw/old.html',original_sha256='a',facts=[{'units':10}],source_date='2026-10-23')
    try:
        with s.sessions.begin() as db:
            old,_=upsert_revision(db,'document_evidence','lh_notice_detail','test',original,'one')
            newer=dict(original,original_file='raw/new.html',original_sha256='b')
            same,state=upsert_revision(db,'document_evidence','lh_notice_detail','test',newer,'two')
            assert state=='unchanged' and same.id==old.id and same.payload==original
            assert same.payload_hash==hashlib.sha256(json.dumps(original,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            updated,state=upsert_revision(db,'document_evidence','lh_notice_detail','test',dict(newer,facts=[{'units':11}]),'three')
            assert state=='changed' and updated.revision_no==2
            _,state=upsert_revision(db,'document_evidence','lh_notice_detail','test',dict(updated.payload,source_date='2026-10-24'),'four')
            assert state=='changed'
            upsert_revision(db,'document_evidence','other','test',original,'one')
            _,state=upsert_revision(db,'document_evidence','other','test',newer,'two')
            assert state=='changed'
    finally:e.dispose()


def test_live_worker_heartbeat_overrides_api_scheduler_disabled(tmp_path,monkeypatch):
    monkeypatch.setenv('POC10_AUTO_COLLECT','false')
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e,tmp_path)
    try:
        (tmp_path/'runtime').mkdir()
        (tmp_path/'runtime/collection-worker-health.json').write_text(json.dumps(dict(checked_at=datetime.now(timezone.utc).isoformat(),running_threads=['home-collector'])))
        source=next(v for v in s.sources() if v['id']=='lh_press_watch')
        assert source['operations']['mode']=='자동 수집'
        assert source['operations']['frequency']=='1시간마다'
        assert operations(SOURCES_BY_ID['lh_press_watch'])['mode']=='자동 수집 일시 중지'
    finally:e.dispose()


def test_new_badge_does_not_create_article_revision():
    source=SOURCES_BY_ID['lh_press_watch']
    body=(ROOT/'lh.html').read_bytes()
    rows=watch.board_rows(body,source)
    assert not any(r['name'].startswith('새글') for r in rows)
    assert rows==watch.board_rows(body.replace('새글'.encode(),b''),source)


def test_sh_publication_date_is_not_original_notice_date_and_records_are_review_only():
    class Fetcher:
        def get(self,url,*args):
            group='sale' if 'm_244/' in url else 'rental' if 'm_247/' in url else 'movein'
            return (ROOT/f'sh-{group}.html').read_bytes()
    with patch.object(watch,'today',return_value=date(2026,10,28)):
        records,stats=watch.collect(SOURCES_BY_ID['sh_notice_watch'],Fetcher())
    assert len(records)==19
    assert len({key for _,key,_ in records})==19
    item=next(p for _,key,p in records if key=='312294')
    assert '2026.04.27' in item['name'] and item['source_date']=='2026-10-27'
    assert item['evidence_url'].endswith('view.do?seq=312294')
    assert all(p['authority']=='OFFICIAL' and p['facts']==[] and p['units'] is None and p['status']=='REVIEW' for _,_,p in records)
    assert stats['actual_events_created']==0 and not stats['complete_population']


def test_sh_invalid_listing_cannot_be_reported_as_successful_empty_collection():
    for body in [b'<html>Access denied</html>',
                 b'<tr><td><a onclick="getDetailView(\'123\')">2026-10-27 title</a></td></tr>']:
        with pytest.raises(ValueError):watch.sh_board_rows(body)


@pytest.mark.parametrize('sid,file,key,day', [
    ('molit_press_watch','molit-press.html','95092532','2026-10-28'),
    ('opm_press_watch','opm-list.html','163970','2026-10-27')])
def test_government_board_real_rows_dates_and_overlap(sid,file,key,day):
    body=(ROOT/file).read_bytes();source=SOURCES_BY_ID[sid]
    class Fetcher:
        def get(self,*args):return body
    with patch.object(watch,'today',return_value=date(2026,10,29)):
        records,stats=watch.collect(source,Fetcher())
    p=next(p for _,k,p in records if k==key)
    assert p['source_date']==day and p['facts']==[] and p['units'] is None
    assert p['authority']=='OFFICIAL'
    assert len({k for _,k,_ in records})==len(records)
    assert stats['actual_events_created']==0 and not stats['complete_population']
    with pytest.raises(ValueError):watch.government_board_rows(b'<html>blocked</html>',source)
    with pytest.raises(ValueError):watch.government_board_rows(body.replace(day.encode(),b'unknown').replace(day.replace('-','.').encode(),b'unknown'),source)
