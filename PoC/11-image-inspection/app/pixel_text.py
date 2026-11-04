"""Local glyph and blur evidence. No answer key, dictionary or API calls.

Only clean, horizontal, short Hangul text can use font-shape matching. Unmatched
fonts/perspective/segmentation failures are unsupported, never errors or PASS.
"""
import copy
from functools import lru_cache
import hashlib
import io
import json
import re
import time
import subprocess

import cv2
import numpy as np
from PIL import Image

from .config import ROOT
from . import text_ocr
from .isolated_glyphs import split_word

VERSION = 'pixel-text-v2-coverage'
TEXT_RULES = {'D-02-l', 'H-06-b'}


@lru_cache(maxsize=1)
def atlas():
    path=ROOT/'rules/glyph-shapes/hangul-v1.npz'
    manifest=json.loads(path.with_name('manifest.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['asset_sha256']:
        raise ValueError('글자 형태 비교 자산 무결성 오류')
    with np.load(path,allow_pickle=False) as data:array=data['glyphs']
    if array.ndim!=4 or array.shape[1:]!=(11172,64,64):raise ValueError('글자 형태 비교 자산 형식 오류')
    return array,manifest


def measure(image):
    gray=cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2GRAY).astype(float)
    if min(gray.shape)<12:return None
    lo,hi=np.percentile(gray,[5,95]);contrast=float(hi-lo)
    if contrast<18:return None
    norm=np.clip((gray-lo)/contrast,0,1)
    grad=np.hypot(cv2.Sobel(norm,cv2.CV_64F,1,0,ksize=3),cv2.Sobel(norm,cv2.CV_64F,0,1,ksize=3))
    edges=grad[grad>grad.max()*.2]
    if len(edges)<20:return None
    border=np.concatenate((gray[0],gray[-1],gray[:,0],gray[:,-1]))
    uniform=float(np.quantile(abs(border-np.median(border)),.9))<max(12,contrast*.2)
    return dict(edge_strength=round(float(np.quantile(edges,.8)),4),laplacian=round(float(cv2.Laplacian(norm,cv2.CV_64F).var()),5),contrast=round(contrast,2),uniform_background=bool(uniform),pixels=[gray.shape[1],gray.shape[0]])


def ink(image):
    gray=cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2GRAY)
    _,a=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if np.mean(np.concatenate((a[0],a[-1],a[:,0],a[:,-1])))>127:a=255-a
    y,x=np.nonzero(a)
    if not len(x):return None
    return a[y.min():y.max()+1,x.min():x.max()+1]


def variants(char):
    n=ord(char)-0xAC00
    if not 0<=n<11172:return []
    initial,vowel,final=n//588,n//28%21,n%28
    # Enumerate the Unicode syllable space, never a hand-written typo word list.
    return sorted({initial*588+i*28+final for i in range(21)}|
                  {initial*588+vowel*28+i for i in range(28)}|
                  {i*588+vowel*28+final for i in range(19)})


def compare_char(image, char):
    shape=ink(image)
    if shape is None or min(shape.shape)<18:return None
    source=cv2.resize(shape,(64,64),interpolation=cv2.INTER_AREA).astype(np.float32)/255
    templates,manifest=atlas();indices=variants(char)
    if not indices:return None
    candidates=templates[:,indices].astype(np.float32)/255
    scores=np.minimum(candidates,source).sum(axis=(2,3))/np.maximum(candidates,source).sum(axis=(2,3))
    maxima=scores.max(axis=0);order=np.argsort(maxima)[::-1]
    best,second=int(order[0]),int(order[1]);original=indices.index(ord(char)-0xAC00)
    winner=chr(0xAC00+indices[best]);margin=float(maxima[best]-maxima[second])
    strong=float(maxima[best])>=.82 and margin>=.045
    return dict(ocr_char=char,shape_char=winner,score=round(float(maxima[best]),4),original_score=round(float(maxima[original]),4),margin=round(margin,4),
                accepted=bool(winner==char or strong),font=manifest['sources'][int(scores[:,best].argmax())]['name'])


