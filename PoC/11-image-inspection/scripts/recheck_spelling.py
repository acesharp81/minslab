"""Bounded text-only check of stored, independently agreed source strings."""
import argparse,copy,hashlib,json,shutil,sys,time,uuid
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app import spelling_audit
from app.config import Settings
from app.storage import Store,now
from app.usage import Usage,RATES,BudgetError
from app.providers import Provider
from evaluation_budget import capped_usage

def run(evaluation,names):
    settings=Settings();store=Store(settings.data/'inspection.sqlite3')
    limits=json.loads((evaluation/'snapshot.json').read_text())['limits']
    Meter=capped_usage(Usage,evaluation/'budget.sqlite3',limits,RATES,BudgetError,wait_seconds=30)
    engine=SimpleNamespace(provider=Provider(settings,Meter(settings,store)),checkpoint=lambda *a:None)
    destination=evaluation/'spelling-release/gpt-5.4--gpt-5.4-mini';destination.mkdir(parents=True,exist_ok=True)
    for source in sorted((evaluation/'release-final/gpt-5.4--gpt-5.4-mini').glob('QA_*.json')):
        if names and not any(source.stem.startswith(n) for n in names):continue
        target=destination/source.name
        if target.exists():continue
        saved=json.loads(source.read_text());prior=saved['run'];result=copy.deepcopy(prior)
        result.update(id=uuid.uuid4().hex,created_at=now(),calls=[],observation_reused_from={'run_id':prior['id']},analysis_reused_from={'run_id':prior['id'],'reason':'원문 철자만 mini로 독립 검사 · 다른 행동 유지'})
        result.pop('local_revision',None);started=time.monotonic()
        spelling_audit.inspect(engine,{'id':'offline-spelling'},result)
        spelling_audit.protect(result,result['results'],['D-02-l'])
        result.update(finished_at=now(),elapsed_seconds=round(time.monotonic()-started,2))
        for row in result['results']:row['id']=uuid.uuid4().hex
        shutil.copytree(source.parent/(source.stem+'-work')/'references',destination/(source.stem+'-work')/'references',dirs_exist_ok=True)
        saved.update(revision='spelling-release',run=result,source_code='.',source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').glob('*.py')})
        target.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
        print(json.dumps(dict(image=source.name,status=result.get('spelling_audit',{}).get('status'),calls=len(result['calls']),findings=[x for x in result.get('spelling_audit',{}).get('results',[]) if x['verdict']=='TYPO']),ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation-root',type=Path,default=ROOT/'data/qa-release-20261101');p.add_argument('--images',nargs='*');a=p.parse_args();run(a.evaluation_root,a.images)
