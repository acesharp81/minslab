"""Conservative color-mask comparison of Taegeuk disks, not whole-flag approval.

Uses the approved image and detected components, never fixture coordinates.
Mirrored disks remain REVIEW: a flag's reverse face needs separate assessment.
"""
import hashlib
from pathlib import Path
import cv2
import numpy as np
from .imaging import cell_rect

VERSION='taegeuk-disk-orientation-v1'


def components(raw):
    im=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if im is None:return []
    height,width=im.shape[:2];b,g,r=[im[:,:,i].astype(float) for i in range(3)]
    red=(r>90)&(r>g*1.35)&(r>b*1.25);blue=(b>55)&(b>r*1.3)&(b>g*1.02)
    mask=cv2.morphologyEx((red|blue).astype('uint8'),cv2.MORPH_CLOSE,np.ones((3,3),'uint8'))
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8);out=[]
    for i in range(1,n):
        x,y,w,h,area=stats[i];where=labels[y:y+h,x:x+w]==i
        nr=(red[y:y+h,x:x+w]&where).sum();nb=(blue[y:y+h,x:x+w]&where).sum()
        if w<30 or h<30 or not .55<w/h<1.8 or not .2<nr/max(1,nr+nb)<.8 or area/(w*h)<.5:continue
        patch=np.zeros((h,w),np.int8)
        patch[red[y:y+h,x:x+w]&where]=1;patch[blue[y:y+h,x:x+w]&where]=-1
        out.append(dict(rect=[x/width,y/height,(x+w)/width,(y+h)/height],pixels=int(w*h),mask=cv2.resize(patch,(96,96),interpolation=cv2.INTER_NEAREST)))
    return out


def compare(patch,reference):
    scores=[]
    for flipped in (False,True):
        template=np.fliplr(reference) if flipped else reference;best=(0.,0)
        for angle in range(-25,26):
            rotated=cv2.warpAffine(template,cv2.getRotationMatrix2D((47.5,47.5),angle,1),(96,96),flags=cv2.INTER_NEAREST)
            valid=(patch!=0)&(rotated!=0)
            if valid.sum()<.6*max((patch!=0).sum(),(rotated!=0).sum()):continue
            score=float(((patch==rotated)&valid).sum()/max(1,valid.sum()))
            if score>best[0]:best=(score,angle)
        scores.append(best)
    direct,mirrored=scores
    return dict(normal_score=round(direct[0],4),mirrored_score=round(mirrored[0],4),
        normal_angle=direct[1],mirrored_angle=mirrored[1],
        mirrored=mirrored[0]>=.94 and mirrored[0]-direct[0]>=.12)


def inspect(raw,observation,references,data_dir):
    ref=next((r for r in references if r.get('status')=='APPROVED' and r.get('image_file') and '태극기' in r['name']),None)
    result={'version':VERSION,'checks':[],'scope':'중앙 태극의 적·청 영역 방향 비교. 국기 뒷면·괘 배치·제작 의도는 별도 검사. 점수는 색상 일치율이며 확률이 아님.'}
    if not ref:return result
    path=Path(data_dir)/'references'/Path(ref['image_file']).name
    if not path.is_file():return result
    reference_raw=path.read_bytes()
    if hashlib.sha256(reference_raw).hexdigest()!=ref.get('image_hash'):return result
    templates=components(reference_raw)
    if not templates:return result
    template=max(templates,key=lambda x:x['pixels'])['mask'];targets=components(raw)
    for obj in observation['objects']:
        if '태극기' not in obj['label'] or any(t in obj['label'] for t in ('깃대','문구','제목')):continue
        boxes=obj.get('rects') or [cell_rect(c) for c in obj.get('cell_ids',[])]
        matches=[]
        for target in targets:
            a=target['rect'];cx,cy=(a[0]+a[2])/2,(a[1]+a[3])/2
            if any(b[0]<=cx<=b[2] and b[1]<=cy<=b[3] for b in boxes):matches.append(target)
        if len(matches)!=1:continue # Ambiguous or clipped targets are not measured.
        target=matches[0]
        result['checks'].append(dict(object_id=obj['id'],rect=target['rect'],reference_id=ref['id'],reference_hash=ref['image_hash'],**compare(target['mask'],template)))
    return result
