"""Bounded local candidates, never verdicts. No providers or external models.

A candidate is neither an image defect nor a successful inspection. Rectified
pixels are supplementary measurements; source coordinates/evidence are retained.
"""
import hashlib
import io
import json
import time
from collections import Counter

import cv2
import numpy as np
from PIL import Image
from . import pixel_text, text_ocr, text_routing

VERSION = 'artifact-candidates-v2'


def oriented_crop(image, region):
    w,h=image.size;rect=region['rect'];x,y,z,b=rect
    box=[int(x*w),int(y*h),int(np.ceil(z*w)),int(np.ceil(b*h))]
    if (box[2]-box[0])*(box[3]-box[1])>4_000_000 or max(box[2]-box[0],box[3]-box[1])>4096:raise ValueError('GEOMETRY_LIMIT')
    source=image.crop(box)
    points=region.get('polygon_px')
    if not points:
        return source, np.array([[1.,0,box[0]],[0,1.,box[1]],[0,0,1.]]), False
    pts=np.asarray(points,dtype=np.float32)
    if pts.shape!=(4,2) or not np.isfinite(pts).all():raise ValueError('INVALID_POLYGON')
    if np.any(pts<0) or np.any(pts[:,0]>w) or np.any(pts[:,1]>h):raise ValueError('INVALID_POLYGON')
    if not cv2.isContourConvex(pts) or abs(cv2.contourArea(pts))<16:raise ValueError('INVALID_POLYGON')
    # Do not trust a polygon pointing at a different label than its source bbox.
    if np.any(pts[:,0]<box[0]-2) or np.any(pts[:,0]>box[2]+2) or np.any(pts[:,1]<box[1]-2) or np.any(pts[:,1]>box[3]+2):raise ValueError('INVALID_POLYGON')
    rw=round(max(np.linalg.norm(pts[1]-pts[0]),np.linalg.norm(pts[2]-pts[3])))
    rh=round(max(np.linalg.norm(pts[3]-pts[0]),np.linalg.norm(pts[2]-pts[1])))
    if min(rw,rh)<12 or max(rw,rh)>4096 or rw*rh>4_000_000:raise ValueError('GEOMETRY_LIMIT')
    dest=np.float32([[0,0],[rw-1,0],[rw-1,rh-1],[0,rh-1]])
    matrix=cv2.getPerspectiveTransform(pts,dest)
    inverse=np.linalg.inv(matrix)
    crop=Image.fromarray(cv2.warpPerspective(np.asarray(image),matrix,(rw,rh),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE))
    return crop,inverse,True


