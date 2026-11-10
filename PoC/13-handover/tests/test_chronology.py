import copy
import io
import zipfile
from datetime import date
from test_flow import client, new_case, generate
from test_reports import confirm
from app.flow_demo import WORKS
from app.timeline import project_latest, reported_progress, urgency, report_metadata
from app.reports import build_report, render_html


def test_multistage_matching_and_gantt_report(client):
 c=client;base=new_case(c)
 archive=c.get('/samples/flow.zip');assert archive.status_code==200
 with zipfile.ZipFile(io.BytesIO(archive.content)) as z:assert len(z.namelist())==11
 assert c.post(base+'/documents',files={'file':('flow.zip',archive.content)}).status_code==200
 rev=generate(c,base);items=rev['payload']['items'];assert len(items)==5
 for w in WORKS[:3]:
  item=next(i for i in items if i['fields']['title']['value']==w['title'])
  assert len(item['timeline'])==3
  assert [e['progress'] for e in item['timeline']]==[r[2] for r in w['reports']]
  assert reported_progress(item)==w['reports'][-1][2]
  assert item['fields']['issues']['value']==w['reports'][-1][6]
 target=next(i for i in items if i['fields']['title']['value']==WORKS[3]['title'])
 source=next(i for i in items if i['fields']['title']['value']=='예약포털 접근성 보완')
 body={'expected_hash':rev['hash'],'target_id':target['id'],'source_id':source['id'],'owner':'디지털지원팀','reason':'HB-004 동일 업무·담당을 전임자에게 확인'}
 url=base+f'/revisions/{rev["id"]}/match'
 assert c.post(url,json=body,headers={'X-Role':'successor'}).status_code==403
 assert c.post(url,json={**body,'source_id':target['id']}).status_code==422
 matched=c.post(url,json=body);assert matched.status_code==200,matched.text
 new=matched.json();assert len(new['payload']['items'])==4
 assert c.post(url,json=body).status_code==409
 item=next(i for i in new['payload']['items'] if i['id']==target['id'])
 assert reported_progress(item)==75 and len(item['source_documents'])==2
 assert item['fields']['owner']['provenance']=='HUMAN_ENTERED'
 assert item['fields']['issues']['value']=='키보드 탐색 오류 2건 미해결'
 assert c.get(base+f'/revisions/{rev["id"]}').json()['payload']==rev['payload']
 confirm(c,base,new)
 confirmed=c.get(base+'/revisions/confirmed').json()
 # Fixed date test independent of execution date. Live report freezes actual confirmation date.
 confirmed['confirmation']['created']='2026-11-09T00:00:00+00:00'
 report=build_report(c.get(base).json(),confirmed,lambda bid:c.get(base+'/blocks/'+bid).json())
 assert [t['urgency']['key'] for t in report['tasks']]==['soon','overdue','complete','issue']
 html=render_html(report)
 assert html.index('class="gantt-wrap"')<html.index('id="overview"')
 for text in ['65%','40%','100%','75%','지연 3일','D-3','D-15','기준일 11/09']:assert text in html
 assert report['completed']==1
 for fmt in ['html','md','docx']:
  a=c.get(base+f'/exports/{new["id"]}.{fmt}');b=c.get(base+f'/exports/{new["id"]}.{fmt}',headers={'X-Role':'successor'});assert a.status_code==b.status_code==200
  if fmt!='docx':assert a.content==b.content
  else:
   with zipfile.ZipFile(io.BytesIO(a.content)) as z:assert 'word/media/image1.png' in z.namelist()
 assert c.get(base+'/reports/confirmed').status_code==200


def test_uncertain_dates_no_invented_progress_and_no_discrepancy_urgency():
 item={'fields':{'title':{'value':'a'},'status':{'value':'검토 중'},'due_date':{'value':'2026-11-01 / 2026-11-30','review_status':'CONFLICT'},'issues':{'value':'없음'}},'timeline':[{'document_id':'x','reported_at':None,'progress':80,'fields':{}},{'document_id':'y','reported_at':'2026-11-08','progress':90,'fields':{}}]}
 item['latest_document_id']='y'
 project_latest(item);assert reported_progress(item) is None
 assert urgency(item,date(2026,11,9))['key']=='normal'
 assert not report_metadata([])['progress']
