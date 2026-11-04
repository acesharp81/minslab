"""Versioned, approved term criteria; literal OCR evidence is never normalized in place."""
from datetime import date
import json
import re
import unicodedata

SCHEMA='chekmi-term-dictionary-v1'


def normalized(text):
    return unicodedata.normalize('NFKC',text).casefold()


def find_literals(text, aliases):
    """Map normalized matches back to literal spans; never rewrite the OCR source."""
    pieces=[];positions=[]
    for m in re.finditer(r'.(?:[\u0300-\u036f\u1160-\u11ff])*',text,re.S):
        part=normalized(m.group());pieces.append(part);positions.extend([(m.start(),m.end())]*len(part))
    match_text=''.join(pieces);spans=set()
    for alias in aliases:
        needle=normalized(alias)
        for m in re.finditer(re.escape(needle),match_text):
            if m.start()!=m.end():spans.add((positions[m.start()][0],positions[m.end()-1][1]))
    return [text[a:b] for a,b in sorted(spans)]


def parse(content):
    try:doc=json.loads(content)
    except (ValueError,TypeError):return None
    if not isinstance(doc,dict) or doc.get('schema')!=SCHEMA:return None
    if not isinstance(doc.get('version'),str) or not doc['version'].strip():raise ValueError('용어 사전 version이 필요합니다.')
    terms=doc.get('terms')
    if not isinstance(terms,list) or not 1<=len(terms)<=300:raise ValueError('용어 사전은 1~300개 항목이어야 합니다.')
    seen=set()
    for term in terms:
        if not isinstance(term,dict) or not isinstance(term.get('id'),str) or term['id'] in seen:raise ValueError('용어 사전 항목 ID는 중복 없는 문자열이어야 합니다.')
        seen.add(term['id'])
        if not isinstance(term.get('canonical'),str) or not 1<=len(term['canonical'])<=100:raise ValueError('기준 표기는 1~100자여야 합니다.')
        for field in ('context','aliases','sources','rule_ids'):
            values=term.get(field)
            if not isinstance(values,list) or not values or len(values)>30 or not all(isinstance(v,str) and 1<=len(v)<=1000 for v in values):raise ValueError('용어 항목의 context·aliases·sources·rule_ids가 필요합니다.')
        if any(not url.startswith('https://') for url in term['sources']):raise ValueError('용어 출처는 HTTPS 주소여야 합니다.')
        if term.get('severity','REVIEW') not in ('REVIEW','FAIL'):raise ValueError('용어 심각도는 REVIEW 또는 FAIL입니다.')
        for field in ('valid_from','valid_until'):
            if term.get(field):date.fromisoformat(term[field])
        if term.get('valid_from') and term.get('valid_until') and term['valid_from']>term['valid_until']:raise ValueError('용어 적용 기간을 확인하세요.')
    return doc


def active(run, builtin):
    terms=[{**t,'version':builtin['version']} for t in builtin['terms']]
    at=run.get('inspection_date') or run.get('created_at','')[:10] or date.today().isoformat()
    for ref in run.get('reference_snapshot',[]):
        if ref.get('status')!='APPROVED' or ref.get('kind')!='language':continue
        try:doc=parse(ref.get('content',''))
        except (ValueError,TypeError):continue
        if not doc:continue
        for term in doc['terms']:
            if term.get('valid_from') and at<term['valid_from'] or term.get('valid_until') and at>term['valid_until']:continue
            terms.append({**term,'version':doc['version'],'dictionary_reference_id':ref['id'],'parent_ids':ref.get('parent_ids',[])})
    return terms
