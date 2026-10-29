"""Closed-book D-02-l evaluation. No ground truth is read by either inference worker.
Run baseline from a frozen source archive, then improved OCR on the SAME visual inventory.
The score subcommand alone reads ground_truth.json (no provider is constructed).
"""
import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVAL=ROOT/'data/ocr-evaluation'
# All fixtures containing labelled D-02-l cases. This only selects images, not ROIs.
IMAGES=['QA_02_hands.png','QA_03_ocr_readability.png','QA_05_chart_numbers.png','QA_06_privacy_signs.png',
        'QA_07_culture_food.png','QA_08_all_pass.png','QA_09_history.png','QA_10_emblem.png']


def infer(mode,filename):
    code=EVAL/'baseline-source' if mode=='baseline' else ROOT
    sys.path.insert(0,str(code))
    from dotenv import dotenv_values
    from app.config import Settings
    from app.engine import Engine
    from app.storage import Store
    from app.providers import Provider
    from app.usage import Usage
    values=dict(dotenv_values(ROOT/'.env'))
    prod_data=Path(values.get('DATA_DIR','data'))
    if not prod_data.is_absolute():prod_data=ROOT/prod_data
    prod=Store(prod_data/'inspection.sqlite3')
    template=prod.get('e0b01890ca0b4b5ea8e1e55f46b8ea4b')['runs'][-1]
    target=EVAL/mode;target.mkdir(parents=True,exist_ok=True)
    settings=Settings({**values,'DATA_DIR':str(target),'OCR_ENABLED':'true','OCR_VISION_MAX_REGIONS':'24','OCR_HIGH_EFFORT_RECHECK':'true','NAVER_OCR_ENABLED':'false'})
    # Worker path must point to installed environment, independent of baseline ROOT.
    settings.values['OCR_PYTHON']=str(ROOT/'.venv-ocr/bin/python')
    meter=Usage(settings,prod)
    engine=Engine(settings,Store(target/'evaluation.sqlite3'))
    engine.provider=Provider(settings,meter);engine.checkpoint=lambda *args:None
    jid=Path(filename).stem;path=EVAL/'fixtures/images'/filename;raw=path.read_bytes()
    (target/jid).mkdir(exist_ok=True);(target/jid/'image.png').write_bytes(raw)
    # Reuse official registry only, never test answer images or answer JSON.
    refs=target/'references';refs.mkdir(exist_ok=True)
    for r in template['reference_snapshot']:
        if r.get('image_file'):(refs/Path(r['image_file']).name).write_bytes((prod_data/'references'/Path(r['image_file']).name).read_bytes())
    job={'id':jid,'metadata':{'title':'문자 품질 회귀검사','context':'홍보물의 실제 글자 모양과 철자를 확인합니다.'}}
    started=time.monotonic()
    if mode=='baseline':
        run={'id':'baseline-'+jid,'options':{'mode':'live','vision_model':'gpt-5.4','analysis_model':'gpt-5.4-mini','text_sensitivity':'strict'},
            'selected':['D-02-l','H-06-b'],'rule_pack':template['rule_pack'],'reference_snapshot':template['reference_snapshot'],
            'calls':[],'analysis':[],'results':[],'progress':0,'total':2}
        engine.inspect(job,run,None,started)
    else:
        from app import text_ocr
        baseline=json.loads((EVAL/'baseline'/f'{jid}.json').read_text())
        run=copy.deepcopy(baseline['run']);run['calls']=[];run['id']='improved-'+jid
        # OCR model files are shared on disk; image results are never global-cached.
        modeldir=target/'ocr-models'
        if not modeldir.exists():modeldir.symlink_to(prod_data/'ocr-models',target_is_directory=True)
        text_ocr.run_text_ocr(engine,job,run,raw)
        run['analysis_observation']=copy.deepcopy(baseline['run']['analysis_observation'])
        text_ocr.attach_observations(run)
        run['results']=text_ocr.protect_rows(run,copy.deepcopy(baseline['run']['results']),['D-02-l','H-06-b'],'gpt-5.4-mini')
    elapsed=round(time.monotonic()-started,2)
    result={'mode':mode,'image':filename,'image_sha256':hashlib.sha256(raw).hexdigest(),'seconds':elapsed,'run':run}
    (target/f'{jid}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'mode':mode,'image':filename,'seconds':elapsed,'calls':len(run['calls']),'ocr':run.get('text_ocr',{}).get('counts')},ensure_ascii=False),flush=True)
    engine.pool.shutdown()


def score(only=None):
    from collections import Counter
    truth=json.loads((EVAL/'fixtures/ground_truth.json').read_text())
    def hits(rect,roi):
        x,y,z,b=rect;cx,cy=(x+z)/2,(y+b)/2
        return roi[0]<=cx<=roi[2] and roi[1]<=cy<=roi[3]
    rows=[];extras={};costs={}
    for mode in ('baseline','improved'):
        mode_rows=[];extra=[];calls=[];seconds=0
        for image in truth['images']:
            name=Path(image['image']).name
            if name not in IMAGES or (only and not any(name.startswith(prefix) for prefix in only)):continue
            saved=json.loads((EVAL/mode/(Path(name).stem+'.json')).read_text());run=saved['run'];calls+=run['calls'];seconds+=saved['seconds']
            cases=[c for c in image['cases'] if c['rule_id']=='D-02-l']
            predictions=[p for p in run['results'] if p['rule_id']=='D-02-l']
            for c in cases:
                roi=c['roi_normalized'];matched=[p for p in predictions if any(hits(r,roi) for r in p.get('rects',[]))]
                # Worst finding within the labelled region; REVIEW is not a successful detection.
                status=next((s for s in ('FAIL','REVIEW','PASS','ERROR') if any(p['status']==s for p in matched)),'NOT_RUN')
                objects=run.get('analysis_observation',run.get('observation',{})).get('objects',[])
                transcribed=any(o.get('text','').replace('[판독불가]','').replace('□','').strip() and any(hits(r,roi) for r in o.get('rects',[])) for o in objects)
                if mode=='baseline':
                    from app.imaging import cell_rect
                    transcribed=any(o.get('text','').replace('[판독불가]','').replace('□','').strip() and any(hits(r,roi) for r in o.get('rects') or [cell_rect(x) for x in o['cell_ids']]) for o in objects)
                mode_rows.append({'image':name,'target':c['target'],'expected':c['expected_status'],'predicted':status,'ocr_omitted':not transcribed,
                                  'matches':[{'status':p['status'],'reason':p['reason'],'rects':p.get('rects'),'error_type':p.get('error_type')} for p in matched]})
            extra.extend({'image':name,'reason':p['reason'],'rects':p.get('rects')} for p in predictions if p['status']=='FAIL' and not any(any(hits(r,c['roi_normalized']) for r in p.get('rects',[])) for c in cases))
        faults=[r for r in mode_rows if r['expected']=='FAIL'];normal=[r for r in mode_rows if r['expected']=='PASS']
        extras[mode]=extra
        costs[mode]={'calls':len(calls),'tokens':sum(sum(c.get('usage',{}).values()) for c in calls),'estimated_cost_usd':sum(c.get('cost_usd') or 0 for c in calls),'total_seconds':round(seconds,2)}
        rows.append({'mode':mode,'labelled_cases':len(mode_rows),'faults':len(faults),'normal':len(normal),
          'detection_rate':sum(r['predicted']=='FAIL' for r in faults)/len(faults),
          'false_positive_rate':sum(r['predicted']=='FAIL' for r in normal)/len(normal),
          'ocr_omission_rate':sum(r['ocr_omitted'] for r in mode_rows)/len(mode_rows),
          'review_rate':sum(r['predicted']=='REVIEW' for r in mode_rows)/len(mode_rows),
          'counts':dict(Counter(r['predicted'] for r in mode_rows)),'cases':mode_rows})
    report={'scope':'D-02-l 문자 오탈자·가독성 평가. 25개 전체 규칙 성능평가 아님. 기존 판독 inventory 공유. 선택 이미지: '+str(only or IMAGES),
      'matching':'예측 영역 중심이 정답 ROI 안에 있는 경우만 매칭. 한 ROI의 최악 상태 사용. REVIEW는 검출 성공 아님.',
      'limitations':'OCR 누락률은 정답 문자 ROI에 비어 있지 않은 전사가 있는지이며 문자별 CER/WER 아님. 미라벨 영역 FAIL은 오탐 확정 없이 별도 수록. 합성 테스트이며 자연형 스트레스 이미지는 별도.',
      'results':rows,'unlabelled_failures':extras,'usage':costs}
    (EVAL/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({**report,'results':[{k:v for k,v in r.items() if k!='cases'} for r in rows],'unlabelled_failures':{k:len(v) for k,v in extras.items()}},ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['baseline','improved','score']);p.add_argument('image',nargs='?');p.add_argument('--only',nargs='+');a=p.parse_args()
    if a.mode=='score':sys.path.insert(0,str(ROOT));score(a.only)
    else:infer(a.mode,a.image)
