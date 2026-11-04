"""Offline paired scoring and optional no-API geometry/evidence revision.

Labels are read only after model inference. Never imported by the application.
"""
import argparse,copy,hashlib,json,math,sqlite3,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app import precheck,spelling_audit
from app.storage import now
from score_suite import matches,metrics


def finalize(evaluation):
    sources=list(sorted((evaluation/'control-a/gpt-5.4--gpt-5.4-mini').glob('QA_*.json')))
    sources=[p for p in sources if '.progress.' not in p.name]
    if not sources:raise ValueError('No paired inputs')
    for source in sources:
        for arm in ('guidance-b','spelling-common'):
            if not (evaluation/arm/source.parent.name/source.name).exists():raise ValueError('Incomplete pair: '+source.name)
    for source in sources:
        shared=json.loads((evaluation/'spelling-common'/source.parent.name/source.name).read_text())['run']
        for arm,revision in [('control-a','control-final'),('guidance-b','guidance-final')]:
            original=evaluation/arm/source.parent.name/source.name
            saved=json.loads(original.read_text());prior=saved['run'];run=copy.deepcopy(prior)
            output=evaluation/revision/source.parent.name/source.name
            if output.exists():continue
            run['spelling_audit']=copy.deepcopy(shared['spelling_audit'])
            spelling_audit.protect(run,run['results'],run['selected'])
            precheck.annotate(run,run['results'],run['selected'])
            run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),calls=[],elapsed_seconds=0,
                       observation_reused_from={'run_id':prior['id']},
                       analysis_reused_from={'run_id':prior['id'],'reason':'동일 원문 철자 근거를 A/B 양쪽에 동일 적용 · 기존 오류의 위치 보정'},
                       local_revision={'method':'evidence-reconcile-v1','api_calls':0,'source_run_id':prior['id'],'spelling_source_run_id':shared['id'],
                                       'note':'동일 입력의 mini 철자 검사 근거와 독립 OCR 위치를 적용했습니다. 이 버전의 추가 API 호출은 없습니다.'})
            for row in run['results']:row['id']=uuid.uuid4().hex
            saved.update(revision=revision,run=run,source_code='.',source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').glob('*.py')})
            output.parent.mkdir(parents=True,exist_ok=True)
            work=output.parent/(source.stem+'-work');work.mkdir(exist_ok=True)
            (work/'references').symlink_to((original.parent/(source.stem+'-work')/'references').resolve(),target_is_directory=True)
            output.write_text(json.dumps(saved,ensure_ascii=False,indent=2))


def quantile(values,q):
    values=sorted(values)
    if not values:return None
    position=(len(values)-1)*q;low=math.floor(position);high=math.ceil(position)
    return round(values[low]+(values[high]-values[low])*(position-low),3)


def report(evaluation,destination):
    truth=json.loads((evaluation/'scoring/ground_truth.json').read_text());rows=[];runs=[];usage={};extra=[]
    for image in truth['images']:
        name=Path(image['image']).stem+'.json'
        files={arm:evaluation/arm/'gpt-5.4--gpt-5.4-mini'/name for arm in ('control-a','guidance-b','control-final','guidance-final','spelling-common')}
        if not all(p.exists() for p in files.values()):continue
        data={a:json.loads(p.read_text()) for a,p in files.items()};values={a:d['run'] for a,d in data.items()}
        for arm in ('control-a','guidance-b','spelling-common'):
            run=values[arm];meter=usage.setdefault(arm,dict(calls=0,input_tokens=0,output_tokens=0,cost_usd=0,unknown_calls=0,prompt_bytes=0))
            for call in run['calls']:
                meter['calls']+=1
                for k in ('input_tokens','output_tokens'):meter[k]+=call.get('usage',{}).get(k,0)
                meter['cost_usd']+=call.get('cost_usd') or 0
                meter['unknown_calls']+=bool(call.get('usage_unknown'));meter['prompt_bytes']+=call.get('prompt_bytes',0)
            runs.append(dict(image=name,arm=arm,run_id=run['id'],selected=len(run['selected']),errors=sum(x['status'] in ('ERROR','NOT_RUN') for x in run['results']),
                             seconds=run.get('elapsed_seconds'),calls=len(run['calls']),stopped_reason=run.get('stopped_reason'),
                             observation_reused=bool(run.get('observation_reused_from')),source_hashes=data[arm].get('source_hashes')))
        for case in image['cases']:
            semantic='D-02-l' if case['rule_id']=='H-04-n' and '기관명' in case['target'] else case['rule_id']
            row=dict(image=name,rule_id=case['rule_id'],semantic_rule=semantic,target=case['target'],expected=case['expected_status'])
            for arm in ('control-a','guidance-b','control-final','guidance-final'):
                for mode,rid in [('strict',case['rule_id']),('semantic',semantic)]:
                    candidates=[p for p in values[arm]['results'] if p['rule_id']==rid and not p.get('supplemental_evidence') and not p.get('reported_issues')]
                    found=[p for p in candidates if matches(p,case['roi_normalized'])]
                    if not found and case.get('kind')=='document_required':found=[p for p in candidates if p.get('document_review') or p.get('evidence_quality')=='DOCUMENT']
                    row[arm+'_'+mode]=next((s for s in ('FAIL','REVIEW','PASS','NOT_APPLICABLE','ERROR','NOT_RUN') if any(p['status']==s for p in found)),'NO_LOCATION')
                    if mode=='semantic':row[arm+'_reasons']=[dict(status=p['status'],reason=p['reason'],rects=p.get('rects')) for p in found]
            rows.append(row)
        for arm in ('control-final','guidance-final'):
            unlabelled=[dict(rule_id=p['rule_id'],reason=p['reason'],rects=p.get('rects')) for p in values[arm]['results'] if p['status']=='FAIL' and not any(p['rule_id'] in (c['rule_id'],'D-02-l' if c['rule_id']=='H-04-n' and '기관명' in c['target'] else c['rule_id']) and matches(p,c['roi_normalized']) for c in image['cases'])]
            extra.append(dict(image=name,arm=arm,unlabelled_failures=unlabelled))
    stats={arm+'_'+mode:metrics([dict(expected=r['expected'],predicted=r[arm+'_'+mode]) for r in rows]) for arm in ('control-a','guidance-b','control-final','guidance-final') for mode in ('strict','semantic')}
    latency={arm:dict(p50_seconds=quantile([r['seconds'] for r in runs if r['arm']==arm],.5),p95_seconds=quantile([r['seconds'] for r in runs if r['arm']==arm],.95)) for arm in ('control-a','guidance-b','spelling-common')}
    baseline,candidate=stats['control-final_semantic'],stats['guidance-final_semantic']
    accepted=bool(rows) and candidate['fail_recall']>=baseline['fail_recall'] and candidate['false_positive_rate']<=baseline['false_positive_rate']
    with sqlite3.connect(evaluation/'budget.sqlite3') as db:
        accounting=[dict(model=m,state=s,calls=n,tokens_and_reservations=amount) for m,s,n,amount in db.execute('select model,state,count(*),sum(amount) from reservations group by model,state')]
    result=dict(images=len(rows) and len({r['image'] for r in rows}),cases=rows,metrics=stats,usage=usage,latency=latency,runs=runs,
                unlabelled=extra,accounting=accounting,acceptance_guard_passed=accepted,
                acceptance_scope='Labelled FAIL recall and normal-case FAIL rate only; review coverage and location regressions remain documented.',
                limitations=['Paired same saved scene readings, references and current rules; no new full-image reading in this A/B.',
                    'Single run per arm on known regression fixtures; cannot isolate model variability or claim statistical significance.',
                    'Spelling-common uses identical literal inputs, is called once per image, and is applied to both arms without additional calls.',
                    'Raw and final scores are separate; final arms include evidence-based spelling and geometry changes, no answer labels.',
                    'Semantic scores map agency-name H-04-n labels to D-02-l; strict rule-ID metrics are also reported.',
                    'NO_LOCATION includes coarse-grid and evidence-connection problems, not only missing detections.',
                    'Labelled normal-case false-positive rate excludes unlabelled FAILs, which are preserved for qualitative review.',
                    'p95 is sample interpolation for analysis with reused observations; not end-to-end upload latency.',
                    'USD is standard-rate equivalent for daily-quota models, not verified provider billing.',
                    '21/210 mapping completeness is distinct from execution/detection coverage. These seven fixtures do not cover all 210 tips.'])
    targeted=evaluation/'targeted-c/gpt-5.4--gpt-5.4-mini'
    if targeted.is_dir():
        import score_suite
        score_suite.EVAL=evaluation
        checks=score_suite.score(targeted)
        checks['limitations']+=['Two selected regression fixtures, not a representative holdout or all-210-tip evaluation.','This is the final per-tip target-scoping smoke test; the seven-image A/B precedes that narrowing.']
        result['targeted_smoke']={k:checks[k] for k in ('files','metrics','usage','runs','limitations')}
    destination.mkdir(parents=True,exist_ok=True);(destination/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:result[k] for k in ('images','usage','latency','acceptance_guard_passed')},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation-root',type=Path,default=ROOT/'data/qa-precheck-20261104');p.add_argument('--report-dir',type=Path,default=ROOT/'docs/precheck-2026-11-04');p.add_argument('--finalize',action='store_true');a=p.parse_args()
    if a.finalize:finalize(a.evaluation_root)
    report(a.evaluation_root,a.report_dir)
