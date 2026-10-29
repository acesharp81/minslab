"""Local, conservative comparator for flat, upright printed Taegeukgi diagrams.
No model verdicts, fixed sample coordinates, network calls, or implicit approval.
Only four trigrams' three-line patterns/positions are checked, not the whole flag.
"""
import io
import math
import cv2
import numpy as np
from PIL import Image

VERSION='trigrams-v1'
SOURCE='https://www.guri.go.kr/www/contents.do?key=461'
REFERENCE={'version':'2026-10-29','url':SOURCE,'name':'구리시 · 국기의 제작 / 괘의 작도',
           'scope':'정면·수평 인쇄 도안의 4괘 획 구성과 위치. 색도·비율·태극 곡선·법적 적합성은 미검사.'}
PATTERNS={(1,1,1):'건',(2,2,2):'곤',(2,1,2):'감',(1,2,1):'리'}
CORNERS=[('왼쪽 위',-1,-1,'건'),('오른쪽 위',1,-1,'감'),('왼쪽 아래',-1,1,'리'),('오른쪽 아래',1,1,'곤')]


def _read(patch,diameter,threshold):
    # Require neutral dark ink; saturated blue/red are not trigram strokes.
    ink=((patch.max(2)<threshold)&(np.ptp(patch.astype(int),axis=2)<55)).astype('uint8')
    count,labels,stats,centers=cv2.connectedComponentsWithStats(ink,8)
    parts=[]
    for k in range(1,count):
        x,y,w,h,area=stats[k]
        if area<max(5,diameter**2*.002):continue
        if x<1 or y<1 or x+w>=patch.shape[1]-1 or y+h>=patch.shape[0]-1:return None
        ys,xs=np.where(labels==k);points=np.column_stack([xs,ys]).astype(float)
        eigen,vectors=np.linalg.eigh(np.cov(points.T));direction=vectors[:,-1]
        if eigen[0]<=0 or eigen[1]/eigen[0]<4:return None
        parts.append((points,direction,points.mean(0)))
    if not 3<=len(parts)<=6:return None
    direction=max(parts,key=lambda p:len(p[0]))[1]
    if direction[0]<0:direction=-direction
    normal=np.array([-direction[1],direction[0]])
    if any(abs(np.dot(p[1],direction))<.96 for p in parts):return None
    ordered=sorted(parts,key=lambda p:np.dot(p[2],normal));lines=[]
    for p in ordered:
        if not lines or abs(np.dot(p[2]-lines[-1][0][2],normal))>diameter*.055:lines.append([p])
        else:lines[-1].append(p)
    if len(lines)!=3 or any(len(row)>2 for row in lines):return None
    spans=[];thickness=[];offsets=[]
    for row in lines:
        pts=np.concatenate([p[0] for p in row]);along=pts@direction;across=pts@normal
        spans.append(float(np.ptp(along)));thickness.append(float(np.ptp(across)));offsets.append(float(across.mean()))
        if len(row)==2:
            segments=sorted([(float((p[0]@direction).min()),float((p[0]@direction).max())) for p in row])
            gap=segments[1][0]-segments[0][1]
            if not .02*diameter<gap<.16*diameter:return None
            lengths=[b-a for a,b in segments]
            if min(lengths)/max(lengths)<.65:return None
    if min(spans)/max(spans)<.85 or not .38*diameter<min(spans)<.63*diameter:return None
    if max(thickness)/min(thickness)>1.6 or not .035*diameter<min(thickness)<.12*diameter:return None
    spacing=np.diff(offsets)
    if min(spacing)/max(spacing)<.8 or not .075*diameter<min(spacing)<.19*diameter:return None
    pattern=tuple(len(row) for row in lines)
    if pattern not in PATTERNS:return None
    angle=abs(math.degrees(math.atan2(direction[1],direction[0])))
    if not 45<angle<68:return None
    return {'name':PATTERNS[pattern],'pattern':list(pattern),'angle':round(angle,1)}


