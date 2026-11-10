"""Idempotent synthetic ring inboxes. No paid inference and no existing case edits."""
import threading
import zipfile
from .store import uid,now,dump,digest
from .parsers import PARSER_VERSION
from .engine import warnings_for
LOCK=threading.Lock()
TITLES=['지역생활서비스 통합지원','공공시설 안전관리','디지털 민원안내 표준화','취약계층 돌봄연계']
PACKS=['01_최신본_먼저등록.zip','02_구판_나중등록.zip','03_미승인초안_마지막등록.zip']

def seed(store,runner,root):
    created=[]
    with LOCK:
        for archive in (False,True):
            for i in range(1,5):
                if archive and i not in (1,3):continue
                ident=f'employee-ring-v1-{i}-'+('completed' if archive else 'active')
                if store.one('SELECT id FROM cases WHERE id=?',(ident,)):continue
                timestamp=now();recipient=i%4+1
                with store.connect(write=True) as db:
                    db.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)',(ident,('완료 이력 · ' if archive else '')+TITLES[i-1],f'직원 {i}',f'직원 {recipient}',timestamp,None,None,None))
                    db.execute('INSERT INTO case_members VALUES (?,?,?)',(ident,f'employee{i}',f'employee{recipient}'))
                    for name in PACKS:
                        with zipfile.ZipFile(root/'release/public'/name) as z:
                            for path in z.namelist():
                                if not path.startswith(f'직원{i}/'):continue
                                raw=z.read(path);sha=digest(raw);(store.root/'raw'/sha).write_bytes(raw)
                                db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?)',(uid(),ident,path,sha,'.'+path.rsplit('.',1)[1],timestamp))
                    store.audit(db,ident,'DEMO_SEED',{'synthetic':True,'archive':archive,'image_processing':'explicit opt-in later'})
                if not archive and i==3:created.append(ident);continue
                docs=store.rows('SELECT id FROM documents WHERE case_id=? ORDER BY path,sha',(ident,))
                cfg={'document_ids':[d['id'] for d in docs],'mode':'rules','model':'label-rules-v1','parent':None,'parser':PARSER_VERSION,'flow_version':'all-immutable-versions-v2','image_consent':False}
                job=uid()
                with store.connect(write=True) as db:db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(job,ident,digest(cfg),'QUEUED','QUEUE',0,1,'',now(),now(),None,dump(cfg)))
                runner.run(job)
                status=store.one('SELECT * FROM jobs WHERE id=?',(job,))
                if status['status']!='SUCCEEDED':raise ValueError('순환 시연자료 생성 실패: '+status['error'])
                if archive or i in (2,4):
                    rev=store.one('SELECT * FROM revisions WHERE id=?',(status['result'],))
                    with store.connect(write=True) as db:
                        db.execute('INSERT INTO confirmations VALUES (?,?,?,?,?)',(rev['id'],ident,rev['hash'],now(),dump(warnings_for(__import__('json').loads(rev['payload'])))))
                        db.execute('UPDATE cases SET confirmed=?,accepted=? WHERE id=?',(rev['id'],now() if archive else None,ident))
                        store.audit(db,ident,'DEMO_CONFIRM',{'synthetic':True,'revision':rev['id'],'accepted':archive})
                created.append(ident)
    return {'created':created,'note':'직원별 진행 인수·인계 각 1건과 완료 이력 1건, 총 3건. 합성 자료이며 재실행 시 기존 시연함을 재사용합니다.'}
