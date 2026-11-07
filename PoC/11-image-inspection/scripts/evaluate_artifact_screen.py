"""Offline candidate comparison; never calls OCR, LLM or writes inspection history.
Synthetic blur labels evaluate only the local signal, not semantic QA accuracy.
Stored OCR/observations are inputs, never treated as human ground truth.
"""
import argparse
import copy
import io
import json
import sqlite3
import sys
import time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import artifact_screen, pixel_text


def score(cases,key):
    tp=sum(c['label_blur'] and c[key] for c in cases);fp=sum(not c['label_blur'] and c[key] for c in cases)
    fn=sum(c['label_blur'] and not c[key] for c in cases);tn=sum(not c['label_blur'] and not c[key] for c in cases)
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,recall=tp/(tp+fn) if tp+fn else None,precision=tp/(tp+fp) if tp+fp else None)


def synthetic(font):
    cases=[]
    for size in (32,48):
        face=ImageFont.truetype(str(font),size,index=1)
        for word in ('한','한복','문자 가독성 검사','한글 안내문 전체의 글자 품질을 확인합니다'):
            for blur in (0,3):
                for unread in (False,True):
                    image=Image.new('RGB',(max(100,len(word)*(size+5)+24),size*2),'white')
                    ImageDraw.Draw(image).text((12,0),word,font=face,fill='black')
                    if blur:image=image.filter(ImageFilter.GaussianBlur(blur))
                    buf=io.BytesIO();image.save(buf,format='PNG');raw=buf.getvalue()
                    region=dict(id='OCR1',rect=[0,0,1,1],text='' if unread else word,recognition_score=.99,detection_score=.95,source='paddle-detector')
                    run=dict(observation={'objects':[]},pixel_text={'detector_regions':[region]},results=[])
                    start=time.perf_counter();old=pixel_text.inspect_regions(raw,[region]);baseline_ms=(time.perf_counter()-start)*1000
                    start=time.perf_counter();new=artifact_screen.collect(raw,run);new_ms=(time.perf_counter()-start)*1000
                    cases.append(dict(size=size,length=len(word.replace(' ','')),unread=unread,label_blur=bool(blur),
                        baseline=any(r.get('blur_observed') for r in old),candidate='LOCAL_BLUR_SIGNAL' in new['signals'],
                        baseline_ms=round(baseline_ms,3),candidate_ms=round(new_ms,3)))
    return {'kind':'controlled_synthetic_blur_signal_only','cases':cases,'baseline':score(cases,'baseline'),'candidate':score(cases,'candidate')}


def replay(db):
    rows=[];directory=db.parent
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
        listing=c.execute('SELECT id,summary FROM job_history').fetchall()
        for jid,summary in listing:
            title=json.loads(summary)['metadata'].get('title','')
            if not any(k in title for k in ('QA_02','QA_03','QA_07','QA_08','Exploratory')):continue
            r=c.execute("SELECT json_extract(body,'$.runs[#-1]') FROM jobs WHERE id=?",(jid,)).fetchone()
            if not r or not r[0]:continue
            run=json.loads(r[0]);before=copy.deepcopy(run)
            start=time.perf_counter();report=artifact_screen.collect((directory/jid/'image.png').read_bytes(),run);elapsed=time.perf_counter()-start
            assert run==before
            rows.append(dict(job_id=jid,title=title,stored_regions=len((run.get('pixel_text') or {}).get('detector_regions',[])),
                candidates=len(report['candidates']),signals=report['signals'],diagnostics=dict(__import__('collections').Counter(d['state'] for d in report['diagnostics'])),
                seconds=round(elapsed,3),stored_findings_unchanged=True,report=report))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--font',type=Path,default=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'));args=p.parse_args()
    result={'api_calls':0,'automatic_fail_added':0,'synthetic':synthetic(args.font) if args.font.exists() else {'status':'FONT_UNAVAILABLE'},
        'stored_replay':replay(args.db) if args.db else [],'limitation':'Candidate signal recall is not final defect recall; model validation remains deferred.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'synthetic':{k:v for k,v in result['synthetic'].items() if k!='cases'},'stored_replay':[{k:v for k,v in r.items() if k!='report'} for r in result['stored_replay']],'api_calls':0},ensure_ascii=False))

if __name__=='__main__':main()
