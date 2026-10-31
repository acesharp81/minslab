"""Recover paid comparison evidence discarded by an older all-or-nothing check.

No provider calls. Preserve source run, verify ledger and uniquely restore IDs
that the older diagnostic redactor masked. Never promote partial evidence to FAIL.
"""
import argparse,copy,hashlib,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.storage import Store,now
from app.rules import redact
from app.verification import reconcile_comparison_aspects
from app import evidence_guards


def revise(source):
    run=copy.deepcopy(source);refs={r['id']:r for r in source['reference_snapshot']}
    steps={s['rule_id']:s for s in source['rule_pack']['steps']};recovered=[]
    objects={o['id']:o for o in source['observation']['objects']}
    for rejected in source.get('verification',{}).get('rejected_results',[]):
        if '상충' not in rejected['reason']:continue
        result=copy.deepcopy(rejected['response']);obj=objects[result['object_id']]
        # Recovery is limited to full-image map crops introduced in v25.
        if '지도' not in obj['label'] or not result.get('territorial_context'):continue
        for cmp in result['comparisons']:
            matching=[rid for rid in refs if rid==cmp['reference_id'] or redact(rid)==cmp['reference_id']]
            if len(matching)!=1:raise ValueError('기준자료 식별자를 유일하게 복구할 수 없음')
            cmp['reference_id']=matching[0]
            if not set(cmp['rule_ids'])<=set(source['selected']):raise ValueError('요청 밖 규칙')
            if any(steps[rid]['parent_id'] not in refs[matching[0]]['parent_ids'] for rid in cmp['rule_ids']):raise ValueError('기준자료 적용 범위 불일치')
        reconcile_comparison_aspects(result)
        result.update(status='COMPLETED',crop_rect=[0.,0.,1.,1.],model=source['options']['vision_model'],event_id=rejected['event_id'],
            first_text=obj.get('text',''),transcription_disagreement=obj.get('text','').strip()!=result['text'].strip(),
            reference_hashes={c['reference_id']:refs[c['reference_id']]['image_hash'] for c in result['comparisons']},
            rule_hashes={rid:hashlib.sha256(steps[rid]['objective'].encode()).hexdigest() for c in result['comparisons'] for rid in c['rule_ids']})
        run['verification']['results']=[v for v in run['verification']['results'] if v['object_id']!=obj['id']]+[result]
        run['verification']['deferred']=[v for v in run['verification']['deferred'] if v['object_id']!=obj['id']]
        if result['coverage']!='COMPLETE':run['verification']['deferred'].append({'object_id':obj['id'],'reason':'일부 가림: 관찰된 강조 범위 문제와 판독 한계를 구분해 확인'})
        recovered.append(obj['id'])
    if not recovered:raise ValueError('복구할 지도 비교 없음')
    reviewed={r['finding_id'] for r in source['reviews']}
    protected=evidence_guards.protect(run,run['results'],source['selected'])
    originals={r['id']:r for r in source['results']}
    run['results']=[copy.deepcopy(originals[r['id']]) if r.get('id') in reviewed else r for r in protected]
    for row in run['results']:row.setdefault('id',uuid.uuid4().hex)
    run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),calls=[],elapsed_seconds=0,phase='DONE',reused_from=None)
    run['observation_reused_from']={'run_id':source['id']}
    run['cache_key']='comparison-recovery-'+run['id']
    run['local_revision']={'kind':'comparison-aspects','source_run_id':source['id'],'recovered_objects':recovered,
        'note':'기존 재판독 응답에서 지도 강조 범위 비교를 복구했습니다. 지명별 상충 의견만 보류하며, 기관명·태극 판정과 사람 검토 기록은 보존합니다. 추가 API 호출 0회.'}
    return run


def main():
    p=argparse.ArgumentParser();p.add_argument('job_id');p.add_argument('source_run_id');args=p.parse_args()
    s=Settings();store=Store(s.data/'inspection.sqlite3')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT body FROM jobs WHERE id=?',(args.job_id,)).fetchone()
        if not row:raise ValueError('검사 없음')
        job=json.loads(row[0]);source=job['runs'][-1]
        if job['state'] in ('RUNNING','QUEUED') or source['id']!=args.source_run_id:raise ValueError('실행 중 또는 최신 버전 변경')
        for item in source.get('verification',{}).get('rejected_results',[]):
            event=c.execute('SELECT body FROM usage_events WHERE id=?',(item['event_id'],)).fetchone()
            if not event or json.loads(event[0]).get('status')!='COMPLETED':raise ValueError('성공한 실제 호출 기록이 없음')
        revision=revise(source);job['runs'].append(revision)
        c.execute('UPDATE jobs SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),job['id']))
    store.audit('system/comparison-aspects','COMPARISON_ASPECT_RECOVERY',job['id'],revision['local_revision'])
    print(json.dumps({'run_id':revision['id'],'recovered_objects':revision['local_revision']['recovered_objects'],'api_calls':0}))

if __name__=='__main__':main()
