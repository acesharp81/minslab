import io
import math
import pytest
from PIL import Image,ImageDraw
from app.taegeukgi import inspect


def diagram(names=('건','감','리','곤'),scale=1):
    d=120;im=Image.new('RGB',(440,320),'white');draw=ImageDraw.Draw(im);cx,cy=220,160
    draw.pieslice((cx-d/2,cy-d/2,cx+d/2,cy+d/2),180,360,fill=(210,0,40))
    draw.pieslice((cx-d/2,cy-d/2,cx+d/2,cy+d/2),0,180,fill=(0,90,170))
    patterns={'건':[1,1,1],'감':[2,1,2],'리':[1,2,1],'곤':[2,2,2]}
    for (sx,sy),name in zip([(-1,-1),(1,-1),(-1,1),(1,1)],names):
        px,py=cx+sx*d*.75,cy+sy*d*.51
        v=(.5547,-sx*sy*.83205);n=(-v[1],v[0])
        for row,segments in enumerate(patterns[name]):
            offset=(row-1)*d/8
            spans=[(-d/4,d/4)] if segments==1 else [(-d/4,-d/48),(d/48,d/4)]
            for a,b in spans:
                points=[(px+v[0]*u+n[0]*(offset+t),py+v[1]*u+n[1]*(offset+t)) for u,t in [(a,-d/24),(b,-d/24),(b,d/24),(a,d/24)]]
                draw.polygon(points,fill='black')
    return im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)


def raw(im,fmt='PNG'):
    out=io.BytesIO();im.save(out,format=fmt,quality=85);return out.getvalue()

@pytest.mark.parametrize('scale,fmt',[(1,'PNG'),(.65,'PNG'),(1.4,'JPEG')])
def test_correct_and_exchanged_trigrams(scale,fmt):
    flags=inspect(raw(diagram(scale=scale),fmt))['flags'];assert len(flags)==1
    assert flags[0]['status']=='MATCH'
    flags=inspect(raw(diagram(('건','리','감','곤'),scale),fmt))['flags']
    assert len(flags)==1 and flags[0]['status']=='MISMATCH'
    assert [t['match'] for t in flags[0]['trigrams']]==[True,False,False,True]


def test_occlusion_does_not_become_pass_and_logo_not_flag():
    im=diagram();ImageDraw.Draw(im).rectangle((90,65,165,125),fill='white')
    flags=inspect(raw(im))['flags'];assert not flags or all(f['status']!='MATCH' for f in flags)
    im=Image.new('RGB',(400,300),'white');ImageDraw.Draw(im).ellipse((140,90,260,210),fill='red')
    assert inspect(raw(im))['flags']==[]


def test_unsupported_rotation_is_not_claimed_correct():
    assert not any(f['status']=='MATCH' for f in inspect(raw(diagram().rotate(30,fillcolor='white')))['flags'])


def test_measurements_never_replace_original_rule_analysis_and_reuse_is_full(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.config import Settings
    from test_observations import poll, inventory, BATCHES
    import json
    settings=Settings({'DATA_DIR':str(tmp_path),'ADMIN_PASSWORD':'test','COOKIE_SECURE':'false','EXTERNAL_API_ENABLED':'true','OPENAI_API_KEY':'test','UPSTAGE_API_KEY':'test'})
    with TestClient(create_app(settings)) as c:
        c.post('/api/login',json={'role':'admin','password':'test'})
        j=c.post('/api/jobs',files={'file':('flag.png',raw(diagram()),'image/png')}).json()
        calls=[]
        c.app.state.engine.s.values['AUTO_VERIFY_MAX_CALLS']='0'
        def fake(model,prompt,images=(),workload='image-inspection'):
            payload=json.loads(prompt);calls.append((workload,payload))
            meta={'model':model,'usage':{'input_tokens':1,'output_tokens':1}}
            if images:
                assert len(payload['inspection_checklist'])==25
                assert all(p['original'] for p in payload['inspection_checklist'])
                return inventory(),meta
            assert payload['original_checklist']
            if any(p['id']=='H-04' for p in payload['original_checklist']):assert payload['structural_checks']['flags']
            else:assert payload['structural_checks'] is None
            return {'results':[{'target_presence':'ABSENT','rule_ids':[r['rule_id']],'status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'원문에 따른 적용 대상 검토 결과','recommended_action':'없음'} for r in payload['rules']]},meta
        c.app.state.engine.provider.call=fake
        path='/api/jobs/'+j['id']
        c.post(path+'/runs',json={'mode':'live','consent':True,'rule_ids':['H-04-h','H-04-i']})
        j=poll(c,j['id']);old=j['runs'][-1]
        assert [x[0] for x in calls]==['image-observation','checklist-analysis']
        assert [r['rule_id'] for r in calls[-1][1]['rules']]==['H-04-h','H-04-i']
        assert not any(r['model'].startswith('local/') for r in old['results'])
        assert old['structural_checks']['flags'][0]['status']=='MATCH'
        calls.clear()
        c.post(path+'/runs',json={'mode':'live','consent':True,'rule_ids':[],'reuse_observation_run_id':old['id'],'force':True})
        j=poll(c,j['id'])
        assert j['runs'][0]==old
        assert len(j['runs'][-1]['selected'])==156
        assert len(calls)==BATCHES and all(x[0]=='checklist-analysis' for x in calls)
        report=j['checklist_report'];assert report['total']==25 and report['complete_count']==25 and report['assessed_steps']==156
        assert all(item['original'] and item['evaluations'] for item in report['items'])
        assert all(not item['technical_evidence'] for item in report['items'] if item['id']!='H-04')
