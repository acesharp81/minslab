"""Append explicitly attributed user feedback without pretending an AI detected it.

Does not invoke models. Preserves source runs and human reviews. Rectangles are
manual follow-up locations, never fixtures used by automatic inspection.
"""
import argparse,copy,hashlib,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.storage import Store,now
from app.text_ocr import valid_rect
from app.rules import validate_batch


def revise(source,manifest):
    run=copy.deepcopy(source);objects={o['id']:o for o in run['observation']['objects']}
    steps={s['rule_id']:s for s in run['rule_pack']['steps']}
    reviewed={r['finding_id'] for r in run['reviews']}
    for target in manifest['targets']:
        oid=target['object_id']
        if oid not in objects or not target['parts']:raise ValueError('대상 누락')
        if any(not valid_rect(p['rect']) or not p['reason'].strip() for p in target['parts']):raise ValueError('영역/근거 오류')
        for rid in target['rule_ids']:
            if rid not in steps:raise ValueError('규칙 오류')
            rows=[r for r in run['results'] if r['rule_id']==rid and r.get('evidence_ids')==[oid]]
            if not rows:
                obj=objects[oid]
                rows=validate_batch({'results':[dict(rule_id=rid,instance_id=oid,status='REVIEW',observation=obj['label'],reason='사용자 지적',evidence_quality='UNCERTAIN',cell_ids=obj['cell_ids'],reference_ids=[],recommended_action='원본을 확인하세요.')]},[rid],run['reference_snapshot'],None,'system/reported-issue',pack=run['rule_pack'])
                for row in rows:row.update(evidence_ids=[oid],target_presence='PRESENT',vision_model=run.get('observation_model'))
                run['results'].extend(rows)
            for row in rows:
                row['reported_issues']={'source':'USER_FEEDBACK','parts':copy.deepcopy(target['parts']),'source_run_id':source['id'],
                    'prior_model_status':row['status'],'prior_model_reason':row['reason'],
                    'note':'사용자 지적에 따른 수동 위치 기록. 자동 검출 성공으로 집계하지 않습니다.'}
                if row['id'] in reviewed or row['status']=='FAIL':continue
                row.update(status='REVIEW',model='system/reported-issue',visual_issue=True,document_review=False,
                    error_type='OCR_UNCERTAIN' if target.get('kind')=='text' else 'FACT_OR_STYLE_ISSUE',review_basis='OBSERVED_ANOMALY',
                    reason='사용자 지적 · 자동 판정과 별도: '+' / '.join(p['part']+': '+p['reason'] for p in target['parts']),
                    rects=[p['rect'] for p in target['parts']],location_unresolved=False,
                    recommended_action='모델이 정상으로 읽은 결과와 별개로 지적된 원본 획·도안을 확인하세요.')
    run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),elapsed_seconds=0,calls=copy.deepcopy(manifest.get('calls',[])),phase='DONE',reused_from=None)
    run['cache_key']='reported-issues-'+run['id']
    run['local_revision']={'source_run_id':source['id'],'kind':'user-feedback','note':'사용자 지적과 독립 판독 기록 추가. 전체 자동 검사를 새로 수행한 결과가 아닙니다.'}
    run['followup_diagnostics']=copy.deepcopy(manifest.get('diagnostics',{}))
    return run


def main():
    p=argparse.ArgumentParser();p.add_argument('job_id');p.add_argument('source_run_id');p.add_argument('manifest');args=p.parse_args()
    s=Settings();store=Store(s.data/'inspection.sqlite3');manifest=json.loads(Path(args.manifest).read_text())
    if hashlib.sha256((s.data/args.job_id/'image.png').read_bytes()).hexdigest()!=manifest['image_sha256']:raise ValueError('원본 해시 오류')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        record=c.execute('SELECT body FROM jobs WHERE id=?',(args.job_id,)).fetchone()
        if not record:raise ValueError('기록 없음')
        job=json.loads(record[0])
        if job['state'] in ('RUNNING','QUEUED') or job['runs'][-1]['id']!=args.source_run_id:raise ValueError('검사 버전 변경됨')
        for call in manifest.get('calls',[]):
            event=c.execute('SELECT body FROM usage_events WHERE id=?',(call['event_id'],)).fetchone()
            if not event or json.loads(event[0])['status']!='COMPLETED':raise ValueError('완료된 실제 호출 아님')
        run=revise(job['runs'][-1],manifest)
        job['runs'].append(run);c.execute('UPDATE jobs SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),job['id']))
    store.audit('system/user-feedback','APPEND_REPORTED_ISSUES',job['id'],{'run_id':run['id'],'source_run_id':args.source_run_id})
    print(json.dumps({'run_id':run['id'],'target_count':len(manifest['targets']),'new_api_calls':0}))

if __name__=='__main__':main()
