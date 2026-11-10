"""Frozen accepted-report snapshots, scoped evidence copies and conservative updates."""
import copy
import html
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from .store import digest, dump, now
from .engine import normalize, annotate_items
from .timeline import project_latest
from .versions import newest, eligible


def candidates(db, target):
    return [dict(r) for r in db.execute('''SELECT c.id,c.title,c.predecessor,c.successor,c.accepted,c.confirmed AS revision_id,r.hash
      FROM cases c JOIN case_members m ON m.case_id=c.id JOIN revisions r ON r.id=c.confirmed
      JOIN case_members t ON t.case_id=? AND t.predecessor_id=m.successor_id
      WHERE c.accepted IS NOT NULL AND c.id!=? ORDER BY c.accepted DESC''',(target,target))]


def remap(value, ids):
    if isinstance(value,dict):return {k:remap(v,ids) for k,v in value.items()}
    if isinstance(value,list):return [remap(v,ids) for v in value]
    return ids.get(value,value) if isinstance(value,str) else value


def freeze(db, store, target, source_id, revision_id):
    source=next((r for r in candidates(db,target) if r['id']==source_id and r['revision_id']==revision_id),None)
    if not source:raise HTTPException(409,'현재 인계자가 인수 완료한 확정본을 다시 선택해 주세요.')
    original=json.loads(db.execute('SELECT payload FROM revisions WHERE id=?',(revision_id,)).fetchone()[0])
    if len(original.get('handover_chain',[]))>=30:raise HTTPException(422,'인수인계 이력은 최대 30단계까지 지원합니다.')
    ids={};stamp=now()
    for doc_id in original['document_ids']:
        doc=db.execute('SELECT * FROM documents WHERE id=? AND case_id=?',(doc_id,source_id)).fetchone()
        if not doc:raise HTTPException(422,'이전 보고서의 원문 자료를 확인할 수 없습니다.')
        new=digest(['inherited-doc',target,doc_id]);ids[doc_id]=new
        path=f"이전 인계/{source_id[:12]}/{doc_id[:12]}/{doc['path']}"
        db.execute('INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?)',(new,target,path,doc['sha'],doc['format'],stamp))
        db.execute('INSERT OR IGNORE INTO inherited_documents VALUES (?,?,?)',(new,target,doc_id))
    for parse_id in original['corpus']:
        parsed=db.execute('SELECT * FROM parses WHERE id=?',(parse_id,)).fetchone()
        if not parsed or parsed['doc_id'] not in ids:raise HTTPException(422,'이전 보고서의 분석 근거를 확인할 수 없습니다.')
        new=digest(['inherited-parse',target,parse_id]);ids[parse_id]=new
        db.execute('INSERT OR IGNORE INTO parses VALUES (?,?,?,?,?,?)',(new,ids[parsed['doc_id']],parsed['parser'],parsed['status'],parsed['warnings'],stamp))
        for block in db.execute('SELECT * FROM blocks WHERE parse_id=? AND case_id=?',(parse_id,source_id)).fetchall():
            block_id=digest(['inherited-block',target,block['id']]);ids[block['id']]=block_id
            db.execute('INSERT OR IGNORE INTO blocks VALUES (?,?,?,?,?,?,?,?,?)',(block_id,target,new,ids[block['doc_id']],block['ordinal'],block['location'],block['kind'],block['text'],block['sha']))
    payload=remap(original,ids)
    # Old images remain in the accepted snapshot; they are not sent for inference again.
    for item in payload['items']:item['image_reviews']=[]
    chain=copy.deepcopy(original.get('handover_chain',[]))
    chain.append({'case_id':source_id,'revision_id':revision_id,'hash':source['hash'],'predecessor':source['predecessor'],'successor':source['successor'],'date':source['accepted'],'status':'인수인계완료'})
    store.audit(db,target,'INHERIT_ACCEPTED_REPORT',{'source_case':source_id,'source_revision':revision_id,'source_hash':source['hash']})
    return {'source':source,'payload':payload,'chain':chain}


def codes(item):
    return {e['work_code'] for e in item.get('timeline',[])+item.get('supporting_records',[]) if e.get('work_code')}


