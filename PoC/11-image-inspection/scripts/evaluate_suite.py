"""Blind QA worker. Only the score command reads answer JSON; no answer overlays.

Uses isolated jobs, production shared usage accounting, a frozen baseline, and
an additional atomic cap fixed to the initial remaining allowance across resets.
"""
import argparse,copy,hashlib,json,os,sqlite3,sys,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EVAL=ROOT/'data/qa-20261031'


def dump(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(body,ensure_ascii=False,indent=2));temp.replace(path)


def infer(args):
    code=EVAL/'baseline-source' if args.revision=='baseline' else ROOT
    code_hashes={str(p.relative_to(code)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((code/'app').glob('*.py'))}
    sys.path.insert(0,str(code))
    from dotenv import dotenv_values
    from app.config import Settings
    from app.storage import Store,now
    from app.usage import Usage,BudgetError,RATES
    from app.providers import Provider
    from app.engine import Engine
    from app.rules import placeholder
    snap=json.loads((EVAL/'snapshot.json').read_text())
    values={**dotenv_values(ROOT/'.env'),**os.environ}
    production=Path(values.get('DATA_DIR','data'));production=production if production.is_absolute() else ROOT/production
    prod=Store(production/'inspection.sqlite3')
    resultdir=EVAL/args.revision/(args.vision.replace('/','_').replace(':','_')+'--'+args.analysis)
    resultpath=resultdir/(Path(args.image).stem+'.json')
    if resultpath.exists():raise RuntimeError('Existing result: use another revision; never silently rerun')
    work=resultdir/(Path(args.image).stem+'-work');work.mkdir(parents=True,exist_ok=True)
    settings=Settings({**values,'DATA_DIR':str(work),'NAVER_OCR_ENABLED':'false'})
    # No separate OCR calls during initial end-to-end baseline; matches production setting.
    settings.values['OCR_PYTHON']=str(ROOT/'.venv-ocr/bin/python')
    from evaluation_budget import capped_usage
    CappedUsage=capped_usage(Usage,EVAL/'budget.sqlite3',snap['limits'],RATES,BudgetError,wait_seconds=180)
    usage=CappedUsage(settings,prod)
    engine=Engine(settings,Store(work/'jobs.sqlite3'));engine.usage=usage;engine.provider=Provider(settings,usage)
    jid=Path(args.image).stem;path=EVAL/'inputs/images'/args.image
    if path.parent!=(EVAL/'inputs/images') or path.name not in snap['images']:raise ValueError('Only approved problem images')
    raw=path.read_bytes();(work/jid).mkdir(exist_ok=True);(work/jid/'image.png').write_bytes(raw)
    (work/'references').mkdir(exist_ok=True)
    refs=copy.deepcopy(snap['references'])
    for ref in refs:
        if ref.get('image_file'):(work/'references'/ref['image_file']).write_bytes((EVAL/'references'/ref['image_file']).read_bytes())
    master=json.loads((EVAL/'inputs/reference/MASTER_COPY.json').read_text()).get(args.image,{})
    # User-provided source values are allowed evidence, never expected statuses/ROIs.
    for kind,parents in [('source-data',['D-01','D-02']),('history',['H-01'])]:
        if master:refs.append(dict(id='fixture-'+kind,name='이 이미지의 제작자 제공 기준 원고',kind=kind,parent_ids=parents,status='APPROVED',version='test-source-1',content=json.dumps(master,ensure_ascii=False),issuer='사용자 제공 합성 테스트 원고',official_url='',image_file=None))
    if master.get('logo_reference'):
        asset=EVAL/'inputs'/master['logo_reference'];name='fixture-emblem.png';(work/'references'/name).write_bytes(asset.read_bytes())
        refs.append(dict(id='fixture-emblem',name='가상 안내단 문양 — 제작자 제공 기준',kind='official-emblems',parent_ids=['H-07'],status='APPROVED',version='test-source-1',content='이 합성 이미지의 가상 안내단 표식을 비교하는 제작자 제공 도안. 실제 정부 공식 문양이 아님. 이 실행에만 적용한다.',issuer='테스트 제작자',official_url='',image_file=name,image_hash=hashlib.sha256(asset.read_bytes()).hexdigest()))
        if args.revision!='baseline':refs[-1]['target_image_sha256']=hashlib.sha256(raw).hexdigest()
    selected=[s['rule_id'] for s in snap['pack']['steps']]
    job={'id':jid,'metadata':dict(title='합성 홍보물 품질 검수',context='제작자가 제공한 합성 시험용 홍보물입니다. 실제 개인정보가 아닌 가상 문자열입니다. 발견한 결함은 그대로 기록하고 최종 공개 승인과 분리합니다.',department='',media_type='카드뉴스',release_date='')}
    run=dict(id=uuid.uuid4().hex,created_at=now(),options=dict(mode='live',vision_model=args.vision,analysis_model=args.analysis,text_sensitivity='strict'),selected=selected,rule_pack=snap['pack'],reference_snapshot=refs,calls=[],analysis=[],results=[placeholder(r) for r in selected],reviews=[],progress=0,total=len(selected),scope='FULL_IMAGE')
    if args.reuse:
        saved=json.loads(Path(args.reuse).read_text());prior=saved['run']
        if saved['image_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('reuse image mismatch')
        for key in ('observation','observation_model','verification','text_ocr','structural_checks'):
            if key in prior:run[key]=copy.deepcopy(prior[key])
        run['observation_reused_from']={'run_id':prior['id']}
        if args.repair:
            run['selected']=list(dict.fromkeys(r['rule_id'] for r in prior['results'] if r['status'] in ('ERROR','NOT_RUN')))
            if not run['selected']:raise ValueError('No incomplete actions to repair')
            run['results']=copy.deepcopy([r for r in prior['results'] if r['rule_id'] not in run['selected']])+[placeholder(r) for r in run['selected']]
            run['total']=len(run['selected'])
            run['analysis_reused_from']={'run_id':prior['id'],'reason':'성공한 행동은 유지하고 실행 오류만 재처리'}
        if args.reverify:
            run['options']['recheck_object_ids']=[o['id'] for o in run['observation']['objects']]
    started=time.monotonic()
    def checkpoint(*_):
        dump(resultpath.with_suffix('.progress.json'),dict(image=args.image,revision=args.revision,run=run,elapsed=round(time.monotonic()-started,2)))
    engine.checkpoint=checkpoint
    print('START',args.revision,args.image,args.vision,args.analysis,flush=True)
    try:engine.inspect(job,run,None,started)
    except Exception as exc:
        if getattr(exc,'call_meta',None):run['calls'].append(exc.call_meta)
        run['stopped_reason']=str(exc)[:500];run['failed_phase']=run.get('phase')
        for row in run['results']:
            if row['status']=='NOT_RUN':row.update(status='ERROR',reason=run['stopped_reason'])
    finally:
        run['finished_at']=now();run['elapsed_seconds']=round(time.monotonic()-started,2)
        result=dict(image=args.image,image_sha256=hashlib.sha256(raw).hexdigest(),revision=args.revision,vision_model=args.vision,analysis_model=args.analysis,source_code=str(code.relative_to(ROOT)),source_hashes=code_hashes,run=run)
        dump(resultpath,result);engine.pool.shutdown()
    print('DONE',args.image,run['elapsed_seconds'],len(run['calls']),run.get('stopped_reason',''),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('image');p.add_argument('--revision',default='baseline');p.add_argument('--vision',default='gpt-5.4');p.add_argument('--analysis',default='gpt-5.4-mini');p.add_argument('--reuse');p.add_argument('--reverify',action='store_true');p.add_argument('--repair',action='store_true');a=p.parse_args()
    if a.repair and not a.reuse:p.error('--repair requires --reuse')
    infer(a)

if __name__=='__main__':main()