def inspect_regions(raw, regions, max_regions=48, diagnostics=None):
    im=Image.open(io.BytesIO(raw)).convert('RGB');w,h=im.size;results=[]
    diagnostics = diagnostics if diagnostics is not None else []
    for index,source in enumerate(regions):
        record=dict(source_id=source.get('id'),rect=source.get('rect'),state='NOT_MEASURED')
        diagnostics.append(record)
        if index>=max_regions:record['state']='REGION_LIMIT';continue
        rect=source.get('rect',[])
        if not text_ocr.valid_rect(rect):record['state']='INVALID_LOCATION';continue
        polygon=source.get('polygon_px')
        if polygon:
            # The atlas assumes upright planar text. Bounding boxes alone hide
            # rotation/perspective; unsupported geometry must not become a typo.
            points=np.asarray(polygon,dtype=float)
            if points.shape!=(4,2) or not np.isfinite(points).all():record['state']='INVALID_POLYGON';continue
            top,bottom=points[1]-points[0],points[2]-points[3]
            if any(v[0]<=0 or abs(v[1])>abs(v[0])*.07 for v in (top,bottom)):record['state']='UNSUPPORTED_ROTATION';continue
            if min(top[0],bottom[0])/max(top[0],bottom[0])<.9:record['state']='UNSUPPORTED_PERSPECTIVE';continue
        x,y,z,b=rect;crop=im.crop((int(x*w),int(y*h),int(np.ceil(z*w)),int(np.ceil(b*h))))
        measurements=measure(crop)
        if not measurements:record['state']='INSUFFICIENT_PIXELS_OR_CONTRAST';continue
        result=dict(id='PXT'+str(len(results)+1).zfill(3),rect=rect,detector_text=source.get('text',''),metrics=measurements,shape_checks=[],source=source.get('source'),source_id=source.get('id'))
        width,height=measurements['pixels']
        text=source.get('text','');compact=text_ocr.normalized(text)
        # Strong spread across many edges, not merely low OCR confidence.
        spread=measurements['edge_strength']<1.5 and measurements['laplacian']<.02
        eligible=measurements['uniform_background'] and width>height*2 and height>=20
        detected=source.get('source')=='paddle-detector' and source.get('detection_score',0)>=.55
        result['blur_observed']=bool(spread and eligible and detected and len(compact)>=4)
        result['shape_status']='BLUR_CANDIDATE' if result['blur_observed'] else 'UNSUPPORTED_BACKGROUND' if not measurements['uniform_background'] else 'UNSUPPORTED_TEXT' if not re.fullmatch('[가-힣]{2,6}',compact) else 'INSUFFICIENT_EDGE_DETAIL'
        if not result['blur_observed'] and measurements['uniform_background'] and measurements['edge_strength']>2.7 and re.fullmatch('[가-힣]{2,6}',compact):
            pieces=split_word(raw,rect)
            result['shape_status']='SEGMENTATION_MISMATCH'
            if len(pieces)==len(compact):
                for char,(data,position) in zip(compact,pieces):
                    check=compare_char(Image.open(io.BytesIO(data)),char)
                    if not check:break
                    result['shape_checks'].append({**check,'rect':position})
                if len(result['shape_checks'])==len(compact):
                    chars=iter(c['shape_char'] if c['accepted'] else c['ocr_char'] for c in result['shape_checks'])
                    result['shape_text']=''.join(next(chars) if re.fullmatch('[가-힣]',c) else c for c in text)
                    result['shape_conflict']=any(c['accepted'] and c['shape_char']!=c['ocr_char'] for c in result['shape_checks'])
                    result['shape_status']='CONFLICT_CANDIDATE' if result['shape_conflict'] else 'TEMPLATE_MATCH' if all(c['accepted'] for c in result['shape_checks']) else 'UNCERTAIN_TEMPLATE'
                else:result['shape_status']='UNSUPPORTED_FONT_OR_GLYPH'
        record['state']=result['shape_status']
        results.append(result)
    return results


def run_check(engine,job,run,raw):
    started=time.monotonic();digest=hashlib.sha256(raw).hexdigest()
    previous=run.get('pixel_text') or {}
    if previous.get('version')==VERSION and previous.get('image_sha256')==digest and previous.get('status')=='COMPLETED':return
    audit=dict(version=VERSION,image_sha256=digest,status='RUNNING',regions=[],api_calls=0)
    run['pixel_text']=audit;engine.checkpoint(job['id'],run)
    try:
        saved=run.get('text_ocr') or {}
        if saved.get('image_sha256')==digest and saved.get('regions'):
            regions=copy.deepcopy(saved['regions']);audit['detector_reused']=True
        else:
            detection=text_ocr.local_ocr(engine.s,raw,run['observation'])
            regions=detection['regions'];audit['detector_reused']=False
            audit['detection_summary']={k:v for k,v in detection.items() if k!='regions'}
        # Preserve raw evidence, never replace the OCR text with inferred spelling.
        audit['detector_regions']=regions
        audit['region_diagnostics']=[]
        audit['regions']=inspect_regions(raw,regions,engine.s.integer('PIXEL_TEXT_MAX_REGIONS',48),audit['region_diagnostics'])
        audit.update(status='COMPLETED',candidate_count=len(regions),processed_count=len(audit['regions']))
    except (OSError,RuntimeError,ValueError,KeyError,TimeoutError,subprocess.TimeoutExpired) as exc:
        audit.update(status='UNAVAILABLE',error='원본 획 대조 미완료 · 기존 모델 검사 유지')
    audit['seconds']=round(time.monotonic()-started,2);engine.checkpoint(job['id'],run)


