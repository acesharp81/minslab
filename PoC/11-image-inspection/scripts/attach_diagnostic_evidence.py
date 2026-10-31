"""Append completed independent diagnostics without claiming a new checklist run.

No API calls. A manifest binds evidence to the source image, objects and metered
provider events. Character disagreement is REVIEW, never an invented typo FAIL.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.storage import Store,now
from app.text_ocr import normalized,valid_rect


def revise(source, manifest):
    run=copy.deepcopy(source)
    objects={o['id']:o for o in run['analysis_observation']['objects']}
    steps={s['rule_id']:s for s in run['rule_pack']['steps']}
    diagnostics=manifest['diagnostics'];calls=manifest['calls']
    events=[c['event_id'] for c in calls]
    if not events or len(events)!=len(set(events)):raise ValueError('호출 식별자 누락/중복')
    for d in diagnostics:
        if d['object_id'] not in objects or d['event_id'] not in events:raise ValueError('대상 객체/호출 근거 불일치')
        if not valid_rect(d['rect']):raise ValueError('검증 영역 오류')
        if any(r not in steps for r in d['rule_ids']):raise ValueError('원문 규칙 불일치')
    changed=0
    for d in diagnostics:
        obj=objects[d['object_id']]
        rows=[r for r in run['results'] if d['object_id'] in r.get('evidence_ids',[]) and r['rule_id'] in d['rule_ids']]
        for row in rows:row.setdefault('supplemental_evidence',[]).append(copy.deepcopy(d))
        # Hand observations are retained as evidence only: no inferred defect or
        # new PASS can be manufactured from a provider's failure to find one.
        if d['kind']!='glyph':continue
        literal=''.join(c['literal_text'] for c in d['characters'])
        if normalized(literal)==normalized(d['word_text']):continue
        obj.update(text_disagreement=True,visual_concerns='문구 단위 판독과 독립 음절 판독이 다릅니다. 원본 획 확인 필요.')
        # Detector rectangle is narrower than scene-grid geometry. It is only
        # substituted for this text object, never for adjacent objects.
        obj['rects']=[d['rect']]
        reason=f"문구 판독 ‘{d['word_text']}’과 독립 음절 판독 ‘{literal}’이 다릅니다. 문맥 보정 또는 음절 인식 오류 가능성이 있어 원본 획을 확인해야 합니다. 독립 음절 결과도 확정 정답은 아닙니다."
        for rid in d['rule_ids']:
            related=[r for r in rows if r['rule_id']==rid]
            # Existing FAIL/reviewer decisions remain; new evidence is attached.
            if any(r['status']=='FAIL' or any(v['finding_id']==r['id'] for v in run['reviews']) for r in related):continue
            related=[r for r in related if r.get('evidence_ids')==[d['object_id']]]
            for old in related:run['results'].remove(old)
            step=steps[rid]
            run['results'].append(dict(id=uuid.uuid4().hex,rule_id=rid,parent_id=step['parent_id'],instance_id=d['object_id'],
                status='REVIEW',observation=f"{obj['label']} · 전문 OCR: {d['word_text']} · 음절별: {literal}",reason=reason,
                evidence_quality='UNCERTAIN',cell_ids=obj['cell_ids'],reference_ids=[],recommended_action='음절별 획과 문구 판독이 다른 부분을 원본에서 확인하세요.',
                model='system/independent-evidence',vision_model=d['model'],rule_version=step['version'],grid_id='main-v1',crop_id=None,
                rects=[d['rect']],evidence_ids=[d['object_id']],error_type='OCR_MISMATCH',review_basis='READING_LIMIT',visual_issue=True,
                evidence_status='UNAVAILABLE',direct_comparisons=[],location_unresolved=False,target_presence='PRESENT',document_review=False,
                supplemental_evidence=[copy.deepcopy(d)],supersedes_findings=[r['id'] for r in related]))
            changed+=1
    run.pop('local_revision',None)
    run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),calls=copy.deepcopy(calls),elapsed_seconds=0,
               reused_from=None,phase='DONE',reused_from_cache=False)
    run['options']={**run['options'],'reuse_observation_run_id':source['id'],'recheck_object_ids':list(dict.fromkeys(d['object_id'] for d in diagnostics))}
    run['evidence_revision']={'source_run_id':source['id'],'changed_reviews':changed,'diagnostics':copy.deepcopy(diagnostics),
        'image_sha256':manifest['image_sha256'],
        'note':'승인된 추가 판독 결과를 반영했습니다. 원문 규칙 전체를 새로 분석한 결과가 아닙니다. 음절 분리는 이 이미지에 대한 수동 검증이며 자동 분할 기능은 아닙니다. 손 구조는 추가 판독으로도 오류가 확정되지 않았습니다.'}
    run['cache_key']='independent-evidence-'+run['id']
    return run


def main():
    p=argparse.ArgumentParser();p.add_argument('job_id');p.add_argument('source_run_id');p.add_argument('manifest');args=p.parse_args()
    s=Settings();store=Store(s.data/'inspection.sqlite3');manifest=json.loads(Path(args.manifest).read_text())
    if hashlib.sha256((s.data/args.job_id/'image.png').read_bytes()).hexdigest()!=manifest['image_sha256']:raise ValueError('원본 이미지 불일치')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT body FROM jobs WHERE id=?',(args.job_id,)).fetchone()
        if not row:raise ValueError('기록 없음')
        job=json.loads(row[0])
        if job['state'] in ('RUNNING','QUEUED') or job['runs'][-1]['id']!=args.source_run_id:raise ValueError('현재 버전이 달라 중단')
        for call in manifest['calls']:
            if call.get('unit')=='api_call':
                stored=c.execute("SELECT id FROM naver_ocr_requests WHERE id=? AND state='COMPLETED'",(call['event_id'],)).fetchone()
            else:
                stored=c.execute('SELECT body FROM usage_events WHERE id=?',(call['event_id'],)).fetchone()
            if not stored:raise ValueError('실제 사용량 기록이 없는 호출')
        revision=revise(job['runs'][-1],manifest)
        revision['observation_reused_from']={'job_id':job['id'],'run_id':args.source_run_id}
        job['runs'].append(revision)
        c.execute('UPDATE jobs SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),job['id']))
    store.audit('system/independent-evidence','APPEND_COMPLETED_DIAGNOSTICS',job['id'],{'run_id':revision['id'],'events':[x['event_id'] for x in manifest['calls']]})
    print(json.dumps({'run_id':revision['id'],'changed_reviews':revision['evidence_revision']['changed_reviews'],'new_api_calls':0}))

if __name__=='__main__':main()
