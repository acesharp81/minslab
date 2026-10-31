"""Append a local coverage revision from saved evidence. No provider/API calls.

The original run remains unchanged. A revision records omitted contextual concerns
as system REVIEW findings, not as a new model verdict or an established defect.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.engine import Engine
from app.observations import Decision
from app.storage import Store,now


def revise(source):
    run=copy.deepcopy(source)
    ids=[s['rule_id'] for s in run['rule_pack']['steps'] if any(t in s['objective'] for t in ('충돌','오인 소지'))]
    decisions=[]
    fields=set(Decision.model_fields)-{'rule_ids'}
    for row in source['results']:
        if row['rule_id'] not in ids or row['status'] in ('ERROR','NOT_RUN'):continue
        decisions.append({**{k:row[k] for k in fields if k in row},'rule_ids':[row['rule_id']]})
    selected=list(dict.fromkeys(rid for d in decisions for rid in d['rule_ids']))
    if not selected:raise ValueError('보완할 완료된 맥락 점검이 없습니다.')
    # decisions() is a pure normalization step; do not construct Engine, which
    # starts a worker and handles interrupted jobs on startup.
    normalized=Engine.decisions(object.__new__(Engine),run,None,source['options']['analysis_model'],selected,{'results':decisions})
    existing={(r['rule_id'],tuple(r.get('evidence_ids',[]))) for r in source['results']}
    additions=[r for r in normalized if r.get('coverage_fallback') and (r['rule_id'],tuple(r['evidence_ids'])) not in existing]
    if not additions:raise ValueError('새로 보존할 누락 의견이 없습니다.')
    for row in additions:row['id']=uuid.uuid4().hex
    run['results'].extend(additions)
    run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),calls=[],elapsed_seconds=0,
               reused_from=None,phase='DONE',reused_from_cache=False)
    run['options']={**run['options'],'force':True,'reuse_observation_run_id':source['id'],'recheck_object_ids':[]}
    run['local_revision']={'kind':'observation-coverage','source_run_id':source['id'],'added_reviews':len(additions),
        'note':'기존 AI 검사와 관찰은 유지하고, 규칙 분석이 누락한 맥락 충돌 우려를 로컬 검토 항목으로 보존했습니다. 새 AI 판독·분석은 실행하지 않았습니다.'}
    run['cache_key']='local-coverage-'+run['id']
    return run


def main():
    parser=argparse.ArgumentParser();parser.add_argument('job_id');parser.add_argument('source_run_id');args=parser.parse_args()
    settings=Settings();store=Store(settings.data/'inspection.sqlite3')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT body FROM jobs WHERE id=?',(args.job_id,)).fetchone()
        if not row:raise ValueError('검수 기록 없음')
        job=json.loads(row[0])
        if job['state'] in ('QUEUED','RUNNING') or job['runs'][-1]['id']!=args.source_run_id:raise ValueError('현재 버전이 달라 적용을 중단합니다.')
        revision=revise(job['runs'][-1]);revision['observation_reused_from']={'job_id':job['id'],'run_id':args.source_run_id}
        job['runs'].append(revision)
        c.execute('UPDATE jobs SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),job['id']))
    store.audit('system/local-coverage','LOCAL_COVERAGE_REVISION',args.job_id,revision['local_revision'])
    print(json.dumps({'run_id':revision['id'],'added_reviews':revision['local_revision']['added_reviews'],'api_calls':0}))

if __name__=='__main__':main()
