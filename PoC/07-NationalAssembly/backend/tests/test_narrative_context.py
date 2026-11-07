from copy import deepcopy
import pytest
from app.services.structured_narrative import inputs,validate,apply,PROFILE,has_meta_commentary

def example():
    brief={'topics':[{'id':'t','title':'재원 조달 방안','speaker_points':[
        {'id':'p','role':'ANSWER','evidence_span':{'quote':'그렇습니다.','atom_id':'a','evidence_id':'u'}}]}],'topic_groups':[{'id':'g','title':'예산','topic_ids':['t']}], 'tasks':[]}
    snapshot={'atoms':[{'id':'a','text':'그렇습니다.','before':'기금으로 재원을 조달합니까?','after':'국채 발행도 함께 활용합니다.'}]}
    return brief,snapshot

def test_neighbor_context_preserves_existing_fingerprint():
    brief,snapshot=example();a=inputs(brief,snapshot)[0]
    old=deepcopy(snapshot);old['atoms'][0].pop('before');old['atoms'][0].pop('after')
    assert a['fingerprint']==inputs(brief,old)[0]['fingerprint']
    assert a['contexts'][0]['before']=='기금으로 재원을 조달합니까?'

@pytest.mark.parametrize('text',['원문이 불명확하여 요약할 수 없다.','너무 단편적인 대답이라 요약 할 수 없다.','불분명한 발언으로 요약할 내용이 없다.'])
def test_model_work_commentary_rejected(text):
    brief,snapshot=example()
    with pytest.raises(ValueError,match='NARRATIVE_META_COMMENTARY'):
        validate(inputs(brief,snapshot),{'t':{'summary':'기금과 국채를 활용한 재원 조달 방식이 논의됐다.','points':{'p':text}}})

def test_substantive_uncertainty_is_not_model_commentary():
    assert not has_meta_commentary('장관은 자료가 부족해 사업 효과를 확정하기 어렵다고 답변했다.')

def test_unresolved_source_preserved_without_commentary():
    brief,snapshot=example();items=inputs(brief,snapshot)
    row={'t':{'summary':'','points':{'p':''}}}
    validate(items,row)
    out=apply(brief,[(400001,{'profile':PROFILE,'issues':items},row)],snapshot)
    topic=out['report_summary']['topics'][0]
    assert topic['speaker_points']==[]
    assert topic['source_only_point_ids']==['p']
    assert topic['evidence_ids']==['u']
    assert brief['topics'][0]['speaker_points'][0]['evidence_span']['quote']=='그렇습니다.'

def test_substantive_speech_cannot_be_silently_omitted():
    brief,snapshot=example()
    brief['topics'][0]['speaker_points'][0]['evidence_span']['quote']='국채 발행을 줄이고 기금 재원을 먼저 활용하는 방안을 검토하겠습니다. '*4
    with pytest.raises(ValueError,match='NARRATIVE_SUBSTANTIVE_SOURCE_OMITTED'):
        validate(inputs(brief,snapshot),{'t':{'summary':'','points':{'p':''}}})

def test_point_identifies_its_own_context():
    brief,snapshot=example()
    item=inputs(brief,snapshot)[0]
    assert item['points'][0]['atom_id']==item['contexts'][0]['atom_id']=='a'


def test_extreme_caption_loop_can_remain_as_evidence_without_invented_summary():
    brief,snapshot=example()
    text='지치지 ' * 20 + '지' * 30 + '은 은 해지해지 ' * 10
    brief['topics'][0]['speaker_points'][0]['evidence_span']['quote']=text
    items=inputs(brief,snapshot); row={'t':{'summary':'','points':{'p':''}}}
    validate(items,row)
    result=apply(brief,[(400001,{'profile':PROFILE,'issues':items},row)],snapshot)
    assert result['report_summary']['topics'][0]['source_only_point_ids']==['p']
    assert result['topics'][0]['speaker_points'][0]['evidence_span']['quote']==text


def test_repetition_with_substantive_speech_still_requires_summary():
    from app.services.structured_narrative import repetitive_caption_noise
    assert not repetitive_caption_noise('지'*30 + '추가 과세와 압류를 유보하고 구제 방안을 마련해 주십시오. '*8)
    assert not repetitive_caption_noise('예산 100억 원을 증액해야 합니다. '*20)
