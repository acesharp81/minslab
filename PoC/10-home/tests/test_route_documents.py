"""Source-boundary regression tests for the newly connected official documents."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import patch
import httpx
import pytest
from backend import route_documents as routes
from backend.collectors import Fetcher

EVIDENCE=Path(__file__).resolve().parent/'fixtures/route_documents'


def test_real_hwpx_extracts_text_and_tables():
    text,tables=routes.hwpx_document((EVIDENCE/'lh-department-plan-3.hwpx').read_bytes())
    assert '2026' in text and len(text)>10000 and len(tables)>30
    assert any('주택' in str(table) for table in tables)
    with pytest.raises(ValueError):routes.hwpx_document(b'x'*15_000_001)


def test_real_eum_regional_filter_and_notice_identity():
    body=(EVIDENCE/'eum-incheon.html').read_bytes()
    rows=routes.eum_list(body,'2800000000')
    assert len(rows)==50 and all(r['region']=='인천광역시' for r in rows)
    assert len({r['source_object_id'] for r in rows})==50
    with pytest.raises(ValueError,match='지역 필터'):routes.eum_list(body,'1100000000')
    p=routes.eum_detail((EVIDENCE/'eum-detail.html').read_bytes(),rows[0])
    assert p['attachments'] and p['facts']==[] and p['units'] is None
    with pytest.raises(ValueError,match='번호/일자'):
        routes.eum_detail(b'<html>access denied</html>',rows[0])


def test_legacy_download_query_is_not_reencoded(tmp_path):
    fetcher=Fetcher('eum_housing_notices',tmp_path)
    url='https://www.eum.go.kr/web/FileDownload.do?'+urlencode({'file':'/고시.pdf'},encoding='cp949')
    def response(request):
        assert str(request.url)==url
        return httpx.Response(200,content=b'%PDF'+b'x'*100)
    fetcher.client.close();fetcher.client=httpx.Client(transport=httpx.MockTransport(response))
    try:
        assert fetcher.get(url,'pdf').startswith(b'%PDF')
        assert fetcher.manifest[-1]['url']==url
    finally:fetcher.close()


def test_download_error_is_pending_not_success():
    class Fake:
        manifest=[]
        def get(self,*args):return b'<html>failed download</html>'
    p={'attachments':[dict(url='https://www.eum.go.kr/web/FileDownload.do',path='/고시.pdf')]}
    result=routes.eum_attachments(p,Fake())
    assert not result['attachment_complete']
    assert result['attachments'][0]['status']=='DOWNLOAD_FAILED'


def test_real_pdf_attachment_is_archived_and_extracted():
    class Fake:
        manifest=[dict(file='eum_housing_notices/test.pdf')]
        def get(self,*args):return (EVIDENCE/'eum-attachment.pdf').read_bytes()
    p={'attachments':[dict(url='https://www.eum.go.kr/web/FileDownload.do',path='/고시.pdf')]}
    result=routes.eum_attachments(p,Fake())
    assert result['attachment_complete'] and result['attachments'][0]['status']=='TEXT_EXTRACTED'
    assert result['attachments'][0]['text'] and result['attachments'][0]['original_sha256']


def test_detail_backlog_prevents_complete_and_failures_retry():
    rows=[dict(source_object_id=str(i),name='주택 고시',notice_no=str(i),notice_date='2026-10-01',
               housing_candidate=True,evidence_url='https://www.eum.go.kr/test',regions=['서울특별시']) for i in range(16)]
    service=SimpleNamespace(latest_collection_stats=lambda _: {},rows=lambda _: [])
    class Fake:
        manifest=[dict(file='eum_housing_notices/test.html')]
        def get(self,*args,**kwargs):return b'test'
    with patch.object(routes,'eum_list',return_value=rows),patch.object(routes,'eum_detail',side_effect=lambda body,row:dict(row,attachments=[],facts=[])):
        output,stats=routes.collect_eum({'id':'eum_housing_notices'},Fake(),service)
    assert len([r for r in output if r[0]=='notice_catalogue'])==16
    assert stats['details_fetched']==15 and stats['detail_remaining']==1
    assert not stats['complete_query'] and stats['backfill_pending']
    assert stats['actual_events_created']==0
    service.latest_collection_stats=lambda _:stats
    service.rows=lambda _:[dict(r,source_id='eum_housing_notices') for r in rows]
    with patch.object(routes,'eum_list',return_value=rows),patch.object(routes,'eum_detail',side_effect=ValueError('failure')):
        _,failed=routes.collect_eum({'id':'eum_housing_notices'},Fake(),service)
    assert failed['detail_remaining']==1 and failed['failures'] and not failed['complete_query']


def test_empty_filtered_list_is_not_unconditionally_successful():
    with pytest.raises(ValueError):routes.eum_list(b'<html>login</html>','2800000000')


def test_pdf_resource_failure_preserves_original_and_marks_text_pending():
    import subprocess
    class Fake:
        manifest=[dict(file='eum_housing_notices/test.pdf')]
        def get(self,*args):return b'%PDF'+b'x'*100
    p={'attachments':[dict(url='https://www.eum.go.kr/web/FileDownload.do',path='/고시.pdf')]}
    with patch.object(routes,'pdf_text_bounded',side_effect=subprocess.TimeoutExpired('parser',20)):
        result=routes.eum_attachments(p,Fake())
    assert result['attachment_complete'] and not result['text_extraction_complete']
    assert result['attachments'][0]['status']=='ARCHIVED_TEXT_PENDING'
    assert result['attachments'][0]['original_file']


def test_official_notice_map_images_are_archived_without_claiming_text():
    class Fake:
        manifest=[dict(file='eum_housing_notices/map.png')]
        def get(self,*args):return b'\x89PNG\r\n\x1a\n'+b'x'*100
    p={'attachments':[dict(url='https://www.eum.go.kr/web/FileDownload.do',path='/결정도.png')]}
    out=routes.eum_attachments(p,Fake())
    assert out['attachment_complete'] and not out['text_extraction_complete']
    assert out['attachments'][0]['status']=='IMAGE_ARCHIVED'


def test_eum_whole_province_uses_prefix_and_resets_old_checkpoints():
    calls=[]
    class Fake:
        def get(self, url, **kwargs):
            calls.append(kwargs['params'])
            return b'empty'
    old=dict(region_checkpoints={c:dict(complete_window=True,next_page=99,revisit_page=55) for c in routes.REGIONS})
    service=SimpleNamespace(latest_collection_stats=lambda _:old,rows=lambda _:[])
    with patch.object(routes,'eum_list',return_value=[]):
        _,stats=routes.collect_eum({'id':'eum_housing_notices'},Fake(),service)
    assert {p['selSggCd'] for p in calls}=={'11','28','41'}
    assert all(p['pageNo']==1 for p in calls)
    assert stats['scope_version']==2
