"""Reapply stored spelling evidence with source/spacing guards, no API or labels."""
import copy,hashlib,json,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app import spelling_audit
from app.storage import now

def finalize(evaluation,destination):
    output=evaluation/'spelling-final/gpt-5.4--gpt-5.4-mini';output.mkdir(parents=True,exist_ok=True);summary=[]
    for path in sorted((evaluation/'spelling-release/gpt-5.4--gpt-5.4-mini').glob('QA_*.json')):
        target=output/path.name
        if target.exists():continue
        saved=json.loads(path.read_text());source=saved['run']
        prior=json.loads((evaluation/'release-final/gpt-5.4--gpt-5.4-mini'/path.name).read_text())['run'];run=copy.deepcopy(prior)
        run['spelling_audit']=copy.deepcopy(source['spelling_audit'])
        spelling_audit.protect(run,run['results'],['D-02-l'])
        tasks=spelling_audit.candidates(run);run['spelling_audit']['tasks']=tasks
        run['spelling_audit']['input_hash']=hashlib.sha256(json.dumps(tasks,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        changes=[dict(rule_id=a['rule_id'],before=b['status'],after=a['status'],reason=a['reason']) for a,b in zip(run['results'],prior['results']) if a['status']!=b['status']]
        run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),calls=[],elapsed_seconds=0,
                   analysis_reused_from={'run_id':source['id'],'reason':'저장된 철자 검사에 공백 판독 일치 조건 반영'},
                   local_revision={'method':'evidence-reconcile-v1','source_run_id':source['id'],'api_calls':0,'note':'저장된 mini 철자 검사와 원본 전사·공백 일치 조건을 반영했습니다. 추가 API 호출은 없습니다.'})
        for row in run['results']:row['id']=uuid.uuid4().hex
        shutil.copytree(path.parent/(path.stem+'-work')/'references',output/(path.stem+'-work')/'references',dirs_exist_ok=True)
        saved.update(revision='spelling-final',run=run,source_code='.',source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').glob('*.py')})
        target.write_text(json.dumps(saved,ensure_ascii=False,indent=2));summary.append(dict(image=path.name,run_id=run['id'],source_run_id=source['id'],api_calls=0,changes=changes))
    (destination/'spelling-finalization.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(dict(images=len(summary),changes=sum(len(x['changes']) for x in summary),api_calls=0)))

if __name__=='__main__':finalize(ROOT/'data/qa-release-20261101',ROOT/'docs/release-2026-11-01')