def combine(basis, fresh):
    old=copy.deepcopy(basis['payload']['items']);used=set();output=[]
    counts={'updated':0,'carried':0,'new':0,'review':0}
    for item in fresh:
        code=codes(item);title=normalize(item['fields']['title']['value'])
        matches=[i for i,b in enumerate(old) if (len(code)==1 and code==codes(b)) or (title==normalize(b['fields']['title']['value']) and not(code and codes(b) and code!=codes(b)))]
        if len(matches)!=1 or matches[0] in used:
            item['inheritance_status']='신규 업무' if not matches else '동일 업무 확인 필요'
            counts['new' if not matches else 'review']+=1;output.append(item);continue
        index=matches[0];used.add(index);base=old[index];merged=copy.deepcopy(item)
        merged['id']=base['id'];merged['timeline']=base.get('timeline',[])+item.get('timeline',[])
        merged['supporting_records']=base.get('supporting_records',[])+item.get('supporting_records',[])
        merged['source_documents']=sorted(set(base['source_documents']+item['source_documents']))
        merged['match_history']=base.get('match_history',[])+item.get('match_history',[])
        merged=project_latest(merged)
        # A dated update must also follow the accepted baseline; undated/draft updates cannot erase it.
        cutoff=basis['source']['accepted'][:10]
        fresh_ids={e['document_id'] for e in item.get('timeline',[])+item.get('supporting_records',[])}
        changed=False;pending=False
        for key,prior in base['fields'].items():
            observations=[e for e in merged['timeline']+merged['supporting_records'] if eligible(e) and e['fields'].get(key,{}).get('value')]
            selected,_=newest(observations)
            can_update=selected and selected['document_id'] in fresh_ids and (selected.get('reported_at') or '')>=cutoff
            if can_update:
                value=copy.deepcopy(selected['fields'][key])
                if value['value']!=prior['value']:value['previous']=copy.deepcopy(prior);changed=True
                merged['fields'][key]=value
            else:
                merged['fields'][key]=copy.deepcopy(prior)
                pending=pending or bool(not selected and any(e['document_id'] in fresh_ids for e in observations))
        latest=next((e for e in merged['timeline'] if e['document_id']==merged.get('latest_document_id')),None)
        if latest and latest['document_id'] in fresh_ids and (latest.get('reported_at') or '')<cutoff:
            merged['latest_document_id']=base.get('latest_document_id');pending=True
        kind='review' if pending else 'updated' if changed else 'carried'
        merged['inheritance_status']={'review':'현행화 확인 필요','updated':'기존 업무 현행화','carried':'이전 보고서 유지'}[kind]
        counts[kind]+=1;output.append(merged)
    for index,item in enumerate(old):
        if index not in used:item['inheritance_status']='이전 보고서 유지';counts['carried']+=1;output.append(item)
    return annotate_items(output),counts


def chain_lines(report):
    if not report.get('inheritance'):return []
    rows=report.get('handover_chain',[])+[{'predecessor':report['predecessor'],'successor':report['successor'],'date':report['confirmed_at'],'status':'이번 인계'}]
    lines=[]
    for row in rows:
        dt=datetime.fromisoformat(row['date'].replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Seoul'))
        lines.append(f"{row['predecessor']} → {row['successor']} ('{dt:%y}.{dt.month}.{dt.day}., {row['status']})")
    return lines


def banner(report):
    lines=chain_lines(report)
    if not lines:return ''
    counts=report['inheritance']['counts'];summary=f"기존 업무 현행화 {counts['updated']}건 · 이전 내용 유지 {counts['carried']}건 · 신규 업무 {counts['new']}건 · 확인 필요 {counts['review']}건"
    return '<section class="inheritance-banner" id="handover-history"><h2>이전 인계 보고서 기반 · 인수인계 이력</h2><ol>'+''.join('<li>'+html.escape(line)+'</li>' for line in lines)+'</ol><p>'+summary+'</p><small>이전 인수 완료 판본을 보존하고 새 자료를 반영했습니다. 기존 내용 유지 항목은 최신 현황을 다시 확인하세요.</small></section>'
