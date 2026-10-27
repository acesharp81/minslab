from copy import deepcopy
import pytest
from app.services.live_discussion_classification import classification_request, apply_classification, project_classification, BATCH_SIZE


def turn(uid, summary, topic='치료감호 청구율', source_hash='source'):
    return dict(utterance_id=str(uid),content_hash=source_hash,summary=summary,summary_kind='AI_CACHED',is_final=True,
        first_cursor=int(uid),last_cursor=int(uid)+1,live_insight={'topic':topic,'topic_key':topic,'role':'ANSWER','task':'치료감호 제도 검토'})


def group(ids, gid='new-1', title='정신질환 범죄자 치료·관리 제도'):
    return {'id':gid,'title':title,'scope':'치료감호 청구와 시설 확충, 정신질환 수용자 관리','utterance_ids':ids}


def test_semantic_group_preserves_distinct_summaries_tasks_and_source_ids():
    turns=[turn(1,'청구율이 낮은 이유를 물었다.'),turn(2,'법정 요건을 설명했다.',topic='심신미약 인정 기준')]
    original=deepcopy(turns);request=classification_request(turns,{})
    state=apply_classification('bid',{},request,{'groups':[group(['u0','u1'])]})
    project_classification(turns,state)
    assert turns[0]['live_insight']['discussion_group']['id']==turns[1]['live_insight']['discussion_group']['id']
    for a,b in zip(turns,original):
        assert a['summary']==b['summary'] and a['content_hash']==b['content_hash']
        assert a['live_insight']['task']==b['live_insight']['task']
    assert not classification_request(turns,state)['turns']


@pytest.mark.parametrize('groups',[[group(['u0'])],[group(['u0','u1','u1'])],[group(['u0','missing'])],[group(['u0','u1'],'invented-id')]])
def test_missing_duplicate_or_invented_assignments_cannot_be_published(groups):
    turns=[turn(1,'질의'),turn(2,'답변')];request=classification_request(turns,{})
    with pytest.raises(ValueError):
        apply_classification('bid',{},request,{'groups':groups})


def test_same_short_answer_hash_does_not_join_unrelated_contexts():
    turns=[turn(1,'예.'),turn(2,'예.',topic='선거 관리')];request=classification_request(turns,{})
    state=apply_classification('bid',{},request,{'groups':[group(['u0']),group(['u1'],'new-2','선거 관리')]})
    assert len(state['assignments'])==2
    assert len({v['group_id'] for v in state['assignments'].values()})==2


def test_incremental_batch_reuses_stable_id_and_stale_summary_is_reclassified():
    turns=[turn(i,'발언 '+str(i)) for i in range(BATCH_SIZE+1)]
    req=classification_request(turns,{})
    assert sum(r['target'] for r in req['turns'])==BATCH_SIZE
    state=apply_classification('bid',{},req,{'groups':[group([r['id'] for r in req['turns'] if r['target']])]})
    old=deepcopy(state);gid=next(iter(state['groups']))
    req=classification_request(turns,state)
    assert any(not r['target'] and r['previous_group_id']==gid for r in req['turns'])
    new=apply_classification('bid',state,req,{'groups':[group([f'u{BATCH_SIZE}'],gid,'모델이 바꾼 제목')]})
    assert new['groups'][gid]==old['groups'][gid]
    assert state==old
    turns[0]['summary']='원문 대조 후 정정한 요약'
    project_classification(turns,state)
    assert 'discussion_group' not in turns[0]['live_insight']
    assert any(r['target'] and r['id']=='u0' for r in classification_request(turns,state)['turns'])


def test_backend_lineage_uses_same_semantic_groups_as_the_screen():
    from app.services.live_topic_lineage import build_live_topic_clusters
    turns=[turn(1,'청구율 설명'),turn(2,'시설 확충',topic='시설 정원'),turn(3,'별도 사건',topic='시설 정원')]
    req=classification_request(turns,{})
    state=apply_classification('bid',{},req,{'groups':[group(['u0','u1']),group(['u2'],'new-2','별도 사건')]})
    project_classification(turns,state)
    groups,_,source_title_count=build_live_topic_clusters(turns)
    assert source_title_count==2
    assert "시설 정원" in groups[0]["aliases"]
    assert len(groups)==2
    assert groups[0]['utterance_ids']==['1','2']
    assert groups[1]['utterance_ids']==['3']


def test_context_echoes_are_ignored_without_modifying_previous_assignments():
    turns=[turn(i,str(i)) for i in range(BATCH_SIZE+1)]
    req=classification_request(turns,{})
    state=apply_classification('bid',{},req,{'groups':[group([r['id'] for r in req['turns'] if r['target']])]})
    req=classification_request(turns,state)
    response={'groups':[group(['u77','u78','u79'],next(iter(state['groups']))),group(['u80'],'new-2','다른 사안') ]}
    updated=apply_classification('bid',state,req,response)
    assert len(updated['assignments'])==BATCH_SIZE+1
    for uid,assignment in state['assignments'].items():
        assert updated['assignments'][uid]==assignment


def test_conflicting_model_assignments_remain_pending_while_valid_turns_progress():
    from app.services.live_discussion_classification import validated_partial_response
    turns=[turn(1,'질의'),turn(2,'모호한 답변'),turn(3,'또 다른 질의')]
    request=classification_request(turns,{})
    response={'groups':[group(['u0','u0','u1','invented']),group(['u1','u2'],'new-2','선거관리')]}
    subset,cleaned,coverage=validated_partial_response(request,response)
    state=apply_classification('bid',{},subset,cleaned)
    assert set(state['assignments'])=={'1','3'}
    assert coverage['pending_turn_ids']==['u1']
    assert [r['id'] for r in classification_request(turns,state)['turns'] if r['target']]==['u1']


def test_real_task_cannot_be_grouped_as_opening_and_old_mistake_is_requeued():
    from app.services.live_discussion_classification import fingerprint, validated_partial_response
    turns=[turn(1,'투표용지 검증을 원만하게 마무리해 달라고 요청했다.',topic='투표용지 검증')]
    turns[0]['live_insight']['task']='투표용지 검증 마무리'
    state={'groups':{'old':{'title':'국정감사 개회 및 진행','scope':'개회와 회의 진행'}},
           'assignments':{'1':{'group_id':'old','fingerprint':fingerprint(turns[0])}}}
    project_classification(turns,state)
    assert 'discussion_group' not in turns[0]['live_insight']
    req=classification_request(turns,state)
    assert len([r for r in req['turns'] if r['target']])==1
    bad={'groups':[group(['u0'],'old','국정감사 개회 및 진행')]}
    with pytest.raises(ValueError,match='SUBSTANTIVE_TASK_IN_PROCEDURE'):
        apply_classification('bid',state,req,bad)
    with pytest.raises(ValueError,match='NO_UNAMBIGUOUS_ASSIGNMENTS'):
        validated_partial_response(req,bad)
