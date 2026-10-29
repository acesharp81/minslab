import json
import re
from collections import Counter
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .config import ROOT
from .imaging import cell_rect, global_rect

PACK=json.loads((ROOT/'rules/public-media-25.json').read_text())
STEPS={r['rule_id']:r for r in PACK['steps']}
PARENTS={r['id']:r for r in PACK['parents']}
Status=Literal['PASS','FAIL','REVIEW','NOT_APPLICABLE','ERROR','NOT_RUN']

class Finding(BaseModel):
    model_config=ConfigDict(extra='forbid', strict=True)
    rule_id: str
    instance_id: str
    status: Status
    observation: str
    reason: str
    evidence_quality: Literal['CLEAR','UNCERTAIN','OCCLUDED','NOT_VISIBLE','DOCUMENT']
    cell_ids: list[str]
    reference_ids: list[str]
    recommended_action: str

class Batch(BaseModel):
    model_config=ConfigDict(extra='forbid', strict=True)
    results: list[Finding]


def redact(text):
    text=re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b','[이메일 마스킹]',text)
    text=re.sub(r'(?<!\d)(?:\d[ -]?){7,13}(?!\d)','[번호 마스킹]',text)
    return text


def placeholder(rule_id,status='NOT_RUN',reason='아직 실행하지 않았습니다.'):
    return dict(rule_id=rule_id,parent_id=STEPS[rule_id]['parent_id'],instance_id='unresolved',status=status,
                observation='',reason=reason,evidence_quality='NOT_VISIBLE',cell_ids=[],reference_ids=[],recommended_action='담당자 확인',
                grid_id='main-v1',crop_id=None,rects=[],model='none',rule_version=STEPS[rule_id]['version'])


def validate_batch(data, selected, references, grid=None, model='mock', pack=None):
    steps={r['rule_id']:r for r in (pack or PACK)['steps']}
    batch=Batch.model_validate(data)
    output=[];seen=set()
    approved={r['id']:r for r in references if r['status']=='APPROVED'}
    for f in batch.results:
        r=f.model_dump();rid=r['rule_id']
        if rid not in selected or not r['instance_id'].strip() or (rid,r['instance_id']) in seen:
            raise ValueError('unknown_rule_or_duplicate_instance')
        if len(r['cell_ids'])>144 or len(r['observation'])>5000 or len(r['reason'])>5000:
            raise ValueError('response_limit')
        seen.add((rid,r['instance_id']));rule=steps[rid]
        for cell in r['cell_ids']:cell_rect(cell,8 if grid else 12,8 if grid else 12)
        if any(x not in approved for x in r['reference_ids']):raise ValueError('unapproved_reference')
        if not r['reason'].strip():raise ValueError('reason_required')
        if r['status'] in ('PASS','FAIL') and not r['observation'].strip():
            r.update(status='REVIEW',reason='관찰 근거 없음')
        ref_kinds={approved[x]['kind'] for x in r['reference_ids'] if rule['parent_id'] in approved[x]['parent_ids']}
        missing=set(rule['reference_requirements'])-ref_kinds
        if r['status'] in ('PASS','FAIL') and missing:
            r.update(status='REVIEW',reason=r['reason']+' · 승인된 기준자료 미확보: '+', '.join(sorted(missing)))
        if r['status'] in ('PASS','FAIL') and (rule['review_policy']=='HUMAN_REQUIRED' or r['evidence_quality'] in ('OCCLUDED','UNCERTAIN','NOT_VISIBLE')):
            r.update(status='REVIEW',reason=r['reason']+' · 문맥·권리 또는 불확실한 관찰은 사람 검토 필요')
        if rid=='D-03-e' and 'license' in missing and r['status'] not in ('ERROR','NOT_RUN'):
            r.update(status='REVIEW',evidence_quality='DOCUMENT',cell_ids=[],
                     reason='이용권 증빙이 등록·승인되지 않아 원문 기준에 따라 증빙 확인이 필요합니다.',
                     recommended_action='사용 자산의 출처·라이선스와 적용 매체·기간을 등록하고 확인하세요.')
        if rule['parent_id']=='D-03' and r['status'] not in ('ERROR','NOT_RUN','NOT_APPLICABLE'):
            r.update(status='REVIEW',cell_ids=[],reason='이용권 증빙과 적용 범위를 담당자가 확인해야 합니다. '+r['reason'])
        # No blue boxes for conclusions without a directly observed visual area.
        if r['status'] in ('NOT_APPLICABLE','ERROR','NOT_RUN') or r['evidence_quality'] in ('NOT_VISIBLE','DOCUMENT'):
            r['cell_ids']=[]
        r.update(parent_id=rule['parent_id'],model=model,rule_version=rule['version'],grid_id=grid['id'] if grid else 'main-v1',crop_id=grid['id'] if grid else None)
        r['rects']=[global_rect(c,grid['rect']) if grid else cell_rect(c) for c in r['cell_ids']]
        for k in ('observation','reason','recommended_action'):
            r[k]=redact(r[k])
        if rule['parent_id'] in ('P-05','D-04'):
            r['observation']='식별 단서의 노출 여부 및 위치를 확인했습니다. 실제 개인정보 값은 보관하지 않습니다.' if r['observation'] else ''
        output.append(r)
    # Missing steps are never treated as complete.
    for rid in selected:
        if rid not in {x['rule_id'] for x in output}:output.append(placeholder(rid,'ERROR','모델 응답에서 세부 행동이 누락되었습니다.'))
    return output


def rollup(results, reviews=(), pack=None):
    pack=pack or PACK
    overrides={r['finding_id']:r for r in reviews}
    parents=[]
    for p in pack['parents']:
        rows=[r for r in results if r['parent_id']==p['id']]
        states=[overrides.get(r.get('id'),{}).get('status',r['status']) for r in rows]
        status=next((s for s in pack['status_priority'] if s in states),'NOT_RUN')
        parents.append({**p,'status':status,'counts':dict(Counter(states)),
                        'complete':bool(states) and not any(x in states for x in ('ERROR','NOT_RUN')),
                        'reviewed':sum(r.get('id') in overrides for r in rows),'total':len(rows)})
    return parents
