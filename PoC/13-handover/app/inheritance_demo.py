"""Opt-in continuation demo; isolated IDs, no paid inference, no existing case edits."""
import threading,zipfile,json
from .store import uid,now,dump,digest
from .parsers import PARSER_VERSION
from .engine import warnings_for
LOCK=threading.Lock()
BASE='inheritance-demo-v1-base';TARGET='inheritance-demo-v1-next'

def seed(store,runner,root, *, source_id=BASE,target_id=TARGET,title="이어서 작성 · 11월 현행화·신규 업무",owner=2,recipient=3,previous=1):
 with LOCK:
  for ident,case_title,from_person,to_person,pack in [(source_id,title+' · 이전 인계 보고서',previous,owner,'01_이전인계_원본.zip'),(target_id,title,owner,recipient,'02_현행화_신규업무.zip')]:
   if store.one('SELECT id FROM cases WHERE id=?',(ident,)):continue
   stamp='2026-01-10T00:00:00+00:00' if ident==source_id else now()
   with store.connect(write=True) as db:
    db.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)',(ident,case_title,f'직원 {from_person}',f'직원 {to_person}',stamp,None,None,None))
    db.execute('INSERT INTO case_members VALUES (?,?,?)',(ident,f'employee{from_person}',f'employee{to_person}'))
    with zipfile.ZipFile(root/'release/public'/pack) as z:
     for path in z.namelist():
      data=z.read(path);sha=digest(data);(store.root/'raw'/sha).write_bytes(data)
      db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?)',(uid(),ident,path,sha,'.'+path.rsplit('.',1)[1],stamp))
    store.audit(db,ident,'CONTINUATION_DEMO',{'synthetic':True,'historical_date':ident==source_id})
   if ident==source_id:
    cfg={'document_ids':[d['id'] for d in store.rows('SELECT id FROM documents WHERE case_id=?',(source_id,))],'mode':'rules','model':'label-rules-v1','parent':None,'parser':PARSER_VERSION,'image_consent':False}
    job=uid()
    with store.connect(write=True) as db:db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(job,source_id,digest(cfg),'QUEUED','QUEUE',0,1,'',now(),now(),None,dump(cfg)))
    runner.run(job);status=store.one('SELECT * FROM jobs WHERE id=?',(job,))
    if status['status']!='SUCCEEDED':raise ValueError('이전 보고서 시연 준비 실패: '+status['error'])
    rev=store.one('SELECT * FROM revisions WHERE id=?',(status['result'],))
    with store.connect(write=True) as db:
     db.execute('INSERT INTO confirmations VALUES (?,?,?,?,?)',(rev['id'],source_id,rev['hash'],stamp,dump(warnings_for(json.loads(rev['payload'])))))
     db.execute('UPDATE cases SET confirmed=?,accepted=? WHERE id=?',(rev['id'],stamp,source_id))
     store.audit(db,source_id,'DEMO_HISTORICAL_ACCEPT',{'synthetic':True,'accepted':stamp})
 return {'source_case_id':source_id,'target_case_id':target_id,'employee':f'employee{owner}','note':'합성 완료일 2026-01-10. 초안 생성에서 이전 보고서 이어서 작성 옵션을 선택하세요.'}
