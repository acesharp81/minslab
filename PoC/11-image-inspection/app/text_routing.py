"""Keep unrecognized/disagreeing text candidates; spend only existing crop slots."""
import copy
import hashlib
import json
from collections import Counter
from . import text_ocr, text_selection
from .imaging import cell_rect

VERSION = 'text-routing-v2-union-binding'


def reading_relation(region, obj):
    """A detected line may be only one part of a scene text block."""
    literal=text_ocr.normalized(region.get('text'))
    whole=text_ocr.normalized(obj.get('text'))
    if literal and literal==whole:return 'EQUAL'
    if literal and whole and literal in whole:return 'FRAGMENT'
    return 'DIFFERENT'


def object_rects(obj):
    if obj.get('rects'):
        return [r for r in obj['rects'] if text_ocr.valid_rect(r)]
    out = []
    for cell in obj.get('cell_ids', []):
        try: out.append(cell_rect(cell))
        except ValueError: pass
    return out


def linked_objects(region, objects):
    """Geometry constrains matching; repeated identical words aren't unique IDs."""
    rect = region.get('rect', [])
    if not text_ocr.valid_rect(rect):
        return []
    spatial = [o for o in objects if spatial_match(rect,o)
               and (o.get('text') or o.get('text_legibility') in ('CLEAR', 'DEGRADED', 'UNREADABLE'))]
    exact = [o for o in spatial if text_ocr.normalized(o.get('text')) == text_ocr.normalized(region.get('text'))
             and region.get('text', '').strip() and not o.get('transcription_inferred')]
    # Transcript agreement must not choose between overlapping spatial targets.
    # An OCR correction could otherwise hide the very object that disagrees.
    if len(spatial)>1:return spatial
    if exact: return exact
    if spatial: return spatial
    # Legacy imports without geometry may bind an exact, unique transcript.
    return [o for o in objects if not object_rects(o) and not o.get('transcription_inferred')
            and region.get('text', '').strip() and text_ocr.normalized(o.get('text')) == text_ocr.normalized(region['text'])]


def spatial_match(rect,obj):
    rects=object_rects(obj);coverage=covered_fraction(rect,rects)
    if coverage>.5:return True
    # Inventory cells identify an anchor, not a measured object bounding box.
    # A long line can extend across the boundary while its centre is correctly
    # inside the reported cell. Never loosen measured rectangle matching.
    if obj.get('rects') or not obj.get('cell_ids') or coverage<=.2:return False
    cx,cy=(rect[0]+rect[2])/2,(rect[1]+rect[3])/2
    return any(r[0]<=cx<=r[2] and r[1]<=cy<=r[3] for r in rects)


def covered_fraction(target, rects):
    """Exact clipped union area, without filling gaps or double-counting cells."""
    if not text_ocr.valid_rect(target):return 0.
    x,y,z,b=target
    clipped=[]
    for r in rects:
        if not text_ocr.valid_rect(r):continue
        a,c,d,e=max(x,r[0]),max(y,r[1]),min(z,r[2]),min(b,r[3])
        if a<d and c<e:clipped.append((a,c,d,e))
    edges=sorted({v for r in clipped for v in (r[0],r[2])})
    area=0.
    for left,right in zip(edges,edges[1:]):
        spans=sorted((r[1],r[3]) for r in clipped if r[0]<right and r[2]>left)
        end=-1.;height=0.
        for top,bottom in spans:
            height+=max(0.,bottom-max(top,end));end=max(end,bottom)
        area+=(right-left)*height
    return min(1.,area/((z-x)*(b-y)))


def prepare(run, artifact_routing=False):
    pixel = run.get('pixel_text') or {}
    objects = run.get('observation', {}).get('objects', [])
    shaped = {r.get('source_id'): r for r in pixel.get('regions', [])}
    reasons = {r.get('source_id'):r['state'] for r in pixel.get('region_diagnostics',[])}
    extras={c.get('source_id'):c for c in (run.get('artifact_screen') or {}).get('candidates',[]) if c.get('issue_family')=='TEXT_QUALITY'} if artifact_routing else {}
    rows = []
    for region in pixel.get('detector_regions', []):
        matches = linked_objects(region, objects)
        text = region.get('text', '')
        if not text_ocr.valid_rect(region.get('rect', [])): state = 'INVALID_LOCATION'
        elif not text.strip(): state = 'UNREAD'
        elif len(matches) > 1: state = 'AMBIGUOUS_TARGET'
        elif not matches: state = 'NO_SCENE_MATCH'
        elif matches[0].get('transcription_inferred') or reading_relation(region,matches[0])=='DIFFERENT': state = 'DISAGREEMENT'
        elif reading_relation(region,matches[0])=='FRAGMENT': state = 'FRAGMENT_MATCH'
        elif region.get('recognition_score', 0) < .9: state = 'LOW_CONFIDENCE'
        else: state = 'AGREED'
        if state=='AGREED' and set(extras.get(region.get('id'),{}).get('signals',[])).intersection({'LOCAL_BLUR_SIGNAL','SHAPE_CONFLICT'}):state='QUALITY_CONFLICT'
        role = text_selection.role(matches[0]) if len(matches) == 1 else 'notice'
        shape = shaped.get(region.get('id'), {})
        rows.append(dict(region_id=region['id'], rect=region.get('rect'), detector_text=text,
                         object_ids=[o['id'] for o in matches], state=state, role=role,
                         shape_status=shape.get('shape_status', reasons.get(region.get('id'),'NOT_MEASURED')),
                         action='SPELLING' if state == 'AGREED' else 'RECHECK' if state != 'INVALID_LOCATION' else 'UNRESOLVED'))
    run['text_routing'] = dict(version=VERSION, regions=rows, counts=dict(Counter(r['state'] for r in rows)),
                               detector_status=pixel.get('status', 'NOT_RUN'),
                               note='문자 탐지·전사·획·철자 완료를 구분합니다. 미검사와 OCR 실패는 이미지 결함이 아닙니다.')
    return run['text_routing']


