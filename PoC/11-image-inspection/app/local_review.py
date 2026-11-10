"""Reconcile saved review evidence locally. No providers or usage clients."""
import copy
import uuid
from .storage import now
from . import evidence_guards,text_routing


def revised_run(source):
    run=copy.deepcopy(source)
    changed_bindings=text_routing.reconcile_stored_bindings(run,run['results'])
    documents=[r['id'] for r in run['results'] if r.get('status')=='REVIEW' and
               (r.get('rule_id','').startswith('D-03-') or r.get('rule_id') in ('D-04-d','D-04-e')) and r.get('review_basis')!='DOCUMENT_CHECK']
    evidence_guards.classify_document_reviews(run['results'])
    # Preserve source comparison/call records in the old immutable version.
    note='저장 관찰·판정을 재사용해 문서 확인 분류와 문자 영역 연결을 정리했습니다. 새 그림 판독·분석·외부 API 호출은 없습니다. 판독 미완료를 정상으로 바꾸지 않았습니다.'
    run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),phase='DONE',elapsed_seconds=0,calls=[],reused_from=None,
               observation_reused_from={'run_id':source['id']},analysis_reused_from={'run_id':source['id'],'reason':note},
               local_revision={'method':'review-evidence-v1','note':note,'source_run_id':source['id'],
                               'reclassified_rows':documents,'binding_rows':changed_bindings,
                               'inherited_failed_calls':[copy.deepcopy(c) for c in source.get('calls',[]) if c.get('status')=='FAILED']})
    run.pop('evidence_revision',None)
    run['cache_key']='local-review-'+run['id']
    return run
