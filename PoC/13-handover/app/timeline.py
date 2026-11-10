"""Source-labelled report chronology. No dates or completion percentages are inferred."""
import copy
import re
from datetime import date
from .engine import evidence, empty_field, merge_field
from .practice_fields import PROFILE_FIELDS, document_role
from .versions import metadata, newest, eligible, ordered, VERSION_POLICY


def _legacy_report_metadata(blocks):
    patterns={'start_date':r'(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*)?계획 시작일\s*[:：]\s*(\d{4}-\d{2}-\d{2})(?=\s|$|[|])',
              'completed_at':r'(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*)?실제 완료일\s*[:：]\s*(\d{4}-\d{2}-\d{2})(?=\s|$|[|])',
              'reported_at':r'(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*)?보고일\s*[:：]\s*(\d{4}-\d{2}-\d{2})(?=\s|$|[|])',
              'stage':r'(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*)?보고단계\s*[:：]\s*(계획|착수|중간|완료)(?:보고)?(?=\s|$|[|])',
              'progress':r'(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*)?전체\s*진행률\s*[:：]\s*(\d{1,3})\s*%',
              'work_code':r'(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*)?연계관리번호\s*[:：]\s*([A-Za-z0-9-]+)'}
    values={};refs=[]
    for key,pattern in patterns.items():
        matches=[(m,b) for b in blocks for m in re.finditer(pattern,b['text'])]
        distinct={m.group(1) for m,b in matches}
        if len(distinct)!=1:values[key]=None;continue
        m,b=matches[0];v=m.group(1)
        if key in {'reported_at','start_date','completed_at'}:
            try:date.fromisoformat(v)
            except ValueError:v=None
        if key=='progress':v=int(v) if int(v)<=100 else None
        values[key]=v
        if v is not None:refs.append(evidence(b,m.group(0).strip()))
    return {**values,'metadata_evidence':refs}


def report_metadata(blocks):
    old=_legacy_report_metadata(blocks);new=metadata(blocks,evidence)
    for key,value in new.items():
        if value is not None:old[key]=value
    return old


def attach_timeline(result,document,blocks):
    role=document_role(blocks)
    metadata=report_metadata(blocks) if len(result['candidates'])==1 or role=='업무기준정보' else report_metadata([])
    for candidate in result['candidates']:
        event={'document_id':document['id'],'path':document['path'],**copy.deepcopy(metadata),'fields':copy.deepcopy(candidate['fields'])}
        candidate['supporting_records' if role=='업무기준정보' else 'timeline']=[event]
    return result


def project_latest(item):
    events=item.get('timeline',[]);support=item.get('supporting_records',[])
    item.pop('latest_document_id',None)
    current=[e for e in events if eligible(e)]
    latest,reason=newest(current)
    item['version_policy']=VERSION_POLICY
    item['chronology_note']=reason+' 파일명·저장일·업로드 순서는 판단에 사용하지 않습니다.'
    item['timeline']=events=ordered(events)
    for event in events:
        event['selection_status']='excluded' if not eligible(event) else 'selected' if latest and event['document_id']==latest['document_id'] else 'superseded' if latest else 'ambiguous'
        event['selection_reason']='본문 문서상태: '+str(event.get('document_state')) if not eligible(event) else reason
    # Rebuild from eligible sources so a newer draft cannot survive a merged field.
    for key in list(item['fields']):
        if key=='title' or item['fields'][key].get('provenance')=='HUMAN_ENTERED':continue
        field=empty_field()
        for event in current:field=merge_field(key,field,copy.deepcopy(event['fields'].get(key,empty_field())))
        item['fields'][key]=field
    if latest:
        for key,field in latest['fields'].items():
            if key!='title' and key not in PROFILE_FIELDS and item['fields'].get(key,{}).get('provenance')!='HUMAN_ENTERED':item['fields'][key]=copy.deepcopy(field)
        item['latest_document_id']=latest['document_id']
    # Carry the brief forward even when a later progress report does not repeat it.
    for key in PROFILE_FIELDS:
        if item['fields'].get(key,{}).get('provenance')=='HUMAN_ENTERED':continue
        observations=[e for e in current+support if e['fields'].get(key,{}).get('value')]
        if not observations:continue
        selected_event,_=newest(observations)
        selected=[selected_event] if selected_event else observations
        field=empty_field()
        for event in selected:field=merge_field(key,field,copy.deepcopy(event['fields'][key]))
        item['fields'][key]=field
    return item


def reported_progress(item):
    events=item.get('timeline',[])
    selected=next((e for e in events if e['document_id']==item.get('latest_document_id')),None)
    return selected.get('progress') if selected else None


def has_business_issue(text):
    text=text.strip()
    return bool(text) and not re.match(r'^(없음|해소됨|해소 완료|해당 없음|미기재|미확인)(?:\s|$|[(:：.])',text)


def urgency(item,basis):
    fields=item['fields'];due=fields['due_date'];done=item.get('business_status')=='COMPLETED'
    if done:return {'key':'complete','label':'업무 완료','delta':None}
    if due.get('normalized_date') and due.get('review_status')!='CONFLICT':
        delta=(date.fromisoformat(due['normalized_date'])-basis).days
        if delta<0:return {'key':'overdue','label':f'기한 {abs(delta)}일 경과 · 이행 확인','delta':delta}
        if delta<=7:return {'key':'soon','label':'오늘 기한' if delta==0 else f'기한 {delta}일 남음','delta':delta}
    if has_business_issue(fields.get('issues',{}).get('value','')):return {'key':'issue','label':'업무 장애·미결 현안','delta':None}
    return {'key':'normal','label':'진행 중 · 다음 조치 확인','delta':None}
