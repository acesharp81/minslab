"""Bounded text recovery from verified archived EUM attachments; no stage facts."""
import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import timedelta
from .api_samples import today

VERSION = 1
# A separate process applies limits before launching native document tools.
LIMITER = '''import os,resource,sys
resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024*1024,20*1024*1024))
os.execv(sys.argv[1],sys.argv[1:])
'''

def run_tool(name, args, timeout=25):
    executable=shutil.which(name)
    if not executable:raise RuntimeError('TOOL_UNAVAILABLE: '+name)
    result=subprocess.run([sys.executable,'-c',LIMITER,executable,*map(str,args)],
                          capture_output=True,timeout=timeout,env=dict(os.environ,OMP_THREAD_LIMIT='1'))
    if result.returncode:raise ValueError('TOOL_FORMAT_OR_RESOURCE_LIMIT: '+name)
    if len(result.stdout)>2_000_000:raise ValueError('TEXT_SIZE_LIMIT')
    return result.stdout.decode('utf-8',errors='replace')

def extract(path, body):
    if len(body)>15_000_000:raise ValueError('FILE_SIZE_LIMIT')
    if body.startswith(b'\xd0\xcf\x11\xe0'):
        text=run_tool('hwp5txt',[path])
        if len(text.strip())<30:raise ValueError('EMPTY_TEXT')
        return dict(text=text,status='TEXT_EXTRACTED',text_method='HWP5',text_scope='FULL_DOCUMENT')
    # OCR is a review aid, never a verified transcription or numeric fact.
    with tempfile.TemporaryDirectory(prefix='home-ocr-') as folder:
        if body.startswith(b'%PDF'):
            # Four pages maximum; explicitly partial even for short files.
            run_tool('pdftoppm',['-f','1','-l','4','-scale-to','1800','-png',path,Path(folder)/'page'])
            images=sorted(Path(folder).glob('page-*.png'))
        else:images=[path]
        parts=[run_tool('tesseract',[image,'stdout','-l','kor+eng','--psm','3']) for image in images]
        text='\n'.join(parts)
        if len(text.strip())<30:raise ValueError('EMPTY_OCR_TEXT')
        return dict(text=text,status='OCR_REVIEW_REQUIRED',text_method='TESSERACT_KOR_ENG',
                    text_scope='FIRST_4_PAGES_MAX' if body.startswith(b'%PDF') else 'IMAGE',
                    text_review_required=True)

FIELDS=('text','tables','status','error','text_method','text_scope','text_review_required',
        'text_attempted_on','text_extractor_version')

def recover_item(item, data_dir):
    path=(Path(data_dir)/item['original_file']).resolve()
    if not path.is_relative_to((Path(data_dir)/'raw').resolve()):raise ValueError('ARCHIVE_PATH_INVALID')
    if path.stat().st_size>15_000_000:raise ValueError('FILE_SIZE_LIMIT')
    body=path.read_bytes()
    if hashlib.sha256(body).hexdigest()!=item.get('original_sha256'):raise ValueError('ARCHIVE_HASH_MISMATCH')
    return extract(path,body)

def pending(item):
    if not item.get('original_file') or item.get('status') in ('TEXT_EXTRACTED','OCR_REVIEW_REQUIRED'):return False
    # Maps require spatial interpretation; automatic OCR does not resolve it.
    if any(w in (item.get('name','')+item.get('path','')) for w in ('지형도','결정도','지형도면')):return False
    return (item.get('text_extractor_version')!=VERSION or
            item.get('text_attempted_on','')<=(today()-timedelta(days=7)).isoformat())

def refresh_flags(payload):
    items=payload.get('attachments',[])
    payload['attachment_complete']=all(a.get('original_file') for a in items)
    payload['text_extraction_complete']=all(a.get('status')=='TEXT_EXTRACTED' for a in items)
    payload['ocr_review_required']=any(a.get('status')=='OCR_REVIEW_REQUIRED' for a in items)

def recover_batch(service, output, limit=4):
    """Reuse by SHA, then drain older archives with a strict per-batch budget."""
    if not hasattr(service,'sessions'):return dict(text_recovery_attempted=0)
    from sqlalchemy import select
    from .db import Revision
    fresh={key:p for kind,key,p in output if kind=='document_evidence'}
    old_candidates=[];eligible_count=0
    with service.sessions() as session:
        query=select(Revision).where(Revision.source_id=='eum_housing_notices',
              Revision.kind=='document_evidence',Revision.superseded_at.is_(None)).order_by(Revision.recorded_at)
        for revision in session.scalars(query.execution_options(yield_per=25)):
            old=revision.payload;key=old.get('source_object_id')
            if key in fresh:
                cache={a.get('original_sha256'):a for a in old.get('attachments',[]) if a.get('original_sha256')}
                for item in fresh[key].get('attachments',[]):
                    previous=cache.get(item.get('original_sha256'))
                    if previous and previous.get('text_extractor_version')==VERSION and (previous.get('status') in ('TEXT_EXTRACTED','OCR_REVIEW_REQUIRED') or item.get('status')!='TEXT_EXTRACTED'):
                        item.update({k:previous[k] for k in FIELDS if k in previous})
            elif key:
                count=sum(pending(a) for a in old.get('attachments',[]));eligible_count+=count
                if count and len(old_candidates)<limit:old_candidates.append((key,copy.deepcopy(old)))
    eligible_count+=sum(pending(a) for p in fresh.values() for a in p.get('attachments',[]))
    attempted=0;recovered=0;ocr=0;failures=[]
    # Reserve half the budget for older records; new notices also make progress.
    candidates=old_candidates[:limit//2]+list(fresh.items())+old_candidates[limit//2:]
    for key,payload in candidates:
        changed=False
        for item in payload.get('attachments',[]):
            if attempted>=limit or not pending(item):continue
            attempted+=1;changed=True
            item.update(text_attempted_on=today().isoformat(),text_extractor_version=VERSION)
            try:
                item.update(recover_item(item,service.data_dir));item.pop('error',None)
                recovered+=item['status']=='TEXT_EXTRACTED';ocr+=item['status']=='OCR_REVIEW_REQUIRED'
            except Exception as error:
                # Retain archive status and original; a failed retry is not completion.
                item['error']=str(error)[:160] if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__
                failures.append(dict(seq=key,error=item['error']))
        if changed and key not in fresh:output.append(('document_evidence',key,payload))
        if changed or key in fresh:refresh_flags(payload)
    return dict(text_recovery_attempted=attempted,text_recovered=recovered,ocr_review_pending=ocr,
                text_recovery_failures=failures,text_recovery_limit=limit,text_extractor_version=VERSION,
                text_recovery_remaining=max(0,eligible_count-attempted))
