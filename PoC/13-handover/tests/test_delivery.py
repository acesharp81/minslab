from test_flow import client,seed,generate
from test_reports import confirm


def body(rev,message='미접수 증빙을 확인하고 다음 주 일정을 협의해 주세요.'):
 return {'revision_id':rev['id'],'expected_hash':rev['hash'],'recipient_id':'employee2','message':message}


def test_delivery_pins_confirmed_report_comment_and_recipient(client):
 c=client;base,rev=seed(c);b=body(rev)
 assert c.post(base+'/deliver',json=b).status_code==409
 confirm(c,base,rev)
 assert c.post(base+'/deliver',json=b,headers={'X-Employee':'employee2'}).status_code==403
 assert c.post(base+'/deliver',json={**b,'recipient_id':'employee3'}).status_code==409
 assert c.post(base+'/deliver',json=body(rev,'   ')).status_code==422
 r=c.post(base+'/deliver',json=b,headers={'X-Employee':'employee1'});assert r.status_code==200,r.text
 d=r.json();assert d['revision_hash']==rev['hash'] and d['recipient_id']=='employee2' and d['message']==b['message']
 assert c.post(base+'/deliver',json=b).json()['id']==d['id']
 assert c.post(base+'/deliver',json=body(rev,'다른 의견')).status_code==409
 received=c.get(base,headers={'X-Employee':'employee2'}).json()['deliveries'];assert received==[d]
 assert c.get(base,headers={'X-Employee':'employee3'}).status_code==403
 rows=c.get('/api/cases',headers={'X-Employee':'employee2'}).json();assert next(x for x in rows if x['id']==d['case_id'])['delivery']['revision_id']==rev['id']
 assert c.post(base+'/accept',headers={'X-Employee':'employee2'},json={'expected_hash':rev['hash']}).status_code==200
 assert c.get(base,headers={'X-Employee':'employee2'}).json()['accepted']


def test_new_draft_and_new_documents_cannot_deliver_old_confirmation(client):
 c=client;base,rev=seed(c);confirm(c,base,rev)
 item=rev['payload']['items'][0]
 edit=c.patch(base+f"/revisions/{rev['id']}/items/{item['id']}",json={'expected_hash':rev['hash'],'fields':{'notes':'다음 인계 전 확인'},'reason':'추가 확인'});assert edit.status_code==200
 assert c.post(base+'/deliver',json=body(rev)).status_code==409
 newer=edit.json();confirm(c,base,newer)
 assert c.post(base+'/deliver',json=body(newer)).status_code==200
 c.post(base+'/documents',files={'file':('new.txt','업무: 추가 업무\n담당: 직원 1'.encode())}).raise_for_status()
 assert c.post(base+'/deliver',json=body(newer)).status_code==409
 assert len(c.get(base).json()['deliveries'])==1
