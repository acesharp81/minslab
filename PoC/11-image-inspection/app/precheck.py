"""Approved internal PDF guidance, routed by rule and observed target.

Case illustrations are not visual standards, current factual evidence or rights
certificates. No provider calls, answer keys, invented coordinates or verdicts.
"""
import hashlib
import json
import re
from functools import lru_cache
from .rules import PACK

SCHEMA='chekmi-precheck-item-v1'
KIND='inspection-guidance'
VERSION='precheck-router-v3-targeted-tips'
POLICY='내부 참고자료의 검사 행동만 사용합니다. 사례 사진·기사·모식도는 정상 도안/현재 사실/이용허락 증빙이 아닙니다. 해당 객체·규칙 범위에서만 참고하며 관찰하지 않은 검사를 완료했다고 하지 않습니다. 공식 원본 대조와 문서 증빙 상태는 별도로 판단합니다.'

# Execution scopes derived from the source tip titles, not QA images or labels.
# A topic can mention text, vehicles and people; its ten tips do not all apply
# to every object in that topic.
TIP_TARGETS={
    'OFFICIAL-19-03':r'기관|부처|부서|행정|정부|경찰|소방|국립|공공',
    'OFFICIAL-19-04':r'\d',
    'OFFICIAL-19-07':r'의학|의료|응급|심폐|소화|안전|대피|구조|CPR|AED',
    'OFFICIAL-19-09':r'[A-Za-z]|영문|로마자',
    'OFFICIAL-20-02':r'손|발|관절|인물|사람|얼굴|캐릭터',
    'OFFICIAL-20-03':r'문자|문구|간판|명찰|현수막|글씨|텍스트|제목|표지|라벨',
    'OFFICIAL-20-04':r'태극|국기|휘장|배지|뱃지|계급|견장|문양',
    'OFFICIAL-20-05':r'배경|건물|거리|풍경|간판|도시',
    'OFFICIAL-20-06':r'차량|번호판|자동차|버스|승용차|차체|경찰차|소방차',
    'OFFICIAL-20-07':r'사진|인물|사람|얼굴',
    'OFFICIAL-20-08':r'연기|구름|그림자|반사',
    'OFFICIAL-20-09':r'인물|사람|캐릭터|성별|여성|남성|연령',
    'OFFICIAL-20-10':r'장소|건물|시설|배경|명칭',
}


@lru_cache(maxsize=128)
def _parse(content):
    value=json.loads(content)
    if not isinstance(value,dict) or value.get('schema')!=SCHEMA:raise ValueError('사전점검 자료 형식 오류')
    number=value.get('number');tips=value.get('tips')
    if type(number)!=int or not 1<=number<=21 or value.get('id')!=f'O{number:02}' or value.get('source_page')!=number+2:raise ValueError('항목 번호·원문 페이지 오류')
    if value.get('source_status')!='APPROVED_INTERNAL_REFERENCE' or value.get('image_role')!='ILLUSTRATIVE_CASE':raise ValueError('사례와 공식 도안을 구분해야 합니다.')
    if not re.fullmatch('[a-f0-9]{64}',value.get('source_sha256','')):raise ValueError('원문 PDF 해시 필요')
    valid={s['rule_id'] for s in PACK['steps']}
    if not isinstance(tips,list) or len(tips)!=10:raise ValueError('항목별 10개 검수 요령이 필요합니다.')
    parents=set()
    for n,tip in enumerate(tips,1):
        if tip.get('id')!=f'OFFICIAL-{number:02}-{n:02}' or tip.get('number')!=n:raise ValueError('검수 요령 누락·중복·순서 오류')
        ids=tip.get('rule_ids')
        if not isinstance(ids,list) or not ids or not set(ids)<=valid:raise ValueError('기존 세부 규칙 매핑 오류')
        parents.update(r.rsplit('-',1)[0] for r in ids)
        if any(not isinstance(tip.get(k),str) or not 1<=len(tip[k])<=1200 for k in ('title','action','source_text','exceptions')):raise ValueError('원문·검사 행동·예외를 확인하세요.')
    if set(value.get('parent_ids',[]))!=parents:raise ValueError('원문 항목 매핑 불일치')
    triggers=value.get('trigger_terms')
    if not isinstance(triggers,list) or not 1<=len(triggers)<=30 or any(not isinstance(t,str) or not 1<=len(t)<=80 for t in triggers) or not isinstance(value.get('limitations'),str):raise ValueError('대상 조건·판단 한계 필요')
    if not isinstance(value.get('title'),str) or not 1<=len(value['title'])<=150:raise ValueError('참고 항목 제목 필요')
    for tip in tips:
        if tip.get('evidence_mode') not in ('DOCUMENT_OR_VISUAL','VISUAL_CONTEXT') or tip.get('execution_scope') not in ('HUMAN_OR_OTHER_MEDIA','IMAGE_OR_DOCUMENT'):raise ValueError('검사 범위·증빙 구분 오류')
    hashes=value.get('mapped_rule_hashes',{})
    if set(hashes)!={r for t in tips for r in t['rule_ids']} or any(not re.fullmatch('[a-f0-9]{64}',h) for h in hashes.values()):raise ValueError('매핑 당시 규칙 버전 필요')
    if any(c.get('runtime_use') is not False for c in value.get('cases',[])):raise ValueError('미검증 사례를 사실 기준으로 사용하지 마세요.')
    return value


