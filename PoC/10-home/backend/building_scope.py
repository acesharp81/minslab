"""Bounded, resumable building API expansion against the official code universe."""
import os
from collections import Counter,defaultdict,deque
from datetime import datetime, timedelta, timezone
from .api_samples import DISTRICTS


def balanced_pending(codes,counts,pending):
    """Round-robin provinces; lowest collected fraction first, priority within each."""
    total=Counter(r['source_object_id'][:2] for r in codes)
    done=Counter(r['source_object_id'][:2] for r in codes if counts.get(r['source_object_id'],{}).get('complete_query'))
    groups=defaultdict(deque)
    for row in pending:groups[row['source_object_id'][:2]].append(row)
    first_rank={}
    for index,row in enumerate(pending):first_rank.setdefault(row['source_object_id'][:2],index)
    regions=sorted(groups,key=lambda r:(done[r]/total[r],first_rank[r],r))
    result=[]
    while any(groups.values()):
        for region in regions:
            if groups[region]:result.append(groups[region].popleft())
    return result


def next_districts(service,source_id):
    codes=service.rows('policy_legal_dong') if source_id=='building_hub_incheon' else service.rows('legal_dong')
    if source_id in ('building_register', 'building_register_recap'):codes+=service.rows('policy_legal_dong')
    if source_id=='building_general_permit':codes+=service.rows('policy_legal_dong')
    if not codes:raise ValueError('공식 법정동 코드 수집이 먼저 필요합니다')
    old=service.latest_collection_stats(source_id)
    counts={}
    lookup={r['address'].split(' ',1)[1]:r['source_object_id'] for r in codes}
    for label,meta in old.get('district_counts',{}).items():
        code=meta.get('legal_dong_code') or lookup.get(label)
        if not code:
            district=next((d for d in DISTRICTS if d[3]==label),None)
            if district:code=district[1]+district[2]
        if code:counts[code]=dict(meta,legal_dong_code=code)
    # Newly identified policy sites are queried first, followed by other live codes.
    addresses=[p.get('address','') for p in service.projects()]
    def priority(row):
        return (0 if any(row['address'] in address for address in addresses if address) else 1,row['source_object_id'])
    pending=sorted((r for r in codes if not counts.get(r['source_object_id'],{}).get('complete_query')),key=priority)
    pending=balanced_pending(codes,counts,pending)
    limit=max(1,min(20,int(os.environ.get('POC10_BUILDING_DONGS_PER_BATCH','20'))))
    if source_id=='building_general_permit':limit=max(1,min(20,int(os.environ.get('POC10_GENERAL_PERMIT_DONGS_PER_BATCH','5'))))
    instant=datetime.now(timezone.utc)
    def overdue(row):
        stamp=counts.get(row['source_object_id'],{}).get('checked_at')
        try:return datetime.fromisoformat(stamp).astimezone(timezone.utc) <= instant-timedelta(days=7)
        except (ValueError,TypeError):return True
    revisit=sorted((r for r in codes if counts.get(r['source_object_id'],{}).get('complete_query') and overdue(r)),
                   key=lambda r:(counts[r['source_object_id']].get('checked_at') or '',priority(r)))
    # Reserve capacity for aged completed districts even during initial backfill.
    # Even a one-area override must not starve previously collected districts.
    # Alternate backfill/revisit using the latest successful batch marker.
    revisit_count=min(len(revisit),max(1,limit//4)) if not pending or limit>1 or (source_id=='building_general_permit' and not old.get('single_revisit_batch')) else 0
    selected=pending[:limit-revisit_count]+revisit[:revisit_count]
    if len(selected)<limit:
        selected+=revisit[revisit_count:revisit_count+limit-len(selected)]
    districts=[(r['region'],r['sigungu_code'],r['bjdong_code'],r['address'].split(' ',1)[1]) for r in selected]
    if source_id=='building_general_permit' and limit==1:
        service._single_revisit_batch = bool(selected and selected[0] in revisit)
    return districts,counts,len(codes)


def expansion_stats(counts,total,records):
    complete=sum(r.get('complete_query') is True for r in counts.values())
    return dict(incremental=True,scope_total_dongs=total,scope_completed_dongs=complete,
        scope_remaining_dongs=max(0,total-complete),batch_records=records,complete_scope=complete==total,
        complete_query=all(v.get('complete_query') is True for v in counts.values()),
        district_counts=counts,revisit_after_days=7,scope_note=f'공식 현존 법정동 {total}개 중 {complete}개 조회 완료. 미수집 동 확장과 7일 경과 완료 동 재방문을 병행. 조회 완료는 최신성·모집단 완결과 구분하며 기존 재고·인허가를 정책 공급실적으로 자동 합산하지 않음')