def recheck(engine, job, run, raw):
    routing = prepare(run,engine.s.flag('ARTIFACT_RECHECK_ENABLED',False))
    pending = [r for r in routing['regions'] if r['action'] == 'RECHECK']
    if not pending: return
    reason = None
    if run.get('observation_reused_from'): reason = 'OBSERVATION_REUSED'
    elif run.get('text_ocr'): reason = 'EXISTING_OCR_PATH'
    elif not engine.s.flag('TEXT_ROUTING_RECHECK_ENABLED', True): reason = 'DISABLED'
    cap = max(0, min(3, engine.s.integer('AUTO_VERIFY_MAX_CALLS', 3)))
    used = sum(c.get('workload') in ('image-verification', 'text-ocr', 'text-ocr-recheck') for c in run.get('calls', []))
    if used >= cap: reason = 'SHARED_CROP_CALL_LIMIT'
    if reason:
        for row in pending: row['deferred_reason'] = reason
        return
    priority = {'QUALITY_CONFLICT': 0, 'UNREAD': 0, 'DISAGREEMENT': 1, 'NO_SCENE_MATCH': 2, 'LOW_CONFIDENCE': 3, 'AMBIGUOUS_TARGET': 4}
    pending.sort(key=lambda r: (priority.get(r['state'], 5), r['rect'][3]-r['rect'][1]))
    pending = text_selection.balanced(pending, lambda r:r['role'])
    limit = max(0, min(3, engine.s.integer('TEXT_ROUTING_MAX_REGIONS', 3), engine.s.integer('AUTO_VERIFY_MAX_OBJECTS', 9)))
    selected = pending[:limit]
    for row in pending[limit:]: row['deferred_reason'] = 'REGION_LIMIT'
    if not selected: return
    by_id = {r['id']: r for r in run['pixel_text']['detector_regions']}
    regions = [copy.deepcopy(by_id[r['region_id']]) for r in selected]
    for region, row in zip(regions, selected):region['linked_object_ids']=row['object_ids']
    audit = dict(version=text_ocr.VERSION, mode='targeted', status='RUNNING', regions=regions,
                 call_count=0, candidate_count=len(routing['regions']), deferred_count=len(pending)-len(selected),
                 image_sha256=hashlib.sha256(raw).hexdigest(), note=routing['note'], vision_model='gpt-5.4',
                 vision_checked=0, vision_deferred=len(regions))
    run['text_ocr'] = audit
    images = []; tasks = []
    for region in regions:
        data, rect, size = text_ocr.native_crop(raw, region['rect'])
        region.update(crop_rect=rect, source_pixels=size, sent_pixels=size)
        x,y,z,b = region['rect']; a,c,d,e = rect
        tasks.append(dict(region_id=region['id'], image_index=len(images), target_rect_in_crop=[(x-a)/(d-a),(y-c)/(e-c),(z-a)/(d-a),(b-c)/(e-c)]))
        images.append(data)
    engine.checkpoint(job['id'], run)
    try:
        # No OCR strings, suggested corrections, dictionary or answer keys here.
        payload = dict(tasks=tasks, sensitivity=run['options'].get('text_sensitivity','strict'),
                       instruction='원본 crop의 지정 영역을 독립 전사하고 글자 획과 철자를 별도로 검사합니다.')
        body, meta = engine.provider.call('gpt-5.4', json.dumps(payload,ensure_ascii=False), images, workload='text-ocr')
        run['calls'].append(meta);audit['call_count']=1
        readings = text_ocr.TextReadings.model_validate(body).model_dump()['results']
        if len(readings)!=len(regions) or {r['region_id'] for r in readings}!=set(r['id'] for r in regions):
            raise ValueError('독립 문자 판독 영역 누락 또는 중복')
        lookup = {r['region_id']:r for r in readings}
        for region in regions:
            reading = lookup[region['id']]
            for key in ('literal_text','glyph_evidence','suggested_text','spelling_evidence'):
                reading[key]=text_ocr.redact(reading[key])[:2000]
            reading['uncertain_characters']=[text_ocr.redact(c)[:200] for c in reading['uncertain_characters'][:80]]
            region['vision']=reading
            # Capture model/engine disagreement without converting it to a typo.
            region['verdict']=text_ocr.verdict(region)
        audit.update(status='COMPLETED',vision_checked=len(regions),vision_deferred=0)
        for row in selected: row['action']='RECHECKED'
    except Exception as exc:
        if getattr(exc,'call_meta',None):run['calls'].append(exc.call_meta);audit['call_count']=1
        audit.update(status='UNAVAILABLE', error='선택 문자 재판독 미완료 · 추가 재시도 없음')
        for region in regions:region['verdict']=text_ocr.verdict(region)
        for row in selected:row['deferred_reason']='CALL_FAILED'
    engine.checkpoint(job['id'],run)


