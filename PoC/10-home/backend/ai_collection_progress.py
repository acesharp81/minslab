"""Read-only progress and token estimates; reservations are never actual usage."""
import math
import time

ACTIVE = {'QUEUED', 'RUNNING', 'STOPPING'}
DOCUMENT_EVENTS = ('ANALYZED', 'ANALYSIS_ERROR', 'UNCHANGED', 'DOCUMENT_ERROR')


def summarize(run, checkpoint, calls, counts, at=None):
    at = time.time() if at is None else at
    p = dict(checkpoint or {})
    active = run['status'] in ACTIVE
    models = {}
    for call in calls:
        m = models.setdefault(call['model'], dict(model=call['model'], input_tokens=0, output_tokens=0,
                                                confirmed_tokens=0, reserved_tokens=0, unknown_tokens=0))
        inp, out = call['input_tokens'], call['output_tokens']
        if inp is not None and out is not None:
            m['input_tokens'] += inp; m['output_tokens'] += out; m['confirmed_tokens'] += inp + out
        elif call['status'] == 'RESERVED' and active:
            m['reserved_tokens'] += call['reserved_tokens']
        else:
            m['unknown_tokens'] += call['reserved_tokens']
    tokens = {k:sum(m[k] for m in models.values()) for k in ('confirmed_tokens','reserved_tokens','unknown_tokens')}
    done = p.get('documents_done',sum(counts.get(k,0) for k in DOCUMENT_EVENTS))
    total = p.get('documents_total')
    stage = p.get('stage') or ('ANALYZE' if calls or done else 'DISCOVERY')
    if run['status'] == 'QUEUED': stage = 'QUEUED'
    source_stage = stage == 'DISCOVERY' and total is None
    completed = p.get('sources_done',sum(counts.get(k,0) for k in ('SOURCE','SEARCH','SOURCE_ERROR'))) if source_stage else done
    target = p.get('sources_total') if source_stage else total
    percent = min(100,100*completed/target) if target else (100 if target==0 and not active else None)
    remaining = max(0,total-done) if total is not None else None
    estimate = None
    sample_tokens = p.get('completed_tokens',0)
    if remaining == 0:
        estimate = 0
    elif remaining is not None and done > 0 and sample_tokens > 0:
        # The average includes cached/skipped/failed attempts from this same run.
        # Subtract confirmed tokens already spent on the current unfinished item.
        current_tokens = max(0,tokens['confirmed_tokens']-sample_tokens)
        estimate = max(0,math.ceil(sample_tokens/done*remaining-current_tokens))
    return dict(stage=stage,current=p.get('current',''),model=p.get('model'),
                completed=completed,total=target,unit='sources' if source_stage else 'documents',percent=percent,
                documents_done=done,documents_total=total,documents_remaining=remaining,
                documents_skipped=p.get('documents_skipped',counts.get('UNCHANGED',0)),
                documents_failed=p.get('documents_failed',counts.get('DOCUMENT_ERROR',0)+counts.get('ANALYSIS_ERROR',0)),
                documents_deferred=p.get('documents_deferred',0),
                source_errors=counts.get('SOURCE_ERROR',0),
                elapsed_seconds=max(0,int((at if active else run['updated'])-run['created'])),
                phase_elapsed_seconds=max(0,int(at-p.get('phase_started',run['updated']))) if active else None,
                estimated_remaining_tokens=estimate,estimate_sample_documents=done,
                estimate_note='이번 실행의 처리 완료 자료 평균 × 남은 자료에서 현재 자료의 확인된 사용량을 뺀 추정치입니다. 원문 길이·변경 없음·심층 검토 여부에 따라 달라집니다.',
                models=list(models.values()),**tokens)