def parse(content):
    try:return _parse(content)
    except (ValueError,TypeError,KeyError,AttributeError) as exc:raise ValueError('사전점검 참고자료: '+str(exc)) from None


def is_guidance(ref):return ref.get('kind')==KIND


def target_ids(item,observation):
    found=[]
    for obj in observation.get('objects',[]):
        text=' '.join(str(obj.get(k,'')) for k in ('label','description','text')).casefold()
        if item['id']=='O10' and '번호' in text and not re.search(r'연락|전화|신고|민원|긴급|문의|QR|URL|링크|\d{2,4}[- ]\d{3,4}[- ]\d{4}',text,re.I):
            continue
        for term in item['trigger_terms']:
            if term=='TEXT':
                match=bool(obj.get('text')) or obj.get('text_legibility') in ('CLEAR','DEGRADED','UNREADABLE')
            else:match=term.casefold() in text
            if match:found.append(obj['id']);break
    return found


def approved(run):
    for ref in run.get('reference_snapshot',[]):
        if not is_guidance(ref) or ref.get('status')!='APPROVED':continue
        try:yield ref,parse(ref['content'])
        except ValueError:continue


def compact(run,ids,observation=None,object_ids=None):
    if run.get('precheck_guidance',{}).get('enabled') is not True:return []
    observation=observation or run.get('analysis_observation') or run.get('observation',{})
    steps={s['rule_id']:s for s in run.get('rule_pack',PACK)['steps']}
    selected=set(ids);out=[]
    for ref,item in approved(run):
        targets=target_ids(item,observation)
        if object_ids is not None:targets=[o for o in targets if o in object_ids]
        if not targets:continue
        tips=[]
        for tip in item['tips']:
            related=[r for r in tip['rule_ids'] if r in selected and r in steps and
                     item['mapped_rule_hashes'][r]==hashlib.sha256(steps[r]['objective'].encode()).hexdigest()]
            tip_targets=targets
            if tip['id'] in TIP_TARGETS:
                tip_targets=[o['id'] for o in observation.get('objects',[]) if o['id'] in targets and
                             re.search(TIP_TARGETS[tip['id']],' '.join(str(o.get(k,'')) for k in ('label','description','text')),re.I)]
                if tip['id']=='OFFICIAL-19-09':
                    # OCR/shape_text are tool metadata in descriptions, not
                    # English words printed in the artwork.
                    tip_targets=[o['id'] for o in observation.get('objects',[]) if o['id'] in targets and
                                 (re.search('[A-Za-z]',o.get('text','')) or re.search('영문|로마자',o.get('label','')))]
                if tip['id']=='OFFICIAL-19-04':
                    tip_targets=[o['id'] for o in observation.get('objects',[]) if o['id'] in targets and
                                 (re.search(r'\d',o.get('text','')) or re.search('날짜|숫자|금액|주년',o.get('label','')))]
                if tip['id']=='OFFICIAL-20-03':
                    tip_targets=list(dict.fromkeys(tip_targets+[o['id'] for o in observation.get('objects',[]) if o['id'] in targets and (o.get('text') or o.get('text_legibility') in ('CLEAR','DEGRADED','UNREADABLE'))]))
            if related and tip_targets:tips.append(dict(id=tip['id'],rule_ids=related,object_ids=tip_targets,title=tip['title'],action=tip['action'],
                                                       evidence_mode=tip['evidence_mode'],execution_scope=tip['execution_scope']))
        if tips:out.append(dict(reference_id=ref['id'],item_id=item['id'],title=item['title'],source_page=item['source_page'],
                               version=ref['version'],source_sha256=item['source_sha256'],source_status=item['source_status'],
                               object_ids=targets,tips=tips,limitations=item['limitations']))
    return out


