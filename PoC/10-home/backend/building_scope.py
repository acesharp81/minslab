"""Bounded, resumable building API expansion against the official code universe."""
import os
from .api_samples import DISTRICTS


def next_districts(service,source_id):
    codes=service.rows('legal_dong')
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
    limit=max(1,min(20,int(os.environ.get('POC10_BUILDING_DONGS_PER_BATCH','4'))))
    selected=pending[:limit]
    districts=[(r['region'],r['sigungu_code'],r['bjdong_code'],r['address'].split(' ',1)[1]) for r in selected]
    return districts,counts,len(codes)


def expansion_stats(counts,total,records):
    complete=sum(r.get('complete_query') is True for r in counts.values())
    return dict(incremental=True,scope_total_dongs=total,scope_completed_dongs=complete,
        scope_remaining_dongs=max(0,total-complete),batch_records=records,complete_scope=complete==total,
        complete_query=all(v.get('complete_query') is True for v in counts.values()),
        district_counts=counts,scope_note=f'공식 현존 법정동 {total}개 중 {complete}개 조회 완료. 법정동별 전 페이지 검증 후 누적 저장, 재실행은 다음 미수집 동부터 계속. 기존 재고·인허가를 정책 공급실적으로 자동 합산하지 않음')
