"""Versioned Markdown authoring. Rule IDs and technical safeguards stay stable."""
import copy
import hashlib
import json
import re
from .rules import PACK
from .storage import now

BASE_VERSION=PACK['version']

def compatibility_warnings(pack):
    warnings=[]
    for parent in pack['parents']:
        ids=sorted(set(re.findall(r'\b[HEPD]-\d{2}-[a-z]\b',parent['original'])))
        if ids:warnings.append(parent['id']+': 상위 본문에 세부 ID가 중복 설명되어 있습니다 ('+', '.join(ids)+'). 의미는 각 ### ID 본문과 일치해야 합니다.')
    return warnings

def to_markdown(pack):
    lines=['# 췤미! 검수 규칙','', '# 공통 검수 지침','',pack.get('guidance','관찰 근거와 제작 의도를 함께 확인하세요. 불확실한 사실을 단정하지 마세요.'),'']
    for parent in pack['parents']:
        lines += [f"## {parent['id']} | {parent['title']}",'',parent['original'],'']
        for step in pack['steps']:
            if step['parent_id']==parent['id']:lines += [f"### {step['rule_id']}",'',step['objective'],'']
    return '\n'.join(lines)


def parse_markdown(markdown):
    # No executable YAML/HTML. Reserved headings define records; other text is prose.
    if not markdown.strip() or len(markdown)>150000:raise ValueError('Markdown은 1~150,000자여야 합니다.')
    headings=list(re.finditer(r'^(#{1,3}) (.+?)\s*$',markdown,re.M));sections={}
    allowed={'췤미! 검수 규칙','공통 검수 지침'}
    for i,m in enumerate(headings):
        level,title=m.group(1),m.group(2)
        key=title.split(' | ',1)[0] if level=='##' else title
        if key in sections:raise ValueError('중복 제목/ID: '+key)
        body=markdown[m.end():headings[i+1].start() if i+1<len(headings) else len(markdown)].strip()
        sections[key]=(level,title,body)
    expected=allowed|{p['id'] for p in PACK['parents']}|{s['rule_id'] for s in PACK['steps']}
    missing=expected-sections.keys();extra=sections.keys()-expected
    if missing or extra:raise ValueError('저장 형식이 맞지 않습니다. 상위 항목은 ## ID | 제목, 세부 항목은 ### ID로 각각 구분해야 합니다. 자유 형식 문서는 ‘다른 AI에 전달할 내용 복사’로 변환할 수 있습니다. 필수 제목/ID 누락: '+', '.join(sorted(missing)[:8])+' / 알 수 없는 제목: '+', '.join(sorted(extra)[:8]))
    pack=copy.deepcopy(PACK)
    if sections['공통 검수 지침'][0]!='#' or sections['췤미! 검수 규칙'][0]!='#':raise ValueError('공통 제목은 # 형식을 유지하세요.')
    pack['guidance']=sections['공통 검수 지침'][2]
    if not 5<=len(pack['guidance'])<=6000:raise ValueError('공통 검수 지침은 5~6,000자여야 합니다.')
    for parent in pack['parents']:
        level,title,body=sections[parent['id']]
        if level!='##' or ' | ' not in title:raise ValueError(parent['id']+' 제목은 ## ID | 제목 형식이어야 합니다.')
        name=title.split(' | ',1)[1].strip()
        if not 2<=len(name)<=200 or not 5<=len(body)<=6000:raise ValueError(parent['id']+' 제목(2~200자)·원문(5~6,000자)을 확인하세요.')
        parent.update(title=name,original=body)
    for step in pack['steps']:
        level,_,body=sections[step['rule_id']]
        if level!='###' or not 5<=len(body)<=6000:raise ValueError(step['rule_id']+'는 ### ID와 5~6,000자의 점검 내용이 필요합니다.')
        step.update(title=body,objective=body,inspection_actions=[{'action':'OBSERVE_AND_CHECK','instruction':body,'repeat_per_instance':True}])
    version='md-'+hashlib.sha256(markdown.encode()).hexdigest()[:16]
    pack['version']=version
    for r in pack['parents']+pack['steps']:r['version']=version
    return pack


def initialize(store):
    with store.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS rule_versions(seq INTEGER PRIMARY KEY, version TEXT NOT NULL, created TEXT NOT NULL, actor TEXT NOT NULL, markdown TEXT NOT NULL, body TEXT NOT NULL)')


def current(store):
    with store.connect() as c:row=c.execute('SELECT * FROM rule_versions ORDER BY seq DESC LIMIT 1').fetchone()
    if row:return {'version':row['version'],'created_at':row['created'],'markdown':row['markdown'],'pack':json.loads(row['body'])}
    return {'version':BASE_VERSION,'created_at':None,'markdown':to_markdown(PACK),'pack':copy.deepcopy(PACK)}


def history(store):
    with store.connect() as c:return [dict(r) for r in c.execute('SELECT seq,version,created,actor FROM rule_versions ORDER BY seq DESC LIMIT 100')]


def save(store,markdown,base_version,actor):
    pack=parse_markdown(markdown)
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT version FROM rule_versions ORDER BY seq DESC LIMIT 1').fetchone()
        latest=row['version'] if row else BASE_VERSION
        if latest!=base_version:raise RuntimeError('다른 관리자가 먼저 저장했습니다. 편집 내용을 복사한 뒤 최신 버전을 불러와 병합하세요.')
        if pack['version']!=latest:
            c.execute('INSERT INTO rule_versions(version,created,actor,markdown,body) VALUES(?,?,?,?,?)',
                (pack['version'],now(),actor,markdown,json.dumps(pack,ensure_ascii=False)))
            c.execute('INSERT INTO audit(at,actor,action,target,body) VALUES(?,?,?,?,?)',
                (now(),actor,'RULES_SAVE',pack['version'],json.dumps({'previous':latest})))
    return current(store)
