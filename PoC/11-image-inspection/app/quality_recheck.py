"""Plan explicit, bounded crop reinspection without assuming the first read is right.

Coverage gaps are not findings. This module does not call providers or certify
normality. Its plan can be built for old runs without modifying their history.
"""
import re
from . import text_ocr, text_routing
from .imaging import cell_rect

VERSION='quality-recheck-v1'
HAND_RULES={f'D-02-{c}' for c in 'cdefghi'}
TEXT_RULES={'H-06-b','D-02-l'}


def focus(obj):
    description=obj.get('label','')+' '+obj.get('description','')
    if obj.get('hands') or re.search(r'손가락|왼손|오른손|양손|손짓|손동작|브이|경례',description):return 'anatomy'
    if obj.get('text') or obj.get('text_legibility') in ('CLEAR','DEGRADED','UNREADABLE'):return 'text'
    return None


def bounds(rects):
    return [min(r[0] for r in rects),min(r[1] for r in rects),max(r[2] for r in rects),max(r[3] for r in rects)]


def measured_text_rect(obj, run):
    """Use a uniquely bound complete OCR line, never a fragment of a long block."""
    objects=run.get('observation',{}).get('objects',[])
    found=[]
    for region in (run.get('pixel_text') or {}).get('detector_regions',[]):
        if not text_ocr.valid_rect(region.get('rect',[])):continue
        linked=text_routing.linked_objects(region,objects)
        if len(linked)!=1 or linked[0]['id']!=obj['id']:continue
        relation=text_routing.reading_relation(region,obj)
        # Geometry is independent evidence. A different, similarly sized line
        # is exactly the case needing a tight crop, not a reason to discard it.
        literal=text_ocr.normalized(region.get('text'))
        whole=text_ocr.normalized(obj.get('text'))
        complete_candidate=relation=='EQUAL' or (relation=='DIFFERENT' and literal and whole
            and .75<=len(literal)/len(whole)<=1.25)
        if complete_candidate:found.append(region['rect'])
    return found[0] if len(found)==1 else None


def plan(run, max_objects=6, max_calls=2):
    previous={r['object_id']:r for r in (run.get('verification') or {}).get('results',[])}
    entries=[]
    for obj in run.get('observation',{}).get('objects',[]):
        domain=focus(obj)
        if not domain:continue
        rects=text_routing.object_rects(obj)
        cells=obj.get('cell_ids',[])
        try:
            for cell in cells:cell_rect(cell)
        except ValueError:cells=[]
        located=bool(rects and cells)
        prior=previous.get(obj['id'],{})
        structured=bool(prior.get('hands') if domain=='anatomy' else prior.get('glyph_checks'))
        if prior.get('status')!='COMPLETED':state='NOT_RECHECKED'
        elif prior.get('coverage')!='COMPLETE':state='PARTIAL'
        elif not structured:state='STRUCTURE_NOT_RECORDED'
        else:state='PREVIOUSLY_CHECKED'
        # Complete prior "CLEAR" is selectable too; it is not a permanent exemption.
        measured=measured_text_rect(obj,run) if domain=='text' else None
        base=measured or (bounds([cell_rect(c) for c in cells]) if cells else None)
        preview=None
        if base:
            x,y,z,b=base
            dx=max(.015,(z-x)*.12) if measured else (1.25 if domain=='text' else 1)/12
            dy=max(.015,(b-y)*.12) if measured else (.3 if domain=='text' else 1)/12
            preview=[max(0,x-dx),max(0,y-dy),min(1,z+dx),min(1,b+dy)]
        entries.append(dict(object_id=obj['id'],label=obj.get('label',obj['id']),focus=domain,
                            state=state,selectable=located,rect=bounds(rects) if rects else None,
                            measured_rect=measured,preview_rect=preview,
                            priority={'PARTIAL':0,'NOT_RECHECKED':1,'STRUCTURE_NOT_RECORDED':1,'PREVIOUSLY_CHECKED':2}[state]))
    entries.sort(key=lambda e:(e['priority'],e['object_id']))
    # Alternate domains so text cannot use all suggested slots before any hand.
    pools={d:[e for e in entries if e['focus']==d and e['selectable']] for d in ('anatomy','text')}
    recommended=[]
    while len(recommended)<max_objects and any(pools.values()):
        for domain in ('anatomy','text'):
            if pools[domain] and len(recommended)<max_objects:recommended.append(pools[domain].pop(0)['object_id'])
    return dict(version=VERSION,entries=entries,recommended_ids=recommended,max_objects=max_objects,max_calls=max_calls,
                note='저장된 위치에서 손 구조·글자 획을 새로 판독합니다. 미검사·부분 확인은 오류가 아닙니다. 처음부터 발견되지 않은 객체는 목록에 없을 수 있습니다.')
