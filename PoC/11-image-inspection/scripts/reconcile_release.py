"""Append no-API revisions from stored evidence. Never reads answer labels."""
import argparse, copy, hashlib, json, shutil, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app import text_location, pixel_text, verification
from app.storage import now


def reconcile(evaluation,destination):
    directory=evaluation/'release-candidate/gpt-5.4--gpt-5.4-mini'
    target=evaluation/'release-final/gpt-5.4--gpt-5.4-mini';target.mkdir(parents=True,exist_ok=True)
    summary=[]
    sources={p.name:p for p in directory.glob('QA_*.json') if '.progress.' not in p.name}
    # Budget-blocked fresh readings can be completed using stored observations.
    # Select the explicitly recorded recovery, never based on answer-key scores.
    sources.update({p.name:p for p in (evaluation/'release-reused/gpt-5.4--gpt-5.4-mini').glob('QA_*.json') if '.progress.' not in p.name})
    for path in sorted(sources.values()):
        output=target/path.name
        if output.exists():continue
        saved=json.loads(path.read_text());prior=saved['run'];run=copy.deepcopy(prior)
        conflicts=0
        for row in run['results']:
            if any(row.get(k) for k in ('glyph_evidence','pixel_text_evidence','symbol_geometry','emblem_geometry','structural_check')):continue
            proof=verification.direct_comparisons(run,row['rule_id'],row.get('evidence_ids',[]),row.get('reference_ids',[]))
            if verification.reconcile_verdict(row,proof):row['visual_issue']=False;conflicts+=1
        text_location.protect(run,run['results'])
        pixel_text.protect(run,run['results'],[])
        changes=[dict(rule_id=a['rule_id'],instance_id=a['instance_id'],before_status=b['status'],after_status=a['status'],before_rects=b.get('rects'),after_rects=a.get('rects'))
                 for a,b in zip(run['results'],prior['results']) if a!=b]
        run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),calls=[],elapsed_seconds=0,
                   observation_reused_from={'run_id':prior['id']},analysis_reused_from={'run_id':prior['id'],'reason':'저장된 판독·분석에 최신 근거 충돌/위치 보정 적용'},
                   local_revision={'method':'evidence-reconcile-v1','source_run_id':prior['id'],'api_calls':0,'note':'추가 API 호출 없이 원본 비교 충돌과 독립 OCR 위치 근거를 반영했습니다.'})
        for row in run['results']:row['id']=uuid.uuid4().hex
        refs=path.parent/(path.stem+'-work')/'references'
        shutil.copytree(refs,target/(path.stem+'-work')/'references',dirs_exist_ok=True)
        saved.update(revision='release-final',source_code='.',source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').glob('*.py')},run=run)
        output.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
        summary.append(dict(image=path.name,source_revision=str(path.parent.relative_to(evaluation)),source_run_id=prior['id'],run_id=run['id'],api_calls=0,conflicts=conflicts,changes=changes))
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'reconciliation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(dict(images=len(summary),conflicts=sum(x['conflicts'] for x in summary),changes=sum(len(x['changes']) for x in summary),api_calls=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation-root',type=Path,default=ROOT/'data/qa-release-20261101');p.add_argument('--report-dir',type=Path,default=ROOT/'docs/release-2026-11-01')
    a=p.parse_args();reconcile(a.evaluation_root,a.report_dir)
