"""Share immutable snapshot content while preserving each observation's identity."""
import hashlib
import json
from copy import deepcopy
from .db import MetricSnapshotContent

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def normalized(context,result):
    context=deepcopy(context);result=deepcopy(result)
    context.pop('known_at',None);result.pop('known_at',None)
    return dict(context=context,result=result)

def store_content(db,context,result):
    value=normalized(context,result);key=fingerprint(value)
    dialect=db.get_bind().dialect.name
    if dialect=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(MetricSnapshotContent).values(id=key,payload=value).on_conflict_do_nothing(index_elements=['id']))
    return {'_content_ref':key}

def restore_content(db,context,result):
    if '_content_ref' not in result:return result
    row=db.get(MetricSnapshotContent,result['_content_ref'])
    if row is None or fingerprint(row.payload)!=row.id:
        raise ValueError('산출 기준본 공유 내용 무결성 확인 실패')
    if normalized(context,{})['context']!=row.payload['context']:
        raise ValueError('산출 기준본 관측 맥락 불일치')
    value=deepcopy(row.payload['result']);value['known_at']=context['known_at']
    return value
