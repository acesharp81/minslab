from backend.mapping_workbench import review_state
from backend.collection_tags import tag
from backend.requirements_status import acquisition_summary

def test_official_source_does_not_turn_a_proposal_into_approval():
    link=dict(policy_id='POL',status='REVIEW',evidence_url='https://www.korea.kr/official')
    assert review_state(link)['group']=='REVIEW'
    link['status']='CONFIRMED'
    assert review_state(link)['group']=='CONNECTED'
    assert review_state(link,dict(id='PRG',policy_id='POL',status='REVIEW'))['group']=='REVIEW'
    assert review_state(link,{})['group']=='UNLINKED'

def test_officer_confirmed_news_stays_identifiable_without_releasing_the_mapping():
    r=review_state(dict(policy_id='POL',status='CONFIRMED',evidence_url='https://www.newsis.com/story'))
    assert r['group']=='OFFICER' and r['linked'] and r['officer_confirmed']
    assert r['publisher']=='뉴시스'
    assert review_state(dict(policy_id='POL',status='RELEASED',evidence_url='https://www.korea.kr/a'))['group']=='UNLINKED'
    assert review_state(dict(policy_id='POL',status='CONFIRMED',evidence_url='https://korea.kr.attacker.example/a'))['authority']=='NONOFFICIAL'

def test_five_tags_do_not_treat_officer_estimates_as_observations():
    assert tag(dict(evidence_url='https://www.lh.or.kr/a'))['code']=='OFFICIAL'
    assert tag(dict(evidence_url='https://www.newsis.com/a',officer_confirmed=True))['code']=='OFFICER'
    assert tag(dict(evidence_url='https://www.lh.or.kr/a',inferred=True,officer_confirmed=True))['code']=='ESTIMATED'
    assert tag(missing=True)['code']=='MISSING'
    assert tag(missing=True,upcoming=True)['code']=='UPCOMING'
    assert tag(dict(evidence_url='https://www.newsis.com/a'))['code']=='MISSING'

def test_acquisition_uses_the_same_denominator_and_accepts_zero_units():
    m={'items':[{'cells':{'BUSINESS':{'management':{'target':[{'milestone':'BUSINESS','date':'2026-01-01','units':0,'field_tags':{'date':{'code':'OFFICIAL'},'units':{'code':'ESTIMATED'}}}]}}}}]}
    r=acquisition_summary(m)
    assert r['without_estimates']['total']==r['with_estimates']['total']==24
    assert r['without_estimates']['count']==1 and r['with_estimates']['count']==2

def test_review_scope_excludes_other_policies_and_counts_known_quantities_only():
    from backend.mapping_workbench import build
    class Service:
        def mappings(self):
            return {'policies':[{'policy_id':'POL_2025_0907'},{'policy_id':'OTHER'}],
                'programs':[dict(id='p',name='9.7',policy_id='POL_2025_0907',status='CONFIRMED',evidence_url='https://www.korea.kr/a'),dict(id='q',name='다른 정책',policy_id='OTHER',status='CONFIRMED')],
                'items':[dict(id=pid,name=pid,planned_units=qty,manual_fields=fields,mapping=dict(policy_id=policy,program_id=prg,status='CONFIRMED',evidence_url='https://www.korea.kr/a')) for pid,qty,fields,policy,prg in [('a',100,{},'POL_2025_0907','p'),('b',50,{'planned_units':{'inferred':True}},'POL_2025_0907','p'),('c',None,{},'UNASSIGNED',None),('d',900,{},'OTHER','q')]]}
    r=build(Service())
    assert len(r['items'])==3 and len(r['programs'])==1 and len(r['policies'])==1
    assert r['counts']['CONNECTED']==dict(programs=1,projects=2,units=100,unknown_units=1)
    assert r['counts']['UNLINKED']['unknown_units']==1


def test_officer_category_requires_confirmed_complete_path():
    news=dict(policy_id='POL',status='REVIEW',evidence_url='https://www.newsis.com/a')
    assert review_state(news)['group']=='REVIEW'
    news['status']='CONFIRMED'
    assert review_state(news)['group']=='OFFICER'
    parent=dict(id='prg',**news,review=review_state(news))
    child=dict(policy_id='POL',status='CONFIRMED',evidence_url='https://www.lh.or.kr/a')
    assert review_state(child,parent)['group']=='OFFICER'
    parent['status']='REVIEW'
    assert review_state(child,parent)['group']=='REVIEW'
    assert review_state(dict(policy_id='POL',status='CONFIRMED',evidence_url=''))['group']=='REVIEW'


def test_mixed_basis_is_officer_completed_even_when_primary_url_is_official():
    link=dict(policy_id='POL',status='CONFIRMED',evidence_url='https://www.fsc.go.kr/a',basis='공식 정부 자료; 담당자 확인 - 비공식 자료: 건설사 수주 목록을 대조하여 확인')
    r=review_state(link)
    assert r['group']=='OFFICER' and r['authority']=='OFFICIAL' and r['mixed_officer_basis']
    link['status']='REVIEW'
    assert review_state(link)['group']=='REVIEW'


def test_focus_project_can_open_its_other_policy_without_changing_default_scope():
 from backend.mapping_workbench import build
 from copy import deepcopy
 raw=dict(policies=[dict(policy_id='POL_2025_0907',name='9·7'),dict(policy_id='OTHER',name='다른 정책')],programs=[dict(id='program',policy_id='OTHER',name='다른 프로그램',status='REVIEW',project_count=1)],items=[dict(id='other-project',name='신길4',planned_units=100,mapping=dict(policy_id='OTHER',program_id='program',status='REVIEW',basis='기존 사유'))])
 class Service:
  def mappings(self):return deepcopy(raw)
 assert build(Service())['items']==[]
 selected=build(Service(),focus_project_id='other-project')
 assert selected['active_policy_id']=='OTHER' and selected['items'][0]['id']=='other-project'
 assert selected['programs'][0]['id']=='program' and selected['policies'][0]['policy_id']=='OTHER'
