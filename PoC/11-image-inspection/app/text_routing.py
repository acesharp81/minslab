"""Keep unrecognized/disagreeing text candidates; spend only existing crop slots."""
import copy
import hashlib
import json
from collections import Counter
from . import text_ocr, text_selection
from .imaging import cell_rect

VERSION = 'text-routing-v1'


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
    spatial = [o for o in objects if any(text_ocr.overlap(rect, r) > .5 for r in object_rects(o))
               and (o.get('text') or o.get('text_legibility') in ('CLEAR', 'DEGRADED', 'UNREADABLE'))]
    exact = [o for o in spatial if text_ocr.normalized(o.get('text')) == text_ocr.normalized(region.get('text'))
             and region.get('text', '').strip() and not o.get('transcription_inferred')]
    if exact: return exact
    if spatial: return spatial
    # Legacy imports without geometry may bind an exact, unique transcript.
    return [o for o in objects if not object_rects(o) and not o.get('transcription_inferred')
            and region.get('text', '').strip() and text_ocr.normalized(o.get('text')) == text_ocr.normalized(region['text'])]


def prepare(run):
    pixel = run.get('pixel_text') or {}
    objects = run.get('observation', {}).get('objects', [])
    shaped = {r.get('source_id'): r for r in pixel.get('regions', [])}
    reasons = {r.get('source_id'):r['state'] for r in pixel.get('region_diagnostics',[])}
    rows = []
    for region in pixel.get('detector_regions', []):
        matches = linked_objects(region, objects)
        text = region.get('text', '')
        if not text_ocr.valid_rect(region.get('rect', [])): state = 'INVALID_LOCATION'
        elif not text.strip(): state = 'UNREAD'
        elif len(matches) > 1: state = 'AMBIGUOUS_TARGET'
        elif not matches: state = 'NO_SCENE_MATCH'
        elif text_ocr.normalized(matches[0].get('text')) != text_ocr.normalized(text) or matches[0].get('transcription_inferred'): state = 'DISAGREEMENT'
        elif region.get('recognition_score', 0) < .9: state = 'LOW_CONFIDENCE'
        else: state = 'AGREED'
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
    routing = prepare(run)
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
    priority = {'UNREAD': 0, 'DISAGREEMENT': 1, 'NO_SCENE_MATCH': 2, 'LOW_CONFIDENCE': 3, 'AMBIGUOUS_TARGET': 4}
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
