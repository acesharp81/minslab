from app import text_selection as t, verification as v
from app.rules import PACK


def obj(i,label):
    return dict(id=i,label=label,description='',text='문구',text_legibility='CLEAR',quality='CLEAR',cell_ids=['R04C04'])


def test_many_small_labels_do_not_starve_heading_and_body():
    objects=[obj(str(i),'작은 안내판') for i in range(20)]+[obj('title','큰 제목'),obj('agency','기관명'),obj('body','본문')]
    steps={s['rule_id']:s for s in PACK['steps']}
    tasks=v.candidates({'objects':objects},[],steps,list(steps),balanced=True)
    assert {t.role(x['object']) for x in tasks[:4]}==set(t.ROLES)
    assert len({x['object']['id'] for x in tasks})==len(objects)


def test_nontext_domain_budget_still_reserved():
    objects=[obj(str(i),'기관명') for i in range(20)]+[dict(id='hand',label='오른손',description='손가락',text='',text_legibility='NOT_TEXT',quality='UNCERTAIN',cell_ids=['R05C05'])]
    steps={s['rule_id']:s for s in PACK['steps']}
    assert 'hand' in [x['object']['id'] for x in v.candidates({'objects':objects},[],steps,list(steps),balanced=True)[:9]]


def test_partial_checks_not_counted_as_full_role_coverage():
    cv=v.coverage({'objects':[obj('title','제목'),obj('body','본문')]},{'results':[dict(object_id='title',status='COMPLETED',coverage='PARTIAL')]})
    assert cv['roles']['heading']==dict(label='제목',detected=1,rechecked=0)
