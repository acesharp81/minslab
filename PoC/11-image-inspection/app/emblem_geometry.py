"""Measured component comparison for clear, flat, single-colour circular emblems.

Uses approved reference pixels and observed object locations, never answer keys.
Unsupported shapes, colour/pose ambiguity and tiny images receive no verdict.
"""
import copy
import hashlib
import re
from pathlib import Path
import cv2
import numpy as np
from .imaging import cell_rect
from .verification import reference_candidates
from .rules import validate_batch, PACK

VERSION='flat-emblem-components-v1'


def decode(raw):
    image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if image is not None and max(image.shape[:2])>1800:
        factor=1800/max(image.shape[:2]);image=cv2.resize(image,(round(image.shape[1]*factor),round(image.shape[0]*factor)),interpolation=cv2.INTER_AREA)
    return image


def components(raw,hue):
    image=decode(raw)
    if image is None:return []
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV);delta=np.abs(hsv[:,:,0].astype(float)-hue)
    mask=((np.minimum(delta,180-delta)<8)&(hsv[:,:,1]>100)&(hsv[:,:,2]>50)).astype(np.uint8)
    found=[]
    for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour);area=cv2.contourArea(contour)
        if min(w,h)<100 or not .94<w/h<1.06 or area/(w*h)<.72:continue
        if 4*np.pi*area/max(1,cv2.arcLength(contour,True)**2)<.88:continue
        filled=np.zeros_like(mask);cv2.drawContours(filled,[contour],-1,1,-1)
        holes=(filled&~mask)[y:y+h,x:x+w]
        n,labels,stats,_=cv2.connectedComponentsWithStats(holes,8);parts=[]
        for label,(px,py,pw,ph,pixels) in enumerate(stats[1:],1):
            if pixels<w*h*.004:continue
            # Clipped/open shapes cannot be treated as complete components.
            if px<=1 or py<=1 or px+pw>=w-1 or py+ph>=h-1:continue
            colour=hsv[y:y+h,x:x+w][labels==label]
            if np.mean((colour[:,1]<35)&(colour[:,2]>200))<.98:
                parts=[];break  # Multicolour/texture comparison is outside this method.
            shape=cv2.resize((labels[py:py+ph,px:px+pw]==label).astype('uint8'),(48,48),interpolation=cv2.INTER_NEAREST)
            parts.append(dict(box=[px/w,py/h,(px+pw)/w,(py+ph)/h],shape=shape))
        if not 2<=len(parts)<=8:continue
        ink=image[y:y+h,x:x+w][(mask[y:y+h,x:x+w]&filled[y:y+h,x:x+w])>0]
        if np.max(np.percentile(ink,75,axis=0)-np.percentile(ink,25,axis=0))>8:continue
        found.append(dict(rect=[x/image.shape[1],y/image.shape[0],(x+w)/image.shape[1],(y+h)/image.shape[0]],parts=parts,colour=np.median(ink,axis=0)))
    return found


def compare(target,reference):
    if np.max(np.abs(target['colour']-reference['colour']))>12:return 'UNRESOLVED'
    matches=[];used=set()
    for part in target['parts']:
        candidates=[]
        for index,other in enumerate(reference['parts']):
            if index in used or max(abs(a-b) for a,b in zip(part['box'],other['box']))>.025:continue
            a,b=part['shape'].astype(bool),other['shape'].astype(bool)
            score=float((a&b).sum()/max(1,(a|b).sum()))
            if score>=.9:candidates.append((score,index))
        if candidates:
            score,index=max(candidates);used.add(index);matches.append(score)
    actual,expected=len(target['parts']),len(reference['parts'])
    if len(matches)==actual==expected:return 'MATCH'
    # Only a clean subset/superset difference is eligible; arbitrary similarity
    # or a different logo is not converted to an error.
    if actual!=expected and len(matches)==min(actual,expected) and len(matches)>=2:return 'MISMATCH'
    return 'UNRESOLVED'