def inspect(raw):
    im=Image.open(io.BytesIO(raw)).convert('RGB');im.thumbnail((1800,1800));rgb=np.array(im)
    h,w=rgb.shape[:2];r,g,b=[rgb[:,:,i].astype(int) for i in range(3)]
    red=(r>130)&(r>g*1.5)&(r>b*1.4);blue=(b>75)&(b>r*1.4)&(b>g*1.1)
    count,labels,stats,_=cv2.connectedComponentsWithStats((red|blue).astype('uint8'),8)
    flags=[]
    for k in range(1,count):
        x,y,cw,ch,area=map(int,stats[k]);d=(cw+ch)/2
        if d<32 or not .92<cw/ch<1.09 or not .70<area/(cw*ch)<.87:continue
        region=labels[y:y+ch,x:x+cw]==k
        if not .3<(red[y:y+ch,x:x+cw]&region).sum()/area<.7:continue
        # Colour footprint must fill a disk, not text or disconnected blobs.
        yy,xx=np.mgrid[0:ch,0:cw];disk=((xx-(cw-1)/2)**2+(yy-(ch-1)/2)**2)<(d*.47)**2
        if (region&disk).sum()/disk.sum()<.94:continue
        cx,cy=x+cw/2,y+ch/2
        panel=[cx-d*1.55,cy-d, cx+d*1.55,cy+d]
        if panel[0]<0 or panel[1]<0 or panel[2]>w or panel[3]>h:continue
        readings=[]
        for position,sx,sy,expected in CORNERS:
            px,py=cx+sx*d*.75,cy+sy*d*.51;half=d*.43
            x0,y0,x1,y1=map(round,(px-half,py-half,px+half,py+half))
            patch=rgb[y0:y1,x0:x1]
            # White field and threshold consensus are essential to confidence.
            white=(patch.min(2)>205)&(np.ptp(patch.astype(int),axis=2)<30)
            values=[_read(patch,d,t) for t in (105,135,165)] if white.mean()>.6 else []
            valid=[v for v in values if v]
            names=[v['name'] for v in valid]
            stable=next((name for name in names if names.count(name)>=2),None)
            result=next((v for v in valid if v['name']==stable),None) if stable else None
            readings.append({'position':position,'expected':expected,'observed':result['name'] if result else None,
                'pattern':result['pattern'] if result else None,'rect':[x0/w,y0/h,x1/w,y1/h],
                'match':result['name']==expected if result else None})
        # Require 3 recognisable trigrams to distinguish flags from circular logos.
        if sum(t['observed'] is not None for t in readings)<3:continue
        flags.append({'rect':[panel[0]/w,panel[1]/h,panel[2]/w,panel[3]/h],'trigrams':readings,
            'status':'UNCERTAIN' if any(t['observed'] is None for t in readings) else 'MATCH' if all(t['match'] for t in readings) else 'MISMATCH'})
    flags.sort(key=lambda f:(round(f['rect'][1]*h/25),f['rect'][0]))
    for i,f in enumerate(flags,1):f.update(id=f'local-flag-{i}',label=f'태극기 {i} (위→아래, 왼쪽→오른쪽)')
    return {'version':VERSION,'reference':REFERENCE,'flags':flags,'api_calls':0,'tokens':0,
        'limitation':'정면·수평 인쇄 도안만 비교합니다. 미검출은 정상 판정이 아닙니다. 퀴즈의 오답 보기일 수 있으므로 제작 의도를 확인하세요.'}


def findings(checks,selected,pack):
    from .rules import placeholder
    rules={s['rule_id']:s for s in pack['steps']};rows=[]
    for flag in checks['flags']:
        text='; '.join(f"{t['position']}: {t['observed'] or '판독 불가'} (기준 {t['expected']})" for t in flag['trigrams'])
        for rid in ('H-04-h','H-04-i'):
            if rid not in selected:continue
            status='REVIEW' if flag['status']=='UNCERTAIN' else 'FAIL' if rid=='H-04-i' and flag['status']=='MISMATCH' else 'PASS'
            reason=('세 줄의 연속/분절 패턴 확인. ' if rid=='H-04-h' else '괘 배치가 공식 기준과 일치. ' if status=='PASS' else '공식 배치와 다름. 퀴즈라면 의도된 오답 후보. ' if status=='FAIL' else '획이 불분명하여 배치 확정 불가. ')+text
            row=placeholder(rid,status,reason)
            row.update(instance_id=flag['id'],object_label=flag['label'],evidence_ids=[flag['id']],observation=text,
                evidence_quality='UNCERTAIN' if flag['status']=='UNCERTAIN' else 'CLEAR',rects=[flag['rect']],
                model='local/'+VERSION,rule_version=rules[rid]['version'],visual_issue=status in ('FAIL','REVIEW'),
                comparison=flag,technical_reference=REFERENCE,document_review=False,
                recommended_action='퀴즈의 오답 보기인지 확인. 일반 홍보 도안이면 표시된 괘 배치 수정.' if status=='FAIL' else '이 결과는 4괘만 검사합니다. 태극 문양·색도 등은 별도 확인.')
            rows.append(row)
    return rows