def attach(run):
    observation=run['analysis_observation'];objects=observation['objects']
    existing={o['id'] for o in objects}
    for r in (run.get('pixel_text') or {}).get('regions',[]):
        if not (r.get('blur_observed') or r.get('shape_conflict')) or r['id'] in existing:continue
        x,y,z,b=r['rect']
        note='원본 픽셀의 문자 획 경계가 넓게 번짐. 전사 성공 여부와 독립된 품질 결함.' if r.get('blur_observed') else 'OCR 전사와 로컬 자모 모양 대조가 다름. shape_text는 교정문이 아니라 픽셀 형태 후보이며 철자 정상 여부는 별도로 검사.'
        if r.get('shape_confirmed'):note+=' 원본과 후보 글꼴을 단어/전사 힌트 없이 독립 비교한 결과 변경된 음절 형태가 일치했다. 이 형태 전사를 기준으로 오탈자를 검사하되 획 품질·정확한 사실관계와는 구분한다.'
        from .imaging import cell_rect
        contextual=[]
        for original in run.get('observation',{}).get('objects',[]):
            rects=original.get('rects') or [cell_rect(c) for c in original.get('cell_ids',[])]
            if original.get('text') and any(text_ocr.overlap(r['rect'],a)>.3 for a in rects):
                distance=min(abs((a[0]+a[2])/2-(x+z)/2)+abs((a[1]+a[3])/2-(y+b)/2) for a in rects)
                contextual.append((distance,original['label']))
        label=min(contextual)[1]+' · 원본 획 대조' if contextual else '원본 문자 획 대조 영역'
        objects.append(dict(id=r['id'],label=label,description=note,text=r.get('shape_text') or r['detector_text'],first_text=r['detector_text'],quality='UNCERTAIN' if r.get('blur_observed') else 'CLEAR',
            cell_ids=[f'R{min(12,int((y+b)/2*12)+1):02}C{min(12,int((x+z)/2*12)+1):02}'],rects=[r['rect']],text_legibility='DEGRADED' if r.get('blur_observed') else 'CLEAR',transcription_inferred=False,
            visual_concerns=note,pixel_text_region=True,pixel_evidence={k:r.get(k) for k in ('detector_text','shape_text','shape_confirmed','metrics','shape_checks')}))


def protect(run,rows,ids):
    from .rules import validate_batch
    for r in (run.get('pixel_text') or {}).get('regions',[]):
        if not r.get('blur_observed'):continue
        for rid in set(ids).intersection(TEXT_RULES):
            matches=[row for row in rows if row['rule_id']==rid and r['id'] in row.get('evidence_ids',[])]
            reason='원본 문자 영역의 획 경계가 넓게 번져 있습니다. OCR 인식 실패와 별개로 원본 픽셀에서 가독성 저하를 측정했습니다.'
            if not matches:
                matches=validate_batch({'results':[dict(rule_id=rid,instance_id=r['id'],status='FAIL',observation='원본 문자 흐림',reason=reason,evidence_quality='CLEAR',cell_ids=[],reference_ids=[],recommended_action='선명한 원본 글자로 재조판하세요.')]},[rid],run['reference_snapshot'],None,'system/pixel-text',pack=run['rule_pack'])
                rows.extend(matches)
            for row in matches:
                if row['status']=='ERROR':continue
                row.update(status='FAIL',reason=reason,error_type='VISUAL_TEXT_DEFECT',evidence_quality='CLEAR',evidence_ids=[r['id']],rects=[r['rect']],cell_ids=[],visual_issue=True,document_review=False,target_presence='PRESENT',
                           pixel_text_evidence=r,location_evidence={'status':'VERIFIED_REGION','rects':[r['rect']],'method':'local-text-pixels'})
    for row in rows:
        evidence=next((r for r in (run.get('pixel_text') or {}).get('regions',[]) if r['id'] in row.get('evidence_ids',[])),None)
        if evidence:
            from .text_location import cells_for_rects
            if evidence.get('shape_conflict') and not evidence.get('shape_confirmed') and not evidence.get('blur_observed') and row['status'] in ('FAIL','PASS'):
                row.update(status='REVIEW',evidence_quality='UNCERTAIN',error_type='OCR_MISMATCH',review_basis='READING_LIMIT',
                           reason='OCR 전사와 획 형태 후보가 다르지만 독립 비교로 확인되지 않았습니다. 원본 오탈자 여부는 미확정입니다.')
            row.update(pixel_text_evidence=evidence,rects=[evidence['rect']],cell_ids=cells_for_rects([evidence['rect']]),location_unresolved=False,location_evidence={'status':'VERIFIED_REGION','rects':[evidence['rect']],'method':'local-text-pixels'})
    return rows
