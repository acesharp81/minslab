"""Compare approved, image-scoped copy only AFTER independent visual reading.

No dictionary guessing, fuzzy target matching, or correction hints in OCR prompts.
Matching copy does not certify glyph quality. An unreadable region is not a typo.
"""
import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
from .rules import PACK, validate_batch

SCHEMA = 'chekmi-source-copy-v1'


def normalized(text):
    # Spaces remain meaningful. Do not turn 울 into 을 or remove unknown glyphs.
    return unicodedata.normalize('NFC', text).replace('\r\n', '\n').strip()


def parse(content):
    try:
        doc = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(doc, dict) or doc.get('schema') != SCHEMA:
        return None
    if not re.fullmatch('[0-9a-f]{64}', str(doc.get('image_sha256', ''))):
        raise ValueError('기준 원고의 image_sha256에 해당 이미지 식별값 64자리를 넣어 주세요.')
    entries = doc.get('entries')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 40:
        raise ValueError('기준 원고 entries는 1~40개여야 합니다.')
    for entry in entries:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in ('label', 'text')):
            raise ValueError('각 원고 항목에 저장된 객체의 label과 해당 영역 전체의 text가 필요합니다.')
        if len(entry['text']) > 2000:
            raise ValueError('원고 한 영역은 2,000자 이내로 입력하세요.')
    return doc


def bindings(run, image_hash):
    objects = run.get('observation', {}).get('objects', [])
    matched = []; unresolved = []
    for ref in run.get('reference_snapshot', []):
        if ref.get('status') != 'APPROVED' or ref.get('kind') != 'source-data':
            continue
        try:
            doc = parse(ref.get('content', ''))
        except ValueError as exc:
            unresolved.append(dict(reference_id=ref['id'], reason=str(exc))); continue
        if not doc or doc['image_sha256'] != image_hash:
            continue
        for entry in doc['entries']:
            targets = [o for o in objects if o.get('label') == entry['label']]
            if len(targets) != 1:
                unresolved.append(dict(reference_id=ref['id'], label=entry['label'], reason='대상 이름이 없거나 여러 곳에 있어 원고 대조 보류')); continue
            matched.append(dict(object=targets[0], expected=normalized(entry['text']), reference_id=ref['id'], parent_ids=ref.get('parent_ids', [])))
    return matched, unresolved


def differences(observed, expected):
    return [dict(operation=op, observed=observed[a:b], expected=expected[c:d], observed_range=[a,b], expected_range=[c,d])
            for op,a,b,c,d in SequenceMatcher(None, observed, expected, autojunk=False).get_opcodes() if op != 'equal']


def inspect(run, raw):
    image_hash = hashlib.sha256(raw).hexdigest()
    matches, unresolved = bindings(run, image_hash)
    results = []
    for item in matches:
        obj = item['object']; expected = item['expected']
        alternatives = {m['expected'] for m in matches if m['object']['id'] == obj['id']}
        if len(alternatives) != 1:
            unresolved.append(dict(object_id=obj['id'], reason='승인 원고끼리 내용 충돌')); continue
        checks = [c for c in run.get('verification', {}).get('results', []) if c.get('object_id') == obj['id'] and c.get('status') == 'COMPLETED']
        first = normalized(obj.get('text', ''))
        # Partial rechecks cannot replace a complete first read.
        complete = [c for c in checks if c.get('coverage') == 'COMPLETE']
        literal = normalized(complete[-1].get('text', '')) if complete else first
        certain = bool(literal and complete) and first == literal and obj.get('quality') == 'CLEAR' and not obj.get('transcription_inferred') and obj.get('text_legibility') == 'CLEAR'
        certain = certain and all(c.get('quality') == 'CLEAR' and c.get('text_legibility') == 'CLEAR' and not c.get('transcription_inferred') and normalized(c.get('text', '')) == literal for c in complete)
        unknown = not literal or bool(re.search(r'□|�|\[판독불가\]|\[마스킹\]', literal))
        delta = differences(literal, expected) if not unknown else []
        state = 'UNREADABLE' if unknown else 'DIFFERENCE' if delta else 'TEXT_MATCH'
        results.append(dict(object_id=obj['id'], label=obj['label'], reference_id=item['reference_id'], parent_ids=item['parent_ids'], literal=literal, expected=expected, differences=delta, state=state,
                            confirmed=bool(certain and not unknown), event_ids=[c.get('event_id') for c in complete],
                            status='FAIL' if delta and certain and not unknown else 'REVIEW' if delta or unknown or not certain else 'TEXT_MATCH'))
    run['source_copy'] = dict(version=SCHEMA, image_sha256=image_hash, results=results, unresolved=unresolved,
                              note='독립 판독 후 글자별 대조. 원고 일치는 획 품질 정상 판정이 아닙니다. 추가 API 호출 없음.')
    return run['source_copy']


def protect(run, rows, ids):
    from .evidence_guards import general_text_rules
    pack = run.get('rule_pack') or PACK
    steps = {s['rule_id']: s for s in pack['steps']}
    objects = {o['id']:o for o in run.get('observation', {}).get('objects', [])}
    for check in run.get('source_copy', {}).get('results', []):
        if check['state'] == 'TEXT_MATCH':
            continue  # Never lower a visual defect or award PASS on text agreement.
        obj = objects.get(check['object_id'])
        if not obj: continue
        for rid in general_text_rules(steps, ids):
            if steps[rid]['parent_id'] not in check['parent_ids']: continue
            selected = [r for r in rows if r['rule_id'] == rid and check['object_id'] in r.get('evidence_ids', [])]
            if not selected:
                selected = validate_batch({'results':[dict(rule_id=rid, instance_id=obj['id'], status='REVIEW', observation=obj['label']+': '+check['literal'], reason='승인 원고 대조', evidence_quality='UNCERTAIN', cell_ids=obj.get('cell_ids', []), reference_ids=[check['reference_id']], recommended_action='원본과 승인 원고를 확인하세요.')]}, [rid], run['reference_snapshot'], None, 'system/source-copy', pack=pack)
                for row in selected: row.update(evidence_ids=[obj['id']], target_presence='PRESENT', vision_model=run.get('observation_model'))
                rows.extend(selected)
            for row in selected:
                row['source_copy_check'] = check
                if row['status'] == 'ERROR': continue
                reason = '승인 원고와 문자 차이 확인.' if check['status'] == 'FAIL' else '원고 대조 후보: 독립 판독 미확정. 원본 확인이 필요합니다.'
                if check['state'] == 'UNREADABLE': reason = '원본 문자 판독 불가: 원고로 추측 복원하지 않고 검토를 보류합니다.'
                preserve = row['status'] == 'FAIL'
                row.update(status='FAIL' if preserve else check['status'], reason=(row.get('reason', '')+' · '+reason) if preserve else reason,
                           visual_issue=True, document_review=False, recommended_action='차이가 표시된 원문과 승인 원고를 원본에서 대조하세요.')
                if not preserve: row.update(error_type='FACT_OR_STYLE_ISSUE' if check['status']=='FAIL' else 'OCR_UNCERTAIN', evidence_quality='CLEAR' if check['confirmed'] else 'UNCERTAIN', review_basis='OBSERVED_ANOMALY')
                row['reference_ids']=list(dict.fromkeys(row.get('reference_ids', [])+[check['reference_id']]))
    return rows
