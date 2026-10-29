from app.checklist_report import build
from app.rules import PACK,STEPS,placeholder


def test_originals_all_present_and_missing_rules_not_hidden():
    r=placeholder('H-04-i','FAIL','배치 다름');r.update(id='local',model='local/trigrams-v1')
    report=build({'results':[r],'rule_pack':PACK,'selected':['H-04-i']})
    assert len(report['items'])==25 and report['assessed_steps']==0
    h=next(p for p in report['items'] if p['id']=='H-04')
    assert h['original']==next(p['original'] for p in PACK['parents'] if p['id']=='H-04')
    assert 'H-04-i' in h['missing_rule_ids'] and h['status']=='NOT_RUN'


def test_nonflag_findings_have_original_evidence_reason_action_and_review():
    rows=[]
    for rid in STEPS:
        row=placeholder(rid,'NOT_APPLICABLE','관련 대상이 관찰되지 않음');row.update(id=rid,model='solar-pro4')
        rows.append(row)
    target=next(r for r in rows if r['rule_id']=='D-04-a')
    target.update(status='REVIEW',observation='포스터 하단에 전화번호 형식 문자열',reason='공개 동의 확인 필요',recommended_action='담당자 연락처인지 확인',evidence_ids=['contact'])
    report=build({'results':rows,'rule_pack':PACK,'selected':list(STEPS)})
    assert report['complete_count']==25 and report['assessed_steps']==156
    p=next(p for p in report['items'] if p['id']=='D-04');finding=p['evaluations'][0]
    assert p['status']=='REVIEW' and finding['evidence_ids']==['contact']
    assert finding['observation']==target['observation'] and finding['reason']==target['reason'] and finding['action']==target['recommended_action']
    reviewed=build({'results':rows,'rule_pack':PACK,'selected':list(STEPS),'reviews':[{'finding_id':'D-04-a','status':'PASS'}]})
    assert next(p for p in reviewed['items'] if p['id']=='D-04')['status']=='PASS'
