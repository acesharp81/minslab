"""Atomic multi-work grouping, preserving immutable source and human edit history."""
import copy
from .engine import FIELDS,empty_field,merge_field,annotate_items
from .timeline import project_latest
from .store import now


def regroup(payload,groups,reason):
    lookup={i['id']:i for i in payload['items']}
    ids=[ident for g in groups for ident in g['item_ids']]
    if len(ids)!=len(set(ids)) or set(ids)!=set(lookup):raise ValueError('모든 업무를 빠짐없이 한 묶음에만 배치해 주세요.')
    output=[]
    for group in groups:
        members=[lookup[ident] for ident in group['item_ids']]
        if not members or not group['title'].strip() or not group['owner'].strip():raise ValueError('묶음의 업무명과 담당자를 확인해 주세요.')
        target=copy.deepcopy(members[0]);changed=len(members)>1
        # Conflicting human confirmations must never silently disappear in grouping.
        for key in FIELDS:
            human=[m['fields'].get(key,{}) for m in members if m['fields'].get(key,{}).get('provenance')=='HUMAN_ENTERED']
            if key not in {'title','owner'} and len({f.get('value','') for f in human})>1:raise ValueError(FIELDS[key]+'에 서로 다른 직접 확인값이 있습니다. 항목을 먼저 정정해 주세요.')
            if human and key not in {'title','owner'}:target['fields'][key]=copy.deepcopy(human[0])
        for member in members[1:]:
            for key in FIELDS:
                if target['fields'][key].get('provenance')!='HUMAN_ENTERED':target['fields'][key]=merge_field(key,target['fields'][key],copy.deepcopy(member['fields'].get(key,empty_field())))
            for key in ('timeline','supporting_records','match_history'):target.setdefault(key,[]).extend(copy.deepcopy(member.get(key,[])))
            for key in ('source_documents','related_blocks'):target[key]=sorted(set(target.get(key,[])+member.get(key,[])))
            target.setdefault('match_history',[]).append({'source_id':member['id'],'source_title':member['fields']['title']['value'],'target_title':group['title'].strip(),'owner':group['owner'].strip(),'reason':reason,'actor':'PREDECESSOR','created':now()})
        # Keep the target's verified human inputs; content chronology selects the rest.
        if changed and target.get('timeline'):project_latest(target)
        for key,value in [('title',group['title'].strip()),('owner',group['owner'].strip())]:
            if changed or target['fields'][key]['value']!=value:
                previous=copy.deepcopy(target['fields'][key])
                target['fields'][key]={'value':value,'provenance':'HUMAN_ENTERED','review_status':'CONFIRMED','evidence':[],'observations':[],'previous':previous,'reason':reason,'actor':'PREDECESSOR','changed_at':now()}
        if changed and payload.get('inheritance'):
            states={m.get('inheritance_status','신규 업무') for m in members}
            target['inheritance_status']=('현행화 확인 필요' if any('확인 필요' in s for s in states) else '기존 업무 현행화' if '기존 업무 현행화' in states or {'신규 업무','이전 보고서 유지'}<=states else '이전 보고서 유지' if '이전 보고서 유지' in states else '신규 업무')
        if changed:
            target['merge_note']='인계자가 여러 업무를 하나로 묶고 업무명·담당자를 확인했습니다.'
            target['image_reviews']=[v for m in members for v in m.get('image_reviews',[]) if v['document_id']==target.get('latest_document_id')]
        output.append(target)
    payload['items']=annotate_items(output)
    if payload.get('inheritance'):
        counts={'updated':0,'carried':0,'new':0,'review':0}
        keys={'기존 업무 현행화':'updated','이전 보고서 유지':'carried','신규 업무':'new'}
        for item in output:counts[keys.get(item.get('inheritance_status'),'review')]+=1
        payload['inheritance']['counts']=counts
    return payload
