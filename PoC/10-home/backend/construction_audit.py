"""Explain construction coverage without treating raw permit rows as supply."""
from collections import Counter
from sqlalchemy import select, or_
from .db import Revision


def permit_candidates(service, known_at, period_start, period_end):
    stamp=Revision.payload['dates']['원천 착공일 (stcnsDay)'].as_string()
    query=select(Revision).where(Revision.kind=='permit',Revision.recorded_at<known_at,
        or_(Revision.superseded_at.is_(None),Revision.superseded_at>=known_at),
        stamp>=period_start,stamp<=period_end)
    regions=Counter();quantity=Counter();examples=[];count=0
    with service.sessions() as db:
        for r in db.scalars(query).yield_per(500):
            p=r.payload;count+=1;regions[p.get('region')]+=1
            value=p.get('units')
            state='POSITIVE_UNVERIFIED' if isinstance(value,int) and not isinstance(value,bool) and value>0 else 'ZERO_QUANTITY_UNRESOLVED' if value==0 else 'QUANTITY_MISSING'
            quantity[state]+=1
            if len(examples)<12:examples.append(dict(entity_id=r.entity_id,revision_id=r.id,
                name=p.get('name'),start_date=p['dates']['원천 착공일 (stcnsDay)'],units=value,status=state))
    return dict(candidate_rows=count,regions=dict(regions),quantity_states=dict(quantity),examples=examples,
        counted_as_actual=False,note='착공일 필드가 있는 허가 행. 신규 건설·변경·행위 구분과 총세대수 및 중복 관계를 확인하기 전 실적에 산입하지 않음.')


def latest(service):
    with service.sessions() as db:
        row=db.scalar(select(Revision).where(Revision.kind=='construction_audit',Revision.superseded_at.is_(None)).order_by(Revision.recorded_at.desc()).limit(1))
        return dict(row.payload,id=row.entity_id,revision_no=row.revision_no) if row else dict(id=None)