def protect_conflicts(run, rows, ids):
    """Keep localized, comparable OCR disagreements visible; never call them typos.

    Partial lines, ambiguous objects, poor recognition and unlocated text remain
    diagnostics. Two equal GPT reads do not erase a differing detector reading.
    """
    if 'D-02-l' not in ids:return rows
    from .rules import validate_batch
    from .text_location import cells_for_rects
    objects=run.get('observation',{}).get('objects',[])
    verified={r['object_id']:r for r in (run.get('verification') or {}).get('results',[])
              if r.get('coverage')=='COMPLETE' and r.get('status')=='COMPLETED'}
    conflicts=[]
    for region in (run.get('pixel_text') or {}).get('detector_regions',[]):
        if region.get('recognition_score',0)<.65:continue
        linked=linked_objects(region,objects)
        if len(linked)!=1:continue
        obj=linked[0];check=verified.get(obj['id'],{})
        reading=check.get('text') or obj.get('text','')
        first=text_ocr.normalized(region.get('text'));second=text_ocr.normalized(reading)
        if not first or not second or first==second or first in second or second in first:continue
        if not .75<=len(first)/len(second)<=1.25:continue
        # A completed, independent isolated-character comparison can identify
        # an OCR recognition error. Successful contextual reading alone cannot.
        resolved=any(g.get('isolated_glyphs',{}).get('agreed') and
            text_ocr.normalized(g['isolated_glyphs'].get('literal_text'))==second and
            covered_fraction(region['rect'],[g['rect']])>.8
            for g in (run.get('glyph_audit') or {}).get('regions',[]))
        if resolved:continue
        evidence=dict(region_id=region['id'],object_id=obj['id'],rect=region['rect'],
                      detector_text=region.get('text',''),independent_text=reading,
                      event_id=check.get('event_id'),status='UNRESOLVED')
        conflicts.append(evidence)
        matching=[r for r in rows if r['rule_id']=='D-02-l' and obj['id'] in r.get('evidence_ids',[])]
        reason=f'같은 위치의 OCR 판독 “{evidence["detector_text"]}”와 그림 판독 “{reading}”가 다릅니다. 오탈자인지 OCR 오인식인지 원본 획 확인이 필요합니다.'
        if not matching:
            matching=validate_batch({'results':[dict(rule_id='D-02-l',instance_id=obj['id'],status='REVIEW',
                observation=obj.get('label','문자 영역'),reason=reason,evidence_quality='UNCERTAIN',
                cell_ids=cells_for_rects([region['rect']]),reference_ids=[],recommended_action='서로 다른 음절의 원본 획을 확인하세요.')]},
                ['D-02-l'],run['reference_snapshot'],None,'system/independent-reading-conflict',pack=run['rule_pack'])
            rows.extend(matching)
        for row in matching:
            row.setdefault('independent_reading_conflicts',[])
            if evidence not in row['independent_reading_conflicts']:row['independent_reading_conflicts'].append(evidence)
            if row['status'] in ('FAIL','ERROR','NOT_RUN'):continue
            row.update(status='REVIEW',reason=reason,error_type='OCR_MISMATCH',review_basis='OBSERVED_ANOMALY',
                evidence_ids=[obj['id']],rects=[region['rect']],cell_ids=cells_for_rects([region['rect']]),
                visual_issue=True,document_review=False,diagnostic_only=False,location_unresolved=False,
                evidence_quality='UNCERTAIN',target_presence='PRESENT',
                recommended_action='서로 다른 음절의 원본 획을 확인하세요.')
    if conflicts:
        if not run.get('text_routing',{}).get('regions'):prepare(run)
        run['text_routing']['unresolved_conflicts']=conflicts
    return rows