def windows(image, maximum=6):
    """Overlapping windows; no assumed glyph count or inferred character boundaries."""
    width=min(image.width,max(24,3*image.height));stride=max(1,width//2)
    starts=sorted(set(list(range(0,max(1,image.width-width+1),stride))+[image.width-width]))
    if len(starts)>maximum:
        starts=[starts[round(i*(len(starts)-1)/(maximum-1))] for i in range(maximum)]
    for x in starts:yield [x,0,x+width,image.height]


def map_box(box,inverse,size):
    x,y,z,b=box;w,h=size
    pts=np.float32([[[x,y],[max(x,z-1),y],[max(x,z-1),max(y,b-1)],[x,max(y,b-1)]]])
    mapped=cv2.perspectiveTransform(pts,inverse)[0]
    return [max(0.,float(mapped[:,0].min())/w),max(0.,float(mapped[:,1].min())/h),
            min(1.,float(mapped[:,0].max()+1)/w),min(1.,float(mapped[:,1].max()+1)/h)]


def collect(raw, run, max_regions=48, max_windows=96):
    started=time.monotonic();image=Image.open(io.BytesIO(raw)).convert('RGB')
    pixel=run.get('pixel_text') or {};objects=run.get('observation',{}).get('objects',[])
    shapes={r.get('source_id'):r for r in pixel.get('regions',[])}
    entries=[];diagnostics=[];used=0
    selected=set(run.get('selected',[]))
    regions=pixel.get('detector_regions',[]) if not selected or selected.intersection(pixel_text.TEXT_RULES) else []
    for index,region in enumerate(regions):
        diag={'source_id':region.get('id'),'state':'MEASURED'};diagnostics.append(diag)
        if index>=max_regions:diag['state']='REGION_LIMIT';continue
        rect=region.get('rect',[])
        if not text_ocr.valid_rect(rect):diag['state']='INVALID_LOCATION';continue
        matches=text_routing.linked_objects(region,objects);signals=[];measurements=[];measured_count=0
        text=region.get('text','')
        if not text.strip():signals.append('DETECTED_UNREAD')
        if len(matches)==1 and text.strip() and text_routing.reading_relation(region,matches[0])=='DIFFERENT':signals.append('READING_DISAGREEMENT')
        if shapes.get(region.get('id'),{}).get('shape_conflict'):signals.append('SHAPE_CONFLICT')
        try:
            crop,inverse,rectified=oriented_crop(image,region)
            window_width=min(crop.width,max(24,3*crop.height))
            if (crop.width-window_width)/max(1,window_width//2)+1>6:diag['state']='WINDOW_SAMPLING_LIMIT'
            for box in windows(crop):
                if used>=max_windows:diag['state']='WINDOW_LIMIT';break
                used+=1;sample=crop.crop(box);metrics=pixel_text.measure(sample)
                if not metrics:continue
                measured_count+=1
                # No transcript-length gate. Noise/low confidence alone never count.
                trusted=region.get('source')=='paddle-detector' and (region.get('detection_score') or 0)>=.55
                spread=metrics['uniform_background'] and min(sample.size)>=20 and metrics['edge_strength']<1.5 and metrics['laplacian']<.02
                if trusted and spread:
                    source_rect=map_box(box,inverse,image.size)
                    if text_ocr.valid_rect(source_rect):
                        measurements.append({'rect':source_rect,'metrics':metrics,'rectified':rectified})
            if measurements:signals.append('LOCAL_BLUR_SIGNAL')
            if not measured_count and diag['state']=='MEASURED':diag['state']='INSUFFICIENT_PIXELS_OR_CONTRAST'
        except (ValueError,np.linalg.LinAlgError,cv2.error) as exc:
            diag['state']=str(exc) if str(exc) in ('INVALID_POLYGON','GEOMETRY_LIMIT') else 'GEOMETRY_UNAVAILABLE'
        if not signals:continue
        identity=json.dumps([region.get('id'),rect],sort_keys=True)
        entries.append(dict(candidate_id='ART-'+hashlib.sha256(identity.encode()).hexdigest()[:12],
            source_id=region.get('id'),object_ids=[o['id'] for o in matches],issue_family='TEXT_QUALITY',
            rect=rect,signals=signals,measurements=measurements,status='CANDIDATE_ONLY',automatic_fail=False,
            verify_with='existing_text_recheck',evidence='문자 탐지·전사·픽셀 신호의 확인 후보. OCR 실패와 이미지 결함은 별개입니다.'))
    selected=set(run.get('selected',[]))
    if not selected or selected.intersection({f'D-02-{c}' for c in 'cdefghi'}):
        for obj in objects:
            hands=[hand for hand in obj.get('hands',[]) if hand.get('visible_structure')=='ANOMALOUS' and hand.get('anomaly_evidence','').strip()]
            if not hands:continue
            rects=text_routing.object_rects(obj)
            if not rects:
                diagnostics.append({'source_id':obj['id'],'state':'HAND_LOCATION_UNRESOLVED'});continue
            entries.append(dict(candidate_id='ART-H-'+hashlib.sha256(obj['id'].encode()).hexdigest()[:12],object_ids=[obj['id']],
                issue_family='ANATOMY_OR_STRUCTURE',rects=rects,signals=['OBSERVED_HAND_ANOMALY'],
                status='CANDIDATE_ONLY',automatic_fail=False,verify_with='existing_crop_reinspection',
                evidence=' / '.join(dict.fromkeys(h['anomaly_evidence'] for h in hands)),
                location_scope='EXISTING_OBJECT_REGION',hands=hands))
    return dict(version=VERSION,status='COMPLETED',image_sha256=hashlib.sha256(raw).hexdigest(),
                candidates=entries,diagnostics=diagnostics,signals=dict(Counter(s for c in entries for s in c['signals'])),
                windows_processed=used,regions_total=len(regions),seconds=round(time.monotonic()-started,3),
                api_calls=0,mode='SHADOW',note='검출 후보 기록이며 오류 판정·검사 완료 건수가 아닙니다. 후보만으로 번호나 경고를 만들지 않습니다.')


def inspect(engine,job,run,raw):
    if not engine.s.flag('ARTIFACT_SCREEN_ENABLED',True):return
    # Cache includes the complete input evidence, never just the image hash.
    digest=hashlib.sha256(raw).hexdigest()
    key=hashlib.sha256(json.dumps([VERSION,digest,run.get('selected'),run.get('observation'),run.get('pixel_text'),
        engine.s.integer('ARTIFACT_MAX_REGIONS',48),engine.s.flag('ARTIFACT_RECHECK_ENABLED',False)],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if (run.get('artifact_screen') or {}).get('cache_key')==key:return
    try:
        audit=collect(raw,run,max_regions=max(1,min(48,engine.s.integer('ARTIFACT_MAX_REGIONS',48))))
        audit['mode']='ROUTING' if engine.s.flag('ARTIFACT_RECHECK_ENABLED',False) else 'SHADOW'
        audit['cache_key']=key;run['artifact_screen']=audit
    except (OSError,ValueError,RuntimeError,TypeError,KeyError,AttributeError,cv2.error):
        run['artifact_screen']=dict(version=VERSION,status='UNAVAILABLE',candidates=[],api_calls=0,note='로컬 후보 검사 미완료 · 이미지 결함 판정 아님')
    engine.checkpoint(job['id'],run)
