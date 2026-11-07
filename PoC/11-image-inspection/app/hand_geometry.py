"""Conservative protrusion count for flat, upright open-hand icons only.

Photographs, shaded hands, fists, clipped contours and crowded scenes abstain.
Counts are measured contour evidence, not a certification of anatomy or intent.
"""
import io
import cv2
import numpy as np
from PIL import Image

VERSION='flat-hand-protrusions-v1'

def measure(image):
    a=np.asarray(image.convert('RGB'));height,width=a.shape[:2]
    if min(height,width)<100:return None
    colors,counts=np.unique(a.reshape(-1,3),axis=0,return_counts=True)
    bg=colors[counts.argmax()]
    if min(bg)<220 or counts.max()/a.shape[0]/a.shape[1]<.25:return None
    candidates=[i for i in np.argsort(counts)[::-1][:12] if int(colors[i].max())-int(colors[i].min())>30]
    if not candidates:return None
    index=candidates[0];color=colors[index]
    hsv=cv2.cvtColor(a,cv2.COLOR_RGB2HSV);hue=int(cv2.cvtColor(np.uint8([[color]]),cv2.COLOR_RGB2HSV)[0,0,0])
    delta=abs(hsv[:,:,0].astype(int)-hue)
    mask=np.uint8((np.minimum(delta,180-delta)<12)&(hsv[:,:,1]>35)&(hsv[:,:,2]>60))*255
    if not mask.any() or counts[index]/np.count_nonzero(mask)<.75:return None
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contour=max(contours,key=cv2.contourArea);area=cv2.contourArea(contour)
    if area<2000 or area/np.count_nonzero(mask)<.9:return None
    x,y,w,h=cv2.boundingRect(contour)
    if min(x,y,width-x-w,height-y-h)<3 or not 1.3<h/w<3.2:return None
    rows=[]
    for yy in range(y+int(h*.10),y+int(h*.48)):
        active=mask[yy]>0;edges=np.diff(np.r_[False,active,False].astype(int))
        spans=list(zip(np.where(edges==1)[0],np.where(edges==-1)[0]))
        # Do not silently discard small extra components to manufacture a count.
        if not 4<=len(spans)<=7:continue
        sizes=[b-a for a,b in spans]
        if min(sizes)<h*.025 or max(sizes)>h*.16 or max(sizes)/min(sizes)>2.5:continue
        rows.append((yy,spans))
    if not rows:return None
    count=max(len(v) for _,v in rows);band=[(yy,v) for yy,v in rows if len(v)==count]
    groups=[]
    for entry in band:
        if not groups or entry[0]>groups[-1][-1][0]+1:groups.append([])
        groups[-1].append(entry)
    band=max(groups,key=len)
    if len(band)<max(8,h*.035):return None
    yy,spans=band[len(band)//2];left,right=spans[0][0],spans[-1][1]
    defects=cv2.convexityDefects(contour,cv2.convexHull(contour,returnPoints=False))
    if defects is None:return None
    thumbs=[]
    for start,end,far,depth in defects[:,0]:
        p,q,v=(contour[i,0].astype(float) for i in (start,end,far))
        denom=np.linalg.norm(p-v)*np.linalg.norm(q-v)
        if not denom:continue
        angle=float(np.degrees(np.arccos(np.clip(np.dot(p-v,q-v)/denom,-1,1))))
        lateral=min(p[0],q[0])<left-w*.15 or max(p[0],q[0])>right+w*.15
        if 40<angle<100 and depth/256>h*.08 and v[1]>yy and lateral:
            thumbs.append([p.tolist(),q.tolist(),v.tolist()])
    if len(thumbs)!=1:return None
    return {'version':VERSION,'upper_protrusions':count,'lateral_protrusions':1,'visible_protrusions':count+1,
            'measurement_band':[[int(a)/width,band[0][0]/height,int(b)/width,(band[-1][0]+1)/height] for a,b in spans],
            'contour_rect':[x/width,y/height,(x+w)/width,(y+h)/height],
            'scope':'평면·정면·펼친 손 도식의 외곽 돌출부만 측정. 인체 정상 인증 아님.'}

def inspect(run,raw):
    audit=run.get('hand_audit') or {};audit['local_geometry']=[]
    image=Image.open(io.BytesIO(raw)).convert('RGB')
    for location in audit.get('locations',[]):
        rect=location.get('global_rect')
        if not rect:continue
        box=[round(rect[0]*image.width),round(rect[1]*image.height),round(rect[2]*image.width),round(rect[3]*image.height)]
        crop=image.crop(box)
        try:m=measure(crop)
        except (ValueError,cv2.error):m=None
        if not m:continue
        local=m['contour_rect'];global_rect=[(box[0]+local[0]*crop.width)/image.width,(box[1]+local[1]*crop.height)/image.height,
            (box[0]+local[2]*crop.width)/image.width,(box[1]+local[3]*crop.height)/image.height]
        evidence=f"단색 손 도안의 외곽에서 위쪽 돌출부 {m['upper_protrusions']}개와 옆 돌출부 1개, 합계 {m['visible_protrusions']}개를 측정했습니다. "
        evidence+=('손가락 중복인지 의도적인 도식인지 확인이 필요합니다.' if m['visible_protrusions']>5 else '이 측정에서는 추가 돌출부를 발견하지 않았습니다. 다른 구조 결함이나 정상 여부를 확정하지 않습니다.')
        audit['local_geometry'].append(dict(object_id=location['object_id'],model='system/hand-contour',coverage='VISIBLE_PARTS',
            summary=evidence,measurement=m,source='LOCAL_PIXELS',traces=[],crop_rect=rect,
            accepted_concerns=[dict(kind='EXTRA_DIGIT',evidence=evidence,alternative_explanation='의도적인 다지 도식일 수 있음',confidence='CLEAR',global_rect=global_rect)] if m['visible_protrusions']>5 else []))