def inspect(raw,observation,references,data_dir):
    result=dict(version=VERSION,checks=[],scope='정면 단색 원형 문양의 내부 분리 도형 구성·배치만 비교')
    image_hash=hashlib.sha256(raw).hexdigest();cache={}
    for obj in observation.get('objects',[]):
        if obj.get('quality')!='CLEAR':continue
        if obj.get('text') or obj.get('text_legibility') in ('CLEAR','DEGRADED','UNREADABLE'):continue
        refs=[r for r in reference_candidates(obj,references,image_hash) if r['kind']=='official-emblems']
        if len(refs)!=1:continue
        ref=refs[0]
        if ref['id'] not in cache:
            path=Path(data_dir)/'references'/Path(ref['image_file']).name
            if not path.is_file():continue
            source=path.read_bytes()
            if hashlib.sha256(source).hexdigest()!=ref.get('image_hash'):continue
            image=decode(source)
            if image is None:continue
            hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV);pixels=hsv[:,:,0][(hsv[:,:,1]>100)&(hsv[:,:,2]>60)]
            if not pixels.size:continue
            hue=int(np.bincount(pixels,minlength=180).argmax())
            templates=components(source,hue)
            if len(templates)!=1:continue
            cache[ref['id']]=(templates[0],components(raw,hue))
        template,targets=cache[ref['id']]
        boxes=obj.get('rects') or [cell_rect(c) for c in obj.get('cell_ids',[])]
        nearby=[t for t in targets if any(a[0]<=(t['rect'][0]+t['rect'][2])/2<=a[2] and a[1]<=(t['rect'][1]+t['rect'][3])/2<=a[3] for a in boxes)]
        if len(nearby)!=1:continue
        target=nearby[0];status=compare(target,template)
        if status=='UNRESOLVED':continue
        result['checks'].append(dict(object_id=obj['id'],reference_id=ref['id'],reference_hash=ref['image_hash'],
            rect=target['rect'],status=status,reference_components=len(template['parts']),observed_components=len(target['parts']),
            reference_parts=[p['box'] for p in template['parts']],observed_parts=[p['box'] for p in target['parts']]))
    return result


def protect(run,rows,ids):
    rid='H-07-b'
    checks=run.get('emblem_geometry',{}).get('checks',[])
    if not checks:return rows
    # Reconcile only the *same count claim*, not unrelated defects on this logo.
    # A partial geometric match is insufficient to mark another action PASS.
    for check in checks:
        if check['status']!='MATCH':continue
        for row in rows:
            reason=row.get('reason','')
            if row['rule_id'] not in set(ids).intersection({'D-02-m','D-02-o'}) or row['status']!='FAIL' or check['object_id'] not in row.get('evidence_ids',[]):continue
            if not re.search(r'(막대|분리 도형|내부 도형).{0,30}(개|수)',reason) or re.search(r'문자|글자|철자|색상|색깔|회전|좌우',reason):continue
            prior=copy.deepcopy(row)
            row.update(status='REVIEW',model='system/emblem-evidence-reconciliation',review_basis='READING_LIMIT',error_type='NONE',visual_issue=False,document_review=True,
                reason='원본·기준의 도형 구성과 배치가 일치하여 모델의 개수 불일치 설명은 채택하지 않았습니다. 이 행동의 나머지 판단은 검토 필요입니다.',
                emblem_geometry=check,model_verdicts_before_geometry=[prior])
    pack=run.get('rule_pack') or PACK;step=next((s for s in pack['steps'] if s['rule_id']==rid),None)
    if rid not in ids or not step or 'official-emblems' not in step['reference_requirements']:return rows
    objects={o['id']:o for o in run['observation']['objects']}
    for check in checks:
        obj=objects[check['object_id']]
        status='FAIL' if check['status']=='MISMATCH' else 'PASS'
        if step['review_policy']=='HUMAN_REQUIRED':status='REVIEW'
        reason=f"정면 단색 원형 문양의 내부 분리 도형: 기준 {check['reference_components']}개 / 원본 {check['observed_components']}개. "+('구성 요소가 다릅니다.' if check['status']=='MISMATCH' else '각 도형의 형태·상대 배치가 일치합니다.')
        prior=[r for r in rows if r['rule_id']==rid and obj['id'] in r.get('evidence_ids',[])]
        replacement=validate_batch({'results':[dict(rule_id=rid,instance_id=obj['id'],status=status,observation=obj['label'],reason=reason,
            evidence_quality='CLEAR',cell_ids=obj['cell_ids'],reference_ids=[check['reference_id']],recommended_action='측정 범위와 기준 도안을 확인하세요.')]},[rid],run['reference_snapshot'],None,'system/emblem-geometry',pack=pack)[0]
        replacement.update(evidence_ids=[obj['id']],rects=[check['rect']],emblem_geometry=check,model_verdicts_before_geometry=copy.deepcopy(prior),
            vision_model=run.get('observation_model'),error_type='FACT_OR_STYLE_ISSUE' if status=='FAIL' else 'NONE',review_basis='OBSERVED_ANOMALY' if status=='FAIL' else 'NONE',
            visual_issue=check['status']=='MISMATCH',document_review=False,location_unresolved=False,target_presence='PRESENT',evidence_status='VERIFIED',direct_comparisons=[],
            technical_reference={'name':VERSION})
        rows=[r for r in rows if r not in prior and not (r['rule_id']==rid and not r.get('evidence_ids') and r['status']=='NOT_APPLICABLE')]
        rows.append(replacement)
    return rows
