from datetime import date
import hashlib
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine,select
from backend.db import Base,Revision,upsert_revision
from backend.service import HomeService
from backend import attachment_text as a


def test_archived_hash_and_path_are_verified_before_extraction(tmp_path):
    (tmp_path/'raw').mkdir();p=tmp_path/'raw/a.hwp';p.write_bytes(b'old')
    item=dict(original_file='raw/a.hwp',original_sha256=hashlib.sha256(b'old').hexdigest())
    with patch.object(a,'extract',return_value={'text':'safe'}) as extract:
        assert a.recover_item(item,tmp_path)['text']=='safe'
        p.write_bytes(b'new')
        with pytest.raises(ValueError,match='HASH'):a.recover_item(item,tmp_path)
        with pytest.raises(ValueError,match='PATH'):a.recover_item(dict(item,original_file='../outside'),tmp_path)
        assert extract.call_count==1


def test_ocr_is_partial_and_requires_review(tmp_path):
    def run(name,args,*unused,**kwargs):
        if name=='pdftoppm':
            assert args[args.index('-l')+1]=='4'
            Path(str(args[-1])+'-1.png').write_bytes(b'x')
            return ''
        return '주택 사업의 스캔 이미지에서 추출된 문장입니다. 수치와 사업 연결은 별도 검토가 필요합니다.'
    with patch.object(a,'run_tool',side_effect=run):
        result=a.extract(tmp_path/'in.pdf',b'%PDF')
    assert result['status']=='OCR_REVIEW_REQUIRED' and result['text_review_required']
    assert result['text_scope']=='FIRST_4_PAGES_MAX'
    payload={'attachments':[dict(result,original_file='raw/a.pdf')]}
    a.refresh_flags(payload)
    assert payload['attachment_complete'] and not payload['text_extraction_complete']
    assert payload['ocr_review_required']


def test_recovery_budget_retries_and_candidate_facts_preserved(tmp_path):
    e=create_engine('sqlite://');Base.metadata.create_all(e);service=HomeService(e,tmp_path)
    try:
        with service.sessions.begin() as db:
            for n in range(6):
                upsert_revision(db,'document_evidence','eum_housing_notices',str(n),
                    dict(source_object_id=str(n),facts=[],units=None,attachments=[dict(status='LEGACY_HWP_ARCHIVED',original_file=f'raw/{n}.hwp',original_sha256=str(n))]),'test')
        output=[]
        with patch.object(a,'recover_item',side_effect=ValueError('EMPTY_TEXT')):
            stats=a.recover_batch(service,output,limit=4)
        assert stats['text_recovery_attempted']==4 and len(output)==4
        assert stats['text_recovery_remaining']==2
        assert stats['text_recovered']==0 and len(stats['text_recovery_failures'])==4
        for _,_,p in output:
            assert p['facts']==[] and p['units'] is None and not p['text_extraction_complete']
            assert p['attachment_complete'] and not a.pending(p['attachments'][0])
    finally:e.dispose()


def test_verified_text_cache_survives_redownload_but_new_bytes_reprocess(tmp_path):
    e=create_engine('sqlite://');Base.metadata.create_all(e);service=HomeService(e,tmp_path)
    old=dict(status='OCR_REVIEW_REQUIRED',text='old OCR',original_file='raw/old.pdf',original_sha256='same',text_extractor_version=a.VERSION,text_review_required=True)
    try:
        with service.sessions.begin() as db:
            upsert_revision(db,'document_evidence','eum_housing_notices','one',dict(source_object_id='one',facts=[],attachments=[old]),'old')
        fresh=dict(source_object_id='one',facts=[],attachments=[dict(status='OCR_REQUIRED',original_file='raw/new.pdf',original_sha256='same')])
        output=[('document_evidence','one',fresh)]
        with patch.object(a,'recover_item') as recover:stats=a.recover_batch(service,output)
        assert not recover.called and fresh['attachments'][0]['text']=='old OCR'
        assert fresh['attachments'][0]['original_file']=='raw/new.pdf'
        assert fresh['ocr_review_required'] and not fresh['text_extraction_complete']
        fresh['attachments'][0]=dict(status='LEGACY_HWP_ARCHIVED',original_file='raw/new.hwp',original_sha256='different')
        with patch.object(a,'recover_item',return_value=dict(status='TEXT_EXTRACTED',text='new HWP')) as recover:
            a.recover_batch(service,output)
        assert recover.called and fresh['attachments'][0]['text']=='new HWP'
    finally:e.dispose()


def test_map_images_are_not_treated_as_machine_verified_text():
    assert not a.pending(dict(original_file='raw/map.png',path='/지형도면.png',status='IMAGE_ARCHIVED'))