def prepare(engine,job,run):
    enabled=engine.s.flag('PRECHECK_GUIDANCE_ENABLED',True)
    run['precheck_guidance']={'version':VERSION,'enabled':enabled,'items':[],'invalid_references':[],'mapping_changes':[],'api_calls':0}
    audit=run['precheck_guidance']
    if not enabled:return
    selected=set(run['selected']);steps={s['rule_id']:s for s in run['rule_pack']['steps']}
    for ref in run.get('reference_snapshot',[]):
        if not is_guidance(ref) or ref.get('status')!='APPROVED':continue
        try:item=parse(ref['content'])
        except ValueError as exc:
            audit['invalid_references'].append({'id':ref['id'],'reason':str(exc)});continue
        mapped={r for t in item['tips'] for r in t['rule_ids']} & selected
        if not mapped:continue
        changed=[rid for rid in mapped if rid not in steps or item['mapped_rule_hashes'][rid]!=hashlib.sha256(steps[rid]['objective'].encode()).hexdigest()]
        audit['mapping_changes'].extend(dict(reference_id=ref['id'],rule_id=rid,reason='규칙 내용 변경: 매핑 재검토 전 보조 지침 제외') for rid in sorted(changed))
        targets=target_ids(item,run.get('observation',{}))
        audit['items'].append(dict(id=item['id'],title=item['title'],reference_id=ref['id'],version=ref['version'],
            source_page=item['source_page'],source_sha256=item['source_sha256'],object_ids=targets,
            mapped_tip_count=sum(bool(set(t['rule_ids']) & (selected-set(changed))) for t in item['tips']),
            routing='RELATED_TARGET' if targets else 'NO_OBSERVED_TARGET',status='GUIDANCE_ROUTED' if targets else 'NOT_TRIGGERED',
            note='지침 연결 상태이며 210개 개별 검사 완료율이 아닙니다. 원문 행동의 판정은 별도입니다.'))
    audit['content_hash']=hashlib.sha256(json.dumps([(r['id'],r['version'],r['content']) for r,_ in approved(run)],sort_keys=True).encode()).hexdigest()


def annotate(run,rows,ids):
    routed=compact(run,ids)
    for row in rows:
        targets=set(row.get('evidence_ids',[]));links=[]
        if row['status'] in ('NOT_RUN','ERROR','NOT_APPLICABLE'):continue
        for item in routed:
            if not targets.intersection(item['object_ids']):continue
            tips=[t for t in item['tips'] if row['rule_id'] in t['rule_ids'] and targets.intersection(t['object_ids'])]
            if tips:links.append({k:item[k] for k in ('reference_id','item_id','title','source_page','version','source_sha256','source_status')}|
                                 {'tip_ids':[t['id'] for t in tips]})
        row['precheck_references']=links
        row['official_tip_ids']=list(dict.fromkeys(t for link in links for t in link['tip_ids']))
    return rows


def discovery(refs):
    result=[]
    for ref in refs:
        if not is_guidance(ref) or ref.get('status')!='APPROVED':continue
        try:item=parse(ref['content'])
        except ValueError:continue
        result.append({'id':item['id'],'title':item['title']})
    return result
